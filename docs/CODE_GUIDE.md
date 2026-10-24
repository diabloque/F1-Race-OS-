# How RaceOS works

The normal dashboard now reads TracingInsights prepared files over HTTPS. It
keeps a limited compressed cache and reconstructs replay frames in memory.
The earlier FastF1/SQLite path remains available for reference and comparison.

## Follow one remote sample

1. `SessionControls.tsx` asks the backend for a year's completed races and qualifying.
2. `POST /api/remote/open` loads driver and lap metadata and validates a circuit outline.
3. `providers/tracinginsights.py` builds one UTC origin from lap-start dates and relative times.
4. `remote_replay.py` identifies each car's active lap at the requested replay time.
5. `remote_cache.py` reads that lap's compressed cached JSON or requests it from a CDN.
6. The adapter normalizes the prepared columns without changing their values.
7. Replay returns the most recent sample at or before the clock and completed lap results.
8. `useReplay.ts` updates the map, inputs, and lap information together.

Only current laps are required for a frame. The next lap is buffered when its
boundary approaches. Files can contain future samples internally, but the API
never includes them before their timestamp. The static outline contains
geometry only and may use a complete reference lap.

## Backend modules

| File under `src/raceos/`       | Main job                                                                                      |
| ------------------------------ | --------------------------------------------------------------------------------------------- |
| `providers/tracinginsights.py` | Calendar selection, driver/lap metadata, shared UTC origin, prepared sample conversion        |
| `remote_cache.py`              | HTTPS JSON, fallback URL, compression, bounded disk/memory caches, concurrent request control |
| `remote_replay.py`             | Remote catalog, circuit outline, shared-clock frames, selected-lap quality                    |
| `api.py`                       | HTTP routes, validation, local frontend serving                                               |
| `replay.py`                    | Legacy SQLite replay and shared conservative lap-completion rules                             |
| `contracts.py`                 | Record types and bundle validation                                                            |
| `storage.py`                   | Legacy transactional SQLite archive                                                           |
| `providers/fastf1.py`          | Legacy original FastF1 ingestion                                                              |
| `prepare.py`, `cli.py`         | Reference imports and starting the local server                                               |
| `data.py`, `report.py`         | UTC/numeric helpers, quality summaries, import reports                                        |

The adapter reads the same public prepared files used by tif1 directly. No tif1
package installation is required. Requests already exists in the environment and
is declared as a direct runtime dependency. There is no new database service.

## Storage boundaries

`data/remote/cache` holds gzip-compressed JSON, capped at 200 MiB. Old downloads
are evicted only from this exact cache directory. A hashed key determines each
filename. Saved-session bookmarks live separately in `data/remote/sessions.json`.

Decoded source JSON is bounded to 48 cache entries. Normalized telemetry is
bounded to 40,000 samples. Session metadata is bounded to four open sessions in
memory. An HTTP download is limited to 20 MiB. Network reads use timeouts and
fallback URLs; TLS verification uses system certificates. Cache locks prevent
concurrent requests for the same file from downloading it twice.

Old FastF1 files, SQLite records, and backups are retained outside these limits.
The dashboard does not import remote telemetry into those old tables.

## Frontend modules

| File under `frontend/src/`       | Main job                                                       |
| -------------------------------- | -------------------------------------------------------------- |
| `App.tsx`                        | Navigation and page layout                                     |
| `components/SessionControls.tsx` | One bar for year, Grand Prix, session opening, driver, and lap |
| `hooks/useArchive.ts`            | Saved remote bookmarks, health, refresh                        |
| `hooks/useReplay.ts`             | Playback clock, buffering, seeking, cancellation               |
| `replay.ts`, `types.ts`          | Record shapes, map projection, colors, clock arithmetic        |
| `api.ts`                         | GET/POST JSON and errors, with browser caching disabled        |
| `components/TrackView.tsx`       | Circuit, selectable cars, trail, color key, label controls     |
| `components/DriverPanel.tsx`     | One selected driver and unique telemetry readouts              |
| `components/ReplayControls.tsx`  | Playback controls                                              |
| `styles.css`                     | Responsive layout and presentation                             |

React effects load records after selection changes. AbortController prevents
old responses from overwriting a newer selection. Each playback request is
awaited before another is scheduled. Long network waits show buffering and are
excluded from playback progression. Backward seeks clear the previous frame
immediately, then reconstruct the requested moment.

## Meaning of prepared data

TracingInsights applies interpolation and derived calculations upstream. Replay
labels this provenance rather than presenting these as independent raw samples.
Lap-start dates are serialized UTC from FastF1; the adapter localizes dates that
omit their zone, and checks agreement between all available clock origins.

The prepared DRS field is binary. It is normalized to `drs_open`; `drs_code`
remains null. Legacy FastF1 codes retain their separate mapping. This prevents
prepared 1 (open) from being confused with raw FastF1 code 1 (closed).

Missing prepared values stay null. Values more than one second old stay unknown.
Replay adds no interpolation or extrapolation. The separate distance comparison
interpolates time/position within supported intervals and labels this approximate.
Brake pressure and OnTrack status are not inferred. The prepared source lacks the original location
status flag, so valid cars are described as located rather than known OnTrack.

Lap results use the later of observed completion and start-plus-duration when
both exist. Seeking the same timestamp reconstructs the same state while the
source snapshot is unchanged. Source corrections can change data after a cache
refresh; live information-delivery timestamps are unavailable.

## Common edits

| Change                          | Start here                                   |
| ------------------------------- | -------------------------------------------- |
| Open another session            | Use the Load session picker                  |
| Change disk cache size          | `remote_cache.py` - `RemoteCache.max_bytes`  |
| Change prefetch window          | `remote_replay.py` - boundary threshold      |
| Change freshness tolerance      | `replay.py` - `FRESH_SECONDS`                |
| Add a prepared data field       | Adapter mapping, contracts/types, then panel |
| Change readouts or explanations | `DriverPanel.tsx`                            |
| Change colors or projection     | `TrackView.tsx`, `replay.ts`                 |
| Inspect original provider data  | Legacy FastF1 CLI commands and archive APIs  |

Black formats Python; Prettier formats the frontend. The README lists builds and
tests. Timing, tyres, weather, and completed-lap comparison are implemented below.
Strategy models remain future work.

## Race timing tower

Before any observed crossing, `race_timing.py` displays the starting grid.
`TracingInsights.starting_grid` reads Jolpica's small race metadata response through
the same bounded cache. It checks year, round, date, car number, and driver code,
and reads only the grid field rather than finishing positions. Optional grid
failures leave positions unknown without blocking replay. The API's `basis`
switches from `starting_grid` to `sector_crossings` at the first observed line.
Afterward, `race_timing.py` orders cars using only sector crossings at or before
the replay clock. It compares the same lap and sector to calculate each gap. Generated
retirement laps do not count as real timing observations. Missing comparisons
stay null, and every seek rebuilds the standings without mutable history.
`RemoteReplay.snapshot` includes the result as `race_timing`; qualifying returns
null. `components/RaceTiming.tsx` renders the table and changes the focused
driver when clicked. DRS/Overtake statistics are no longer rendered.

## Phase 5: engineering state

`providers/tracinginsights.py` normalizes compound, tyre life, stint, and pit
timestamps alongside each lap. Its `context` method reads small optional
`weather.json` and `rcm.json` files through the bounded cache. Transient failures
can retry after 60 seconds of wall time; missing or invalid files are marked.

`engineering.py` calculates `tyre_state` from observed lap starts and pit exits.
Tyre life is the reported end-of-lap count: subtract one for the current,
uncompleted lap. Used sets retain prior completed laps. Pit visits are paired
entry/exit events, not inferred from the stint number. `environment` returns
only weather observations and messages at or before the replay clock.

`remote_replay.py` attaches tyres to each car and conditions to the frame.
`replay.py` validates the response models. `components/TyreStint.tsx` renders
one tyre panel for the selected driver; `components/SessionConditions.tsx`
renders weather and race-control messages below the timing area. These panels
use the same frame as the map and inputs. See `PHASE5_RESULTS.md` for semantics.

## Phase 6: completed-lap comparisons

`analysis.py` implements `PerformanceAnalysis`. `choices` returns timed laps
with valid start/end records completed at the requested clock; generated laps
are excluded. `compare` validates both selections before loading either file.
The API routes are `/analysis/laps` and `/analysis/compare` under a session ID.
The existing remote adapter preserves `s1`, `s2`, and `s3` as `sector_times_s`.

`input_metrics` examines intervals from one sample to the next. It holds the
left-hand input state only when the next timestamp is at most one second away.
Duplicate times have no duration. It does not extrapolate the tail, cross large
gaps, include invalid throttle readings, or turn unknown brakes into released
brakes. Each channel reports active seconds, known seconds, coverage of the lap
window, and active percentage of known time. Full throttle starts at 99%.

`components/PerformanceAnalysis.tsx` renders the comparison selectors, timing
table, and input meters inside the race workspace. It refreshes choices when
observed lap completions change. It also filters existing choices/results against the current
clock while requests load, so a backward seek cannot expose future results.
Compared selections are pinned until changed. The code uses ordinary functions,
React state/effects, HTTP JSON, and existing bounded lap caching.

## Distance comparison and setup

`distance_comparison.py` filters each selected lap to its recorded start/end,
requires monotonic distance and both endpoints, then normalizes its observed
span to 0-1. It produces 201 equally spaced progress points. Time and position
are interpolated only across consecutive valid samples at most one second apart.
Inputs hold the preceding observation. Missing distance/time/position breaks
supported segments. No endpoint extrapolation or official-time correction is used.

`LapComparisonTrack.tsx` draws the existing circuit and reference lap positions.
B minus A is the cumulative time difference. The change between adjacent
progress points controls local gain/loss colors, with a 0.010 s neutral tolerance.
The distance slider supports keyboard and touch inspection alongside pointer hover.

`run.py` uses standard Python modules to create `.venv`, install the Python lock,
run `npm ci`, build changed frontend files, and start the API/dashboard. Hashes in
ignored `data/setup.json` avoid reinstalling or rebuilding on every launch.
All child processes use project-local dependency caches and temporary folders.
`.github/workflows/checks.yml` repeats setup/tests on a clean Linux runner.
`frontend/scripts/smoke-browser.mjs` uses an isolated empty database and an
intercepted empty schedule, so CI smoke checks do not depend on remote F1 data.
The larger `verify-browser.mjs` remains an optional real-data integration check
requiring the locally prepared bookmarks and Phase 5 verification fixture.

## Readability review

The 2026-10-22 review simplified the active comparison and engineering code.
`analysis.py` now validates eligibility with early returns and builds completed
lap choices with ordinary loops. Its input totals use named `active_s` and
`known_s` fields rather than positional list entries. `distance_comparison.py`
names the segment count, explains continuity regions, and expands interpolation
and segment checks. Tyre age uses explicit steps in `engineering.py`.

The main frontend hooks declare each state separately. Lap comparison selects
default drivers and laps through explicit conditions, checks both completion
times, and builds its summary with a named quicker lap. The track overlay uses
ordinary conditions for its colors and a small brake label helper. The unused
frontend pagination helper and Page type were removed. Existing tested chart
utilities and the legacy archive remain available.

These changes retain the API fields, time rules, cache bounds, and UI behavior.
125 Python tests, 10 frontend tests, 24 real-data browser scenarios, and the
production build passed after the review. The broader explanation is in
`RACEOS_PROJECT_GUIDE.md` and the accompanying Word document. Necessary concepts
such as cancellation, locks, binary search, and data validation remain in place
and are explained rather than weakened.

## Unified race workspace

On 2026-10-23, track replay and lap comparison were combined under one
`Race workspace` navigation entry. `App.tsx` mounts `ReplayWorkspace` and
`PerformanceAnalysis` with the same `useReplay` result and session ID. The
comparison's separate clock panel was removed, so there is one session bar,
one timeline, and one UTC readout. Section links scroll within the page without
pausing playback or resetting the session. Existing completion checks still
hide future comparisons on backward seeks. Session library is the other navigation entry. The user later requested removal
of the Data quality screen; its components and unused presentation code were
removed while backend telemetry validation remains active. See `UNIFIED_WORKSPACE.md`.

## Prepared lap boundaries and unavailable positions

Some prepared lap files include a sample just before their lap begins. For
example, the 2026 Monaco race's NOR lap 34 begins at -0.043 seconds. The loader
checks chronological order first, then excludes negative lap-relative times.
It preserves the timestamps and row indices of retained samples; it does not
move earlier samples to zero. Missing, non-finite, and reversed timestamps still
raise a data error.

Circuit selection tries different drivers within the existing six-file limit.
If usable telemetry exists but no complete outline can be built, the track
response contains an empty points list and an explanatory note. The dashboard
clears the old circuit and displays that note, while the shared replay clock,
driver inputs, timing, and completed-lap analysis can still work with the data
available. It does not invent car positions or borrow another event's map.

Validation: 134 backend tests, 10 frontend tests, the production build, and the
isolated browser smoke check passed. The affected real Monaco session opens
successfully and returns replay frames without exposing future samples. Live
browser results and screenshots are under `data/` on E:.
