"""Construct a static circuit outline from one complete recorded lap."""

from math import hypot
from raceos.data import DataError, utc_datetime


def build_track(bundle: dict) -> dict:
    points = bundle.get("positions") or []
    candidates = sorted(
        (
            lap
            for lap in bundle["laps"]
            if lap["driver_number"] == bundle["driver"]["number"]
            and lap.get("lap_start_utc")
            and lap.get("lap_duration_s")
        ),
        key=lambda lap: lap["lap_duration_s"],
    )
    from datetime import timedelta

    for lap in candidates:
        begin = utc_datetime(lap["lap_start_utc"])
        end = begin + timedelta(seconds=lap["lap_duration_s"])
        outline = [
            {"x": p["x"], "y": p["y"]}
            for p in points
            if begin <= utc_datetime(p["timestamp_utc"]) < end
            and p["status"] == "OnTrack"
            and p["x"] is not None
            and p["y"] is not None
            and (p["x"] != 0 or p["y"] != 0)
        ]
        if len(outline) < 50:
            continue
        # Coordinates use 0.1 m units. A large closing gap is an incomplete path.
        if (
            hypot(
                outline[-1]["x"] - outline[0]["x"], outline[-1]["y"] - outline[0]["y"]
            )
            > 1500
        ):
            continue
        return {
            "source": "fastf1",
            "coordinate_unit": "0.1 m",
            "points": outline,
            "reference_driver_number": bundle["driver"]["number"],
            "reference_lap_number": lap["lap_number"],
            "approximate": True,
        }
    raise DataError("No complete recorded lap is available for the track outline.")
