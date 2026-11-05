"""UTC and numeric helpers, sample normalization, JSON files, and quality summaries."""

from __future__ import annotations

import json
import hashlib
import re
import math
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

SCHEMA_VERSION = 1
CHANNELS = ("speed_kmh", "throttle_pct", "brake_pressed", "gear", "rpm", "drs_code")
BOUNDS = {
    "speed_kmh": (0, 450),
    "throttle_pct": (0, 100),
    "gear": (0, 8),
    "rpm": (0, 20000),
}


class DataError(ValueError):
    """A provider returned missing, ambiguous, or unusable session data."""


def utc_datetime(value: str | datetime) -> datetime:
    if isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        result = value
    if result.tzinfo is None:
        raise DataError("A timestamp must include its timezone.")
    return result.astimezone(UTC)


def utc_iso(value: str | datetime) -> str:
    return utc_datetime(value).isoformat().replace("+00:00", "Z")


def number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def brake_state(value: Any) -> bool | None:
    """Accept FastF1's boolean brake state; preserve unknowns as None."""
    return value if isinstance(value, bool) else None


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def telemetry_sample(driver_number: int, timestamp: str, row: dict) -> dict:
    """Convert FastF1 names to the names used by our database and dashboard."""
    return {
        "source": "fastf1",
        "driver_number": driver_number,
        "timestamp_utc": utc_iso(timestamp),
        "speed_kmh": number(row.get("Speed")),
        "throttle_pct": number(row.get("Throttle")),
        "brake_pressed": brake_state(row.get("Brake")),
        "gear": number(row.get("nGear")),
        "rpm": number(row.get("RPM")),
        "drs_code": number(row.get("DRS")),
    }


def profile(bundle: dict) -> dict:
    """Report gaps and invalid values without inventing replacements."""
    samples = bundle["telemetry"]
    if not samples:
        raise DataError(f"{bundle['source']}: no telemetry for the selected driver.")
    timestamps = [utc_datetime(row["timestamp_utc"]) for row in samples]
    differences = [
        (right - left).total_seconds()
        for left, right in zip(timestamps, timestamps[1:])
    ]
    positive = [delta for delta in differences if delta > 0]
    missing = {
        channel: sum(row.get(channel) is None for row in samples)
        for channel in CHANNELS
    }
    # Broad sanity limits, not engineering precision or sport-specific vehicle limits.
    out_of_range = {
        channel: sum(
            row.get(channel) is not None and not low <= row[channel] <= high
            for row in samples
        )
        for channel, (low, high) in BOUNDS.items()
    }
    warnings = []
    if any(missing.values()):
        warnings.append("Some telemetry channels have missing or unrecognized values.")
    if any(out_of_range.values()):
        warnings.append(
            "Some telemetry values fall outside the configured sanity bounds."
        )
    if any(delta < 0 for delta in differences):
        warnings.append("Telemetry timestamps arrive out of order.")
    if any(delta == 0 for delta in differences):
        warnings.append(
            "Telemetry contains duplicate timestamps; records have been preserved."
        )
    if any(delta > 1 for delta in differences):
        warnings.append("Telemetry contains gaps longer than one second.")
    return {
        "drivers": len(bundle["drivers"]),
        "laps": len(bundle["laps"]),
        "selected_driver_laps": sum(
            row["driver_number"] == bundle["driver"]["number"] for row in bundle["laps"]
        ),
        "telemetry_samples": len(samples),
        "first_sample_utc": utc_iso(min(timestamps)),
        "last_sample_utc": utc_iso(max(timestamps)),
        "median_sample_interval_s": median(positive) if positive else None,
        "maximum_gap_s": max(positive) if positive else None,
        "gaps_over_1s": sum(delta > 1 for delta in differences),
        "duplicate_timestamps": sum(delta == 0 for delta in differences),
        "out_of_order_timestamps": sum(delta < 0 for delta in differences),
        "missing_by_channel": missing,
        "out_of_range_by_channel": out_of_range,
        "warnings": warnings,
    }


def session_directory(data_dir: Path, selector: dict) -> Path:
    """Keep one repeatable folder name per session and selected driver."""
    fingerprint = hashlib.sha256(
        json.dumps(selector, sort_keys=True).encode()
    ).hexdigest()[:8]
    slug = re.sub(
        r"[^a-z0-9-]",
        "-",
        "{year}-{location}-{session}-{driver}".format(**selector).lower(),
    )
    return data_dir.resolve() / f"{slug}-{fingerprint}"
