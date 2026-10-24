"""Read prepared TracingInsights JSON files, one driver/lap at a time."""

from __future__ import annotations
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from statistics import median
from threading import RLock
from urllib.parse import quote
import re
import time
from raceos.data import DataError, number, read_json, write_json, utc_datetime
from raceos.remote_cache import RemoteCache, RemoteMissing, RemoteUnavailable
from raceos.storage import NotFound, timestamp, quality_flags

SOURCE = "tracinginsights"


def date(value):
    if value in (None, "", "None", "NaT", "nan"):
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # lSD comes from FastF1's UTC LapStartDate, commonly serialized without a zone.
        return (
            result.replace(tzinfo=UTC)
            if result.tzinfo is None
            else result.astimezone(UTC)
        )
    except ValueError:
        raise DataError("Prepared data contains an invalid lap-start date.")


def urls(year, *segments):
    path = "/".join(quote(str(part), safe="") for part in segments)
    return [
        f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}@main/{path}",
        f"https://raw.githubusercontent.com/TracingInsights/{year}/main/{path}",
    ]


def rows(columns, key="lap"):
    if not isinstance(columns, dict) or not isinstance(columns.get(key), list):
        raise DataError("The remote lap table has an unsupported format.")
    count = len(columns[key])
    if any(
        isinstance(value, list) and len(value) != count for value in columns.values()
    ):
        raise DataError("The remote lap table contains unequal column lengths.")
    return [
        {key: value[i] for key, value in columns.items() if isinstance(value, list)}
        for i in range(count)
    ]


def positive_integer(value, *, allow_zero=False):
    value = number(value)
    return (
        int(value)
        if value is not None
        and value.is_integer()
        and value >= (0 if allow_zero else 1)
        else None
    )


def relative_time(origin, value):
    seconds = number(value)
    return (
        timestamp(origin + timedelta(seconds=seconds))
        if seconds is not None and seconds >= 0
        else None
    )


class TracingInsights:
    def __init__(self, directory, *, cache=None):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.cache = cache or RemoteCache(directory / "cache")
        self.bookmark_path = directory / "sessions.json"
        self.lock = RLock()
        self.sessions = OrderedDict()
        self.normalized_laps = OrderedDict()
        self.bookmarks = (
            read_json(self.bookmark_path) if self.bookmark_path.exists() else {}
        )

    def events(self, year):
        if not 2018 <= year <= datetime.now(UTC).year:
            raise DataError("Choose a season from 2018 through the current year.")
        data = self.cache.get(
            f"schedule:{year}",
            [
                f"https://raw.githubusercontent.com/theOehrly/f1schedule/master/schedule_{year}.json"
            ],
            ttl=21600,
        )
        events = []
        for key, round_number in data["round_number"].items():
            if round_number <= 0:
                continue
            offset = data.get("gmt_offset", {}).get(key) or "+00:00"
            sign = -1 if offset.startswith("-") else 1
            hours, minutes = map(int, offset.lstrip("+-").split(":")[:2])
            zone = timezone(sign * timedelta(hours=hours, minutes=minutes))
            sessions = []
            for slot in range(1, 6):
                name = data[f"session{slot}"].get(key)
                value = data[f"session{slot}_date"].get(key)
                if name not in ("Race", "Qualifying") or not value:
                    continue
                start = datetime.fromisoformat(value)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=zone)
                if start.astimezone(UTC) + timedelta(hours=3) <= datetime.now(UTC):
                    sessions.append(
                        {"name": name, "scheduled_start_utc": timestamp(start)}
                    )
            if sessions:
                events.append(
                    {
                        "round": round_number,
                        "event": data["event_name"][key],
                        "location": data["location"][key],
                        "sessions": sessions,
                    }
                )
        return events

    def library(self):
        with self.lock:
            if self.bookmark_path.exists():
                self.bookmarks = read_json(self.bookmark_path)
            return sorted(
                self.bookmarks.values(), key=lambda item: (item["year"], item["id"])
            )

    def open(self, year, round_number, kind, *, validate=None):
        if kind not in ("Race", "Qualifying"):
            raise DataError("Only Race and Qualifying are supported.")
        event = next(
            (event for event in self.events(year) if event["round"] == round_number),
            None,
        )
        timing = (
            next((s for s in event["sessions"] if s["name"] == kind), None)
            if event
            else None
        )
        if timing is None:
            raise DataError(
                "That race or qualifying session has not finished or is unavailable."
            )
        sid = f"ti-{year}-{round_number}-{'R' if kind == 'Race' else 'Q'}"
        descriptor = {
            "id": sid,
            "year": year,
            "round": round_number,
            "event": event["event"],
            "location": event["location"],
            "name": kind,
            "scheduled_start_utc": timing["scheduled_start_utc"],
            "default_source": SOURCE,
            "sources": [{"source": SOURCE, "telemetry_drivers": []}],
        }
        session = self._load(descriptor)
        descriptor["driver_count"] = len(session["drivers"])
        if validate:
            validate(sid)
        with self.lock:
            if self.bookmark_path.exists():
                self.bookmarks = read_json(self.bookmark_path)
            self.bookmarks[sid] = descriptor
            write_json(self.bookmark_path, self.bookmarks)
        return descriptor

    def get(self, sid):
        with self.lock:
            if sid in self.sessions:
                return self.sessions[sid]
            descriptor = self.bookmarks.get(sid)
        if descriptor is None:
            raise NotFound("Open this session from the remote session picker first.")
        return self._load(descriptor)

    def _load(self, descriptor):
        sid = descriptor["id"]
        with self.lock:
            if sid in self.sessions:
                self.sessions.move_to_end(sid)
                return self.sessions[sid]
        year, event, kind = descriptor["year"], descriptor["event"], descriptor["name"]
        raw = self.cache.get(sid + ":drivers", urls(year, event, kind, "drivers.json"))
        drivers = []
        for driver in raw.get("drivers", []):
            code = str(driver.get("driver", "")).upper()
            if not re.fullmatch(r"[A-Z0-9]{2,4}", code):
                raise DataError("The remote driver identity is invalid.")
            try:
                n = int(driver["dn"])
            except (ValueError, KeyError, TypeError):
                raise DataError("The remote driver number is missing.")
            drivers.append(
                {
                    "number": n,
                    "code": code,
                    "name": f"{driver.get('fn', '')} {driver.get('ln', '')}".strip(),
                    "team": driver.get("team"),
                    "team_color": driver.get("tc"),
                }
            )
        if not drivers or len({d["number"] for d in drivers}) != len(drivers):
            raise DataError("The prepared session has no valid unique driver list.")

        def lap_table(driver):
            try:
                data = self.cache.get(
                    sid + ":" + driver["code"] + ":laps",
                    urls(year, event, kind, driver["code"], "laptimes.json"),
                )
                return driver["number"], rows(data)
            except RemoteMissing:
                return driver["number"], []

        with ThreadPoolExecutor(max_workers=6) as workers:
            tables = dict(workers.map(lap_table, drivers))
        origins = [
            (date(row["lSD"]) - timedelta(seconds=number(row["lST"]))).timestamp()
            for table in tables.values()
            for row in table
            if date(row.get("lSD")) is not None and number(row.get("lST")) is not None
        ]
        if not origins or max(origins) - min(origins) > 1:
            raise DataError(
                "Prepared lap timestamps do not establish a consistent shared session clock."
            )
        origin = datetime.fromtimestamp(median(origins), UTC)
        laps = {}
        for n, table in tables.items():
            normalized = []
            for row in table:
                start, finish, duration, lap = (
                    number(row.get(field)) for field in ("lST", "sesT", "time", "lap")
                )
                if lap is None or lap <= 0 or lap != int(lap):
                    continue
                normalized.append(
                    {
                        "source": SOURCE,
                        "driver_number": n,
                        "lap_number": int(lap),
                        "lap_start_utc": (
                            timestamp(origin + timedelta(seconds=start))
                            if start is not None
                            else None
                        ),
                        "lap_end_utc": (
                            timestamp(origin + timedelta(seconds=finish))
                            if finish is not None
                            else None
                        ),
                        "lap_duration_s": (
                            duration if duration and duration > 0 else None
                        ),
                        "sector_times_s": [
                            value if value is not None and value > 0 else None
                            for value in (
                                number(row.get("s1")),
                                number(row.get("s2")),
                                number(row.get("s3")),
                            )
                        ],
                        # Sector timestamps are timing-line observations, not live gaps.
                        "sector_ends_utc": [
                            (
                                timestamp(origin + timedelta(seconds=value))
                                if value is not None
                                and start is not None
                                and value >= start
                                and (finish is None or value <= finish)
                                else None
                            )
                            for value in (
                                number(row.get("s1T")),
                                number(row.get("s2T")),
                                finish,
                            )
                        ],
                        "timing_generated": row.get("ff1G") is True,
                        "compound": (
                            str(row["compound"]).upper()
                            if row.get("compound")
                            not in (None, "None", "UNKNOWN", "TEST_UNKNOWN", "")
                            else None
                        ),
                        "stint": positive_integer(row.get("stint")),
                        "tyre_life_laps": positive_integer(
                            row.get("life"), allow_zero=True
                        ),
                        "fresh_tyres": (
                            row.get("fresh")
                            if isinstance(row.get("fresh"), bool)
                            else None
                        ),
                        "pit_in_utc": relative_time(origin, row.get("pin")),
                        "pit_out_utc": relative_time(origin, row.get("pout")),
                        "pit_data_available": "pin" in row and "pout" in row,
                    }
                )
            laps[n] = sorted(normalized, key=lambda lap: lap["lap_number"])
        starts = [
            utc_datetime(lap["lap_start_utc"])
            for table in laps.values()
            for lap in table
            if lap["lap_start_utc"]
        ]
        ends = [
            utc_datetime(lap["lap_end_utc"])
            for table in laps.values()
            for lap in table
            if lap["lap_end_utc"]
        ]
        if not starts or not ends or max(ends) <= min(starts):
            raise DataError("The prepared session has no replayable lap window.")
        session = {
            **descriptor,
            "drivers": drivers,
            "laps": laps,
            "origin": origin,
            "begin": min(starts),
            "end": max(ends),
        }
        if kind == "Race":
            session.update(self.starting_grid(session))
        with self.lock:
            self.sessions[sid] = session
            while len(self.sessions) > 4:
                self.sessions.popitem(last=False)
        return session

    def starting_grid(self, session):
        """Read only pre-race grid fields; never use finishing positions."""
        year, round_number = session["year"], session["round"]
        try:
            data = self.cache.get(
                f"grid:{year}:{round_number}",
                [
                    f"https://api.jolpi.ca/ergast/f1/{year}/{round_number}/results.json?limit=100"
                ],
            )
            races = data["MRData"]["RaceTable"]["Races"]
            if not races:
                return {"starting_grid": {}, "grid_status": "missing"}
            race = races[0]
            if (
                len(races) != 1
                or str(race["season"]) != str(year)
                or str(race["round"]) != str(round_number)
                or race["date"] != session["scheduled_start_utc"][:10]
            ):
                raise DataError("Starting grid does not match the selected race.")
            known = {driver["number"]: driver["code"] for driver in session["drivers"]}
            grid, used_positions = {}, set()
            for row in race["Results"]:
                number = positive_integer(row.get("number"))
                position = positive_integer(row.get("grid"), allow_zero=True)
                if (
                    number not in known
                    or position is None
                    or position > 99
                    or row.get("Driver", {}).get("code") != known[number]
                ):
                    continue
                if number in grid or (position > 0 and position in used_positions):
                    raise DataError("Starting grid contains duplicate entries.")
                grid[number] = position
                if position > 0:
                    used_positions.add(position)
            return {
                "starting_grid": grid,
                "grid_status": "ready" if grid else "missing",
            }
        except RemoteMissing:
            return {"starting_grid": {}, "grid_status": "missing"}
        except RemoteUnavailable:
            return {"starting_grid": {}, "grid_status": "unavailable"}
        except (DataError, KeyError, TypeError, AttributeError, IndexError):
            return {"starting_grid": {}, "grid_status": "invalid"}

    def context(self, session):
        """Small optional files; missing conditions must not prevent a replay."""
        existing = session.get("engineering_context")
        if existing and time.monotonic() < existing["retry_after"]:
            return existing

        def fetch(kind):
            try:
                data = self.cache.get(
                    session["id"] + ":" + kind,
                    urls(
                        session["year"],
                        session["event"],
                        session["name"],
                        kind + ".json",
                    ),
                )
                items = rows(data, "wT" if kind == "weather" else "time")
                return kind, {"status": "ready", "items": items}
            except RemoteMissing:
                return kind, {"status": "missing", "items": []}
            except RemoteUnavailable:
                return kind, {"status": "unavailable", "items": []}
            except DataError:
                return kind, {"status": "invalid", "items": []}

        with ThreadPoolExecutor(max_workers=2) as workers:
            context = dict(workers.map(fetch, ("weather", "rcm")))
        context["retry_after"] = (
            float("inf")
            if all(context[key]["status"] == "ready" for key in ("weather", "rcm"))
            else time.monotonic() + 60
        )
        session["engineering_context"] = context
        return context

    def lap_request(self, session, driver, lap):
        key = f"{session['id']}:{driver['code']}:{lap['lap_number']}"
        return key, urls(
            session["year"],
            session["event"],
            session["name"],
            driver["code"],
            f"{lap['lap_number']}_tel.json",
        )

    def samples(self, session, driver, lap):
        key, locations = self.lap_request(session, driver, lap)
        with self.lock:
            if key in self.normalized_laps:
                self.normalized_laps.move_to_end(key)
                return self.normalized_laps[key]
        data = self.cache.get(key, locations)
        tel = data.get("tel")
        if not isinstance(tel, dict) or not isinstance(tel.get("time"), list):
            raise DataError("The prepared telemetry file has an unsupported format.")
        count = len(tel["time"])
        if any(
            isinstance(value, list) and len(value) != count for value in tel.values()
        ):
            raise DataError("The prepared telemetry file has unequal column lengths.")
        start = utc_datetime(lap["lap_start_utc"])
        values, previous = [], float("-inf")
        mapping = {
            "speed_kmh": "speed",
            "distance_m": "distance",
            "throttle_pct": "throttle",
            "gear": "gear",
            "rpm": "rpm",
            "x": "x",
            "y": "y",
            "z": "z",
        }
        for i, raw in enumerate(tel["time"]):
            seconds = number(raw)
            if seconds is None or seconds < previous:
                raise DataError(
                    "The prepared telemetry timestamps are invalid or out of order."
                )
            previous = seconds
            # Prepared files can include padding just before the lap starts.
            # Skip it instead of rejecting the lap or moving it to time zero.
            if seconds < 0:
                continue
            row = {
                name: (
                    number(tel[field][i]) if isinstance(tel.get(field), list) else None
                )
                for name, field in mapping.items()
            }
            brake = tel["brake"][i] if isinstance(tel.get("brake"), list) else None
            drs = tel["drs"][i] if isinstance(tel.get("drs"), list) else None
            row.update(
                source=SOURCE,
                driver_number=driver["number"],
                sample_index=i,
                timestamp_utc=timestamp(start + timedelta(seconds=seconds)),
                brake_pressed=bool(brake) if brake in (0, 1) else None,
                drs_code=None,
                drs_open=bool(drs) if drs in (0, 1) else None,
            )
            # DRS is binary in this dataset; preserve it separately from FastF1 raw codes.
            row["quality_flags"] = [
                flag
                for flag in quality_flags(row)
                if flag != "drs_code_missing_or_unmapped"
            ]
            values.append(row)
        with self.lock:
            self.normalized_laps[key] = values
            while sum(len(value) for value in self.normalized_laps.values()) > 40000:
                self.normalized_laps.popitem(last=False)
        return values
