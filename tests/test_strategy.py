from raceos.strategy import pace_by_stint


def lap(number, duration, age=None, **extra):
    return {
        "lap_number": number,
        "lap_duration_s": duration,
        "tyre_life_laps": age if age is not None else number,
        "stint": 1,
        "compound": "MEDIUM",
        **extra,
    }


def test_fuel_correction_and_trend():
    laps = [lap(i, 90 + i * 0.1 + (100 - (i - 1) * 2) * 0.03) for i in range(1, 6)]
    result = pace_by_stint(laps, 100, 2, 0.03)
    assert result["stints"][0]["slope_s_per_lap"] == 0.1
    assert result["stints"][0]["points"][0]["corrected_s"] == 90.1


def test_excludes_pits_generated_and_large_outliers():
    laps = [lap(i, 90 + i * 0.1) for i in range(1, 7)]
    laps += [
        lap(7, 200),
        lap(8, 100, pit_in_utc="yes"),
        lap(9, 100, timing_generated=True),
    ]
    result = pace_by_stint(laps, 0, 0, 0)
    assert result["excluded_laps"] == 3
    assert result["stints"][0]["laps"] == 6


def test_missing_age_and_same_age_do_not_invent_a_trend():
    result = pace_by_stint(
        [
            lap(1, 90, age=1),
            lap(2, 91, age=1),
            lap(3, 92, age=1),
            {**lap(4, 93), "tyre_life_laps": None},
        ],
        0,
        0,
        0,
    )
    assert result["excluded_laps"] == 1
    assert result["stints"][0]["slope_s_per_lap"] is None


def test_pace_endpoint_uses_selected_driver_and_rejects_qualifying(tmp_path):
    from fastapi.testclient import TestClient
    from raceos.api import create_app

    class Provider:
        def get(self, sid):
            return {
                "name": "Qualifying" if sid.endswith("Q") else "Race",
                "laps": {4: [lap(i, 90 + i * 0.2) for i in range(1, 5)]},
            }

    with TestClient(
        create_app(db_path=tmp_path / "test.db", remote_provider=Provider())
    ) as client:
        result = client.get(
            "/api/sessions/ti-2025-1-R/strategy/pace",
            params={"driver_number": 4, "fuel_start": 0},
        )
        assert result.status_code == 200
        assert result.json()["stints"][0]["slope_s_per_lap"] == 0.2
        assert (
            client.get(
                "/api/sessions/ti-2025-1-R/strategy/pace", params={"driver_number": 7}
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/sessions/ti-2025-1-Q/strategy/pace", params={"driver_number": 4}
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/sessions/ti-2025-1-R/strategy/pace",
                params={"driver_number": 4, "fuel_burn": -1},
            ).status_code
            == 422
        )
