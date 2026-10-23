# RaceOS roadmap

RaceOS will accept motorsport data through provider adapters, validate and retain
it, reconstruct session state, calculate engineering metrics, and expose the
results through an API and engineering interface.

| Phase | Scope                           | Acceptance                                                                                                             |
| ----- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1     | OpenF1 + FastF1 ingestion proof | Real drivers, laps, selected-driver telemetry, provenance, coverage report, offline repeat                             |
| 2     | Data storage and backend        | SQLite, versioned records, repeatable imports, session/driver/lap/telemetry API endpoints                              |
| 3     | Telemetry interface             | Session selection, driver/lap selection, synchronized telemetry charts and sample inspection                           |
| 4     | Historical replay               | Virtual clock, playback speed, deterministic seeking, information availability rules                                   |
| 5     | Race engineering view           | Timing, tyres/stints, weather, and race control sharing the replay clock; track map moved into Phase 4 at user request |
| 6     | Performance analysis            | Defined and validated driver/lap comparisons, pace deltas, throttle/braking percentages, estimates                     |
| 7     | Platform maturity               | System/data health, automated checks, deployment, optional live ingestion                                              |

The backend begins as one Python application with separate modules. FastAPI,
SQLite, and React/TypeScript enter in their respective phases. PostgreSQL,
Timescale, Kafka, and separate services require demonstrated needs before adoption.

Future modules include Strategy Lab, CarTwin, Virtual Sensors, ML,
Radio2Reaction, and an evidence-grounded engineering AI copilot. Other motorsport,
simulator, and synthetic data sources should fit the adapter boundary.

Design rules:

- Preserve source data, units, provenance, missing values, and quality flags.
- Separate provider measurements from derived calculations and model predictions.
- Use UTC timestamps; distinguish event time from information availability time.
- Replay and later strategy evaluation must hide future lap/stint results.
- Calculate time-based percentages using elapsed time, not sample counts.
- Label estimates and avoid treating stint pace trends as isolated tyre wear.

Phases 1 and 2 are complete. Phase 2 passed automated and real-data HTTP verification.
Phase 3 is complete. The dashboard and real-data browser checks passed.
Phase 4 is complete, including the user-requested animated track view.
See `PHASE4_RESULTS.md`. Phase 5 was approved on 2026-10-22 and is complete.
See `PHASE5_RESULTS.md`. Phase 6 was approved on 2026-10-22; its completed-lap
comparison milestone is complete. See `PHASE6_RESULTS.md`. The user approved the distance overlay and local Phase 7 setup on 2026-10-22.
GitHub upload is deferred until the local project is finished.

## Current source choice

After Phase 3, the user selected FastF1 as the sole active source. Ingestion, API
queries, and the dashboard now use FastF1 only. The earlier OpenF1 pilot remains
archived as historical evidence; it is not a runtime fallback. See
`FASTF1_UPDATE.md` and `CODE_GUIDE.md`. The later Phase 4 update imports cached position and car streams for the full
20-driver grids in the two local Monza qualifying sessions.

## Remote loading update

The user later selected TracingInsights prepared files for normal replay, to
reduce disk usage and whole-session processing. RaceOS now uses a year/event/
race-or-qualifying picker, lazy lap downloads, and a 200 MiB compressed cache.
The FastF1/SQLite archive remains a reference path. See `TRACINGINSIGHTS_UPDATE.md`.
This source and loading change remains within the historical replay work.

## Phase 5: race engineering

The selected driver now has compound, completed tyre age, current stint, set
history, and recorded pit-lane visits. Weather observations and issued race
control messages share the same replay clock. New tyres are revealed only after
the recorded pit exit; backward seeking restores earlier tyre and message state.
Optional missing files do not prevent track replay. All new files use the
existing bounded cache on E:. See `PHASE5_RESULTS.md` for validation and limits.

## Phase 6: completed-lap comparison milestone

Completed: same-session driver/lap selection, recorded lap and sector deltas,
time-weighted full-throttle/braking percentages with coverage, and replay-clock
availability checks. Distance-aligned track overlays are now implemented with approximate labels,
local gains/losses, input inspection, and missing-data gaps. Advanced
estimates remain later work. No tyre-degradation or strategy model is claimed.

## Phase 7: local platform setup

The local milestone adds `python run.py`, locked installation/build steps,
fresh-start browser validation, Git initialization, and a GitHub Actions workflow.
See `PHASE7_RESULTS.md`. Hosting/deployment and live ingestion remain optional
future work; no repository has been uploaded and no hosted app is claimed.
