"""Remote replay boundaries, prepared-data semantics, bounded cache, and API behavior."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import json
from math import cos, sin, tau
import random
import time
from urllib.parse import unquote
import pytest
from fastapi.testclient import TestClient
from raceos.api import create_app
from raceos.data import DataError, utc_datetime
from raceos.providers.tracinginsights import TracingInsights
from raceos.remote_cache import RemoteCache, RemoteMissing, RemoteUnavailable
from raceos.remote_replay import RemoteReplay
from raceos.replay import ReplayFrame
from raceos.storage import Store


def fixtures():
    schedule = {
        "round_number": {"0": 16},
        "event_name": {"0": "Italian Grand Prix"},
        "location": {"0": "Monza"},
        "gmt_offset": {"0": "+02:00"},
    }
    for i in range(1, 6):
        schedule[f"session{i}"] = {
            "0": "Qualifying" if i == 4 else "Race" if i == 5 else "Practice 1"
        }
        schedule[f"session{i}_date"] = {"0": f"2025-09-0{6 if i==4 else 7}T16:00:00"}
    drivers = {
        "drivers": [
            {
                "driver": code,
                "dn": str(n),
                "fn": name,
                "ln": "Driver",
                "team": "Team",
                "tc": "ff8000",
            }
            for code, n, name in [("NOR", 4, "Lando"), ("VER", 1, "Max")]
        ]
    }
    laps = {
        "lap": [1, 2],
        "lST": [0, 2.4],
        "sesT": [2.4, 4.4],
        "time": [2.2, 2.0],
        "lSD": ["2025-09-06T14:00:00", "2025-09-06T14:00:02.400"],
    }
    tel = {
        "tel": {
            "time": [i * 2.2 / 59 for i in range(60)],
            "x": [1000 + 100 * cos(tau * i / 59) for i in range(60)],
            "y": [1000 + 100 * sin(tau * i / 59) for i in range(60)],
            "speed": [150] * 60,
            "rpm": [10000] * 60,
            "gear": [5] * 60,
            "throttle": [99] * 60,
            "brake": [0] * 60,
            "drs": [1] * 60,
        }
    }
    return schedule, drivers, laps, tel


@pytest.fixture
def remote(tmp_path):
    schedule, drivers, laps, tel = fixtures()
    calls = []

    def fetch(url):
        calls.append(url)
        if "schedule_" in url:
            return deepcopy(schedule)
        if url.endswith("drivers.json"):
            return deepcopy(drivers)
        if url.endswith("laptimes.json"):
            return deepcopy(laps)
        if url.endswith("weather.json"):
            return {
                "wT": [0.25, 3],
                "wAT": [25, 26],
                "wTT": [40, 42],
                "wR": [False, True],
                "wWS": [1.2, 2],
                "wWD": [90, 180],
            }
        if url.endswith("rcm.json"):
            return {
                "time": ["2025-09-06T14:00:00.200", "2025-09-06T14:00:03"],
                "msg": ["GREEN LIGHT", "YELLOW FLAG"],
                "flag": ["GREEN", "YELLOW"],
            }
        if url.endswith("_tel.json"):
            return deepcopy(tel)
        raise AssertionError(url)

    cache = RemoteCache(tmp_path / "cache", fetch=fetch)
    provider = TracingInsights(tmp_path / "remote", cache=cache)
    yield provider, RemoteReplay(provider), calls, tel
    cache.close()


def opened(remote):
    provider, replay, _, _ = remote
    sid = provider.open(2025, 16, "Qualifying")["id"]
    return provider, replay, sid, provider.get(sid)


def test_only_race_and_qualifying_are_listed_and_opened(remote):
    provider, _, _, _ = remote
    assert {s["name"] for e in provider.events(2025) for s in e["sessions"]} == {
        "Race",
        "Qualifying",
    }
    with pytest.raises(DataError):
        provider.open(2025, 16, "Practice 1")
    with pytest.raises(DataError):
        provider.open(2017, 16, "Race")


def test_catalog_has_lap_starts_without_future_results(remote):
    _, replay, sid, _ = opened(remote)
    catalog = replay.catalog(sid)
    assert catalog["source"] == "tracinginsights" and catalog["prepared"] is True
    assert all(
        set(lap) == {"lap_number", "start_utc"}
        for driver in catalog["drivers"]
        for lap in driver["laps"]
    )
    assert catalog["duration_s"] == 4.4
    assert catalog["drivers"][0]["position_samples"] is None


def test_snapshot_uses_one_clock_and_keeps_binary_drs_separate_from_raw_codes(remote):
    _, replay, sid, session = opened(remote)
    value = replay.snapshot(sid, session["begin"] + timedelta(seconds=0.5), 4)
    frame = ReplayFrame.model_validate(value)
    assert len(frame.drivers) == 2
    for car in frame.drivers:
        assert car.telemetry.drs_open is True
        assert car.telemetry.drs_code is None
        assert car.telemetry.brake_pressed is False
        assert (
            car.position.status is None
        )  # The prepared source does not provide this flag.
        assert car.position.timestamp_utc <= frame.at_utc
    assert all(point.timestamp_utc <= frame.at_utc for point in frame.trail)


def test_results_wait_for_observed_finish_and_backward_seek_is_deterministic(remote):
    _, replay, sid, session = opened(remote)

    def frame(seconds):
        return replay.snapshot(sid, session["begin"] + timedelta(seconds=seconds), 4)

    before = frame(0.5)
    assert frame(2.399999)["completed_laps"] == []
    assert [lap["lap_number"] for lap in frame(2.4)["completed_laps"]] == [1]
    assert len(frame(4.4)["completed_laps"]) == 2
    assert frame(0.5) == before


def test_stale_prepared_values_become_unknown(remote):
    remote[3]["tel"]["time"] = [0] * 59 + [2.2]
    _, replay, sid, session = opened(remote)
    value = replay.snapshot(sid, session["begin"] + timedelta(seconds=1.5), 4)
    assert all(
        car["position"] is None and car["telemetry"] is None for car in value["drivers"]
    )


@pytest.mark.parametrize("padding", [[-0.043], [-0.1, -0.043]])
def test_pre_lap_padding_is_skipped_without_blocking_open_or_leaking_values(
    remote, padding
):
    provider, replay, _, raw = remote
    raw["tel"]["time"][: len(padding)] = padding
    sid = provider.open(2025, 16, "Qualifying", validate=replay.track)["id"]
    session = provider.get(sid)
    driver = session["drivers"][0]
    lap = session["laps"][driver["number"]][0]
    values = provider.samples(session, driver, lap)
    first = len(padding)
    assert len(values) == 60 - first
    assert values[0]["sample_index"] == first
    assert utc_datetime(values[0]["timestamp_utc"]) == session["begin"] + timedelta(
        seconds=raw["tel"]["time"][first]
    )
    assert raw["tel"]["time"][:first] == padding
    start = replay.snapshot(sid, session["begin"], driver["number"])
    assert start["trail"] == []
    assert all(car["telemetry"] is None for car in start["drivers"])
    at = session["begin"] + timedelta(seconds=raw["tel"]["time"][first] + 0.001)
    frame = replay.snapshot(sid, at, driver["number"])
    assert frame["drivers"][0]["telemetry"]["sample_index"] == first
    assert all(utc_datetime(point["timestamp_utc"]) <= at for point in frame["trail"])


@pytest.mark.parametrize("invalid", [None, "NaN", "inf", -0.001, 0.01])
def test_bad_or_reversed_timestamps_still_reject_the_lap(remote, invalid):
    remote[3]["tel"]["time"][2] = invalid
    _, replay, sid, session = opened(remote)
    with pytest.raises(DataError, match="invalid or out of order"):
        replay.snapshot(sid, session["begin"] + timedelta(seconds=0.5), 4)


def test_invalid_prepared_column_lengths_are_rejected(remote):
    remote[3]["tel"]["brake"] = [0]
    provider, replay, sid, session = opened(remote)
    with pytest.raises(DataError, match="unequal column"):
        replay.snapshot(sid, session["begin"], 4)


def test_missing_positions_do_not_block_session_inputs_and_clock(remote, tmp_path):
    provider, _, _, raw = remote
    raw["tel"]["time"][0] = -0.043
    raw["tel"]["x"] = ["None"] * 60
    raw["tel"]["y"] = ["None"] * 60
    with TestClient(
        create_app(tmp_path / "no-positions.sqlite3", remote_provider=provider)
    ) as client:
        opened = client.post(
            "/api/remote/open", json={"year": 2025, "round": 16, "session": "Race"}
        )
        assert opened.status_code == 200, opened.text
        prefix = "/api/sessions/" + opened.json()["id"]
        track = client.get(prefix + "/track")
        assert track.status_code == 200
        assert track.json()["points"] == []
        assert "unavailable" in track.json()["note"]
        response = client.get(
            prefix + "/replay/frame",
            params={"at": "2025-09-06T14:00:00.5Z", "driver_number": 4},
        )
        assert response.status_code == 200, response.text
        frame = ReplayFrame.model_validate(response.json())
        assert all(
            car.position is None and car.telemetry.speed_kmh == 150
            for car in frame.drivers
        )
        assert frame.trail == []
        assert client.get("/api/library").json()["total"] == 1


def test_track_search_can_use_another_driver_when_preferred_has_no_positions(remote):
    provider, replay, _, _ = remote
    original = provider.samples

    def samples(session, driver, lap):
        rows = original(session, driver, lap)
        return (
            [{**row, "x": None, "y": None} for row in rows]
            if driver["code"] == "NOR"
            else rows
        )

    provider.samples = samples
    sid = provider.open(2025, 16, "Race", validate=replay.track)["id"]
    track = replay.track(sid)
    assert track["reference_driver_number"] == 1
    assert len(track["points"]) == 60


def test_static_outline_preserves_source_geometry_and_quality_is_one_lap(remote):
    _, replay, sid, _ = opened(remote)
    track = replay.track(sid)
    assert len(track["points"]) == 60
    assert track["points"][0] == {"x": 1100, "y": 1000}
    quality = replay.quality(sid, 4, 1)
    assert (
        quality["scope"] == "prepared_lap"
        and quality["profile"]["telemetry_samples"] == 60
    )
    assert quality["profile"]["missing_by_channel"]["drs_code"] == 0


def test_remote_api_has_no_sqlite_imports_and_validates_session_and_clock(
    remote, tmp_path
):
    provider, _, calls, _ = remote
    db = tmp_path / "api.sqlite3"
    with TestClient(create_app(db, remote_provider=provider)) as client:
        assert client.get("/api/library").json()["items"] == []
        assert (
            client.post(
                "/api/remote/open",
                json={"year": 2025, "round": 16, "session": "Practice 1"},
            ).status_code
            == 422
        )
        result = client.post(
            "/api/remote/open",
            json={"year": 2025, "round": 16, "session": "Qualifying"},
        )
        assert result.status_code == 200, result.text
        sid = result.json()["id"]
        prefix = "/api/sessions/" + sid
        response = client.get(
            prefix + "/replay/frame",
            params={"at": "2025-09-06T14:00:00.5Z", "driver_number": 4},
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["source"] == "tracinginsights"
        for at in ("2025-09-06T14:00:00", "2025-09-06T13:59:59Z"):
            assert (
                client.get(prefix + "/replay/frame", params={"at": at}).status_code
                == 422
            )
        assert (
            client.get(prefix + "/replay", params={"source": "fastf1"}).status_code
            == 422
        )
        assert (
            client.get(
                prefix + "/replay/frame",
                params={"at": "2025-09-06T14:00:00Z", "driver_number": 99},
            ).status_code
            == 404
        )
        assert client.get("/api/library").json()["total"] == 1
        assert client.get("/api/remote/cache").json()["used_bytes"] <= 200 * 1024 * 1024
    assert not any(Store(db).counts().values())
    assert all("Practice" not in unquote(url) for url in calls)


def test_unknown_session_does_not_trigger_network(remote):
    provider, replay, calls, _ = remote
    before = len(calls)
    with pytest.raises(DataError):
        replay.catalog("ti-2025-1-R")
    assert len(calls) == before


def test_cache_reuses_compressed_files_across_restart_and_fetches_once_for_threads(
    tmp_path,
):
    calls = []

    def fetch(url):
        calls.append(url)
        time.sleep(0.01)
        return {"data": [1, 2, 3]}

    cache = RemoteCache(tmp_path / "cache", fetch=fetch)
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            assert (
                list(
                    pool.map(
                        lambda _: cache.get("same", ["https://example.test/data"]),
                        range(6),
                    )
                )
                == [{"data": [1, 2, 3]}] * 6
            )
        assert len(calls) == 1
    finally:
        cache.close()

    def forbidden(url):
        raise AssertionError("A cached file was downloaded again")

    cache = RemoteCache(tmp_path / "cache", fetch=forbidden)
    try:
        assert cache.get("same", ["https://example.test/data"]) == {"data": [1, 2, 3]}
    finally:
        cache.close()


def test_cache_evicts_only_its_own_files_under_the_limit(tmp_path):
    outside = tmp_path / "keep.json.gz"
    outside.write_bytes(b"keep")
    randomizer = random.Random(7)

    def fetch(url):
        return {"value": randomizer.randbytes(500).hex()}

    cache = RemoteCache(tmp_path / "cache", max_bytes=1000, fetch=fetch)
    try:
        for i in range(10):
            cache.get(str(i), ["https://example.test/data"])
        assert cache.info()["used_bytes"] <= 1000
        assert cache.info()["files"] < 10
        assert outside.read_bytes() == b"keep"
    finally:
        cache.close()


def test_cache_tries_backup_source_and_transient_failures_are_retryable(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("first"):
            raise RemoteMissing("Missing")
        return {"data": 1}

    cache = RemoteCache(tmp_path / "cache", fetch=fetch)
    try:
        assert cache.get(
            "lap", ["https://example.test/first", "https://example.test/second"]
        ) == {"data": 1}
        assert len(calls) == 2
    finally:
        cache.close()


def test_failed_circuit_validation_does_not_save_a_broken_session(remote):
    provider, _, _, _ = remote

    def reject(sid):
        raise DataError("No complete circuit lap")

    with pytest.raises(DataError, match="No complete circuit lap"):
        provider.open(2025, 16, "Qualifying", validate=reject)
    assert provider.library() == []


def test_remote_race_sector_timings_reach_the_frame_contract(remote):
    provider, replay, _, _ = remote
    sid = provider.open(2025, 16, "Race")["id"]
    session = provider.get(sid)
    value = replay.snapshot(sid, session["begin"] + timedelta(seconds=2.4), 4)
    frame = ReplayFrame.model_validate(value)
    assert frame.race_timing.basis == "sector_crossings"
    assert len(frame.race_timing.rows) == 2
    assert all(
        row.sector == 3 and row.timing_at_utc <= frame.at_utc
        for row in frame.race_timing.rows
    )
    assert frame.race_timing.rows[1].interval_s == 0


def test_engineering_observations_survive_api_validation_and_hide_future_data(remote):
    _, replay, sid, session = opened(remote)

    def frame(seconds):
        return ReplayFrame.model_validate(
            replay.snapshot(sid, session["begin"] + timedelta(seconds=seconds), 4)
        )

    assert frame(0).weather is None and frame(0).race_control == []
    early = frame(0.5)
    assert early.weather.track_temp_c == 40 and early.weather.rainfall is False
    assert [m.message for m in early.race_control] == ["GREEN LIGHT"]
    assert early.drivers[0].tyres.compound is None
    assert frame(3.1).weather.track_temp_c == 42
    assert frame(3.1).race_control[0].message == "YELLOW FLAG"
    assert frame(0.5) == early


def test_optional_context_failures_do_not_stop_replay(remote):
    provider, replay, sid, session = opened(remote)
    session["engineering_context"] = {
        "weather": {"status": "missing", "items": []},
        "rcm": {"status": "unavailable", "items": []},
        "retry_after": float("inf"),
    }
    frame = ReplayFrame.model_validate(
        replay.snapshot(sid, session["begin"] + timedelta(seconds=0.5), 4)
    )
    assert frame.weather is None and frame.weather_status == "missing"
    assert frame.race_control == [] and frame.race_control_status == "unavailable"
    assert frame.drivers[0].telemetry.speed_kmh == 150
