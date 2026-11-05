# Race timing tower

The race timing tower sits below the circuit. It uses the same replay clock
as the track and selected-driver panel.

The tower displays each driver's position in the timing order, interval to the
car ahead, and gap to the leader, in seconds. Selecting a driver follows that car
without changing the replay clock. The focused row is highlighted.

## Meaning and limits

TracingInsights lap tables contain sector crossing times (`s1T`, `s2T`) and lap
completion times (`sesT`). RaceOS uses only crossings at or before the replay
clock. Each row shows its last observed lap and sector. Order updates at these
lines; overtakes between lines appear once subsequent timing establishes them.
These are timing-line standings, not a continuously measured live leaderboard or
an official final classification with penalties.

Gaps compare each driver's last observed lap/sector with the same lap/sector
for the leader or preceding car. Different sector timestamps are never directly
subtracted. When there is no nonnegative recorded comparison, the display shows
a dash. Once sector timing begins, cars without any observed crossings are
unranked rather than assigned finishing positions. Some first-lap sectors are missing upstream; the display
uses the first available line instead of inventing a time.

Generated retirement laps are excluded from timing progress. The tower does
not infer DNF, pit status, or a lap deficit from missing data. Gap values remain
seconds at the driver's last observed line, including for cars with older data.
The lap/sector label indicates that observation. The tower appears for Race
sessions; qualifying keeps its existing completed-lap view.

## Starting grid

Before any recorded sector crossing, the tower shows the starting grid, labels
rows `Grid P1`, `Grid P2`, and so on, and leaves Interval and Gap blank. Pole
position is not labelled Leader. A zero grid slot is shown as `No grid slot`;
this alone does not establish pit-lane or DNS status. Missing entries remain
unranked.

The grid comes from the `grid` field in Jolpica's small race metadata response.
Year, round, race date, car number, and driver code must match the selected
TracingInsights session. Finishing positions, lap results, and retirement status
from that response are not used. The file uses the existing compressed cache
on E: and its 200 MiB limit; qualifying does not request it. A missing or failed
grid response does not block the other session data.

At the first observed crossing the tower switches to recorded race order.
Drivers with no observation retain their grid label with `awaiting timing`,
while their race position remains unknown. Gap calculations still require
matching recorded lines for both cars. Updates can occur within Lap 1 when
sector data is available. Seeking back to the beginning restores grid order and
removes future gaps. Race sessions open at their earliest lap start instead of
a potentially later start for the preferred driver.

Jolpica's field definitions are documented in its
[results endpoint reference](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/results.md).

## Implementation

- `src/raceos/providers/tracinginsights.py` normalizes the sector timestamps.
- `src/raceos/race_timing.py` calculates past-only order and same-line gaps.
- `src/raceos/remote_replay.py` includes the tower in the shared-clock frame.
- `src/raceos/replay.py` defines the validated timing response.
- `frontend/src/components/RaceTiming.tsx` renders the selectable table.

Source definitions: [TracingInsights data reference](https://github.com/TracingInsights/2026/blob/main/DATA_REFERENCE.md).

## Verification

Backend tests cover grid validation, the first-sector transition, same-line gap
calculations, missing timings, and backward seeks. The real-session browser
checks compare all 20 displayed rows with shared-clock API snapshots, check
driver selection without a clock reset, and verify desktop/mobile layouts.

A recorded 2022 Monza example at 150 seconds has LEC, RUS, and VER at the top,
with leader gaps of 0.000, 1.420, and 2.654 seconds. The VER-to-RUS interval is
1.234 seconds. These are prepared historical observations, not live timing.

The 2026 Japan race was also checked: the starting grid begins ANT, RUS, PIA.
Its first available sector line is at 77.588 seconds, before the earliest lap
finish at 95.521 seconds. Available sector lines can update the tower within
Lap 1; missing sector records delay the first update.
