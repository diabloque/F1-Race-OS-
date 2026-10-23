"""Tyres, observed weather, and issued messages at the shared replay clock."""

from raceos.data import number, utc_datetime
from raceos.providers.tracinginsights import date, relative_time
from raceos.storage import timestamp


def tyre_state(laps, at, begin):
    clock, beginning = timestamp(at), timestamp(begin)
    candidates, pit_events = [], set()
    pit_available = any(lap.get("pit_data_available") for lap in laps)
    for lap in laps:
        for field, kind in (("pit_in_utc", "in"), ("pit_out_utc", "out")):
            event = lap.get(field)
            if event and beginning <= event <= clock:
                pit_events.add((event, kind))
        start = lap.get("lap_start_utc")
        if not start or start > clock or lap.get("timing_generated"):
            continue
        available = max(start, lap.get("pit_out_utc") or start)
        if available <= clock:
            candidates.append((available, lap["lap_number"], lap))
    pending, visits = False, 0
    for _, kind in sorted(pit_events):
        if kind == "in":
            pending = True
        elif pending:
            visits += 1
            pending = False
    current = (
        max(candidates, key=lambda item: (item[0], item[1])) if candidates else None
    )
    state = {
        "compound": None,
        "stint": None,
        "age_laps": None,
        "fresh": None,
        "pit_visits": visits if pit_available else None,
        "in_pit": pending if pit_available else None,
        "observed_at_utc": None,
    }
    if current:
        available, _, lap = current
        life = lap.get("tyre_life_laps")
        completed = lap.get("lap_end_utc") is not None and lap["lap_end_utc"] <= clock
        state.update(
            compound=lap.get("compound"),
            stint=lap.get("stint"),
            fresh=lap.get("fresh_tyres"),
            age_laps=(
                max(0, life - (0 if completed else 1)) if life is not None else None
            ),
            observed_at_utc=lap["lap_end_utc"] if completed else available,
        )
    return state


def environment(session, context, at):
    clock = timestamp(at)
    observed = []
    for row in context["weather"]["items"]:
        when = relative_time(session["origin"], row.get("wT"))
        if when and when <= clock:
            observed.append((when, row))
    weather = None
    if observed:
        when, row = max(observed, key=lambda item: item[0])
        age = (at - utc_datetime(when)).total_seconds()
        wind = number(row.get("wWS"))
        direction = number(row.get("wWD"))
        weather = {
            "timestamp_utc": when,
            "age_s": age,
            "stale": age > 120,
            "air_temp_c": number(row.get("wAT")),
            "track_temp_c": number(row.get("wTT")),
            "rainfall": row.get("wR") if isinstance(row.get("wR"), bool) else None,
            "wind_speed_ms": wind if wind is not None and wind >= 0 else None,
            "wind_direction_deg": (
                direction if direction is not None and 0 <= direction <= 360 else None
            ),
        }
    messages = []
    for index, row in enumerate(context["rcm"]["items"]):
        try:
            when = date(row.get("time"))
        except ValueError:
            continue
        message = row.get("msg")
        if (
            when is None
            or when > at
            or not isinstance(message, str)
            or message in ("", "None")
        ):
            continue

        def text(key):
            value = row.get(key)
            return str(value) if value not in (None, "None", "") else None

        messages.append(
            {
                "id": index,
                "timestamp_utc": timestamp(when),
                "message": message,
                "category": text("cat"),
                "flag": text("flag"),
                "scope": text("scope"),
                "sector": text("sector"),
                "driver_number": text("dNum"),
            }
        )
    messages.sort(key=lambda row: (row["timestamp_utc"], row["id"]), reverse=True)
    return {
        "weather": weather,
        "weather_status": context["weather"]["status"],
        "race_control": messages[:50],
        "race_control_status": context["rcm"]["status"],
    }
