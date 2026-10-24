from copy import deepcopy
from datetime import timedelta
import pytest
from raceos.data import utc_datetime
from raceos.race_timing import race_timing

ORIGIN = utc_datetime("2025-09-07T13:00:00Z")


def stamp(seconds):
    return (
        (ORIGIN + timedelta(seconds=seconds))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


@pytest.fixture
def session():
    def lap(n, start, times):
        return {
            "lap_number": n,
            "lap_start_utc": stamp(start),
            "sector_ends_utc": [stamp(t) if t is not None else None for t in times],
        }

    return {
        "name": "Race",
        "drivers": [
            {"number": n, "code": code}
            for n, code in [(1, "VER"), (4, "NOR"), (63, "RUS")]
        ],
        "laps": {
            1: [lap(1, 0, [10, 20, 30]), lap(2, 30, [40, 50, 60])],
            4: [lap(1, 0, [12, 22, 32]), lap(2, 32, [39, 48, 59])],
            63: [lap(1, 0, [14, 25, 36]), lap(2, 36, [46, 55, 66])],
        },
    }


def rows(session, seconds):
    return race_timing(session, ORIGIN + timedelta(seconds=seconds))["rows"]


def test_before_first_crossing_does_not_invent_positions_or_gaps(session):
    assert all(
        r["position"] is None
        and r["gap_to_leader_s"] is None
        and r["timing_at_utc"] is None
        for r in rows(session, 9.999)
    )


def test_positions_and_gaps_use_same_observed_sector(session):
    values = rows(session, 15)
    assert [r["number"] for r in values] == [1, 4, 63]
    assert [r["position"] for r in values] == [1, 2, 3]
    assert [r["gap_to_leader_s"] for r in values] == [0, 2, 4]
    assert [r["interval_s"] for r in values] == [None, 2, 2]


def test_gap_does_not_subtract_different_sector_timestamps(session):
    values = rows(session, 21)
    assert values[0]["sector"] == 2 and values[1]["sector"] == 1
    assert values[1]["gap_to_leader_s"] == 2
    assert values[1]["timing_at_utc"] == stamp(12)
    values = rows(session, 25)
    assert values[2]["gap_to_leader_s"] == 5
    assert values[2]["interval_s"] == 3


def test_order_changes_only_after_observed_crossing_and_negative_comparison_is_unknown(
    session,
):
    assert rows(session, 38.999)[0]["number"] == 1
    after = rows(session, 39)
    assert after[0]["number"] == 4
    assert after[1]["gap_to_leader_s"] is None
    assert after[1]["interval_s"] is None
    assert rows(session, 40)[1]["gap_to_leader_s"] == 1


def test_backward_seek_restores_timing_and_never_uses_future_crossing(session):
    earlier = rows(session, 25)
    rows(session, 66)
    assert rows(session, 25) == earlier
    for value in earlier:
        assert value["timing_at_utc"] <= stamp(25)


def test_generated_retirement_lap_does_not_produce_fake_progress(session):
    session["laps"][63][1]["timing_generated"] = True
    retired = next(r for r in rows(session, 66) if r["number"] == 63)
    assert (retired["lap_number"], retired["sector"]) == (1, 3)
    assert retired["timing_at_utc"] == stamp(36)


def test_missing_and_out_of_order_sector_times_are_not_invented(session):
    session["laps"][4][0]["sector_ends_utc"] = [stamp(12), None, stamp(32)]
    value = next(r for r in rows(session, 25) if r["number"] == 4)
    assert value["sector"] == 1
    session["laps"][4][0]["sector_ends_utc"] = [stamp(12), stamp(11), stamp(32)]
    assert next(r for r in rows(session, 25) if r["number"] == 4)["sector"] == 1


def test_qualifying_does_not_show_race_standings(session):
    session["name"] = "Qualifying"
    assert race_timing(session, ORIGIN) is None


def test_grid_order_is_immediate_with_blank_gaps_and_no_fake_leader(session):
    session["starting_grid"] = {1: 3, 4: 1, 63: 2}
    timing = race_timing(session, ORIGIN)
    assert timing["basis"] == "starting_grid"
    assert [row["number"] for row in timing["rows"]] == [4, 63, 1]
    assert [row["position"] for row in timing["rows"]] == [1, 2, 3]
    assert all(
        row["interval_s"] is None
        and row["gap_to_leader_s"] is None
        and row["timing_at_utc"] is None
        for row in timing["rows"]
    )


def test_first_sector_switches_from_grid_before_lap_one_finishes(session):
    session["starting_grid"] = {1: 3, 4: 1, 63: 2}
    timing = race_timing(session, ORIGIN + timedelta(seconds=10))
    assert timing["basis"] == "sector_crossings"
    assert timing["rows"][0]["number"] == 1 and timing["rows"][0]["position"] == 1
    assert timing["rows"][0]["lap_number"] == 1 and timing["rows"][0]["sector"] == 1
    assert all(
        row["position"] is None and row["timing_at_utc"] is None
        for row in timing["rows"][1:]
    )
    after = rows(session, 15)
    assert [row["gap_to_leader_s"] for row in after] == [0, 2, 4]
    assert [row["gap_to_leader_s"] for row in rows(session, 25)] == [0, 2, 5]


def test_grid_handles_unassigned_slots_and_missing_drivers_without_guessing(session):
    session["starting_grid"] = {1: 3, 4: 0}
    timing = race_timing(session, ORIGIN)
    positions = {row["number"]: row["position"] for row in timing["rows"]}
    assert positions == {1: 3, 4: None, 63: None}
    assert (
        next(row for row in timing["rows"] if row["number"] == 4)["grid_position"] == 0
    )


def test_rewinding_restores_grid_and_removes_future_gaps(session):
    session["starting_grid"] = {1: 3, 4: 1, 63: 2}
    before = race_timing(session, ORIGIN)
    race_timing(session, ORIGIN + timedelta(seconds=66))
    assert race_timing(session, ORIGIN) == before
