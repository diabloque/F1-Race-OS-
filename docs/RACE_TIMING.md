# Race timing tower

The dashboard now shows a race timing tower below the circuit instead of the
DRS/Overtake statistic. The track layout and single focused driver input panel
are preserved. Original source fields and the existing archive remain intact.

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

## Checks

90 Python tests and 10 frontend tests passed, and the TypeScript production
build passed. Browser verification checks the 20-car timing table against
shared-clock snapshots, positive real race intervals, backward seeking,
driver selection, removed DRS readouts, and desktop/mobile layouts.
`data/race-timing-validation.json` records six checks from the start through
the finish of the 2022 Monza race, including deterministic backward seeking.
Screenshots and browser evidence are saved under `data/remote-replay-*`.

At 150 seconds, the observed top three are LEC, RUS, and VER, with leader gaps
of 0.000, 1.420, and 2.654 seconds. The VER-to-RUS interval is 1.234 seconds.
These examples are from the locally verified prepared data, not live timing.

## Starting grid validation

The updated production build, 147 backend tests, 10 frontend tests, and offline
browser smoke check passed. All 27 real-data browser scenarios passed, including
immediate grid order with blank gaps and no premature Leader label. Tests also
cover the first-sector transition before Lap 1 finishes, backward seeks,
unassigned grid slots, missing grid service responses, incorrect race identity,
and keeping finishing positions out of the replay.

Browser evidence includes `data/starting-grid-desktop.png` and
`data/remote-replay-browser.json` on E:.

The real 2026 Japan race was also verified against the running app: the starting
grid begins ANT, RUS, PIA. Its first available sector line is at 77.588 seconds,
before the earliest first-lap finish at 95.521 seconds. Browser checks confirmed
positive intervals at 90 seconds during Lap 1, restoration of the grid and blank
gaps on rewind, and a mobile layout without overflow or JavaScript errors.
`data/starting-grid-validation.json` records these checks.
