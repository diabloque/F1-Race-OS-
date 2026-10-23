# Focused-driver interface and race replay

Completed 20 October 2026 after Phase 4, at the user's request.

## Interface

The session-driver list and the duplicate telemetry strip/overview were replaced
by `DriverPanel.tsx`. One selected driver has speed, gear, RPM, DRS, throttle,
brake, current lap, and best completed lap in a single sidebar. The existing
Session/Driver/Lap controls still allow following anyone in the imported field.

Throttle is shown once with a 0-100 pedal meter and a released/full explanation.
Brake is shown once as Applied/Released, with a two-state indicator and a note
that braking pressure is unavailable. Missing and out-of-range inputs stay unknown.

The UI maps DRS 10/12/14 to Open, 0/1/8 to Closed, and missing/unmapped codes to
Unknown. FastF1 describes code 8 as eligibility before activation and 14 as active;
its descriptions are best-effort interpretations. Original codes remain in
SQLite and the telemetry API. Reference:
[FastF1 3.8.3 channel definitions](https://github.com/theOehrly/Fast-F1/blob/v3.8.3/fastf1/_api.py).

The circuit rendering, coordinate projection, and past input trail are retained.
Only the selected driver's label is always visible. Other labels appear on hover
or keyboard focus, or via Show all driver labels. Selected car only hides other
markers for crowded race moments. Selected markers draw last so they remain
visible above traffic. These controls do not move or invent car positions.

## Real race data

The archive now includes **2022 Monza Race**, with all 20 drivers. Choose
**2022 - Monza - Race** in the Session menu and click Play. The existing 2024
and 2025 Monza qualifying sessions remain available.

The 2025 and 2024 race endpoints returned HTTP 401 from the primary feed and
404 from the mirror when checked. The 2022 race was available from FastF1's
public mirror. It was downloaded through FastF1, then all-driver replay was
prepared from the resulting offline cache. No source adapter was added.

`prepare-replay` now accepts optional `--year`, `--location`, and `--session`
filters so adding one race does not reprocess every stored qualifying session.
Missing provider timing data produces a readable error instead of a traceback.

| Active FastF1 records after this update |     Count |
| --------------------------------------- | --------: |
| Sessions                                |         3 |
| Driver/session records                  |        60 |
| Laps                                    |     1,562 |
| Car samples                             | 1,359,520 |
| Position samples                        | 1,398,320 |

This is recorded historical race playback. It does not calculate race standings,
strategy, tyre state, or other Phase 5 modules.

## Validation and local files

- 68 Python tests pass, including separate original position timestamps and lap ends.
- 11 frontend tests pass, including the DRS state mapping and unknown codes.
- TypeScript checking and the production build pass.
- 12 real-data browser scenarios pass with no JavaScript errors: unique readouts,
  focused-driver details, label controls, unchanged outline under display toggles,
  qualifying/race playback, timing boundaries, seeks, errors, and mobile layout.
- Desktop and mobile race screenshots were visually reviewed.

Evidence: `data/focused-replay-browser.json`, `data/focused-replay-dashboard.png`,
`data/focused-replay-mobile.png`. Ingest/preparation logs are under `data/race-*`.
Backups of the prior source and database are in `data/focused-replay-backup`.
All new project files, cache, logs, and test/browser temporary files are on E:.
