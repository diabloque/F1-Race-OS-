"""Replay prepared files on one shared UTC clock, without SQLite sample imports."""

from bisect import bisect_right
from datetime import timedelta
from math import hypot
from raceos.data import DataError, profile, utc_datetime
from raceos.providers.tracinginsights import SOURCE
from raceos.remote_cache import RemoteMissing
from raceos.replay import FRESH_SECONDS, lap_state
from raceos.storage import NotFound, timestamp
from raceos.race_timing import race_timing
from raceos.engineering import tyre_state, environment


class RemoteReplay:
    def __init__(self, provider):
        self.provider = provider

    def catalog(self, sid):
        session = self.provider.get(sid)
        drivers = []
        for driver in session["drivers"]:
            drivers.append(
                {
                    **driver,
                    "telemetry_samples": None,
                    "position_samples": None,
                    "laps": [
                        {
                            "lap_number": lap["lap_number"],
                            "start_utc": lap["lap_start_utc"],
                        }
                        for lap in session["laps"][driver["number"]]
                        if lap["lap_start_utc"]
                    ],
                }
            )
        preferred = next((d for d in drivers if d["code"] == "NOR" and d["laps"]), None)
        preferred = preferred or next((d for d in drivers if d["laps"]), drivers[0])
        return {
            "session_id": sid,
            "source": SOURCE,
            "start_utc": timestamp(session["begin"]),
            "end_utc": timestamp(session["end"]),
            "duration_s": (session["end"] - session["begin"]).total_seconds(),
            "initial_utc": (
                preferred["laps"][0]["start_utc"]
                if preferred["laps"] and session["name"] != "Race"
                else timestamp(session["begin"])
            ),
            "initial_driver_number": preferred["number"],
            "drivers": drivers,
            "freshness_limit_s": FRESH_SECONDS,
            "prepared": True,
            "timing": "Prepared historical event time; positions are interpolated upstream.",
        }

    def track(self, sid):
        session = self.provider.get(sid)
        if "track" in session:
            return session["track"]
        preferred = self.catalog(sid)["initial_driver_number"]
        candidates = [
            (driver, lap)
            for driver in session["drivers"]
            for lap in session["laps"][driver["number"]]
            if lap["lap_start_utc"] and lap["lap_duration_s"]
        ]
        candidates.sort(
            key=lambda item: (item[0]["number"] != preferred, item[1]["lap_duration_s"])
        )
        # Try different drivers before retrying more laps from the same car.
        first_laps, other_laps, seen = [], [], set()
        for driver, lap in candidates:
            if driver["number"] in seen:
                other_laps.append((driver, lap))
            else:
                first_laps.append((driver, lap))
                seen.add(driver["number"])
        has_samples = False
        for driver, lap in (first_laps + other_laps)[:6]:
            try:
                samples = self.provider.samples(session, driver, lap)
            except RemoteMissing:
                continue
            has_samples = has_samples or bool(samples)
            points = [
                {"x": s["x"], "y": s["y"]}
                for s in samples
                if s["x"] is not None and s["y"] is not None and (s["x"] or s["y"])
            ]
            if len(points) < 50:
                continue
            diagonal = hypot(
                max(p["x"] for p in points) - min(p["x"] for p in points),
                max(p["y"] for p in points) - min(p["y"] for p in points),
            )
            if (
                diagonal > 0
                and hypot(
                    points[0]["x"] - points[-1]["x"], points[0]["y"] - points[-1]["y"]
                )
                <= diagonal * 0.2
            ):
                session["track"] = {
                    "session_id": sid,
                    "source": SOURCE,
                    "approximate": True,
                    "points": points,
                    "reference_driver_number": driver["number"],
                    "reference_lap_number": lap["lap_number"],
                    "reference_lap_duration_s": lap["lap_duration_s"],
                    "prepared": True,
                }
                return session["track"]
        if has_samples:
            # Missing positions must not block otherwise usable inputs and timing.
            session["track"] = {
                "session_id": sid,
                "source": SOURCE,
                "approximate": True,
                "points": [],
                "prepared": True,
                "note": "A complete circuit outline is unavailable in this session's prepared data. Driver inputs and timing can still be replayed.",
            }
            return session["track"]
        raise NotFound("No prepared telemetry could be found to open this session.")

    def snapshot(self, sid, at, driver_number=None):
        session = self.provider.get(sid)
        at = utc_datetime(at)
        if not session["begin"] <= at <= session["end"]:
            raise DataError("Replay time must fall inside the recorded session window.")
        focus = driver_number or self.catalog(sid)["initial_driver_number"]
        if focus not in {driver["number"] for driver in session["drivers"]}:
            raise NotFound("The selected driver is not in this session.")
        states = {}
        requests = []
        for driver in session["drivers"]:
            current, completed, best = lap_state(session["laps"][driver["number"]], at)
            states[driver["number"]] = (current, completed, best)
            if current:
                lap = next(
                    lap
                    for lap in session["laps"][driver["number"]]
                    if lap["lap_number"] == current["number"]
                )
                requests.append((driver, lap))

        def fetch(item):
            driver, lap = item
            try:
                return driver["number"], self.provider.samples(session, driver, lap)
            except RemoteMissing:
                return driver["number"], []

        # Limit simultaneous requests and retrieve only each car's active lap.
        samples = dict(self.provider.cache.pool.map(fetch, requests))
        cars, trail = [], []
        clock = timestamp(at)
        for driver in session["drivers"]:
            n = driver["number"]
            current, completed, best = states[n]
            values = samples.get(n, [])
            index = (
                bisect_right([sample["timestamp_utc"] for sample in values], clock) - 1
            )
            latest = values[index] if index >= 0 else None
            age = (
                (at - utc_datetime(latest["timestamp_utc"])).total_seconds()
                if latest
                else None
            )
            fresh = latest is not None and age <= FRESH_SECONDS
            sample = (
                {k: v for k, v in latest.items() if k not in ("x", "y", "z")}
                if fresh
                else None
            )
            position = None
            if (
                fresh
                and latest["x"] is not None
                and latest["y"] is not None
                and (latest["x"] or latest["y"])
            ):
                position = {
                    key: latest[key]
                    for key in (
                        "source",
                        "driver_number",
                        "timestamp_utc",
                        "x",
                        "y",
                        "z",
                    )
                }
                # Prepared files do not contain the original OnTrack/OffTrack flag.
                position["status"] = None
                if index > 0:
                    previous = values[index - 1]
                    gap = (
                        utc_datetime(latest["timestamp_utc"])
                        - utc_datetime(previous["timestamp_utc"])
                    ).total_seconds()
                    if (
                        gap <= FRESH_SECONDS
                        and previous["x"] is not None
                        and previous["y"] is not None
                    ):
                        position.update(
                            dx=latest["x"] - previous["x"],
                            dy=latest["y"] - previous["y"],
                        )
            cars.append(
                {
                    **driver,
                    "telemetry": sample,
                    "position": position,
                    "telemetry_age_s": age,
                    "position_age_s": age,
                    "current_lap_number": current["number"] if current else None,
                    "lap_started_utc": current["start_utc"] if current else None,
                    "completed_laps": len(completed),
                    "last_lap": completed[-1] if completed else None,
                    "best_lap": best,
                    "tyres": tyre_state(session["laps"][n], at, session["begin"]),
                }
            )
            if n == focus:
                trail = [
                    {
                        key: s[key]
                        for key in (
                            "x",
                            "y",
                            "timestamp_utc",
                            "throttle_pct",
                            "brake_pressed",
                        )
                    }
                    for s in values[: index + 1]
                    if s["x"] is not None and s["y"] is not None and (s["x"] or s["y"])
                ]
        # Download the next lap shortly before a boundary, but never return its future values.
        for driver, lap in requests:
            if (
                lap["lap_end_utc"]
                and 0 <= (utc_datetime(lap["lap_end_utc"]) - at).total_seconds() < 30
            ):
                following = next(
                    (
                        p
                        for p in session["laps"][driver["number"]]
                        if p["lap_number"] == lap["lap_number"] + 1
                        and p["lap_start_utc"]
                    ),
                    None,
                )
                if following:
                    self.provider.cache.prefetch(
                        *self.provider.lap_request(session, driver, following)
                    )
        return {
            "session_id": sid,
            "source": SOURCE,
            "prepared": True,
            "at_utc": clock,
            "elapsed_s": (at - session["begin"]).total_seconds(),
            "focus_driver_number": focus,
            "drivers": cars,
            "completed_laps": states[focus][1],
            "trail": trail,
            "race_timing": race_timing(session, at),
            **environment(session, self.provider.context(session), at),
        }

    def quality(self, sid, number, lap_number):
        session = self.provider.get(sid)
        driver = next((d for d in session["drivers"] if d["number"] == number), None)
        lap = next(
            (
                lap
                for lap in session["laps"].get(number, [])
                if lap["lap_number"] == lap_number and lap["lap_start_utc"]
            ),
            None,
        )
        if driver is None or lap is None:
            raise NotFound("Choose a driver and lap with prepared telemetry.")
        samples = self.provider.samples(session, driver, lap)
        # DRS availability is assessed from this dataset's explicit binary state.
        checked = [
            {**s, "drs_code": int(s["drs_open"]) if s["drs_open"] is not None else None}
            for s in samples
        ]
        return {
            "session_id": sid,
            "source": SOURCE,
            "driver_number": number,
            "profile": profile(
                {
                    "source": SOURCE,
                    "telemetry": checked,
                    "drivers": session["drivers"],
                    "driver": driver,
                    "laps": [lap],
                }
            ),
            "scope": "prepared_lap",
            "lap_number": lap_number,
        }
