"""Race order and gaps from observed sector crossings, without extrapolation."""

from raceos.data import utc_datetime
from raceos.storage import timestamp


def race_timing(session, at):
    if session["name"] != "Race":
        return None
    clock = timestamp(at)
    observations = {}
    grid = session.get("starting_grid", {})
    for driver in session["drivers"]:
        points = {}
        for lap in session["laps"][driver["number"]]:
            # A generated retirement lap must not count as a real line crossing.
            if lap.get("timing_generated"):
                continue
            previous = lap["lap_start_utc"]
            if previous is None:
                continue
            for sector, crossing in enumerate(lap.get("sector_ends_utc", []), 1):
                if crossing is None or crossing < previous:
                    continue
                previous = crossing
                if crossing <= clock:
                    progress = (lap["lap_number"] - 1) * 3 + sector
                    points[progress] = crossing
        observations[driver["number"]] = points

    def latest(driver):
        points = observations[driver["number"]]
        progress = max(points, default=0)
        return progress, points.get(progress)

    started = any(observations.values())

    def grid_order(driver):
        position = grid.get(driver["number"])
        return position if position else 1000

    ordered = sorted(
        session["drivers"],
        key=lambda driver: (
            -latest(driver)[0],
            latest(driver)[1] or clock,
            grid_order(driver),
            driver["number"],
        ),
    )
    leader = ordered[0] if latest(ordered[0])[0] else None
    rows = []
    for index, driver in enumerate(ordered):
        progress, crossing = latest(driver)

        def gap(other):
            other_crossing = (
                observations[other["number"]].get(progress) if other else None
            )
            if crossing is None or other_crossing is None:
                return None
            seconds = (
                utc_datetime(crossing) - utc_datetime(other_crossing)
            ).total_seconds()
            return round(seconds, 3) if seconds >= 0 else None

        position = None
        if progress:
            position = index + 1
        elif not started:
            position = grid.get(driver["number"]) or None
        # All comparisons use the same lap/sector for both drivers. No distance/speed estimate.
        rows.append(
            {
                **driver,
                "position": position,
                "grid_position": grid.get(driver["number"]),
                "lap_number": (progress - 1) // 3 + 1 if progress else None,
                "sector": (progress - 1) % 3 + 1 if progress else None,
                "timing_at_utc": crossing,
                "gap_to_leader_s": gap(leader),
                "interval_s": gap(ordered[index - 1]) if index else None,
            }
        )
    return {
        "basis": "sector_crossings" if started else "starting_grid",
        "grid_status": session.get("grid_status", "ready" if grid else "missing"),
        "rows": rows,
    }
