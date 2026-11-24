"""Estimate stint trends from recorded laps and explicit fuel assumptions."""

from math import isfinite
from statistics import median


def pace_by_stint(laps, fuel_start, fuel_burn, fuel_effect):
    groups = {}
    excluded = 0
    for lap in laps:
        duration = lap.get("lap_duration_s")
        age = lap.get("tyre_life_laps")
        number = lap.get("lap_number")
        compound = lap.get("compound")
        stint = lap.get("stint")
        if (
            not isinstance(duration, (int, float))
            or not isfinite(duration)
            or duration <= 0
            or not isinstance(age, (int, float))
            or age < 0
            or not number
            or not compound
            or not stint
            or lap.get("timing_generated")
            or lap.get("pit_in_utc")
            or lap.get("pit_out_utc")
        ):
            excluded += 1
            continue
        fuel = max(0, fuel_start - (number - 1) * fuel_burn)
        corrected = duration - fuel * fuel_effect
        groups.setdefault((stint, compound), []).append(
            {
                "lap": number,
                "age": age,
                "recorded_s": duration,
                "corrected_s": round(corrected, 3),
            }
        )

    results = []
    for (stint, compound), points in sorted(groups.items()):
        # A median filter reduces the influence of unusually slow laps; it cannot
        # identify every safety-car, traffic or weather effect.
        if len(points) >= 5:
            center = median(p["corrected_s"] for p in points)
            mad = median(abs(p["corrected_s"] - center) for p in points)
            limit = max(3.0, 3 * 1.4826 * mad)
            kept = [p for p in points if abs(p["corrected_s"] - center) <= limit]
            excluded += len(points) - len(kept)
            points = kept
        slope = None
        if len(points) >= 3:
            avg_x = sum(p["age"] for p in points) / len(points)
            avg_y = sum(p["corrected_s"] for p in points) / len(points)
            denominator = sum((p["age"] - avg_x) ** 2 for p in points)
            if denominator:
                slope = round(
                    sum((p["age"] - avg_x) * (p["corrected_s"] - avg_y) for p in points)
                    / denominator,
                    3,
                )
        results.append(
            {
                "stint": stint,
                "compound": compound,
                "laps": len(points),
                "slope_s_per_lap": slope,
                "points": points,
            }
        )
    return {"stints": results, "excluded_laps": excluded}
