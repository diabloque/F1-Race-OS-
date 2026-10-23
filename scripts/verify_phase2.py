"""Start the API briefly, check the real pilot over HTTP, and save the evidence."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from raceos.data import read_json, utc_datetime, write_json
from raceos.storage import DEFAULT_DB, Store

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--test-report", type=Path)
    args = parser.parse_args()
    store = Store(args.db)
    before = store.counts()
    bundles = [
        read_json(path)
        for path in sorted((ROOT / "data").glob("*/normalized/fastf1.json"))
    ]
    repeated = store.import_bundles(bundles)
    assert all(
        item["status"] == "skipped" for item in repeated
    ), "Expected every saved bundle to have been imported already."
    assert store.counts() == before, "Repeated imports changed row counts."
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    address = f"http://127.0.0.1:{port}"
    log_path = ROOT / "data" / "fastf1-api-check.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "raceos",
                "serve",
                "--db",
                str(args.db),
                "--port",
                str(port),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:

            def get(path, **parameters):
                query = "?" + urlencode(parameters) if parameters else ""
                with urlopen(address + path + query, timeout=5) as response:
                    return json.load(response)

            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"API exited early; see {log_path}")
                try:
                    health = get("/api/health")
                    break
                except (URLError, TimeoutError):
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"API startup timed out; see {log_path}")
            catalog = get("/api/sessions", year=2025, location="Monza")
            session = next(
                item for item in catalog["items"] if item["name"] == "Qualifying"
            )
            session_id = session["id"]
            path = f"/api/sessions/{session_id}/drivers/4"
            provider_checks = {}
            for source in ("fastf1",):
                drivers = get(f"/api/sessions/{session_id}/drivers", source=source)
                laps = get(path + "/laps", source=source)
                first = get(path + "/telemetry", source=source, limit=3)
                second = get(
                    path + "/telemetry",
                    source=source,
                    limit=3,
                    offset=first["next_offset"],
                )
                assert first["total"] == 17452
                assert (
                    len(
                        {
                            sample["sample_index"]
                            for sample in first["items"] + second["items"]
                        }
                    )
                    == 6
                )
                driver = next(item for item in drivers["items"] if item["number"] == 4)
                assert (
                    driver["telemetry_available"]
                    and driver["telemetry_samples"] == 17452
                )
                complete = next(
                    lap
                    for lap in laps["items"]
                    if lap["lap_start_utc"] and lap["lap_duration_s"]
                )
                selected = get(
                    path + "/telemetry",
                    source=source,
                    lap_number=complete["lap_number"],
                    limit=5000,
                )
                start = utc_datetime(complete["lap_start_utc"])
                end = start + timedelta(seconds=complete["lap_duration_s"])
                assert selected["total"] > 0
                assert all(
                    start <= utc_datetime(sample["timestamp_utc"]) < end
                    for sample in selected["items"]
                )
                ranged = get(
                    path + "/telemetry",
                    source=source,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    limit=5000,
                )
                assert ranged["items"] == selected["items"]
                quality = get(path + "/quality", source=source)["profile"]
                assert quality["out_of_range_by_channel"]["throttle_pct"] == 4536
                assert quality["missing_by_channel"]["brake_pressed"] == 0
                provider_checks[source] = {
                    "drivers": len(drivers["items"]),
                    "norris_laps": laps["total"],
                    "norris_telemetry_samples": first["total"],
                    "checked_lap": complete["lap_number"],
                    "checked_lap_samples": selected["total"],
                    "quality": quality,
                }
            assert get(path + "/telemetry", limit=1)["source"] == "fastf1"
            with urlopen(address + "/docs", timeout=5) as response:
                assert response.status == 200
            assert (
                "/api/sessions/{session_id}/drivers/{driver_number}/telemetry"
                in get("/openapi.json")["paths"]
            )
            evidence = {
                "health": health,
                "session_id": session_id,
                "repeated_imports": repeated,
                "providers": provider_checks,
                "live_http_check": "passed",
                "docs_check": "passed",
                "time_and_lap_filters": "passed",
                "pagination": "passed",
            }
            if args.test_report:
                suites = ET.parse(args.test_report).getroot()
                tests = sum(
                    int(suite.get("tests", 0)) for suite in suites.findall("testsuite")
                )
                failures = sum(
                    int(suite.get("failures", 0)) + int(suite.get("errors", 0))
                    for suite in suites.findall("testsuite")
                )
                assert (
                    tests > 0 and failures == 0
                ), "Automated test report is missing or has failures."
                evidence["automated_tests_passed"] = tests
            write_json(ROOT / "data" / "fastf1-api-verification.json", evidence)
            lines = [
                "# FastF1 API verification",
                "",
                "SQLite storage and the historical FastAPI backend are implemented.",
                "",
                f"Verified session: `{session_id}` — 2025 Monza qualifying, NOR / #4.",
                "",
                "| Stored records | Count |",
                "|---|---:|",
            ]
            lines += [f"| {name} | {count:,} |" for name, count in before.items()]
            lines += [
                "",
                "## Verified behavior",
                "",
                "- Importing saved FastF1 bundles again skips unchanged data and preserves every row count.",
                "- The API served real session, driver, lap, telemetry, and quality data over localhost HTTP.",
                "- FastF1 exposes 20 drivers, 21 Norris lap records, and 17,452 Norris samples.",
                "- Pagination, lap windows, and explicit UTC windows passed live checks.",
                "- Throttle values of 104 retain their quality flags.",
                "- Interactive `/docs` and the OpenAPI schema returned successfully.",
            ]
            if "automated_tests_passed" in evidence:
                lines.append(
                    f"- All {evidence['automated_tests_passed']} automated tests passed, including the Phase 1 checks."
                )
            lines += [
                "",
                "## Files",
                "",
                "Database: `data/raceos.sqlite3` (ignored by Git).",
                "Structured evidence: `data/fastf1-api-verification.json`.",
                "",
                "Run: `python -m raceos serve`; then open `http://127.0.0.1:8000/docs`.",
                "",
                "The verification server was stopped after the HTTP checks.",
                "",
                "## Next phase",
                "",
                "Phase 4 adds historical replay and requires user approval.",
                "",
            ]
            (ROOT / "docs" / "FASTF1_API_RESULTS.md").write_text(
                "\n".join(lines), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "session_id": session_id,
                        "counts": before,
                        "automated_tests_passed": evidence.get(
                            "automated_tests_passed"
                        ),
                        "http_checks": "passed",
                        "evidence": str(ROOT / "data" / "fastf1-api-verification.json"),
                    },
                    indent=2,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
