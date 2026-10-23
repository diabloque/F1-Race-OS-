"""Load FastF1 sessions and normalize original car/position streams separately."""

from __future__ import annotations
import json
import os
from pathlib import Path
from raceos.data import (
    DataError,
    SCHEMA_VERSION,
    number,
    telemetry_sample,
    utc_iso,
    write_json,
)


def timestamp(value):
    import pandas as pd

    if value is None or pd.isna(value):
        return None
    value = pd.Timestamp(value)
    value = (
        value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
    )
    return utc_iso(value.to_pydatetime())


def load_session(
    cache_dir: Path,
    year: int,
    location: str,
    session_name: str,
    *,
    offline=False,
    refresh=False,
):
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir.parent / "matplotlib"))
    import fastf1
    from fastf1.exceptions import DataNotLoadedError

    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir), force_renew=refresh)
    fastf1.Cache.offline_mode(offline)
    fastf1.Cache.set_enabled()
    session = fastf1.get_session(year, location, session_name, backend="fastf1")
    if str(session.event["Location"]).casefold() != location.casefold():
        raise DataError(f"FastF1 resolved a different circuit from {location!r}.")
    if session.name.casefold() != session_name.casefold():
        raise DataError(f"FastF1 resolved a different session from {session_name!r}.")
    try:
        session.load(laps=True, telemetry=True, weather=False, messages=False)
        if session.results.empty or session.laps.empty:
            raise DataError("FastF1 returned no driver results or laps.")
    except DataNotLoadedError as error:
        raise DataError(
            "FastF1 could not load the required timing data. The session may be "
            "unavailable from the provider or missing from the offline cache."
        ) from error
    return session


def frame_records(frame):
    # JSON conversion makes NumPy/Pandas values portable, preserving source samples.
    return json.loads(
        frame.to_json(orient="records", date_format="iso", date_unit="ns")
    )


def normalize(session, driver: str) -> dict:
    import pandas as pd

    results = session.results
    selected = results[
        (results["Abbreviation"].str.upper() == driver.upper())
        | (results["DriverNumber"] == driver)
    ]
    if len(selected) != 1:
        raise DataError(f"Driver {driver!r} was not uniquely found in FastF1.")
    selected = selected.iloc[0]
    driver_number = int(selected["DriverNumber"])
    car_data = session.car_data.get(str(driver_number))
    if car_data is None or car_data.empty:
        raise DataError("FastF1 returned no car telemetry for the selected driver.")
    laps = []
    for _, row in session.laps.iterrows():
        if pd.isna(row["LapNumber"]) or pd.isna(row["DriverNumber"]):
            raise DataError("A lap is missing its driver or lap number.")
        start = (
            session.t0_date + row["LapStartTime"]
            if not pd.isna(row["LapStartTime"])
            else None
        )
        finish = (
            session.t0_date + row["Time"]
            if "Time" in row and not pd.isna(row["Time"])
            else None
        )
        laps.append(
            {
                "source": "fastf1",
                "driver_number": int(row["DriverNumber"]),
                "lap_number": int(row["LapNumber"]),
                "lap_duration_s": (
                    number(row["LapTime"].total_seconds())
                    if not pd.isna(row["LapTime"])
                    else None
                ),
                "lap_start_utc": timestamp(start),
                "lap_end_utc": timestamp(finish),
            }
        )
    telemetry = []
    for row in frame_records(car_data):
        date = timestamp(row["Date"])
        if date is None:
            raise DataError("A telemetry sample is missing its timestamp.")
        telemetry.append(telemetry_sample(driver_number, date, row))
    positions = []
    position_data = getattr(session, "pos_data", {}).get(str(driver_number))
    if position_data is not None:
        for row in frame_records(position_data):
            date = timestamp(row["Date"])
            if date is None:
                raise DataError("A position sample is missing its timestamp.")
            positions.append(
                {
                    "source": "fastf1",
                    "driver_number": driver_number,
                    "timestamp_utc": date,
                    "x": number(row.get("X")),
                    "y": number(row.get("Y")),
                    "z": number(row.get("Z")),
                    "status": row.get("Status"),
                }
            )
    drivers = []
    for _, row in results.iterrows():
        color = row.get("TeamColor")
        drivers.append(
            {
                "number": int(row["DriverNumber"]),
                "code": row["Abbreviation"],
                "name": row["FullName"],
                "team": row["TeamName"],
                "team_color": (
                    str(color) if color is not None and not pd.isna(color) else None
                ),
            }
        )
    year = timestamp(session.date)[:4]
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "fastf1",
        "session": {
            "id": f"{year}:{int(session.event['RoundNumber'])}:{session.name}",
            "year": int(year),
            "location": str(session.event["Location"]),
            "name": session.name,
            "scheduled_start_utc": timestamp(session.date),
            "recording_origin_utc": timestamp(session.t0_date),
        },
        "driver": next(row for row in drivers if row["number"] == driver_number),
        "drivers": drivers,
        "laps": laps,
        "telemetry": telemetry,
        "positions": positions,
        "provenance": "FastF1 car_data and pos_data are retained separately without resampling; the underlying cache stays on disk.",
    }


def load(
    cache_dir: Path,
    export_dir: Path,
    year: int,
    location: str,
    session_name: str,
    driver: str,
    *,
    offline=False,
    refresh=False,
) -> dict:
    session = load_session(
        cache_dir, year, location, session_name, offline=offline, refresh=refresh
    )
    bundle = normalize(session, driver)
    for name, frame in (
        ("drivers", session.results),
        ("laps", session.laps),
        ("car_data", session.car_data[str(bundle["driver"]["number"])]),
    ):
        write_json(export_dir / f"{name}.json", frame_records(frame))
    return bundle
