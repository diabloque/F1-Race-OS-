from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote
import pytest
from fastapi.testclient import TestClient
from raceos.analysis import PerformanceAnalysis, LapComparison, eligible, input_metrics
from raceos.api import create_app
from raceos.data import DataError, utc_datetime
from raceos.remote_cache import RemoteCache, RemoteMissing
from raceos.providers.tracinginsights import TracingInsights
from raceos.storage import NotFound

START = utc_datetime("2025-09-06T14:00:00Z")


def sample(seconds, throttle=100, brake=False):
    return {
        "timestamp_utc": (START + timedelta(seconds=seconds)).isoformat(),
        "throttle_pct": throttle,
        "brake_pressed": brake,
    }


def test_input_percentages_weight_elapsed_time_not_sample_count():
    rows = [sample(0, 100, True), sample(1, 0, False), sample(1.25, 0, False)]
    result = input_metrics(rows, START, START + timedelta(seconds=1.25))
    for metric in result.values():
        assert metric["active_s"] == 1 and metric["percent"] == 80
        assert metric["coverage_pct"] == 100


def test_gaps_unknown_brake_and_invalid_throttle_are_not_counted_as_released():
    rows = [
        sample(0, 104, None),
        sample(0.5, 99, True),
        sample(1, 0, False),
        sample(3, 100, False),
        sample(3.5, 100, False),
    ]
    result = input_metrics(rows, START, START + timedelta(seconds=4))
    assert result["full_throttle"]["known_s"] == 1
    assert result["full_throttle"]["percent"] == 100
    assert result["full_throttle"]["coverage_pct"] == 25
    assert result["braking"]["known_s"] == 1
    assert result["braking"]["percent"] == 50


def test_metrics_do_not_extrapolate_tail_or_use_samples_past_finish():
    rows = [sample(0), sample(0.5), sample(1.5)]
    result = input_metrics(rows, START, START + timedelta(seconds=1))["full_throttle"]
    assert result["known_s"] == 0.5 and result["coverage_pct"] == 50


def test_duplicate_timestamp_uses_last_sample_for_next_interval():
    result = input_metrics(
        [sample(0, 100), sample(0, 0), sample(1, 100)],
        START,
        START + timedelta(seconds=1),
    )
    assert result["full_throttle"]["active_s"] == 0
    assert result["full_throttle"]["percent"] == 0


def test_absent_coverage_is_unknown_and_nonpositive_window_is_rejected():
    assert (
        input_metrics([], START, START + timedelta(seconds=1))["braking"]["percent"]
        is None
    )
    with pytest.raises(DataError):
        input_metrics([], START, START)


@pytest.fixture
def analysis(tmp_path):
    # Use real adapter parsing with distinct known driver timings and sector values.
    schedule = {
        "round_number": {"0": 16},
        "event_name": {"0": "Italian Grand Prix"},
        "location": {"0": "Monza"},
        "gmt_offset": {"0": "+02:00"},
    }
    for slot in range(1, 6):
        schedule[f"session{slot}"] = {"0": "Qualifying" if slot == 4 else "Practice 1"}
        schedule[f"session{slot}_date"] = {"0": "2025-09-06T16:00:00"}
    drivers = {
        "drivers": [
            {"driver": code, "dn": str(n), "fn": code, "ln": "Driver", "team": "Team"}
            for n, code in [(4, "NOR"), (1, "VER")]
        ]
    }
    calls = []

    def fetch(url):
        url = unquote(url)
        calls.append(url)
        if "schedule_" in url:
            return deepcopy(schedule)
        if url.endswith("drivers.json"):
            return deepcopy(drivers)
        if url.endswith("laptimes.json"):
            is_b = "/VER/" in url
            return {
                "lap": [1, 2],
                "lST": [0, 2],
                "sesT": [2, 5 if is_b else 4],
                "time": [2, 3 if is_b else 2],
                "lSD": ["2025-09-06T14:00:00", "2025-09-06T14:00:02"],
                "s1": [0.5, 1],
                "s2": [0.5, 1],
                "s3": [1, 1 if is_b else "None"],
                "ff1G": [False, False],
            }
        if url.endswith("_tel.json"):
            return {
                "tel": {
                    "time": [0, 0.5, 1, 1.5, 2],
                    "speed": [150] * 5,
                    "throttle": [100, 0, 100, 0, 100],
                    "brake": [0, 1, 0, 1, 0],
                }
            }
        raise RemoteMissing("No optional file")

    cache = RemoteCache(tmp_path / "cache", fetch=fetch)
    provider = TracingInsights(tmp_path / "remote", cache=cache)
    sid = provider.open(2025, 16, "Qualifying")["id"]
    yield PerformanceAnalysis(provider), provider, sid, calls
    cache.close()


def test_choices_only_include_observed_completions_and_no_final_deletion_data(analysis):
    service, _, sid, _ = analysis
    assert all(
        not d["laps"]
        for d in service.choices(sid, START + timedelta(seconds=1.999))["drivers"]
    )
    choices = service.choices(sid, START + timedelta(seconds=2))
    assert all([l["lap_number"] for l in d["laps"]] == [1] for d in choices["drivers"])
    assert all(
        set(d["laps"][0]) == {"lap_number", "lap_time_s", "completed_at_utc"}
        for d in choices["drivers"]
    )


def test_comparison_preserves_delta_sign_missing_sectors_and_self_comparison(analysis):
    service, _, sid, _ = analysis
    at = START + timedelta(seconds=5)
    result = LapComparison.model_validate(service.compare(sid, at, 4, 2, 1, 2))
    assert result.lap_delta_s == 1
    assert result.sector_deltas_s == [0, 0, None]
    assert result.a.full_throttle.coverage_pct == 100
    assert result.b.full_throttle.coverage_pct == pytest.approx(66.667)
    assert service.compare(sid, at, 1, 2, 4, 2)["lap_delta_s"] == -1
    self_comparison = service.compare(sid, at, 4, 2, 4, 2)
    assert self_comparison["lap_delta_s"] == 0


def test_future_selection_is_rejected_before_either_telemetry_download(analysis):
    service, _, sid, calls = analysis
    before = len(calls)
    with pytest.raises(DataError, match="completed"):
        service.compare(sid, START + timedelta(seconds=4), 4, 2, 1, 2)
    assert len(calls) == before
    with pytest.raises(NotFound):
        service.compare(sid, START + timedelta(seconds=5), 99, 1, 1, 1)


def test_generated_and_incomplete_laps_are_not_eligible(analysis):
    service, provider, sid, _ = analysis
    session = provider.get(sid)
    session["laps"][4][0]["timing_generated"] = True
    assert not service.choices(sid, START + timedelta(seconds=2))["drivers"][0]["laps"]
    row = deepcopy(session["laps"][4][1])
    row["lap_duration_s"] = None
    assert not eligible(row, START + timedelta(seconds=5))


def test_missing_telemetry_keeps_recorded_timing_and_unknown_inputs(analysis):
    service, provider, sid, _ = analysis

    def missing(*args):
        raise RemoteMissing("Not published")

    provider.samples = missing
    result = service.compare(sid, START + timedelta(seconds=5), 4, 2, 1, 2)
    assert result["lap_delta_s"] == 1
    assert result["a"]["full_throttle"]["percent"] is None
    assert result["a"]["full_throttle"]["coverage_pct"] == 0
    assert any("not published" in w for w in result["a"]["warnings"])


def test_api_validates_clock_completion_and_source_and_does_not_cache(
    analysis, tmp_path
):
    _, provider, sid, _ = analysis
    with TestClient(
        create_app(tmp_path / "archive.sqlite3", remote_provider=provider)
    ) as client:
        prefix = f"/api/sessions/{sid}/analysis"
        params = {
            "at": "2025-09-06T14:00:05Z",
            "driver_a": 4,
            "lap_a": 2,
            "driver_b": 1,
            "lap_b": 2,
        }
        response = client.get(prefix + "/compare", params=params)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["lap_delta_s"] == 1
        assert (
            client.get(
                prefix + "/compare", params={**params, "at": "2025-09-06T14:00:04Z"}
            ).status_code
            == 422
        )
        assert (
            client.get(
                prefix + "/compare", params={**params, "at": "2025-09-06T14:00:05"}
            ).status_code
            == 422
        )
        assert (
            client.get(
                prefix + "/compare", params={**params, "driver_a": 0}
            ).status_code
            == 422
        )
        assert (
            client.get(
                prefix + "/laps", params={"at": "2025-09-06T13:59:59Z"}
            ).status_code
            == 422
        )
        choices = client.get(prefix + "/laps", params={"at": "2025-09-06T14:00:02Z"})
        assert (
            choices.status_code == 200
            and choices.headers["cache-control"] == "no-store"
        )
        assert (
            client.get(
                "/api/sessions/old-fastf1-id/analysis/laps", params={"at": params["at"]}
            ).status_code
            == 422
        )
