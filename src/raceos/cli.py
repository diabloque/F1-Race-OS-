"""Download FastF1 sessions, import saved data, or run RaceOS locally."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from raceos.data import (
    DataError,
    SCHEMA_VERSION,
    read_json,
    write_json,
    session_directory,
)
from raceos.providers import fastf1
from raceos.report import save_report
from raceos.storage import Store

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def save_to_database(bundles: list[dict], database: Path) -> None:
    for result in Store(database).import_bundles(bundles):
        print(
            f"  database: {result['status']} FastF1 driver #{result['driver_number']}"
            f" -> {result['session_id']}"
        )
    print(f"Database: {database.resolve()}")


def ingest_session(args: argparse.Namespace) -> int:
    selector = {
        "year": args.year,
        "location": args.location,
        "session": args.session,
        "driver": args.driver,
    }
    session_dir = session_directory(args.data_dir, selector)
    bundle_path = session_dir / "normalized" / "fastf1.json"
    print(
        f"RaceOS | {args.year} {args.location} | {args.session} | {args.driver}",
        flush=True,
    )

    if bundle_path.exists() and not args.refresh:
        bundle = read_json(bundle_path)
        if (
            bundle.get("selector") != selector
            or bundle.get("schema_version") != SCHEMA_VERSION
            or bundle.get("source") != "fastf1"
        ):
            raise DataError(
                "Saved FastF1 bundle has an incompatible selector or schema. Run --refresh."
            )
        print("  FastF1: using saved normalized data", flush=True)
    elif args.offline:
        raise DataError(
            "FastF1 saved data missing. Run this session online once first."
        )
    else:
        # Use Windows/system certificates while keeping TLS verification enabled.
        import truststore

        truststore.inject_into_ssl()
        bundle = fastf1.load(
            args.data_dir.resolve() / "cache" / "fastf1",
            session_dir / "exports" / "fastf1",
            args.year,
            args.location,
            args.session,
            args.driver,
            refresh=args.refresh,
        )
        bundle["selector"] = selector
        write_json(bundle_path, bundle)

    report_path = save_report(bundle, session_dir / "reports")
    print(
        f"  FastF1: {len(bundle['drivers'])} drivers, {len(bundle['laps'])} laps, "
        f"{len(bundle['telemetry']):,} telemetry samples"
    )
    print(f"Quality report: {report_path}")
    save_to_database([bundle], args.db or args.data_dir / "raceos.sqlite3")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RaceOS: FastF1 data, SQLite storage, and a local dashboard."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser(
        "ingest", help="Download/cache FastF1 data and import it into SQLite."
    )
    ingest.add_argument("--year", type=int, default=2025)
    ingest.add_argument(
        "--location",
        default="Monza",
        help="Circuit location, e.g. Monza or Silverstone.",
    )
    ingest.add_argument("--session", default="Qualifying")
    ingest.add_argument(
        "--driver", default="NOR", help="Three-letter code or driver number."
    )
    mode = ingest.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Use saved FastF1 bundles without network requests.",
    )
    mode.add_argument(
        "--refresh",
        action="store_true",
        help="Download the selected session's data again.",
    )

    importer = commands.add_parser(
        "import", help="Import saved FastF1 bundles without downloading data."
    )
    prepare = commands.add_parser(
        "prepare-replay",
        help="Import cached car/position streams for replay, with no downloads.",
    )
    prepare.add_argument("--year", type=int)
    prepare.add_argument("--location")
    prepare.add_argument("--session", dest="session_name")
    for command in (ingest, importer, prepare):
        command.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
        command.add_argument(
            "--db",
            type=Path,
            help="SQLite file; defaults to <data-dir>/raceos.sqlite3.",
        )

    server = commands.add_parser(
        "serve", help="Run the dashboard at / and API documentation at /docs."
    )
    server.add_argument(
        "--db", type=Path, default=PROJECT_ROOT / "data" / "raceos.sqlite3"
    )
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == "ingest":
        if args.year < 2018:
            parser.error("FastF1 telemetry coverage starts in 2018.")
        args.location = args.location.strip()
        args.session = args.session.strip()
        args.driver = args.driver.strip().upper()
        if not all((args.location, args.session, args.driver)):
            parser.error("Location, session, and driver must be nonempty.")
    elif args.command == "serve" and not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")

    try:
        if args.command == "ingest":
            return ingest_session(args)
        if args.command == "prepare-replay":
            from raceos.prepare import prepare_replay

            prepare_replay(
                args.data_dir.resolve(),
                args.db or args.data_dir / "raceos.sqlite3",
                year=args.year,
                location=args.location,
                session_name=args.session_name,
            )
            return 0
        if args.command == "import":
            # Ignore archived files from the old OpenF1 pilot.
            paths = sorted(args.data_dir.resolve().glob("*/normalized/fastf1.json"))
            if not paths:
                raise DataError(
                    "No saved FastF1 bundles found. Run 'raceos ingest' first."
                )
            save_to_database(
                [read_json(path) for path in paths],
                args.db or args.data_dir / "raceos.sqlite3",
            )
            return 0

        import uvicorn
        from raceos.api import create_app

        uvicorn.run(create_app(args.db), host=args.host, port=args.port)
        return 0
    except (DataError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(f"RaceOS failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
