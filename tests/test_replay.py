"""Replay contract: deterministic seeks, past-only samples and lap availability."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import cos, sin, tau
import sqlite3

import pytest
from fastapi.testclient import TestClient
from raceos import replay
from raceos.api import create_app
from raceos.data import DataError
from raceos.storage import Store
from raceos.track import build_track
from test_backend import bundle

START = datetime(2025, 9, 6, 14, tzinfo=UTC)


def at(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def recording():
    data = bundle()
    data["laps"] = [
        dict(
            source="fastf1",
            driver_number=4,
            lap_number=1,
            lap_start_utc=at(0),
            lap_end_utc=at(1.2),
            lap_duration_s=1,
        ),
        dict(
            source="fastf1",
            driver_number=4,
            lap_number=2,
            lap_start_utc=at(1.2),
            lap_end_utc=at(2.2),
            lap_duration_s=1,
        ),
        dict(
            source="fastf1",
            driver_number=4,
            lap_number=3,
            lap_start_utc=at(2.2),
            lap_duration_s=None,
        ),
    ]
    for seconds in (2, 8, 9):
        sample = deepcopy(data["telemetry"][-1])
        sample["timestamp_utc"] = at(seconds)
        data["telemetry"].append(sample)
    data["telemetry"][2].update(throttle_pct=0, brake_pressed=True)
    data["positions"] = [
        dict(
            source="fastf1",
            driver_number=4,
            timestamp_utc=at(seconds),
            x=x,
            y=y,
            z=0,
            status=status,
        )
        for seconds, x, y, status in [
            (0.1, 100, 100, "OnTrack"),
            (0.5, 200, 100, "OnTrack"),
            (1.2, 400, 200, "OffTrack"),
            (2, 500, 400, "OnTrack"),
            (8, 1000, 1000, "OnTrack"),
        ]
    ]
    return data


@pytest.fixture
def archive(tmp_path):
    store = Store(tmp_path / "replay.sqlite3")
    sid = store.import_bundles([recording()])[0]["session_id"]
    store.save_track(
        sid,
        dict(
            source="fastf1",
            approximate=True,
            points=[dict(x=100, y=100), dict(x=200, y=100), dict(x=100, y=200)],
        ),
    )
    return store, sid


def frame(archive, seconds):
    store, sid = archive
    return replay.snapshot(store, sid, at(seconds), 4)


def focused(value):
    return next(car for car in value["drivers"] if car["number"] == 4)


def test_catalog_contains_jump_starts_without_future_results(archive):
    store, sid = archive
    catalog = replay.catalog(store, sid)
    assert catalog["initial_driver_number"] == 4
    assert catalog["duration_s"] == 9
    for driver in catalog["drivers"]:
        assert "best_lap" not in driver
        assert all(set(lap) == {"lap_number", "start_utc"} for lap in driver["laps"])


def test_only_past_samples_and_stable_duplicate_order_are_visible(archive):
    car = focused(frame(archive, 0.499999))
    assert car["telemetry"]["sample_index"] == 1
    assert car["telemetry"]["speed_kmh"] == 101
    assert car["position"]["x"] == 100
    assert car["best_lap"] is None
    unknown = next(car for car in frame(archive, 0.5)["drivers"] if car["number"] == 1)
    assert unknown["telemetry"] is None and unknown["position"] is None


def test_results_appear_exactly_at_observed_finish(archive):
    assert frame(archive, 1.199999)["completed_laps"] == []
    result = frame(archive, 1.2)
    assert [lap["lap_number"] for lap in result["completed_laps"]] == [1]
    assert focused(result)["current_lap_number"] == 2
    assert focused(result)["best_lap"]["lap_duration_s"] == 1


def test_unknown_last_lap_never_gets_a_fabricated_finish(archive):
    result = frame(archive, 9)
    assert [lap["lap_number"] for lap in result["completed_laps"]] == [1, 2]
    assert focused(result)["current_lap_number"] == 3


def test_completion_is_conservative_when_source_times_disagree():
    lap = dict(lap_start_utc=at(0), lap_end_utc=at(0.9), lap_duration_s=1)
    assert replay.completion_time(lap, None) == START + timedelta(seconds=1)
    assert replay.completion_time({}, {"lap_start_utc": at(2)}) == START + timedelta(
        seconds=2
    )
    assert replay.completion_time({}, None) is None


def test_stale_samples_become_unknown_then_recover(archive):
    stale = focused(frame(archive, 5))
    assert stale["telemetry"] is None and stale["position"] is None
    assert stale["telemetry_age_s"] == 3
    fresh = focused(frame(archive, 8))
    assert fresh["position"]["x"] == 1000
    assert fresh["telemetry"] is not None
    assert "dx" not in fresh["position"]  # No orientation across a six-second gap.


def test_off_track_status_is_preserved(archive):
    car = focused(frame(archive, 1.2))
    assert car["position"]["status"] == "OffTrack"
    assert car["position"]["dx"] == 200


def test_trail_joins_each_position_only_to_telemetry_available_then(archive):
    result = frame(archive, 0.5)
    assert [p["throttle_pct"] for p in result["trail"]] == [99, 0]
    assert [p["brake_pressed"] for p in result["trail"]] == [False, True]
    assert all(
        datetime.fromisoformat(p["timestamp_utc"]) <= START + timedelta(seconds=0.5)
        for p in result["trail"]
    )


def test_backward_seek_reconstructs_identical_state(archive):
    before = frame(archive, 0.5)
    frame(archive, 9)
    assert frame(archive, 0.5) == before
    assert before["completed_laps"] == []


def test_legacy_import_preserves_positions_but_explicit_empty_clears(archive):
    store, _ = archive
    old = recording()
    del old["positions"]
    store.import_bundles([old])
    assert store.counts()["positions"] == 5
    old["positions"] = []
    store.import_bundles([old])
    assert store.counts()["positions"] == 0


@pytest.mark.parametrize("invalid", ["driver", "source", "naive", "nan"])
def test_invalid_position_batch_never_partially_imports(tmp_path, invalid):
    bad = recording()
    position = bad["positions"][0]
    if invalid == "driver":
        position["driver_number"] = 1
    if invalid == "source":
        position["source"] = "openf1"
    if invalid == "naive":
        position["timestamp_utc"] = "2025-09-06T14:00:00"
    if invalid == "nan":
        position["x"] = float("nan")
    store = Store(tmp_path / "invalid.sqlite3")
    store.initialize()
    with pytest.raises(DataError):
        store.import_bundles([recording(), bad])
    assert not any(store.counts().values())


def test_schema_one_migration_preserves_existing_archive(archive):
    store, sid = archive
    count = store.counts()["telemetry"]
    with sqlite3.connect(store.path) as connection:
        connection.executescript(
            "DROP TABLE tracks; DROP TABLE positions; PRAGMA user_version=1;"
        )
    Store(store.path).initialize()
    assert store.counts()["telemetry"] == count
    assert store.session(sid)["id"] == sid
    assert store.counts()["positions"] == 0
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


def test_replay_api_validates_clock_and_driver_and_disables_frame_cache(archive):
    store, sid = archive
    with TestClient(create_app(store.path)) as client:
        path = f"/api/sessions/{sid}"
        assert client.get(path + "/track").json()["approximate"] is True
        assert client.get(path + "/replay").status_code == 200
        response = client.get(
            path + "/replay/frame", params={"at": at(0.5), "driver_number": 4}
        )
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["drivers"][1]["position"]["dx"] == 100
        for invalid in ("2025-09-06T14:00:00", at(-1), at(10)):
            assert (
                client.get(path + "/replay/frame", params={"at": invalid}).status_code
                == 422
            )
        assert (
            client.get(
                path + "/replay/frame", params={"at": at(0), "driver_number": 99}
            ).status_code
            == 404
        )
        assert (
            client.get(path + "/replay", params={"source": "openf1"}).status_code == 422
        )


def test_static_outline_requires_a_complete_recorded_path():
    data = recording()
    with pytest.raises(DataError):
        build_track(data)
    data["laps"] = [
        dict(driver_number=4, lap_number=1, lap_start_utc=at(0), lap_duration_s=80)
    ]
    data["positions"] = [
        dict(
            timestamp_utc=at(i),
            x=1000 + 800 * cos(tau * i / 80),
            y=1000 + 800 * sin(tau * i / 80),
            status="OnTrack",
        )
        for i in range(80)
    ]
    outline = build_track(data)
    assert len(outline["points"]) == 80
    assert outline["points"][0] == dict(x=1800, y=1000)
    assert outline["approximate"] is True
