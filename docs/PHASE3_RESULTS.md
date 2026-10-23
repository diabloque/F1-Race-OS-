# Phase 3 completion

The React/TypeScript RaceOS dashboard now opens at the main server URL (`/`).
The FastAPI documentation remains at `/docs`.

## Implemented

- Stored session, provider, driver, and lap selection, plus a session library.
- Speed, throttle, brake, gear, and RPM traces on a shared elapsed-time axis.
- Linked sample values, hover/click pinning, a time slider, and keyboard sample steps.
- Lap directory, source quality report, and explicit flags for unexpected measurements.
- Loading, missing-telemetry, and API-error states with retry.
- Same-origin compiled frontend hosting through the existing Python server.

## Real data

The archive includes 2025 Monza qualifying for Norris and Verstappen, plus 2024
Monza qualifying for Norris, from OpenF1 and FastF1. Each source remains separate.

| Stored records | Count |
|---|---:|
| sessions | 2 |
| session_sources | 4 |
| drivers | 80 |
| laps | 1,182 |
| telemetry | 104,620 |
| imports | 6 |

## Verification

- 54 backend regression tests passed.
- 6 frontend data/plotting checks passed.
- TypeScript checking and production Vite build passed.
- 9 real-data headless browser scenarios passed:
  - Homepage loads real Monza telemetry
  - Lap selection and keyboard sample inspection match API measurements
  - Synchronized hover, pinning, and engine channels work
  - Source selection and switching to real Verstappen telemetry work
  - Drivers without telemetry clear old traces and show an honest empty state
  - Session library and selection reset dependent data
  - API errors are visible and retry restores data
  - Repeated session, source, driver, and lap selections preserve displayed data
  - Desktop and mobile layouts render without horizontal overflow
- No browser JavaScript errors were observed.
- Desktop and mobile screenshots were visually reviewed; chart axis labels use fixed-size text for readability.

The in-app browser connection failed during bootstrap, so browser verification used
an independent headless Edge browser. The original user-started server was left running;
the verification servers were stopped after their checks.

## Run

Stop an older running server with Ctrl+C, then run `python -m raceos serve`.
Open `http://127.0.0.1:8000/`. The frontend is already built locally.

Screenshots: `data/phase3-dashboard.png` and `data/phase3-mobile.png`.
Browser evidence: `data/phase3-browser.json`; backend results: `data/phase3-tests.xml`.

## Next phase

Phase 4 adds historical replay and requires user approval.
