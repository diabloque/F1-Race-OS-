"""Offline checks for FastF1 normalization, quality reporting, and repeatable imports."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from raceos import cli
from raceos.data import DataError, brake_state, profile, telemetry_sample, utc_iso
from raceos.providers import fastf1
from raceos.storage import Store


def make_bundle():
    samples = [
        telemetry_sample(
            4,
            f"2025-09-06T14:00:00.{index:03d}Z",
            {
                "Speed": 250,
                "Throttle": 100,
                "Brake": False,
                "nGear": 7,
                "RPM": 11000,
                "DRS": 12,
            },
        )
        for index in (0, 250, 500)
    ]
    return {
        "schema_version": 1,
        "source": "fastf1",
        "session": {
            "id": "fastf1:pilot",
            "year": 2025,
            "location": "Monza",
            "name": "Qualifying",
            "scheduled_start_utc": "2025-09-06T14:00:00Z",
        },
        "driver": {"number": 4, "code": "NOR", "name": "Lando Norris"},
        "drivers": [
            {"number": 4, "code": "NOR", "name": "Lando Norris", "team": "McLaren"}
        ],
        "laps": [{"driver_number": 4, "lap_number": 1, "lap_duration_s": 80.123}],
        "telemetry": samples,
    }


@pytest.mark.parametrize(
    "value,expected", [(False, False), (True, True), (None, None), (104, None)]
)
def test_braking_is_a_boolean_state_not_pressure(value, expected):
    assert brake_state(value) is expected


def test_timestamps_convert_offsets_and_reject_unknown_timezone():
    assert utc_iso("2025-09-06T16:00:00+02:00") == "2025-09-06T14:00:00Z"
    with pytest.raises(DataError, match="timezone"):
        utc_iso("2025-09-06T14:00:00")


def test_missing_values_remain_missing_and_unknown_drs_codes_survive():
    sample = telemetry_sample(
        4, "2025-09-06T14:00:00Z", {"Speed": float("nan"), "DRS": 9}
    )
    assert sample["speed_kmh"] is None
    assert sample["throttle_pct"] is None
    assert sample["brake_pressed"] is None
    assert sample["drs_code"] == 9


def test_quality_checks_expose_gaps_and_invalid_data_without_repair():
    bundle = make_bundle()
    bundle["telemetry"][1]["speed_kmh"] = 999
    bundle["telemetry"][1]["throttle_pct"] = None
    bundle["telemetry"][2]["timestamp_utc"] = "2025-09-06T14:00:05Z"
    before = deepcopy(bundle)
    summary = profile(bundle)
    assert summary["maximum_gap_s"] == 4.75
    assert summary["gaps_over_1s"] == 1
    assert summary["missing_by_channel"]["throttle_pct"] == 1
    assert summary["out_of_range_by_channel"]["speed_kmh"] == 1
    assert bundle == before


def test_quality_checks_preserve_out_of_order_and_duplicate_samples():
    bundle = make_bundle()
    bundle["telemetry"][2]["timestamp_utc"] = bundle["telemetry"][0]["timestamp_utc"]
    bundle["telemetry"].append(deepcopy(bundle["telemetry"][2]))
    summary = profile(bundle)
    assert summary["out_of_order_timestamps"] == 1
    assert summary["duplicate_timestamps"] == 1
    assert summary["telemetry_samples"] == 4


def test_cli_online_then_offline_uses_only_fastf1(tmp_path, monkeypatch):
    import truststore

    downloads = []
    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: None)

    def download(*args, **kwargs):
        downloads.append(args)
        return make_bundle()

    monkeypatch.setattr(fastf1, "load", download)
    arguments = ["ingest", "--data-dir", str(tmp_path)]
    assert cli.main(arguments) == 0
    assert len(downloads) == 1

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline mode attempted to contact a provider")

    monkeypatch.setattr(fastf1, "load", forbidden)
    monkeypatch.setattr(truststore, "inject_into_ssl", forbidden)
    assert cli.main(arguments + ["--offline"]) == 0
    assert list(tmp_path.glob("*/normalized/openf1.json")) == []
    assert len(list(tmp_path.rglob("quality.md"))) == 1
    assert Store(tmp_path / "raceos.sqlite3").counts()["telemetry"] == 3


def test_cli_offline_without_saved_data_returns_failure(tmp_path, capsys):
    assert cli.main(["ingest", "--data-dir", str(tmp_path), "--offline"]) == 1
    assert "Run this session online once first" in capsys.readouterr().err


def test_pre_2023_fastf1_sessions_are_supported(tmp_path, monkeypatch):
    import truststore

    old = make_bundle()
    old["session"]["year"] = 2020
    old["session"]["scheduled_start_utc"] = "2020-09-06T14:00:00Z"
    for sample in old["telemetry"]:
        sample["timestamp_utc"] = sample["timestamp_utc"].replace("2025", "2020")
    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: None)
    monkeypatch.setattr(fastf1, "load", lambda *args, **kwargs: old)
    assert cli.main(["ingest", "--year", "2020", "--data-dir", str(tmp_path)]) == 0
    assert Store(tmp_path / "raceos.sqlite3").sessions(year=2020)["total"] == 1


def test_adapter_preserves_samples_and_treats_naive_library_dates_as_utc(
    tmp_path, monkeypatch
):
    import fastf1 as library
    import pandas as pd

    calls = []
    start = pd.Timestamp("2025-09-06T14:00:00")
    session = SimpleNamespace(
        event={"Location": "Monza", "RoundNumber": 16},
        name="Qualifying",
        date=start,
        t0_date=start,
        results=pd.DataFrame(
            [
                {
                    "DriverNumber": "4",
                    "Abbreviation": "NOR",
                    "FullName": "Lando Norris",
                    "TeamName": "McLaren",
                }
            ]
        ),
        laps=pd.DataFrame(
            [
                {
                    "DriverNumber": "4",
                    "LapNumber": 1,
                    "LapTime": pd.Timedelta(seconds=80),
                    "LapStartTime": pd.Timedelta(seconds=1),
                    "Time": pd.Timedelta(seconds=81),
                }
            ]
        ),
        car_data={
            "4": pd.DataFrame(
                {
                    "Date": [start, start + pd.Timedelta(milliseconds=240)],
                    "Speed": [0, 100],
                    "Throttle": [104, 90],
                    "Brake": [False, True],
                    "nGear": [0, 3],
                    "RPM": [0, 9000],
                    "DRS": [9, 12],
                }
            )
        },
        pos_data={
            "4": pd.DataFrame(
                {
                    "Date": [
                        start + pd.Timedelta(milliseconds=100),
                        start + pd.Timedelta(milliseconds=700),
                    ],
                    "X": [-10, 50],
                    "Y": [100, 150],
                    "Z": [0, 0],
                    "Status": ["OnTrack", "OffTrack"],
                }
            )
        },
        load=lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    monkeypatch.setattr(library, "get_session", lambda *args, **kwargs: session)
    monkeypatch.setattr(library.Cache, "enable_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(library.Cache, "offline_mode", lambda *args, **kwargs: None)
    monkeypatch.setattr(library.Cache, "set_enabled", lambda: None)
    result = fastf1.load(
        tmp_path / "cache", tmp_path / "exports", 2025, "Monza", "Qualifying", "NOR"
    )
    assert calls == [
        {"laps": True, "telemetry": True, "weather": False, "messages": False}
    ]
    assert result["source"] == "fastf1"
    assert result["telemetry"][0]["timestamp_utc"] == "2025-09-06T14:00:00Z"
    assert result["telemetry"][0]["throttle_pct"] == 104
    assert result["telemetry"][1]["brake_pressed"] is True
    assert result["laps"][0]["lap_start_utc"] == "2025-09-06T14:00:01Z"
    assert (tmp_path / "exports" / "car_data.json").is_file()

    assert result["laps"][0]["lap_end_utc"] == "2025-09-06T14:01:21Z"
    assert len(result["positions"]) == 2
    assert result["positions"][0]["x"] == -10
    assert result["positions"][1]["status"] == "OffTrack"
    assert (
        result["positions"][0]["timestamp_utc"]
        != result["telemetry"][0]["timestamp_utc"]
    )
