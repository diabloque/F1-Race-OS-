"""Store and query FastF1 sessions with ordinary SQLite transactions."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from raceos.contracts import Bundle, Source, validated_bundle
from raceos.data import BOUNDS, CHANNELS, DataError, profile, utc_datetime

DB_SCHEMA_VERSION = 2
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "data" / "raceos.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, year INTEGER NOT NULL, location TEXT NOT NULL,
    name TEXT NOT NULL, scheduled_start_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_sources (
    session_id TEXT NOT NULL REFERENCES sessions(id), source TEXT NOT NULL,
    source_session_id TEXT NOT NULL, input_schema_version INTEGER NOT NULL,
    session_json TEXT NOT NULL, PRIMARY KEY (session_id, source),
    UNIQUE (source, source_session_id)
);
CREATE TABLE IF NOT EXISTS drivers (
    session_id TEXT NOT NULL, source TEXT NOT NULL, number INTEGER NOT NULL,
    data_json TEXT NOT NULL, PRIMARY KEY (session_id, source, number),
    FOREIGN KEY (session_id, source) REFERENCES session_sources(session_id, source)
);
CREATE TABLE IF NOT EXISTS laps (
    session_id TEXT NOT NULL, source TEXT NOT NULL, driver_number INTEGER NOT NULL,
    lap_number INTEGER NOT NULL, start_utc TEXT, duration_s REAL, data_json TEXT NOT NULL,
    PRIMARY KEY (session_id, source, driver_number, lap_number),
    FOREIGN KEY (session_id, source, driver_number) REFERENCES drivers(session_id, source, number)
);
CREATE TABLE IF NOT EXISTS telemetry (
    session_id TEXT NOT NULL, source TEXT NOT NULL, driver_number INTEGER NOT NULL,
    sample_index INTEGER NOT NULL, timestamp_utc TEXT NOT NULL, data_json TEXT NOT NULL,
    PRIMARY KEY (session_id, source, driver_number, sample_index),
    FOREIGN KEY (session_id, source, driver_number) REFERENCES drivers(session_id, source, number)
);
CREATE INDEX IF NOT EXISTS telemetry_time ON telemetry
    (session_id, source, driver_number, timestamp_utc, sample_index);
CREATE TABLE IF NOT EXISTS imports (
    session_id TEXT NOT NULL, source TEXT NOT NULL, driver_number INTEGER NOT NULL,
    content_sha256 TEXT NOT NULL, first_imported_at_utc TEXT NOT NULL,
    last_imported_at_utc TEXT NOT NULL, sample_count INTEGER NOT NULL,
    quality_json TEXT NOT NULL, PRIMARY KEY (session_id, source, driver_number),
    FOREIGN KEY (session_id, source, driver_number) REFERENCES drivers(session_id, source, number)
);
"""


REPLAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    session_id TEXT NOT NULL, source TEXT NOT NULL, driver_number INTEGER NOT NULL,
    sample_index INTEGER NOT NULL, timestamp_utc TEXT NOT NULL,
    x REAL, y REAL, z REAL, status TEXT,
    PRIMARY KEY(session_id, source, driver_number, sample_index),
    FOREIGN KEY(session_id, source, driver_number) REFERENCES drivers(session_id, source, number)
);
CREATE INDEX IF NOT EXISTS positions_time ON positions
    (session_id, source, driver_number, timestamp_utc, sample_index);
CREATE INDEX IF NOT EXISTS positions_session_time ON positions(session_id, source, timestamp_utc);
CREATE INDEX IF NOT EXISTS telemetry_session_time ON telemetry(session_id, source, timestamp_utc);
CREATE TABLE IF NOT EXISTS tracks (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id), data_json TEXT NOT NULL
);
"""


class NotFound(DataError):
    """A requested stored session, source, driver, or lap does not exist."""


def json_text(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def timestamp(value: str | datetime) -> str:
    # Fixed UTC precision permits correct indexed text comparisons at boundaries.
    return utc_datetime(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def session_identity(bundle: Bundle) -> str:
    session = bundle.session
    identity = [
        session.year,
        session.location.strip().casefold(),
        session.name.strip().casefold(),
        session.scheduled_start_utc.astimezone(UTC).date().isoformat(),
    ]
    digest = hashlib.sha256(json_text(identity).encode()).hexdigest()[:12]
    slug = re.sub(
        r"[^a-z0-9]+", "-", f"{session.year}-{identity[1]}-{identity[2]}"
    ).strip("-")
    return f"{slug}-{digest}"


def quality_flags(sample: dict) -> list[str]:
    flags = [
        f"{field}_missing_or_unmapped"
        for field in CHANNELS
        if sample.get(field) is None
    ]
    flags.extend(
        f"{field}_out_of_range"
        for field, (low, high) in BOUNDS.items()
        if sample.get(field) is not None and not low <= sample[field] <= high
    )
    return flags


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path).resolve()

    @contextmanager
    def connection(self, *, snapshot=False):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if snapshot:
                connection.execute("BEGIN")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, DB_SCHEMA_VERSION):
                raise DataError(
                    f"Unsupported database schema {version}; expected {DB_SCHEMA_VERSION}."
                )
            if version == 0:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    f"BEGIN IMMEDIATE;\n{SCHEMA}\n{REPLAY_SCHEMA}\nPRAGMA user_version = {DB_SCHEMA_VERSION};\nCOMMIT;"
                )

            elif version == 1:
                # Add new tables/indexes without deleting historical records.
                connection.executescript(
                    f"BEGIN IMMEDIATE;\n{REPLAY_SCHEMA}\nPRAGMA user_version = 2;\nCOMMIT;"
                )

    def import_bundles(self, values: list[dict]) -> list[dict]:
        # Validate every input before starting writes; the whole batch then commits atomically.
        bundles = [validated_bundle(value) for value in values]
        if not bundles:
            raise DataError("No normalized bundles were provided for import.")
        self.initialize()
        results = []
        try:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for bundle in bundles:
                    results.append(self._import(connection, bundle))
        except sqlite3.IntegrityError as error:
            raise DataError(
                f"Import rolled back because record identities conflict: {error}"
            ) from error
        return results

    def _import(self, connection, bundle: Bundle) -> dict:
        value = bundle.model_dump(mode="json")
        content_hash = hashlib.sha256(json_text(value).encode()).hexdigest()
        session_id = session_identity(bundle)
        source, driver_number = bundle.source, bundle.driver.number
        existing = connection.execute(
            "SELECT content_sha256 FROM imports WHERE session_id=? AND source=? AND driver_number=?",
            (session_id, source, driver_number),
        ).fetchone()
        result = {
            "session_id": session_id,
            "source": source,
            "driver_number": driver_number,
            "telemetry_samples": len(bundle.telemetry),
            "status": "skipped",
        }
        if existing and existing["content_sha256"] == content_hash:
            return result
        session = bundle.session
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (
                session_id,
                session.year,
                session.location,
                session.name,
                timestamp(session.scheduled_start_utc),
            ),
        )
        connection.execute(
            """INSERT INTO session_sources VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id, source) DO UPDATE SET source_session_id=excluded.source_session_id,
            input_schema_version=excluded.input_schema_version, session_json=excluded.session_json""",
            (
                session_id,
                source,
                session.id,
                bundle.schema_version,
                json_text(value["session"]),
            ),
        )
        connection.executemany(
            """INSERT INTO drivers VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, source, number) DO UPDATE SET data_json=excluded.data_json""",
            [
                (session_id, source, driver["number"], json_text(driver))
                for driver in value["drivers"]
            ],
        )
        # Laps are a complete session snapshot; only the selected driver's telemetry is replaced.
        connection.execute(
            "DELETE FROM laps WHERE session_id=? AND source=?", (session_id, source)
        )
        lap_rows = []
        for lap in value["laps"]:
            lap["source"] = source
            start = timestamp(lap["lap_start_utc"]) if lap["lap_start_utc"] else None
            lap["lap_start_utc"] = start
            lap_rows.append(
                (
                    session_id,
                    source,
                    lap["driver_number"],
                    lap["lap_number"],
                    start,
                    lap["lap_duration_s"],
                    json_text(lap),
                )
            )
        connection.executemany(
            "INSERT INTO laps VALUES (?, ?, ?, ?, ?, ?, ?)", lap_rows
        )
        connection.execute(
            "DELETE FROM telemetry WHERE session_id=? AND source=? AND driver_number=?",
            (session_id, source, driver_number),
        )
        rows = []
        for index, sample in enumerate(value["telemetry"]):
            sample["timestamp_utc"] = timestamp(sample["timestamp_utc"])
            sample["sample_index"] = index
            sample["quality_flags"] = quality_flags(sample)
            rows.append(
                (
                    session_id,
                    source,
                    driver_number,
                    index,
                    sample["timestamp_utc"],
                    json_text(sample),
                )
            )
        connection.executemany("INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?)", rows)
        if bundle.positions is not None:
            connection.execute(
                "DELETE FROM positions WHERE session_id=? AND source=? AND driver_number=?",
                (session_id, source, driver_number),
            )
            position_rows = []
            for index, point in enumerate(value["positions"]):
                position_rows.append(
                    (
                        session_id,
                        source,
                        driver_number,
                        index,
                        timestamp(point["timestamp_utc"]),
                        point["x"],
                        point["y"],
                        point["z"],
                        point["status"],
                    )
                )
            connection.executemany(
                "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                position_rows,
            )
        now = timestamp(datetime.now(UTC))
        connection.execute(
            """INSERT INTO imports VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, source, driver_number) DO UPDATE SET content_sha256=excluded.content_sha256,
            last_imported_at_utc=excluded.last_imported_at_utc, sample_count=excluded.sample_count,
            quality_json=excluded.quality_json""",
            (
                session_id,
                source,
                driver_number,
                content_hash,
                now,
                now,
                len(rows),
                json_text(profile(value)),
            ),
        )
        result["status"] = "imported"
        return result

    def counts(self) -> dict:
        """Count the active FastF1 archive; legacy provider rows stay untouched."""
        with self.connection(snapshot=True) as connection:
            counts = {}
            counts["sessions"] = connection.execute(
                "SELECT COUNT(*) FROM session_sources WHERE source='fastf1'"
            ).fetchone()[0]
            for table in (
                "session_sources",
                "drivers",
                "laps",
                "telemetry",
                "imports",
                "positions",
            ):
                counts[table] = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE source='fastf1'"
                ).fetchone()[0]
            return counts

    def _session(self, connection, session_id) -> dict:
        row = connection.execute(
            """SELECT s.* FROM sessions s JOIN session_sources p ON s.id=p.session_id
               WHERE s.id=? AND p.source='fastf1'""",
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFound("FastF1 session not found.")
        source = connection.execute(
            "SELECT * FROM session_sources WHERE session_id=? AND source='fastf1'",
            (session_id,),
        ).fetchone()
        coverage = [
            dict(item)
            for item in connection.execute(
                """SELECT driver_number, sample_count, first_imported_at_utc, last_imported_at_utc
               FROM imports WHERE session_id=? AND source='fastf1' ORDER BY driver_number""",
                (session_id,),
            )
        ]
        return {
            **dict(row),
            "default_source": "fastf1",
            "sources": [
                {
                    "source": "fastf1",
                    "source_session_id": source["source_session_id"],
                    "input_schema_version": source["input_schema_version"],
                    "telemetry_drivers": coverage,
                }
            ],
        }

    def session(self, session_id: str) -> dict:
        with self.connection(snapshot=True) as connection:
            return self._session(connection, session_id)

    def sessions(self, *, year=None, location=None, limit=50, offset=0) -> dict:
        # Only FastF1 sessions belong to the current catalog. No database migration
        # is needed: earlier provider records can remain archived in these tables.
        clauses = [
            "id IN (SELECT session_id FROM session_sources WHERE source='fastf1')"
        ]
        parameters = []
        if year is not None:
            clauses.append("year=?")
            parameters.append(year)
        if location is not None:
            clauses.append("location=? COLLATE NOCASE")
            parameters.append(location)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection(snapshot=True) as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM sessions" + where, parameters
            ).fetchone()[0]
            ids = connection.execute(
                "SELECT id FROM sessions"
                + where
                + " ORDER BY scheduled_start_utc, id LIMIT ? OFFSET ?",
                parameters + [limit, offset],
            ).fetchall()
            return self.page(
                [self._session(connection, row["id"]) for row in ids],
                total,
                limit,
                offset,
            )

    def _source(self, connection, session_id, source) -> Source:
        if source not in (None, "fastf1"):
            raise DataError("RaceOS uses FastF1 only.")
        self._session(connection, session_id)
        return "fastf1"

    def _driver(self, connection, session_id, source, driver_number):
        if (
            connection.execute(
                "SELECT 1 FROM drivers WHERE session_id=? AND source=? AND number=?",
                (session_id, source, driver_number),
            ).fetchone()
            is None
        ):
            raise NotFound("Driver not found in this provider session.")

    def drivers(self, session_id, source=None) -> dict:
        with self.connection(snapshot=True) as connection:
            chosen = self._source(connection, session_id, source)
            items = []
            for row in connection.execute(
                """SELECT d.data_json, i.sample_count FROM drivers d LEFT JOIN imports i
                    ON d.session_id=i.session_id AND d.source=i.source AND d.number=i.driver_number
                    WHERE d.session_id=? AND d.source=? ORDER BY d.number""",
                (session_id, chosen),
            ):
                item = json.loads(row["data_json"])
                item["telemetry_samples"] = row["sample_count"] or 0
                item["telemetry_available"] = item["telemetry_samples"] > 0
                items.append(item)
            return {"session_id": session_id, "source": chosen, "items": items}

    def laps(
        self, session_id, driver_number, *, source=None, limit=100, offset=0
    ) -> dict:
        with self.connection(snapshot=True) as connection:
            chosen = self._source(connection, session_id, source)
            self._driver(connection, session_id, chosen, driver_number)
            parameters = (session_id, chosen, driver_number)
            total = connection.execute(
                "SELECT COUNT(*) FROM laps WHERE session_id=? AND source=? AND driver_number=?",
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT data_json FROM laps WHERE session_id=? AND source=? AND driver_number=? ORDER BY lap_number LIMIT ? OFFSET ?",
                parameters + (limit, offset),
            )
            return self.page(
                [json.loads(row["data_json"]) for row in rows],
                total,
                limit,
                offset,
                session_id=session_id,
                source=chosen,
            )

    def telemetry(
        self,
        session_id,
        driver_number,
        *,
        source=None,
        lap_number=None,
        start=None,
        end=None,
        limit=1000,
        offset=0,
    ) -> dict:
        with self.connection(snapshot=True) as connection:
            chosen = self._source(connection, session_id, source)
            self._driver(connection, session_id, chosen, driver_number)
            clauses = ["session_id=?", "source=?", "driver_number=?"]
            parameters = [session_id, chosen, driver_number]
            if lap_number is not None:
                lap = connection.execute(
                    "SELECT * FROM laps WHERE session_id=? AND source=? AND driver_number=? AND lap_number=?",
                    (session_id, chosen, driver_number, lap_number),
                ).fetchone()
                if lap is None:
                    raise NotFound("Lap not found.")
                if lap["start_utc"] is None:
                    raise DataError(
                        "Lap has no known start timestamp; its telemetry window cannot be determined."
                    )
                lap_start = utc_datetime(lap["start_utc"])
                if lap["duration_s"] is not None:
                    lap_end = lap_start + timedelta(seconds=lap["duration_s"])
                else:
                    following = connection.execute(
                        "SELECT start_utc FROM laps WHERE session_id=? AND source=? AND driver_number=? AND lap_number>? AND start_utc>? ORDER BY lap_number LIMIT 1",
                        (
                            session_id,
                            chosen,
                            driver_number,
                            lap_number,
                            lap["start_utc"],
                        ),
                    ).fetchone()
                    if following is None:
                        raise DataError(
                            "Lap has no known end timestamp; use an explicit UTC time range."
                        )
                    lap_end = utc_datetime(following["start_utc"])
                clauses.extend(["timestamp_utc>=?", "timestamp_utc<?"])
                parameters.extend([timestamp(lap_start), timestamp(lap_end)])
            if start is not None:
                clauses.append("timestamp_utc>=?")
                parameters.append(timestamp(start))
            if end is not None:
                clauses.append("timestamp_utc<?")
                parameters.append(timestamp(end))
            where = " AND ".join(clauses)
            total = connection.execute(
                "SELECT COUNT(*) FROM telemetry WHERE " + where, parameters
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT data_json FROM telemetry WHERE "
                + where
                + " ORDER BY timestamp_utc, sample_index LIMIT ? OFFSET ?",
                parameters + [limit, offset],
            )
            return self.page(
                [json.loads(row["data_json"]) for row in rows],
                total,
                limit,
                offset,
                session_id=session_id,
                source=chosen,
            )

    def quality(self, session_id, driver_number, source=None) -> dict:
        with self.connection(snapshot=True) as connection:
            chosen = self._source(connection, session_id, source)
            self._driver(connection, session_id, chosen, driver_number)
            row = connection.execute(
                "SELECT quality_json FROM imports WHERE session_id=? AND source=? AND driver_number=?",
                (session_id, chosen, driver_number),
            ).fetchone()
            if row is None:
                raise NotFound(
                    "Telemetry has not been imported for this driver and source."
                )
            return {
                "session_id": session_id,
                "source": chosen,
                "driver_number": driver_number,
                "profile": json.loads(row["quality_json"]),
            }

    def save_track(self, session_id: str, geometry: dict) -> None:
        with self.connection() as connection:
            self._session(connection, session_id)
            connection.execute(
                "INSERT INTO tracks VALUES (?, ?) ON CONFLICT(session_id) DO UPDATE SET data_json=excluded.data_json",
                (session_id, json_text(geometry)),
            )

    @staticmethod
    def page(items, total, limit, offset, **metadata):
        return {
            **metadata,
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
        }
