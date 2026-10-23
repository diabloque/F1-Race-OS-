from copy import deepcopy
from datetime import timedelta
import pytest
from raceos.data import utc_datetime
from raceos.engineering import tyre_state, environment
from raceos.storage import timestamp

ORIGIN = utc_datetime("2025-09-07T13:00:00Z")


def at(seconds):
    return ORIGIN + timedelta(seconds=seconds)


def lap(n, start, finish, life, compound="MEDIUM", stint=1, **extra):
    return {
        "lap_number": n,
        "lap_start_utc": timestamp(at(start)),
        "lap_end_utc": timestamp(at(finish)),
        "tyre_life_laps": life,
        "compound": compound,
        "stint": stint,
        "fresh_tyres": True,
        "pit_data_available": True,
        **extra,
    }


@pytest.fixture
def laps():
    return [
        lap(1, 0, 30, 1),
        lap(2, 30, 60, 2, pit_in_utc=timestamp(at(55))),
        lap(3, 60, 100, 3, "SOFT", 2, fresh_tyres=False, pit_out_utc=timestamp(at(75))),
        lap(4, 100, 130, 4, "SOFT", 2, fresh_tyres=False),
    ]


def test_tyre_age_is_completed_laps_not_future_end_of_lap_count(laps):
    assert tyre_state(laps, at(0), ORIGIN)["age_laps"] == 0
    assert tyre_state(laps, at(29.999), ORIGIN)["age_laps"] == 0
    assert tyre_state(laps, at(30), ORIGIN)["age_laps"] == 1


def test_new_tyre_set_and_stint_wait_for_recorded_pit_exit(laps):
    before = tyre_state(laps, at(74.999), ORIGIN)
    assert before["compound"] == "MEDIUM" and before["stint"] == 1
    assert before["age_laps"] == 2
    assert before["in_pit"] and before["pit_visits"] == 0
    after = tyre_state(laps, at(75), ORIGIN)
    assert after["compound"] == "SOFT" and after["stint"] == 2
    assert after["age_laps"] == 2 and after["fresh"] is False
    assert not after["in_pit"] and after["pit_visits"] == 1


def test_pit_visit_is_counted_at_exit_and_duplicate_events_count_once(laps):
    assert not tyre_state(laps, at(54.999), ORIGIN)["in_pit"]
    assert tyre_state(laps, at(55), ORIGIN)["in_pit"]
    duplicate = deepcopy(laps[2])
    duplicate["lap_number"] = 5
    assert tyre_state(laps + [duplicate], at(76), ORIGIN)["pit_visits"] == 1


def test_initial_garage_exit_is_not_a_completed_pit_visit(laps):
    laps[0]["pit_out_utc"] = timestamp(at(5))
    assert tyre_state(laps, at(4.999), ORIGIN)["compound"] is None
    assert tyre_state(laps, at(5), ORIGIN)["pit_visits"] == 0


def test_older_pit_events_and_stint_number_do_not_invent_visit_count(laps):
    laps[0]["pit_in_utc"] = timestamp(at(-10))
    laps[0]["pit_out_utc"] = timestamp(at(-5))
    laps[0]["stint"] = 5
    assert tyre_state(laps, at(1), ORIGIN)["pit_visits"] == 0


def test_generated_retirement_lap_does_not_reveal_new_tyre_metadata(laps):
    laps[2]["timing_generated"] = True
    assert tyre_state(laps, at(76), ORIGIN)["compound"] == "MEDIUM"


def test_missing_tyre_data_stays_unknown():
    result = tyre_state(
        [{"lap_number": 1, "lap_start_utc": timestamp(at(0))}], at(1), ORIGIN
    )
    assert result["compound"] is None and result["age_laps"] is None
    assert result["pit_visits"] is None and result["fresh"] is None


def test_backward_seek_restores_tyre_and_pit_state(laps):
    before = tyre_state(laps, at(15), ORIGIN)
    tyre_state(laps, at(130), ORIGIN)
    assert tyre_state(laps, at(15), ORIGIN) == before
    assert tyre_state(laps, at(130), ORIGIN)["age_laps"] == 4


def context():
    return {
        "weather": {
            "status": "ready",
            "items": [
                {"wT": 10, "wAT": 25, "wTT": 40, "wR": False, "wWS": 0, "wWD": 0},
                {"wT": 200, "wAT": 22, "wTT": 36, "wR": True},
            ],
        },
        "rcm": {
            "status": "ready",
            "items": [
                {"time": timestamp(at(5)), "msg": "GREEN LIGHT", "flag": "GREEN"},
                {"time": timestamp(at(20)), "msg": "SAFETY CAR DEPLOYED"},
                {"time": timestamp(at(20)), "msg": "PENALTY ISSUED"},
            ],
        },
    }


def test_weather_uses_latest_past_observation_and_flags_old_report():
    session = {"origin": ORIGIN}
    assert environment(session, context(), at(9.999))["weather"] is None
    now = environment(session, context(), at(10))["weather"]
    assert now["track_temp_c"] == 40 and now["rainfall"] is False
    assert now["wind_speed_ms"] == 0 and now["wind_direction_deg"] == 0
    assert now["age_s"] == 0 and not now["stale"]
    older = environment(session, context(), at(150))["weather"]
    assert older["track_temp_c"] == 40 and older["stale"]
    assert environment(session, context(), at(200))["weather"]["rainfall"] is True


def test_messages_appear_at_issue_time_and_equal_times_are_stable():
    session = {"origin": ORIGIN}
    assert environment(session, context(), at(4.999))["race_control"] == []
    assert len(environment(session, context(), at(5))["race_control"]) == 1
    assert [
        m["id"] for m in environment(session, context(), at(20))["race_control"]
    ] == [2, 1, 0]
    early = environment(session, context(), at(15))
    environment(session, context(), at(200))
    assert environment(session, context(), at(15)) == early


def test_invalid_message_dates_and_missing_observations_stay_unavailable():
    data = context()
    data["rcm"]["items"] = [
        {"time": "bad", "msg": "Do not show"},
        {"time": "None", "msg": "No clock"},
    ]
    data["weather"]["items"] = [{"wT": "None", "wTT": 40}]
    result = environment({"origin": ORIGIN}, data, at(100))
    assert result["weather"] is None and result["race_control"] == []


def test_message_response_is_bounded_to_latest_fifty_past_events():
    data = context()
    data["rcm"]["items"] = [
        {"time": timestamp(at(i)), "msg": str(i)} for i in range(100)
    ]
    result = environment({"origin": ORIGIN}, data, at(75))["race_control"]
    assert len(result) == 50
    assert result[0]["message"] == "75" and result[-1]["message"] == "26"
