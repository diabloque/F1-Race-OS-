"""Storage and API behavior against real temporary SQLite databases."""

from copy import deepcopy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from raceos import cli
from raceos.api import create_app
from raceos.data import DataError, write_json
from raceos.storage import Store


def bundle(source="fastf1"):
    return {
        "schema_version": 1,
        "source": source,
        "session": {
            "id": f"{source}:2025:16:Q",
            "year": 2025,
            "location": "Monza",
            "name": "Qualifying",
            "scheduled_start_utc": "2025-09-06T14:00:00Z",
        },
        "driver": {"number": 4, "code": "NOR", "name": "Lando Norris"},
        "drivers": [
            {"number": 4, "code": "NOR", "name": "Lando Norris", "team": "McLaren"},
            {"number": 1, "code": "VER", "name": "Max Verstappen", "team": "Red Bull"},
        ],
        "laps": [
            {
                "source": source,
                "driver_number": 4,
                "lap_number": 1,
                "lap_duration_s": 1.0,
                "lap_start_utc": "2025-09-06T14:00:00Z",
            },
            {
                "source": source,
                "driver_number": 4,
                "lap_number": 2,
                "lap_duration_s": None,
                "lap_start_utc": "2025-09-06T14:00:01Z",
            },
            {
                "source": source,
                "driver_number": 1,
                "lap_number": 1,
                "lap_duration_s": 1.0,
                "lap_start_utc": "2025-09-06T14:00:00Z",
            },
        ],
        "telemetry": [
            {
                "source": source,
                "driver_number": 4,
                "timestamp_utc": time,
                "speed_kmh": 100 + index,
                "throttle_pct": 104 if index == 0 else 99,
                "brake_pressed": None if index == 0 else False,
                "gear": 4,
                "rpm": 10000,
                "drs_code": 9,
            }
            for index, time in enumerate(
                (
                    "2025-09-06T14:00:00Z",
                    "2025-09-06T16:00:00+02:00",
                    "2025-09-06T14:00:00.500000Z",
                    "2025-09-06T14:00:01Z",
                )
            )
        ],
    }


@pytest.fixture
def database(tmp_path):
    store = Store(tmp_path / "raceos.sqlite3")
    imports = store.import_bundles([bundle()])
    return store, imports[0]["session_id"]


@pytest.fixture
def client(database):
    store, session_id = database
    with TestClient(create_app(store.path)) as client:
        yield client, session_id


def test_imports_are_persistent_and_repeated_imports_are_noops(database):
    store, session_id = database
    original_quality = store.session(session_id)["sources"]
    repeated = store.import_bundles([bundle()])
    assert {item["status"] for item in repeated} == {"skipped"}
    assert store.session(session_id)["sources"] == original_quality
    assert Store(store.path).counts() == {
        "sessions": 1,
        "session_sources": 1,
        "drivers": 2,
        "laps": 3,
        "telemetry": 4,
        "imports": 1,
        "positions": 0,
    }


def test_corrected_samples_replace_the_selected_driver(database):
    store, session_id = database
    corrected = bundle()
    corrected["telemetry"][0]["speed_kmh"] = 321
    assert store.import_bundles([corrected])[0]["status"] == "imported"
    assert store.counts()["telemetry"] == 4
    assert store.telemetry(session_id, 4)["items"][0]["speed_kmh"] == 321


def test_importing_another_driver_preserves_previous_driver_telemetry(database):
    store, session_id = database
    second = bundle()
    second["driver"] = deepcopy(second["drivers"][1])
    for sample in second["telemetry"]:
        sample["driver_number"] = 1
    store.import_bundles([second])
    assert store.telemetry(session_id, 4)["total"] == 4
    assert store.telemetry(session_id, 1)["total"] == 4
    assert store.counts()["laps"] == 3
    assert store.counts()["imports"] == 2
    assert store.import_bundles([second])[0]["status"] == "skipped"


@pytest.mark.parametrize(
    "invalid",
    ["schema", "naive_time", "wrong_driver", "wrong_source", "duplicate_lap", "nan"],
)
def test_invalid_batch_never_partially_imports(tmp_path, invalid):
    store = Store(tmp_path / "invalid.sqlite3")
    store.initialize()
    bad = bundle()
    if invalid == "schema":
        bad["schema_version"] = 999
    elif invalid == "naive_time":
        bad["telemetry"][0]["timestamp_utc"] = "2025-09-06T14:00:00"
    elif invalid == "wrong_driver":
        bad["telemetry"][0]["driver_number"] = 1
    elif invalid == "wrong_source":
        bad["laps"][0]["source"] = "openf1"
    elif invalid == "duplicate_lap":
        bad["laps"].append(deepcopy(bad["laps"][0]))
    else:
        bad["telemetry"][0]["speed_kmh"] = float("nan")
    with pytest.raises(DataError):
        store.import_bundles([bundle(), bad])
    assert not any(store.counts().values())


def test_database_failure_rolls_back_the_whole_driver_batch(tmp_path):
    store = Store(tmp_path / "rollback.sqlite3")
    store.initialize()
    second = bundle()
    second["driver"] = deepcopy(second["drivers"][1])
    for sample in second["telemetry"]:
        sample["driver_number"] = 1
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """CREATE TRIGGER reject_second_driver BEFORE INSERT ON telemetry
                            WHEN NEW.driver_number=1 BEGIN SELECT RAISE(ABORT, 'test failure'); END"""
        )
    with pytest.raises(DataError, match="rolled back"):
        store.import_bundles([bundle(), second])
    assert not any(store.counts().values())


def test_future_database_schema_is_refused(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(DataError, match="Unsupported database schema"):
        Store(path).initialize()


def test_empty_database_has_healthy_empty_catalog(tmp_path):
    with TestClient(create_app(tmp_path / "empty.sqlite3")) as client:
        assert client.get("/api/health").json()["counts"]["sessions"] == 0
        assert client.get("/api/sessions").json()["items"] == []


def test_session_sources_filters_and_pagination(client):
    client, session_id = client
    page = client.get(
        "/api/sessions", params={"year": 2025, "location": "monza", "limit": 1}
    ).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == session_id
    assert page["items"][0]["default_source"] == "fastf1"
    assert {item["source"] for item in page["items"][0]["sources"]} == {"fastf1"}
    assert client.get("/api/sessions", params={"offset": 1}).json()["items"] == []
    assert (
        client.get("/api/sessions", params={"location": "Monza' OR 1=1 --"}).json()[
            "total"
        ]
        == 0
    )
    assert client.get(f"/api/sessions/{session_id}").status_code == 200


def test_driver_catalog_states_telemetry_availability(client):
    client, session_id = client
    result = client.get(f"/api/sessions/{session_id}/drivers").json()
    assert result["source"] == "fastf1"
    drivers = {item["number"]: item for item in result["items"]}
    assert drivers[4]["telemetry_available"] is True
    assert drivers[4]["telemetry_samples"] == 4
    assert drivers[1]["telemetry_available"] is False


def test_lap_pagination_retains_incomplete_laps(client):
    client, session_id = client
    path = f"/api/sessions/{session_id}/drivers/4/laps"
    first = client.get(path, params={"limit": 1}).json()
    assert first["total"] == 2
    assert first["next_offset"] == 1
    second = client.get(path, params={"limit": 1, "offset": 1}).json()
    assert second["items"][0]["lap_duration_s"] is None
    assert second["next_offset"] is None


def test_telemetry_pagination_preserves_duplicate_timestamps(client):
    client, session_id = client
    path = f"/api/sessions/{session_id}/drivers/4/telemetry"
    first = client.get(path, params={"limit": 2}).json()
    second = client.get(
        path, params={"limit": 2, "offset": first["next_offset"]}
    ).json()
    assert first["total"] == second["total"] == 4
    assert [item["sample_index"] for item in first["items"] + second["items"]] == [
        0,
        1,
        2,
        3,
    ]
    assert first["items"][0]["timestamp_utc"] == first["items"][1]["timestamp_utc"]


def test_time_range_uses_utc_and_half_open_boundaries(client):
    client, session_id = client
    result = client.get(
        f"/api/sessions/{session_id}/drivers/4/telemetry",
        params={
            "start": "2025-09-06T16:00:00.500+02:00",
            "end": "2025-09-06T14:00:01Z",
        },
    ).json()
    assert result["total"] == 1
    assert result["items"][0]["sample_index"] == 2


def test_lap_filter_excludes_next_lap_and_explains_unknown_end(client):
    client, session_id = client
    path = f"/api/sessions/{session_id}/drivers/4/telemetry"
    first = client.get(path, params={"lap_number": 1}).json()
    assert [item["sample_index"] for item in first["items"]] == [0, 1, 2]
    missing_end = client.get(path, params={"lap_number": 2})
    assert missing_end.status_code == 422
    assert "explicit UTC time range" in missing_end.json()["detail"]
    assert client.get(path, params={"lap_number": 99}).status_code == 404


def test_missing_lap_duration_uses_next_known_lap_start(database):
    store, session_id = database
    changed = bundle()
    changed["laps"][0]["lap_duration_s"] = None
    store.import_bundles([changed])
    assert store.telemetry(session_id, 4, lap_number=1)["total"] == 3


def test_quality_flags_preserve_anomalies_and_unknown_braking(client):
    client, session_id = client
    path = f"/api/sessions/{session_id}/drivers/4"
    sample = client.get(path + "/telemetry", params={"limit": 1}).json()["items"][0]
    assert sample["throttle_pct"] == 104
    assert sample["brake_pressed"] is None
    assert "throttle_pct_out_of_range" in sample["quality_flags"]
    assert "brake_pressed_missing_or_unmapped" in sample["quality_flags"]
    assert sample["drs_code"] == 9
    profile = client.get(
        path + "/quality",
    ).json()["profile"]
    assert profile["missing_by_channel"]["brake_pressed"] == 1
    assert profile["out_of_range_by_channel"]["throttle_pct"] == 1


def test_known_driver_without_telemetry_returns_empty_data(client):
    client, session_id = client
    path = f"/api/sessions/{session_id}/drivers/1"
    assert client.get(path + "/telemetry").json()["total"] == 0
    assert client.get(path + "/quality").status_code == 404


@pytest.mark.parametrize(
    "parameters",
    [
        {"limit": 0},
        {"limit": 5001},
        {"offset": -1},
        {"source": "unknown"},
        {"source": "openf1"},
        {"lap_number": 0},
        {"start": "2025-09-06T14:00:00"},
        {"start": "2025-09-06T14:00:01Z", "end": "2025-09-06T14:00:00Z"},
    ],
)
def test_invalid_query_inputs_are_rejected(client, parameters):
    client, session_id = client
    assert (
        client.get(
            f"/api/sessions/{session_id}/drivers/4/telemetry", params=parameters
        ).status_code
        == 422
    )


def test_missing_entities_and_sql_like_ids_return_404(client):
    client, session_id = client
    assert client.get("/api/sessions/unknown").status_code == 404
    assert client.get("/api/sessions/anything' OR 1=1 --").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/drivers/99/laps").status_code == 404
    assert client.get("/api/health").json()["counts"]["sessions"] == 1


@pytest.mark.parametrize("endpoint", ["", "/4/laps", "/4/telemetry", "/4/quality"])
def test_removed_provider_is_rejected_on_every_driver_endpoint(client, endpoint):
    client, session_id = client
    response = client.get(
        f"/api/sessions/{session_id}/drivers{endpoint}", params={"source": "openf1"}
    )
    assert response.status_code == 422


def test_api_schema_and_interactive_documentation(client):
    client, session_id = client
    specification = client.get("/openapi.json").json()
    assert (
        "/api/sessions/{session_id}/drivers/{driver_number}/telemetry"
        in specification["paths"]
    )
    assert "schemas" in specification["components"]
    assert client.get("/docs").status_code == 200


def test_cli_import_ignores_archived_openf1_files(tmp_path, monkeypatch):
    from raceos.providers import fastf1

    data_dir = tmp_path / "data"
    write_json(data_dir / "pilot" / "normalized" / "fastf1.json", bundle())
    # An unreadable old provider file must not affect FastF1 imports.
    archived = data_dir / "pilot" / "normalized" / "openf1.json"
    archived.write_text("archived, not a current bundle")

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved import attempted a provider download")

    monkeypatch.setattr(fastf1, "load", forbidden)
    assert cli.main(["import", "--data-dir", str(data_dir)]) == 0
    assert cli.main(["import", "--data-dir", str(data_dir)]) == 0
    assert Store(data_dir / "raceos.sqlite3").counts()["telemetry"] == 4
    assert archived.read_text() == "archived, not a current bundle"


def test_legacy_rows_remain_saved_but_do_not_appear_in_the_active_archive(database):
    store, session_id = database
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """INSERT INTO session_sources
            SELECT session_id, 'openf1', 'legacy:pilot', input_schema_version, session_json FROM session_sources"""
        )
        connection.execute(
            """INSERT INTO drivers
            SELECT session_id, 'openf1', number, data_json FROM drivers"""
        )
        connection.execute(
            """INSERT INTO laps
            SELECT session_id, 'openf1', driver_number, lap_number, start_utc, duration_s, data_json FROM laps"""
        )
        connection.execute(
            """INSERT INTO telemetry
            SELECT session_id, 'openf1', driver_number, sample_index, timestamp_utc, data_json FROM telemetry"""
        )
        connection.execute(
            """INSERT INTO imports
            SELECT session_id, 'openf1', driver_number, content_sha256, first_imported_at_utc,
                   last_imported_at_utc, sample_count, quality_json FROM imports"""
        )
        connection.execute(
            "INSERT INTO sessions VALUES ('legacy-only', 2025, 'Spa', 'Race', '2025-07-27T13:00:00Z')"
        )
        connection.execute(
            "INSERT INTO session_sources VALUES ('legacy-only', 'openf1', 'legacy:spa', 1, '{}')"
        )
        before = connection.execute(
            "SELECT COUNT(*) FROM telemetry WHERE source='openf1'"
        ).fetchone()[0]

    with TestClient(create_app(store.path)) as client:
        catalog = client.get("/api/sessions").json()
        assert catalog["total"] == 1
        assert catalog["items"][0]["id"] == session_id
        assert [item["source"] for item in catalog["items"][0]["sources"]] == ["fastf1"]
        assert client.get("/api/sessions/legacy-only").status_code == 404
        assert client.get("/api/health").json()["counts"]["telemetry"] == 4
        assert (
            client.get(f"/api/sessions/{session_id}/drivers/4/telemetry").json()[
                "source"
            ]
            == "fastf1"
        )
    with sqlite3.connect(store.path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM telemetry WHERE source='openf1'"
            ).fetchone()[0]
            == before
            == 4
        )
