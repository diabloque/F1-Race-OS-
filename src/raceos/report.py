"""Save a readable quality report for one imported FastF1 driver."""

from datetime import UTC, datetime
from pathlib import Path

from raceos.data import CHANNELS, profile, utc_iso, write_json


def save_report(bundle: dict, directory: Path) -> Path:
    summary = profile(bundle)
    report = {
        "generated_at_utc": utc_iso(datetime.now(UTC)),
        "source": "fastf1",
        "session": bundle["session"],
        "driver": bundle["driver"],
        "profile": summary,
    }
    write_json(directory / "quality.json", report)
    session, driver = bundle["session"], bundle["driver"]
    lines = [
        "# FastF1 import quality",
        "",
        f"Session: {session['year']} {session['location']} — {session['name']}",
        f"Driver: {driver['code']} #{driver['number']} ({driver['name']})",
        "",
        f"Telemetry samples: {summary['telemetry_samples']:,}",
        f"Selected driver laps: {summary['selected_driver_laps']}",
        f"Sampling gaps over one second: {summary['gaps_over_1s']}",
        "",
        "| Channel | Missing / unknown | Outside expected range |",
        "|---|---:|---:|",
    ]
    for channel in CHANNELS:
        missing = summary["missing_by_channel"][channel]
        outside = summary["out_of_range_by_channel"].get(channel, 0)
        lines.append(f"| {channel} | {missing} | {outside} |")
    lines += [
        "",
        "Counts cover the whole driver session, including time between runs.",
        "Throttle 104 may indicate unavailable source data; it is preserved and flagged.",
        "Brake is a pressed/released state, not brake pressure.",
        "No measurements are interpolated, fabricated, or silently clamped.",
        "",
    ]
    lines += [f"- {warning}" for warning in summary["warnings"]]
    path = directory / "quality.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
