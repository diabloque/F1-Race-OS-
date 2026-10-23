from datetime import timedelta
from copy import deepcopy
import pytest
from raceos.data import utc_datetime
from raceos.distance_comparison import align_laps, DistanceAlignment

START = utc_datetime("2025-09-06T14:00:00Z")
LAP = {
    "start_utc": START.isoformat(),
    "completed_at_utc": (START + timedelta(seconds=2)).isoformat(),
}


def sample(time, distance, throttle=100):
    return {
        "timestamp_utc": (START + timedelta(seconds=time)).isoformat(),
        "distance_m": distance,
        "x": distance,
        "y": distance / 2 if distance is not None else None,
        "speed_kmh": 200,
        "throttle_pct": throttle,
        "brake_pressed": False,
    }


def test_normalized_distance_compares_different_recorded_lengths_and_local_gains():
    a = [sample(0, 10), sample(1, 60), sample(2, 110)]
    b = [sample(0, 20), sample(0.8, 120), sample(1.4, 170), sample(2, 220)]
    result = DistanceAlignment.model_validate(align_laps(a, b, LAP, LAP))
    assert result.available and result.coverage_pct == 100
    middle, finish = result.points[100], result.points[-1]
    assert middle.delta_s == -0.2 and middle.gain_s < 0
    assert finish.delta_s == 0 and finish.gain_s > 0
    assert middle.distance_m == 75
    assert result.distance_a_m == 100 and result.distance_b_m == 200


def test_inputs_are_held_but_time_and_position_are_interpolated():
    rows = [sample(0, 0, 0), sample(1, 50, 100), sample(2, 100)]
    result = align_laps(rows, rows, LAP, LAP)
    point = result["points"][50]["a"]
    assert point["time_s"] == 0.5 and point["x"] == 25
    assert point["throttle_pct"] == 0
    assert point["sample_at_utc"] == rows[0]["timestamp_utc"]


def test_gaps_and_unknown_distance_break_segments_without_extrapolation():
    rows = [sample(0, 0), sample(0.25, 10), sample(1.75, 90), sample(2, 100)]
    result = align_laps(rows, rows, LAP, LAP)
    assert result["points"][100]["a"] is None
    assert result["points"][180]["segment_valid"] is False
    assert result["coverage_pct"] < 25
    rows = [sample(0, 0), sample(0.5, None), sample(1, 50), sample(2, 100)]
    result = align_laps(rows, rows, LAP, LAP)
    assert result["points"][50]["delta_s"] is None
    assert result["points"][100]["segment_valid"] is False


def test_future_padding_is_excluded_before_distance_normalization():
    rows = [
        sample(-0.5, -50),
        sample(0, 0),
        sample(1, 50),
        sample(2, 100),
        sample(2.5, 1000),
    ]
    result = align_laps(rows, rows, LAP, LAP)
    assert result["distance_a_m"] == 100
    assert result["points"][-1]["a"]["time_s"] == 2
    assert all(
        utc_datetime(point["a"]["sample_at_utc"])
        <= utc_datetime(LAP["completed_at_utc"])
        for point in result["points"]
    )


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [sample(0, 0)],
        [sample(0, 100), sample(1, 0), sample(2, 200)],
        [sample(1.1, 0), sample(2, 100)],
    ],
)
def test_missing_reversed_or_partial_distance_is_unavailable(rows):
    result = DistanceAlignment.model_validate(align_laps(rows, rows, LAP, LAP))
    assert not result.available and not result.points


def test_duplicate_distance_uses_last_observation_and_invalid_inputs_stay_unknown():
    rows = [sample(0, 0), sample(0.5, 50, 104), sample(1, 50, 104), sample(2, 100)]
    rows[2]["brake_pressed"] = None
    point = align_laps(rows, rows, LAP, LAP)["points"][100]["a"]
    assert (
        point["time_s"] == 1
        and point["throttle_pct"] is None
        and point["brake_pressed"] is None
    )


def test_missing_positions_disables_map_without_changing_input_data():
    rows = [sample(0, 0), sample(1, 50), sample(2, 100)]
    for row in rows:
        row["x"] = row["y"] = None
    before = deepcopy(rows)
    assert not align_laps(rows, rows, LAP, LAP)["available"]
    assert rows == before
