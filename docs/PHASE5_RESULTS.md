# Phase 5: race engineering view

Completed 2026-10-22 in `E:\Personal project\F1 RaceOs`.

RaceOS now includes replay-synchronized tyre/stint state, observed weather,
and issued race-control messages. The existing track layout, timing tower,
and single focused driver panel are preserved. DRS/Overtake statistics remain
removed; historical race-control messages are displayed as issued.

## Driver tyres and pit visits

The selected driver panel shows compound, tyre age in completed laps, current
stint, set history, and completed recorded pit-lane visits. A visit in progress
shows **In pit lane**. Data comes from the already-loaded per-driver lap tables;
there is no additional full-session telemetry import.

The prepared tyre life field describes age at the end of a lap. RaceOS subtracts
one while that lap is uncompleted, retaining prior laps when a used set is
fitted. Age changes at completion and is not interpreted as physical wear.
Compound/stint metadata is available from the recorded lap start, or pit exit
when that is later. The next set is not shown while waiting for that exit.
Generated retirement laps do not introduce tyre information.

Pit visits count matched entry/exit timestamps since the replay window began.
An initial garage exit without a recorded entry does not count as a completed
visit. Duplicate events count once. A visit does not prove that a stationary
stop or tyre change occurred, so the UI labels the count **Pit visits**.
Missing metadata stays unknown. In the pit lane, the old set remains the last
observed set until the recorded exit establishes the next set.

## Session conditions

Optional `weather.json` and `rcm.json` files load through the existing compressed
cache. Weather relative times use the session's shared UTC origin. Message
issue times are UTC dates; naive source dates are interpreted as UTC as in the
other prepared source dates. Only records at or before the replay clock are
returned. Up to 50 most recent messages are returned, newest first; source order
breaks equal-time ties deterministically. Pre-start messages already issued are
valid past information and remain available.

Weather displays track/air temperature, rainfall report, wind speed in m/s,
and wind direction. It is an observation rather than a forecast. Reports older
than 120 replay seconds are marked **Older report**. Missing measurements stay
unknown; no weather values or flags are extrapolated. Race-control messages are
shown as issued, including their scope/driver/sector when supplied. A local
sector flag is not promoted to a current whole-track condition.

Missing, invalid, or unreachable optional files do not fail the main replay.
Failures are marked unavailable and can retry after 60 wall-clock seconds.
Backward seeking rebuilds the earlier tyre, pit, weather, and message state.
These are logical event-time availability rules; original broadcast delivery
latency is unavailable from the prepared files.

## Main modules

- `src/raceos/engineering.py`: deterministic tyre state and conditions filtering.
- `src/raceos/providers/tracinginsights.py`: metadata normalization and optional files.
- `src/raceos/remote_replay.py`: shared-clock engineering frames.
- `src/raceos/replay.py`: tyre, weather, and message response contracts.
- `frontend/src/components/TyreStint.tsx`: selected-driver tyre details.
- `frontend/src/components/SessionConditions.tsx`: observed weather and issued messages.

All downloaded files, browser profiles, logs, test temporary files, and evidence
stay under the project on E:. The remote cache remains capped at 200 MiB. The
legacy SQLite archive and prior data have not been removed or reimported.

## Validation

- 104 Python tests passed, including pit-entry/exit boundaries, reused tyre age,
  generated retirement laps, missing data, future-message filtering, stale
  weather, same-time message order, and backward seeking.
- 10 frontend tests passed; TypeScript and the production build passed.
- 19 real-data browser scenarios passed in installed headless Edge. New checks
  compare tyres, weather, and messages to the same qualifying/race frame; verify
  a real pit exit; recover after missing optional data; and inspect desktop/mobile
  layouts. No JavaScript errors or horizontal overflow were reported.
- Real 2022 Monza metadata was checked at six times from start through finish.
  Norris's first pit exit is at replay second 3112.967. Just before it, the last
  observed set is Medium, stint 1, and the visit is still in progress. At exit it
  becomes used Soft, stint 2, with two prior completed tyre laps and one completed
  pit visit. The end-of-race count is two visits. All returned observations and
  messages are at or before the clock.

Evidence: `data/phase5-validation.json`, `data/remote-replay-browser.json`,
`data/remote-replay-dashboard.png`, and `data/remote-replay-mobile.png`.

Source definitions: [TracingInsights data reference](https://github.com/TracingInsights/2026/blob/main/DATA_REFERENCE.md).

Phase 6 performance analysis remains separate work and has not been started.
