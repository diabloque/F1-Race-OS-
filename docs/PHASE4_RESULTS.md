# Phase 4: historical track replay

Completed 20 October 2026. Runtime and package version: 0.4.0.

## Delivered

The telemetry chart panel is replaced with an approximate circuit map made from
actual recorded FastF1 positions. Car markers move with a shared session clock.
Click a car or choose a driver to follow its speed, throttle, brake, gear, RPM,
and original DRS code. The selected driver's already-replayed lap has a colored
throttle/braking/coasting trail.

Playback supports play/pause, 0.25x-16x speed, timeline seeking, ten-second steps,
start/end controls, and lap-start jumps. Changing drivers preserves the session
clock. Changing sessions resets to that session's initial replay point. Playback
starts paused, and stops automatically at the recording's end.

All-driver snapshots use the latest original car and position samples at or
before the replay clock. The streams remain separate. Samples older than one
second become unknown; there is no interpolation or extrapolation. The map
shows only fresh OnTrack positions. Missing speed remains unknown.

Completed and best lap times appear only after completion. If a source finish
and calculated start-plus-duration disagree, the later timestamp is used.
Backward seeking reconstructs the earlier state from SQLite. The replay catalog
contains lap-start jump targets without future durations or results. Historical
archive endpoints and the explicitly labeled full-session quality page retain
complete records for analysis.

## Local data

The existing cached 2024 and 2025 Monza qualifying sessions were prepared in
FastF1 offline mode. No provider downloads were requested. Each session now has
20 imported drivers with car and position streams.

| Active FastF1 records     |   Count |
| ------------------------- | ------: |
| Sessions                  |       2 |
| Driver/session records    |      40 |
| Lap records               |     591 |
| Original car samples      | 697,160 |
| Original position samples | 723,080 |

SQLite schema 2 adds position and track tables and timestamp indexes. Existing
tables and archived OpenF1 records are retained. Legacy imports without a
positions field preserve already-imported positions. FastF1 remains the only
active source.

Project edits, new normalized data, browser profiles/screenshots, preparation
logs, and test/build temporary files are under `E:/Personal project/F1 RaceOs`.
The original source, frontend, tests, documentation, manifests, and a SQLite
backup are in `data/phase4-backup`.

## Verification

- 68 Python tests passed, including schema migration, atomic validation, stable
  sample ordering, exact lap completion boundaries, stale data, trail matching,
  deterministic backward seeks, and replay API validation.
- 10 frontend tests passed, including elapsed-time speed scaling, clock bounds,
  projection geometry, and unknown input colors.
- TypeScript checking and the production Vite build passed.
- 10 real-data browser scenarios passed in installed headless Edge. They cover
  recorded coordinates and inputs, full-grid coverage, backward seeks, pause,
  4x playback, driver changes, completion boundaries, recording end, session
  changes, quality/library navigation, error recovery, and mobile overflow.
- No browser JavaScript errors were recorded. Desktop and mobile screenshots
  were inspected. The running server responds at `/` with version 0.4.0.

Browser evidence is saved in `data/phase4-browser.json`,
`data/phase4-dashboard.png`, and `data/phase4-mobile.png`. Provider preparation
logs are in `data/phase4-prepare.log` and `data/phase4-prepare-errors.log`.

The Python suite reports one existing third-party Starlette/httpx deprecation
warning; all checks pass without adding another dependency.

## Limits and next phase

This replays historical recorded event times. Original live delivery latency is
unavailable. Positions and the circuit outline are approximate broadcast data;
OffTrack is not interpreted as a pit-stop event. The static geometry can use a
complete reference lap, but exposes no future dynamic positions or lap times.
Cars may disappear during position gaps instead of following an invented path.
Driver labels can overlap when several cars are close together.

Phase 5 timing classification, tyres/stints, weather, and race-control modules
have not been implemented. They require the next phase's approval.
