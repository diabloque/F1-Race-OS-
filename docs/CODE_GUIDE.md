# How RaceOS works

RaceOS has a Python backend and a React frontend. The backend reads prepared
TracingInsights JSON files and builds replay frames. The frontend requests those
frames and displays the circuit, driver inputs, timing, conditions, and comparisons.
The original FastF1/SQLite tools remain available for archive work.

## Follow one replay frame

1. `SessionControls.tsx` requests the available events for a year.
2. `POST /api/remote/open` loads driver/lap metadata and checks the circuit outline.
3. `providers/tracinginsights.py` combines lap-start dates and relative sample times into UTC.
4. `useReplay.ts` sends a session ID, driver number, and replay timestamp to the API.
5. `remote_replay.py` finds each car's active lap and loads its prepared samples.
6. `remote_cache.py` reuses compressed JSON or downloads the required file over HTTPS.
7. The backend selects the latest sample at or before the requested time.
8. The response updates the track, selected driver, timings, tyres, and conditions together.

Only active laps are required. The next lap is buffered near its boundary. Files
can contain future observations internally, but replay responses never reveal
those observations before their timestamps. The static outline is geometry only
and may come from a complete reference lap.

## Backend files

Files below are under `src/raceos/`.

| File | Responsibility |
| --- | --- |
| `api.py` | HTTP routes, input validation, and serving the compiled frontend |
| `providers/tracinginsights.py` | Events, session metadata, shared UTC origin, prepared sample conversion |
| `remote_cache.py` | HTTPS requests, compression, limits, and download coordination |
| `remote_replay.py` | Circuit outline, replay catalog, shared-clock frames, quality summaries |
| `race_timing.py` | Starting grid and gaps at matching recorded sector crossings |
| `engineering.py` | Tyres, pit visits, weather, and issued race-control messages |
| `analysis.py` | Completed-lap selection, timing differences, time-weighted input percentages |
| `distance_comparison.py` | Approximate distance alignment and local gain/loss |
| `data.py`, `contracts.py` | UTC/numeric helpers, data shapes, and validation |
| `replay.py` | Shared response models, lap-completion rules, and SQLite replay |
| `storage.py` | Transactional SQLite archive and queries |
| `providers/fastf1.py`, `prepare.py`, `report.py` | Original FastF1 import, cached archive preparation, reports |
| `cli.py`, `__main__.py` | Command-line entry point and server startup |

`run.py` at the repository root creates the environment, installs locked
packages, builds the frontend, and starts the local server. Setup fingerprints
in ignored `data/setup.json` avoid repeating unchanged work.

## Frontend files

Files below are under `frontend/src/`.

| File | Responsibility |
| --- | --- |
| `App.tsx` | Navigation, selected session, and the two workspace screens |
| `hooks/useArchive.ts` | Saved session bookmarks, backend health, and refresh |
| `hooks/useReplay.ts` | Playback clock, seeking, buffering, and request cancellation |
| `components/SessionControls.tsx` | Year, event, session, followed driver, and lap selection |
| `components/ReplayWorkspace.tsx` | Track, timing, conditions, and completed-lap layout |
| `components/TrackView.tsx` | Selectable cars, track trail, legend, and label controls |
| `components/DriverPanel.tsx`, `TyreStint.tsx` | The selected driver's telemetry and tyres |
| `components/ReplayControls.tsx` | Play, pause, speed, steps, and timeline |
| `components/RaceTiming.tsx`, `SessionConditions.tsx` | Race order, gaps, weather, and messages |
| `components/PerformanceAnalysis.tsx` | Completed-lap choices, timing table, and input comparison |
| `components/LapComparisonTrack.tsx` | Distance-aligned circuit overlay and inspection slider |
| `components/Common.tsx` | Shared icons and empty-state presentation |
| `api.ts`, `types.ts`, `data.ts` | JSON requests, record shapes, and lap-time formatting |
| `replay.ts` | Replay shapes, clock math, projection, colors, and safe trail segments |
| `styles.css` | Desktop/mobile layout and presentation |

The race workspace mounts replay and comparison with the same session and
`useReplay` result. Section links scroll without resetting playback. Session
library is the second screen. There is no separate data-quality screen.

## Rules that matter

Replay holds the latest recorded sample. Values over one second old remain
unknown, and no car position is extrapolated. TracingInsights may already have
interpolated positions upstream; the UI labels the source as prepared data.

Lap results appear only after conservative completion checks. Comparison choices
and results are also filtered against the current clock while requests load,
so backward seeking hides unfinished laps immediately.

Before the first sector observation, race timing shows the starting grid from
small cached Jolpica metadata. Only grid fields are read; finishing positions
are not used. After timing starts, order uses observed sector progress. Gaps
compare the same lap and sector for both cars. Missing comparisons stay unknown.
See [race timing](RACE_TIMING.md) for the detailed rules.

Tyre age counts completed laps. Pit visits require matched recorded entry/exit
pairs and do not prove a tyre change. Weather and race-control messages must
already have occurred at the replay clock. Weather older than 120 seconds is
marked stale. Optional data failures do not stop replay.

Input comparison holds each reading until the next timestamp, for intervals no
longer than one second. Full throttle starts at 99%. Percentages use known time;
unknown inputs and longer gaps are excluded. It does not extrapolate the tail.

Distance comparison normalizes both recorded distance spans to 0-1 and uses
201 inspection points. It interpolates time/position only across supported
intervals, holds the preceding input, and leaves missing segments disconnected.
B minus A is the time delta. Local colors use a 0.010-second neutral tolerance.
This is approximate and does not establish identical physical racing lines.

Track trails join adjacent valid samples only. They reject gaps over one second,
non-increasing timestamps, and unusually large position jumps. The movement
bound is four times the reference lap's average movement plus a noise allowance.
This display filter leaves the original coordinates and inputs unchanged.

## Storage and asynchronous work

The compressed cache under `data/remote/cache` is capped at 200 MiB. Individual
HTTP downloads are limited to 20 MiB. Decoded JSON is bounded to 48 entries,
normalized telemetry to 40,000 samples, and session metadata to four sessions.
Bookmarks live separately in `data/remote/sessions.json`. Cache eviction touches
only its own files. Old archives and backups stay outside this cache.

The frontend uses `AbortController` so stale requests cannot replace newer
selections. Playback awaits each snapshot before scheduling another. Cache locks
prevent duplicate downloads, and a six-worker pool limits concurrent requests.
These safeguards are necessary to keep timing and storage correct.

## Reading and editing the code

Start with `App.tsx`, then follow `useReplay.ts` into the corresponding route in
`api.py` and frame building in `remote_replay.py`. These use ordinary components,
functions, loops, dictionaries, and named variables. Keep explanations next to
rules whose purpose is not obvious, especially timing and missing-data checks.

Black formats Python and Prettier formats the frontend. TypeScript checks types
and rejects unused local variables/parameters. The old chart helpers, unused
icons/styles, phase reports, and one-off phase script have been removed. Earlier
versions remain in Git history. The current explanation is in the
[project guide](RACEOS_PROJECT_GUIDE.md) and its Word copy.

The [README](../README.md) lists setup and checks. `tests/` covers Python behavior;
`frontend/tests/` covers time formatting, projection, playback math, colors, and
trail continuity. The offline smoke check verifies fresh startup. The optional
online browser suite opens its required Monza fixtures when needed and checks
real sessions; it no longer depends on a local phase-validation report.
