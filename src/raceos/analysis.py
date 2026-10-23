"""Compare completed laps using recorded sector times and time-weighted inputs."""

from typing import Literal
from pydantic import AwareDatetime, BaseModel
from raceos.data import DataError, utc_datetime
from raceos.remote_cache import RemoteMissing
from raceos.storage import NotFound, timestamp
from raceos.distance_comparison import DistanceAlignment, align_laps


class InputMetric(BaseModel):
    active_s: float
    known_s: float
    coverage_pct: float
    percent: float | None


class AnalyzedLap(BaseModel):
    driver_number: int
    code: str
    name: str
    lap_number: int
    start_utc: AwareDatetime
    completed_at_utc: AwareDatetime
    lap_time_s: float
    sector_times_s: list[float | None]
    window_s: float
    full_throttle: InputMetric
    braking: InputMetric
    warnings: list[str]


class LapComparison(BaseModel):
    session_id: str
    source: Literal["tracinginsights"] = "tracinginsights"
    prepared: bool = True
    at_utc: AwareDatetime
    a: AnalyzedLap
    b: AnalyzedLap
    lap_delta_s: float
    sector_deltas_s: list[float | None]
    alignment: DistanceAlignment


def eligible(lap, at):
    start, finish = lap.get("lap_start_utc"), lap.get("lap_end_utc")
    return bool(
        not lap.get("timing_generated")
        and start
        and finish
        and utc_datetime(start) < utc_datetime(finish) <= at
        and lap.get("lap_duration_s")
        and lap["lap_duration_s"] > 0
    )


def input_metrics(samples, start, finish):
    """Hold the left sample to the next, only across supported gaps <= 1 second."""
    window = (finish - start).total_seconds()
    if window <= 0:
        raise DataError("The selected lap has no positive timing window.")
    values = [
        (utc_datetime(row["timestamp_utc"]), row)
        for row in samples
        if start <= utc_datetime(row["timestamp_utc"]) <= finish
    ]
    totals = {"full_throttle": [0.0, 0.0], "braking": [0.0, 0.0]}
    for (left, row), (right, _) in zip(values, values[1:]):
        seconds = (right - left).total_seconds()
        if not 0 < seconds <= 1:
            continue
        throttle, brake = row.get("throttle_pct"), row.get("brake_pressed")
        states = {
            "full_throttle": (
                throttle >= 99
                if throttle is not None and 0 <= throttle <= 100
                else None
            ),
            "braking": brake if isinstance(brake, bool) else None,
        }
        for channel, active in states.items():
            if active is not None:
                totals[channel][1] += seconds
                if active:
                    totals[channel][0] += seconds
    return {
        key: {
            "active_s": round(active, 6),
            "known_s": round(known, 6),
            "coverage_pct": round(100 * known / window, 3),
            "percent": round(100 * active / known, 3) if known else None,
        }
        for key, (active, known) in totals.items()
    }


class PerformanceAnalysis:
    def __init__(self, provider):
        self.provider = provider

    def session_at(self, sid, at):
        if not sid.startswith("ti-"):
            raise DataError("Open a remote session to use lap comparison.")
        session = self.provider.get(sid)
        at = utc_datetime(at)
        if not session["begin"] <= at <= session["end"]:
            raise DataError(
                "Comparison time must fall inside the recorded session window."
            )
        return session, at

    def choices(self, sid, at):
        session, at = self.session_at(sid, at)
        return {
            "session_id": sid,
            "at_utc": timestamp(at),
            "drivers": [
                {
                    **driver,
                    "laps": [
                        {
                            "lap_number": lap["lap_number"],
                            "lap_time_s": lap["lap_duration_s"],
                            "completed_at_utc": lap["lap_end_utc"],
                        }
                        for lap in session["laps"][driver["number"]]
                        if eligible(lap, at)
                    ],
                }
                for driver in session["drivers"]
            ],
        }

    def select(self, session, at, number, lap_number):
        driver = next((d for d in session["drivers"] if d["number"] == number), None)
        if driver is None:
            raise NotFound("The selected driver is not in this session.")
        lap = next(
            (
                lap
                for lap in session["laps"][number]
                if lap["lap_number"] == lap_number and eligible(lap, at)
            ),
            None,
        )
        if lap is None:
            raise DataError("Choose a timed lap completed by the replay clock.")
        return driver, lap

    def analyze(self, session, selection):
        driver, lap = selection
        start, finish = utc_datetime(lap["lap_start_utc"]), utc_datetime(
            lap["lap_end_utc"]
        )
        warnings = []
        try:
            samples = self.provider.samples(session, driver, lap)
        except RemoteMissing:
            samples = []
            warnings.append("Telemetry is not published for this lap.")
        metrics = input_metrics(samples, start, finish)
        if any(metric["coverage_pct"] < 99 for metric in metrics.values()):
            warnings.append(
                "Input percentages describe covered time; missing intervals are excluded."
            )
        if any(
            lap.get(key) and start <= utc_datetime(lap[key]) <= finish
            for key in ("pit_in_utc", "pit_out_utc")
        ):
            warnings.append("This lap includes a recorded pit-lane entry or exit.")
        window = (finish - start).total_seconds()
        if abs(window - lap["lap_duration_s"]) > 0.5:
            warnings.append("The recording window differs from the reported lap time.")
        sectors = lap.get("sector_times_s", [None, None, None])
        report = {
            "driver_number": driver["number"],
            "code": driver["code"],
            "name": driver["name"],
            "lap_number": lap["lap_number"],
            "start_utc": lap["lap_start_utc"],
            "completed_at_utc": lap["lap_end_utc"],
            "lap_time_s": lap["lap_duration_s"],
            "sector_times_s": sectors,
            "window_s": round(window, 6),
            **metrics,
            "warnings": warnings,
        }
        return report, samples

    def compare(self, sid, at, driver_a, lap_a, driver_b, lap_b):
        session, at = self.session_at(sid, at)
        # Validate both selections before fetching either file, including guessed future IDs.
        selections = [
            self.select(session, at, driver_a, lap_a),
            self.select(session, at, driver_b, lap_b),
        ]
        analyzed_a, analyzed_b = list(
            self.provider.cache.pool.map(
                lambda item: self.analyze(session, item), selections
            )
        )
        a, samples_a = analyzed_a
        b, samples_b = analyzed_b
        return {
            "session_id": sid,
            "alignment": align_laps(samples_a, samples_b, a, b),
            "source": "tracinginsights",
            "prepared": True,
            "at_utc": timestamp(at),
            "a": a,
            "b": b,
            "lap_delta_s": round(b["lap_time_s"] - a["lap_time_s"], 6),
            "sector_deltas_s": [
                round(y - x, 6) if x is not None and y is not None else None
                for x, y in zip(a["sector_times_s"], b["sector_times_s"])
            ],
        }
