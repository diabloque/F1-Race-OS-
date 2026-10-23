"""Approximate time comparison on normalized recorded lap distance."""

from bisect import bisect_right
from pydantic import AwareDatetime, BaseModel
from raceos.data import utc_datetime

# Two hundred segments give 201 inspection points around the lap.
COMPARISON_SEGMENTS = 200


class AlignedSample(BaseModel):
    time_s: float
    x: float | None
    y: float | None
    speed_kmh: float | None
    throttle_pct: float | None
    brake_pressed: bool | None
    sample_at_utc: AwareDatetime


class DistancePoint(BaseModel):
    progress: float
    distance_m: float
    a: AlignedSample | None
    b: AlignedSample | None
    delta_s: float | None
    gain_s: float | None
    segment_valid: bool


class DistanceAlignment(BaseModel):
    approximate: bool = True
    available: bool
    note: str
    distance_a_m: float | None = None
    distance_b_m: float | None = None
    coverage_pct: float = 0
    points: list[DistancePoint]


def series(samples, lap):
    """Normalize the recorded lap distance; a new region marks a data gap."""
    start, end = utc_datetime(lap["start_utc"]), utc_datetime(lap["completed_at_utc"])
    values = []
    region = 0
    previous = None
    for sample in samples:
        when = utc_datetime(sample["timestamp_utc"])
        if not start <= when <= end:
            continue
        distance = sample.get("distance_m")
        if distance is None:
            region += 1
            continue
        if previous:
            if distance < previous["distance"]:
                return [], "Recorded distance reverses within a lap."
            gap = (when - previous["when"]).total_seconds()
            if not 0 < gap <= 1:
                region += 1
        value = {
            "distance": distance,
            "when": when,
            "time": (when - start).total_seconds(),
            "region": region,
            "sample": sample,
        }
        values.append(value)
        previous = value
    if len(values) < 2 or values[-1]["distance"] <= values[0]["distance"]:
        return [], "Recorded lap distance is unavailable."
    if values[0]["time"] > 1 or (end - values[-1]["when"]).total_seconds() > 1:
        return [], "Recorded distance does not cover both ends of the lap."
    span = values[-1]["distance"] - values[0]["distance"]
    for value in values:
        value["progress"] = (value["distance"] - values[0]["distance"]) / span
    return values, None


def sample_state(value):
    row = value["sample"]
    speed, throttle = row.get("speed_kmh"), row.get("throttle_pct")
    return {
        "time_s": value["time"],
        "x": row.get("x"),
        "y": row.get("y"),
        "speed_kmh": speed if speed is not None and 0 <= speed <= 450 else None,
        "throttle_pct": (
            throttle if throttle is not None and 0 <= throttle <= 100 else None
        ),
        "brake_pressed": (
            row.get("brake_pressed")
            if isinstance(row.get("brake_pressed"), bool)
            else None
        ),
        "sample_at_utc": row["timestamp_utc"],
    }


def at_distance(values, progress_values, target):
    """Find neighboring samples, then interpolate only within one supported region."""
    index = bisect_right(progress_values, target) - 1
    if index < 0:
        return None, None
    left = values[index]
    state = sample_state(left)
    if abs(left["progress"] - target) < 1e-9:
        return state, left["region"]
    if index + 1 >= len(values):
        return None, None
    right = values[index + 1]
    if left["region"] != right["region"] or right["progress"] <= left["progress"]:
        return None, None
    fraction = (target - left["progress"]) / (right["progress"] - left["progress"])
    state["time_s"] += fraction * (right["time"] - left["time"])
    for axis in ("x", "y"):
        other = right["sample"].get(axis)
        if state[axis] is None or other is None:
            state[axis] = None
        else:
            state[axis] += fraction * (other - state[axis])
    # Inputs are held from the preceding supported sample, never interpolated brake pressure.
    return state, left["region"]


def align_laps(samples_a, samples_b, lap_a, lap_b):
    a, reason_a = series(samples_a, lap_a)
    b, reason_b = series(samples_b, lap_b)
    unavailable = reason_a or reason_b
    if unavailable:
        return {"available": False, "note": unavailable, "points": []}
    position_count = 0
    for value in a:
        sample = value["sample"]
        if sample.get("x") is not None and sample.get("y") is not None:
            position_count += 1
    if position_count < 2:
        return {
            "available": False,
            "note": "Reference lap positions are unavailable.",
            "points": [],
        }
    length_a, length_b = (
        a[-1]["distance"] - a[0]["distance"],
        b[-1]["distance"] - b[0]["distance"],
    )
    progress_a, progress_b = [v["progress"] for v in a], [v["progress"] for v in b]
    points = []
    previous_regions = None
    previous_delta = None
    for step in range(COMPARISON_SEGMENTS + 1):
        progress = step / COMPARISON_SEGMENTS
        state_a, region_a = at_distance(a, progress_a, progress)
        state_b, region_b = at_distance(b, progress_b, progress)
        delta = None
        if state_a and state_b:
            delta = state_b["time_s"] - state_a["time_s"]
        regions = (region_a, region_b)
        valid = False
        # Compare adjacent points only when neither lap crossed a data gap.
        if (
            delta is not None
            and previous_delta is not None
            and regions == previous_regions
        ):
            previous_a = points[-1]["a"]
            valid = all(
                value is not None
                for value in (
                    state_a["x"],
                    state_a["y"],
                    previous_a["x"],
                    previous_a["y"],
                )
            )
        points.append(
            {
                "progress": progress,
                "distance_m": progress * (length_a + length_b) / 2,
                "a": state_a,
                "b": state_b,
                "delta_s": round(delta, 6) if delta is not None else None,
                "gain_s": round(delta - previous_delta, 6) if valid else None,
                "segment_valid": bool(valid),
            }
        )
        previous_regions, previous_delta = regions, delta
    return {
        "available": True,
        "approximate": True,
        "note": "Aligned by normalized recorded lap distance; gaps are not joined.",
        "distance_a_m": length_a,
        "distance_b_m": length_b,
        "coverage_pct": round(
            100 * sum(p["segment_valid"] for p in points) / COMPARISON_SEGMENTS, 3
        ),
        "points": points,
    }
