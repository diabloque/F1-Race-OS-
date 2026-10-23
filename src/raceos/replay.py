"""Deterministic event-time replay. Every dynamic query uses timestamp <= clock."""

from __future__ import annotations
import json
from datetime import timedelta
from typing import Any, Literal
from pydantic import AwareDatetime, BaseModel, Field
from raceos.contracts import DriverRecord, PositionRecord, TelemetryRecord, Source
from raceos.data import DataError, utc_datetime
from raceos.storage import Store, NotFound, timestamp

FRESH_SECONDS = 1.0


class LapResult(BaseModel):
    lap_number: int
    lap_duration_s: float | None
    completed_at_utc: AwareDatetime


class TyreState(BaseModel):
    compound: str | None
    stint: int | None = Field(default=None, ge=1)
    age_laps: int | None = Field(default=None, ge=0)
    fresh: bool | None
    pit_visits: int | None = Field(default=None, ge=0)
    in_pit: bool | None
    observed_at_utc: AwareDatetime | None


class CarState(DriverRecord):
    telemetry: TelemetryRecord | None
    position: PositionRecord | None
    telemetry_age_s: float | None
    position_age_s: float | None
    current_lap_number: int | None
    lap_started_utc: AwareDatetime | None
    completed_laps: int
    last_lap: LapResult | None
    best_lap: LapResult | None
    tyres: TyreState | None = None


class TrailPoint(BaseModel):
    x: float
    y: float
    timestamp_utc: AwareDatetime
    throttle_pct: float | None
    brake_pressed: bool | None


class RaceTimingRow(DriverRecord):
    position: int | None
    lap_number: int | None
    sector: int | None
    timing_at_utc: AwareDatetime | None
    gap_to_leader_s: float | None
    interval_s: float | None


class RaceTiming(BaseModel):
    basis: Literal["sector_crossings"]
    rows: list[RaceTimingRow]


class WeatherObservation(BaseModel):
    timestamp_utc: AwareDatetime
    age_s: float = Field(ge=0)
    stale: bool
    air_temp_c: float | None
    track_temp_c: float | None
    rainfall: bool | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None


class RaceControlMessage(BaseModel):
    id: int
    timestamp_utc: AwareDatetime
    message: str
    category: str | None
    flag: str | None
    scope: str | None
    sector: str | None
    driver_number: str | None


Availability = Literal["ready", "missing", "unavailable", "invalid"]


class ReplayFrame(BaseModel):
    session_id: str
    source: Source = "fastf1"
    prepared: bool = False
    at_utc: AwareDatetime
    elapsed_s: float
    focus_driver_number: int
    drivers: list[CarState]
    completed_laps: list[LapResult]
    trail: list[TrailPoint]
    race_timing: RaceTiming | None = None
    weather: WeatherObservation | None = None
    weather_status: Availability = "unavailable"
    race_control: list[RaceControlMessage] = Field(default_factory=list)
    race_control_status: Availability = "unavailable"


def window(connection, session):
    """Indexed first/last lookups avoid scanning the whole session every frame."""
    beginnings, endings = [], []
    for table in ("telemetry", "positions"):
        for direction, target in (("ASC", beginnings), ("DESC", endings)):
            row = connection.execute(
                f"SELECT timestamp_utc FROM {table} WHERE session_id=? AND source='fastf1' ORDER BY timestamp_utc {direction} LIMIT 1",
                (session["id"],),
            ).fetchone()
            if row:
                target.append(utc_datetime(row[0]))
    if not beginnings:
        raise NotFound("No recorded data is available for replay.")
    begin = max(min(beginnings), utc_datetime(session["scheduled_start_utc"]))
    end = max(endings)
    if end <= begin:
        raise DataError("The recording has no replay window after the scheduled start.")
    return begin, end


def grouped_laps(connection, session_id):
    groups = {}
    rows = connection.execute(
        "SELECT data_json FROM laps WHERE session_id=? AND source='fastf1' ORDER BY driver_number, lap_number",
        (session_id,),
    )
    for row in rows:
        lap = json.loads(row[0])
        groups.setdefault(lap["driver_number"], []).append(lap)
    return groups


def catalog(store: Store, session_id: str) -> dict:
    with store.connection(snapshot=True) as connection:
        session = store._session(connection, session_id)
        begin, end = window(connection, session)
        laps = grouped_laps(connection, session_id)
        drivers = []
        for row in connection.execute(
            """SELECT d.number, d.data_json, i.sample_count,
            (SELECT COUNT(*) FROM positions p WHERE p.session_id=d.session_id AND p.source=d.source AND p.driver_number=d.number) AS position_samples
            FROM drivers d LEFT JOIN imports i ON d.session_id=i.session_id AND d.source=i.source AND d.number=i.driver_number
            WHERE d.session_id=? AND d.source='fastf1' ORDER BY d.number""",
            (session_id,),
        ):
            driver = json.loads(row["data_json"])
            driver.update(
                {
                    "telemetry_samples": row["sample_count"] or 0,
                    "position_samples": row["position_samples"],
                    "laps": [],
                }
            )
            # Jump destinations contain starts only, never future lap durations/results.
            for lap in laps.get(driver["number"], []):
                start = lap.get("lap_start_utc")
                if start and begin <= utc_datetime(start) <= end:
                    driver["laps"].append(
                        {"lap_number": lap["lap_number"], "start_utc": start}
                    )
            drivers.append(driver)
        available = [
            d for d in drivers if d["position_samples"] and d["telemetry_samples"]
        ]
        preferred = next((d for d in available if d["code"] == "NOR"), None)
        preferred = preferred or next(iter(available), next(iter(drivers), None))
        initial = (
            preferred["laps"][0]["start_utc"]
            if preferred and preferred["laps"]
            else timestamp(begin)
        )
        return {
            "session_id": session_id,
            "source": "fastf1",
            "start_utc": timestamp(begin),
            "end_utc": timestamp(end),
            "duration_s": (end - begin).total_seconds(),
            "initial_utc": initial,
            "initial_driver_number": preferred["number"] if preferred else 0,
            "drivers": drivers,
            "freshness_limit_s": FRESH_SECONDS,
            "timing": "Recorded event time; original live delivery latency is unavailable.",
        }


def track(store: Store, session_id: str) -> dict:
    with store.connection(snapshot=True) as connection:
        store._session(connection, session_id)
        row = connection.execute(
            "SELECT data_json FROM tracks WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise NotFound(
                "Track positions are not prepared. Run 'raceos prepare-replay' first."
            )
        return {"session_id": session_id, **json.loads(row[0])}


def completion_time(lap, following):
    """Prefer an observed finish, and publish conservatively if timings disagree."""
    finish = utc_datetime(lap["lap_end_utc"]) if lap.get("lap_end_utc") else None
    if lap.get("lap_start_utc") and lap.get("lap_duration_s") is not None:
        calculated = utc_datetime(lap["lap_start_utc"]) + timedelta(
            seconds=lap["lap_duration_s"]
        )
        finish = max(finish, calculated) if finish else calculated
    if finish is None and following and following.get("lap_start_utc"):
        finish = utc_datetime(following["lap_start_utc"])
    return finish


def lap_state(laps, at):
    completed, current = [], None
    for index, lap in enumerate(laps):
        following = laps[index + 1] if index + 1 < len(laps) else None
        finish = completion_time(lap, following)
        start = utc_datetime(lap["lap_start_utc"]) if lap.get("lap_start_utc") else None
        if finish and finish <= at:
            completed.append(
                {
                    "lap_number": lap["lap_number"],
                    "lap_duration_s": lap.get("lap_duration_s"),
                    "completed_at_utc": timestamp(finish),
                }
            )
        if start and start <= at:
            current = (
                None
                if finish and finish <= at
                else {"number": lap["lap_number"], "start_utc": timestamp(start)}
            )
    known = [lap for lap in completed if lap["lap_duration_s"] is not None]
    best = min(known, key=lambda lap: lap["lap_duration_s"]) if known else None
    return current, completed, best


def latest_sample(connection, table, session_id, driver_number, at):
    rows = connection.execute(
        f"SELECT * FROM {table} WHERE session_id=? AND source='fastf1' AND driver_number=? AND timestamp_utc<=? ORDER BY timestamp_utc DESC, sample_index DESC LIMIT 2",
        (session_id, driver_number, timestamp(at)),
    ).fetchall()
    row = rows[0] if rows else None
    if row is None:
        return None, None
    age = (at - utc_datetime(row["timestamp_utc"])).total_seconds()
    if age > FRESH_SECONDS:
        return None, age
    value = json.loads(row["data_json"]) if table == "telemetry" else dict(row)
    value.pop("session_id", None)
    if table == "positions" and (
        value["x"] is None or value["y"] is None or value["x"] == value["y"] == 0
    ):
        return None, age
    if table == "positions" and len(rows) > 1:
        previous = rows[1]
        if (
            previous["x"] is not None
            and previous["y"] is not None
            and (
                utc_datetime(row["timestamp_utc"])
                - utc_datetime(previous["timestamp_utc"])
            ).total_seconds()
            <= FRESH_SECONDS
        ):
            value["dx"] = value["x"] - previous["x"]
            value["dy"] = value["y"] - previous["y"]
    return value, age


def input_trail(connection, session_id, driver_number, start, at):
    """Match each past position to the last car sample already available then."""
    positions = connection.execute(
        """SELECT x, y, status, timestamp_utc FROM positions
        WHERE session_id=? AND source='fastf1' AND driver_number=? AND timestamp_utc>=? AND timestamp_utc<=?
        ORDER BY timestamp_utc, sample_index""",
        (session_id, driver_number, timestamp(start), timestamp(at)),
    ).fetchall()
    samples = [
        json.loads(row[0])
        for row in connection.execute(
            """SELECT data_json FROM telemetry
        WHERE session_id=? AND source='fastf1' AND driver_number=? AND timestamp_utc>=? AND timestamp_utc<=?
        ORDER BY timestamp_utc, sample_index""",
            (
                session_id,
                driver_number,
                timestamp(start - timedelta(seconds=1)),
                timestamp(at),
            ),
        )
    ]
    trail, cursor, latest = [], 0, None
    for point in positions:
        point_time = utc_datetime(point["timestamp_utc"])
        while (
            cursor < len(samples)
            and utc_datetime(samples[cursor]["timestamp_utc"]) <= point_time
        ):
            latest = samples[cursor]
            cursor += 1
        if (
            point["status"] != "OnTrack"
            or point["x"] is None
            or point["y"] is None
            or point["x"] == point["y"] == 0
        ):
            continue
        fresh = (
            latest is not None
            and (point_time - utc_datetime(latest["timestamp_utc"])).total_seconds()
            <= FRESH_SECONDS
        )
        trail.append(
            {
                "x": point["x"],
                "y": point["y"],
                "timestamp_utc": point["timestamp_utc"],
                "throttle_pct": latest["throttle_pct"] if fresh else None,
                "brake_pressed": latest["brake_pressed"] if fresh else None,
            }
        )
    return trail


def snapshot(store: Store, session_id: str, at, driver_number=None) -> dict:
    at = utc_datetime(at)
    with store.connection(snapshot=True) as connection:
        session = store._session(connection, session_id)
        begin, end = window(connection, session)
        if not begin <= at <= end:
            raise DataError("Replay time must fall inside the recorded session window.")
        all_laps = grouped_laps(connection, session_id)
        records = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT data_json FROM drivers WHERE session_id=? AND source='fastf1' ORDER BY number",
                (session_id,),
            )
        ]
        if driver_number is None:
            driver_number = next(
                (d["number"] for d in records if d["code"] == "NOR"),
                records[0]["number"] if records else 0,
            )
        store._driver(connection, session_id, "fastf1", driver_number)
        cars, selected_completed, selected_current = [], [], None
        for driver in records:
            number = driver["number"]
            telemetry, telemetry_age = latest_sample(
                connection, "telemetry", session_id, number, at
            )
            position, position_age = latest_sample(
                connection, "positions", session_id, number, at
            )
            current, completed, best = lap_state(all_laps.get(number, []), at)
            cars.append(
                {
                    **driver,
                    "telemetry": telemetry,
                    "position": position,
                    "telemetry_age_s": telemetry_age,
                    "position_age_s": position_age,
                    "current_lap_number": current["number"] if current else None,
                    "lap_started_utc": current["start_utc"] if current else None,
                    "completed_laps": len(completed),
                    "last_lap": completed[-1] if completed else None,
                    "best_lap": best,
                }
            )
            if number == driver_number:
                selected_completed, selected_current = completed, current
        trail_start = (
            utc_datetime(selected_current["start_utc"])
            if selected_current
            else max(begin, at - timedelta(seconds=90))
        )
        return {
            "session_id": session_id,
            "source": "fastf1",
            "at_utc": timestamp(at),
            "elapsed_s": (at - begin).total_seconds(),
            "focus_driver_number": driver_number,
            "drivers": cars,
            "completed_laps": selected_completed,
            "trail": input_trail(
                connection, session_id, driver_number, trail_start, at
            ),
        }
