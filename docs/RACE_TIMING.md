# Race timing tower

The dashboard now shows a race timing tower below the circuit instead of the
DRS/Overtake statistic. The track layout and single focused driver input panel
are preserved. The quality table also omits the DRS row. Original source fields
and the existing archive remain intact.

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
a dash. Cars without any observed crossings are unranked, rather than assigned
future grid or finishing positions. Some first-lap sectors are missing upstream;
the display waits for the first available line instead of inventing a time.

Generated retirement laps are excluded from timing progress. The tower does
not infer DNF, pit status, or a lap deficit from missing data. Gap values remain
seconds at the driver's last observed line, including for cars with older data.
The lap/sector label indicates that observation. The tower appears for Race
sessions; qualifying keeps its existing completed-lap view.

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
