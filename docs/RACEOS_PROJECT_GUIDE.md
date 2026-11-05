# RaceOS Project Guide

**A guide to the application and its implementation**

Updated for Ryan on 5 November 2026

RaceOS is a local Formula 1 engineering workspace for replaying historical races and qualifying sessions. It shows cars moving around a circuit while a selected driver's speed, throttle, braking, gear and engine RPM follow the same recorded moment. It also provides race timing, tyres, weather, race control and completed lap comparisons.

This guide explains what we built, why the main design choices were made, how the code works and how to run and demonstrate it. It is written for someone learning Python, APIs, databases and React. It describes the implemented local version, including the readability review, rather than treating every idea in the original long term plan as finished.

## What you can do

- Open a published historical Race or Qualifying session through one session selection bar.
- Play, pause, change speed, move backward or forward and jump to a driver's lap.
- Follow one driver while keeping the other cars visible, or display only the selected car.
- Inspect race positions and sector based gaps, tyre information, recorded weather and issued race control messages.
- Compare completed laps using timing, input percentages and an approximate circuit overlay.
- Use track replay and completed lap comparison in one Race workspace with a shared session and timeline.

## The current source choice

The normal dashboard reads prepared JSON files from TracingInsights. A small cached Jolpica response supplies starting-grid positions for races; its finishing results are not used in replay. The TracingInsights files include data prepared from FastF1 and other sources. FastF1 remains installed for the earlier import and SQLite archive tools. OpenF1 was part of the initial experiment and is no longer an active dashboard source. The current app does not merge independent OpenF1 and FastF1 telemetry feeds.

RaceOS turns that source data into a navigable application. The project includes the backend, frontend, replay logic, calculations, storage rules, tests and local startup tooling. A data library supplies data; RaceOS supplies the application around it.

## Completion status

The local historical replay and comparison version works and has been tested. The source and GitHub Actions workflow are published on GitHub. The source repository is https://github.com/diabloque/F1-Race-OS-. Publishing the source does not deploy a running server. Live ingestion, strategy prediction, machine learning and a hosted public deployment remain possible future extensions.

<!-- PAGE -->
# 1 Running and using RaceOS

## Start the application

Use Python 3.11 and Node.js 24 LTS. Open PowerShell in the project folder and run:

```powershell
Set-Location 'E:\Personal project\F1 RaceOs'
python run.py
```

On Windows, `py -3.11 run.py` is another option. On macOS or Linux, use `python3 run.py` if needed. The first run creates `.venv`, installs locked Python and JavaScript dependencies and builds the dashboard. Later runs reuse the setup. Keep the terminal open while using the app and press Ctrl+C to stop it.

The browser address is `http://127.0.0.1:8000/`. This is a server running on your own computer. The `/docs` address is the separate developer API reference; you do not need it for the normal RaceOS interface. A connection refused message usually means the server is stopped or is using another port.

## A useful first demonstration

1. Choose 2025, Italian Grand Prix and Qualifying, then select Open session. Availability depends on publication of the prepared source files.
2. Use Follow Driver to select Norris or Verstappen. Click a car on the circuit to change the focused driver without changing the replay time.
3. Play the session, adjust the playback speed or use Jump to Lap. Moving the timeline pauses playback and reconstructs the selected moment.
4. Read the selected driver's inputs. Turn on Selected car only if the full grid feels crowded. Driver labels can also be shown or hidden.
5. In Race workspace, use the Lap comparison link to jump below the replay. Advance the shared clock until timed laps finish, select A and B, then select Compare laps.
6. Inspect the circuit colors and move the distance slider. Try comparing different drivers and then two completed laps from one driver.
7. Use Back to replay to return to the track. Both links preserve playback and the selected session. The sidebar contains Race workspace and Session library.

Use a Race session to demonstrate the timing tower. Qualifying deliberately does not show race standings. A fresh checkout begins with an empty session library; saved bookmarks and downloaded data are not bundled into Git.

## Other startup options

`python run.py --setup-only` prepares everything without starting a server. `--no-browser` starts without opening a browser, and `--port 8001` changes the port. A separate Node development server is unnecessary for ordinary use because Python serves the compiled frontend too.

<!-- PAGE -->
# 2 How the application fits together

The Race workspace contains Track View and completed lap comparison under one session bar and playback timeline. Section links scroll within the page without resetting the clock. Session library is the other navigation entry; there is no separate Data quality screen.

RaceOS has two main parts. The frontend is the interface in the browser. The backend is a Python program that downloads data, validates it, reconstructs session state and returns JSON responses. They communicate through an API, which is a collection of HTTP routes with defined inputs and outputs.

| Technology | Job in RaceOS |
| --- | --- |
| Python | Data handling, replay state, calculations and startup tooling |
| FastAPI and Pydantic | HTTP endpoints and validation of request and response data |
| Uvicorn | Runs the local Python web server |
| React and TypeScript | Interactive pages, controls, state and typed data shapes |
| SVG and CSS | Circuit drawing, car markers, input trails and responsive layout |
| Requests and JSON | Download and read prepared source files over HTTPS |
| SQLite | Earlier local FastF1 archive with sessions, drivers, laps and samples |
| Vite and npm | Install frontend dependencies and build browser assets |

## Follow one request

The user chooses an event in `SessionControls.tsx`. The browser sends `POST /api/remote/open` with the year, round and session type. The backend loads metadata and looks for a complete reference lap for the circuit outline. If the prepared files have usable telemetry but no complete outline, inputs and timing still replay with a clear map message. The frontend then asks for replay snapshots at specific UTC timestamps.

For a snapshot, `remote_replay.py` finds each driver's active lap. The provider reads the corresponding prepared lap file from the cache or downloads it. RaceOS selects the latest supported sample at or before the requested time, calculates engineering state and sends the frame to the browser. `useReplay.ts` updates the map and driver panel together.

```text
Session selection in the browser
    -> FastAPI routes
    -> Provider and bounded file cache
    -> Replay and engineering calculations
    -> JSON frame
    -> React panels and circuit drawing
```

The source files are a remote collection of prepared JSON data, not a direct connection to an official F1 database. The app still needs local logic to choose files, interpret timestamps and decide what can be shown at each moment.

The project runs as one Python backend and one React frontend. We did not introduce separate microservices, Kafka or another database server. Ordinary functions, a few focused classes and HTTP requests are sufficient for this version.

<!-- PAGE -->
# 3 How the project developed

## Phase 1 Data ingestion proof

The first experiment compared OpenF1 and FastF1 using real Monza qualifying data. It collected drivers, laps and selected driver telemetry, retained source identity and produced quality reports. The point was to understand timestamps, units, missing values and unusual input readings before building the interface. The active code later moved to FastF1, while earlier evidence was retained.

## Phase 2 Storage and backend

We added a SQLite archive and a FastAPI backend. The archive stores sessions, provider identity, drivers, laps, telemetry, import history and later position data. Repeat imports can reuse unchanged content. HTTP routes expose records and health information. FastAPI also supplies the interactive `/docs` page used during development.

## Phase 3 Telemetry interface

We built the React and TypeScript dashboard with session, driver and lap selection, synchronized input views, a session library and an initial data quality screen. That screen was later removed at your request; internal validation remains. The early interface used telemetry charts. It was then adapted to your preferred track based experience, with one focused driver and fewer repeated statistics.

## Phase 4 Historical replay

We added a shared virtual clock, circuit geometry, moving car markers and controls for playing, pausing, speed changes and seeking. The app reconstructs recorded state at a requested moment. Your layout changes included label controls, one selected driver panel, an input color key and removal of the DRS and overtake statistic.

## Later source change

To avoid bulk importing every race, normal replay moved to TracingInsights prepared files. Sessions are selected remotely, lap files load as needed and a bounded cache limits new downloaded data. The earlier FastF1 import and SQLite tools remain available as a reference path.

## Phase 5 Race engineering

We added sector based race timing, tyre compound and stint state, completed tyre age, paired pit visits, recorded weather and issued race control messages. These features use the replay clock and restore earlier state on backward seeks.

## Phases 6 and 7 Analysis and local setup

We added completed lap selection, timing and sector deltas, time weighted input percentages and approximate distance alignment on the circuit. Finally, we added the one command launcher, clean installation verification, local Git history, a GitHub Actions workflow and setup documentation. The later review simplified dense code and added this guide. Further updates combined replay and comparison, added starting-grid order and improved missing-position and timestamp handling.

<!-- PAGE -->
# 4 Remote data and local storage

## Why files load on demand

Bulk importing complete seasons would take time and disk space. The current dashboard loads session and lap metadata first, then retrieves the active lap file for each car. That can involve the whole grid, not just the driver being followed. Upcoming lap files are prefetched near a boundary to reduce waiting when playback continues.

`providers/tracinginsights.py` converts source columns into RaceOS field names, checks table shapes and establishes UTC timestamps. The selector lists completed races and qualifying from 2018 through the current year. This is a selection range, not a promise that every historical session or channel has a published file. Practice is excluded from the normal selector.

## Where things are kept

| Location | Contents |
| --- | --- |
| `data/remote/cache` | Compressed downloaded JSON with a 200 MiB disk limit |
| `data/remote/sessions.json` | Small bookmarks for sessions opened locally |
| `data/raceos.sqlite3` | Earlier FastF1 archive and reference data |
| `.venv` | This project's Python environment and packages |
| `frontend/node_modules` | Frontend dependencies |
| `frontend/dist` | Built browser assets served by Python |
| `data/tmp` and `data/cache` | Project temporary files and installation caches |

The 200 MiB limit applies only to the new remote file cache. It is not a limit on the whole project, old FastF1 cache, SQLite archive, backups or development tools. Old downloads inside that cache can be evicted and fetched again later. Existing archive data was retained.

## Keeping resource use bounded

The cache compresses JSON with gzip, restricts individual downloads to 20 MiB and limits decoded memory entries. Normalized telemetry is bounded to 40,000 samples and session metadata to four open sessions in memory. A small worker pool downloads files concurrently; locks prevent duplicate simultaneous downloads of the same file. These details protect storage and responsiveness.

HTTPS certificate verification remains enabled. The downloader uses system certificates, timeouts and fallback source URLs. Optional grid, weather or race control failures can be reported without stopping the main replay. Cached files help repeated use, but an arbitrary uncached race is not guaranteed to work offline.

Replay begins at racing Lap 1 and does not load a separate formation lap. Prepared positions can remain inaccurate even after visible trail joins are filtered.

<!-- PAGE -->
# 5 Replay and track drawing

## One shared clock

Replay is driven by one UTC timestamp for the session. When you seek, every car and engineering panel is reconstructed for that moment. Cars do not each run on separate stopwatches. Changing the focused driver changes the panel, not the session time.

For each car, RaceOS selects the latest sample at or before the clock. Samples over one second old become unavailable; the app does not extrapolate positions. The source already contains interpolation, as stated in the interface.

A lap result appears after its recorded completion. Seeking backward before the finish removes it again. The same principle applies to tyre changes, weather observations and issued race control messages. Files can contain later samples internally, but the replay response filters what is returned to the browser.

## Playback and waiting for data

`useReplay.ts` stores the catalog, current frame, elapsed time, focused driver, playback speed and loading state. It requests one frame at a time and uses AbortController to cancel obsolete requests after a seek or session change. A slower response cannot overwrite a newer selection.

Playback uses elapsed wall time multiplied by playback speed. Long data waits are excluded from progression and the interface can display buffering. Play stops at the end of the available session window. Seeking pauses playback so the chosen moment remains stable.

## Circuit geometry

A complete prepared reference lap supplies the static x and y outline. Missing reference positions produce an explanatory empty map, while available inputs and timing remain usable. `fitTrack` and `project` scale and rotate source positions into a 1000 by 600 SVG coordinate space while preserving the aspect ratio. The same transform is applied to the outline, cars and selected driver's trail.

| Replay trail color | Meaning |
| --- | --- |
| Green | Throttle above 15 percent with brake released |
| Red | Brake pedal applied, taking priority over throttle |
| Yellow | Throttle from 0 to 15 percent with brake released |

Unsupported input states remain unknown. At your request, there is no separate gray legend label. Selected car only and optional driver labels reduce crowding without changing the circuit. This is a replay of observed data; it does not simulate vehicle physics or supply official broadcast video.

The trail renderer limits short moves to four times the reference lap's average speed, plus a small noise allowance. Using circuit length and lap duration keeps the rule independent of coordinate units. It is a display heuristic, not a physics measurement.

A position jump, invalid point, non-increasing timestamp or gap over one second breaks the colored line. Drawing resumes at consistent points. Source positions and pedal inputs remain unchanged. Samples before lap start are excluded; malformed or reversed timestamps still fail validation.

<!-- PAGE -->
# 6 Race engineering features

## Race timing and intervals

Before the first timing observation, the tower shows starting-grid order from Jolpica, with gaps and intervals blank. It validates the race date, season, round, car number and driver code; finishing positions are never used. Missing grid entries stay unknown.

`race_timing.py` then builds observations of sector line crossings at or before the replay clock. Progress is represented by lap and sector. Cars with more observed progress come first; crossing time breaks a tie. Generated retirement lap records are excluded from real timing observations.

Gap to the leader and interval to the car ahead compare timestamps at the same lap and sector for both cars. For example, crossings at 100.000 and 102.500 seconds produce a 2.500 second gap at that line. A missing or inconsistent comparison stays unknown. These values update at available sector timing lines, potentially during Lap 1. Missing first-lap sectors delay the first update. The display labels grid order and recorded timing separately. Rewinding to the start restores the grid and clears future gaps.

The timing tower appears for Race sessions. Clicking a row changes the focused driver without moving the clock. The displayed race lap is derived from the grid's observed progress, while the selected driver's own lap is a separate value.

## Tyres and pit visits

`engineering.py` reconstructs tyre compound, stint number, fresh or reused set information and tyre age in completed laps. The source tyre life describes an end of lap count, so RaceOS subtracts the unfinished current lap. Previously used sets retain their earlier age.

New set information is gated by the recorded lap start and pit exit. This avoids showing the next tyre set before the car leaves the pit lane. Pit visits count paired entry and exit records. A pit lane visit alone does not prove the car stopped or changed tyres. Missing pit information stays unknown rather than becoming a fabricated zero.

## Weather and race control

Weather uses the latest recorded observation no later than the clock. It shows supported air and track temperature, rainfall and wind fields. An observation older than two virtual minutes is marked as old. Recorded rainfall is a source observation, not a new weather forecast.

Race control shows up to 50 messages already issued at the replay time, such as flags, safety car notices or penalties. Invalid or future timestamps are skipped. Backward seeking restores earlier messages and observations.

## Driver inputs

The single driver panel shows speed in km/h, throttle pedal percentage, binary braking, gear and engine RPM. Brake is Applied or Released because the prepared data does not provide brake pressure. DRS and overtake statistics were removed at your request. Historical race control text may still mention DRS because it is part of a recorded message.

<!-- PAGE -->
# 7 Lap comparison calculations

## Which laps can be selected

`analysis.py` permits timed laps with positive duration, a valid start and finish and a completion at or before the replay clock. Generated laps are excluded. Both selections are checked before either telemetry file is fetched. The browser also hides already loaded results after a backward seek makes either lap unfinished.

A and B belong to the same session. They may represent different drivers or two laps from one driver. Recorded pit laps and laps later deleted by officials can be present; RaceOS does not use a final deletion decision as if it were known earlier in the replay.

## Timing deltas

The lap and sector differences use this convention:

```text
Delta = time for lap B minus time for lap A
Negative delta means B is quicker
Positive delta means A is quicker
```

One verified 2025 Monza qualifying comparison used Norris lap 20 at 78.869 seconds and Verstappen lap 17 at 78.792 seconds. B minus A is -0.077 seconds. The recorded sector deltas are -0.116, +0.045 and -0.006 seconds. Missing sectors stay unknown rather than being reconstructed from the final time.

## Time weighted inputs

Full throttle means a valid reading from 99 through 100 percent. For each pair of consecutive samples at most one second apart, the left sample's state applies until the next reading. Duplicate timestamps contribute no duration. Larger gaps, invalid throttle values and unknown brake states contribute no known time.

```text
Input percent = active seconds / known seconds * 100
Coverage percent = known seconds / recorded lap window * 100
```

If braking is applied for 2 of 8 known seconds, braking is 25 percent. If the lap window is 10 seconds, that channel's coverage is 80 percent. Displaying both values prevents missing time from quietly becoming released brakes or zero throttle.

The calculation stops at the final supported sample. It does not stretch the last reading to the finish or use post finish samples. A recording window that differs substantially from the reported lap time receives a warning. The metrics summarize prepared sampled data; they are not precise pedal transition measurements or isolated measures of driver skill.

<!-- PAGE -->
# 8 Comparing distance around the circuit

## Aligning the laps

`distance_comparison.py` uses recorded distance within each completed lap. It checks that distance is monotonic and that samples cover both ends of the lap within the endpoint tolerance. Missing distance, reversed distance or unavailable reference positions can disable the map while leaving reported timing and input comparisons available.

Each lap's observed distance span is normalized from zero to one. A progress value of 0.5 means halfway through that lap's recorded distance, even if the two observed spans have slightly different lengths. The slider's approximate metres use the mean of the two spans. Equal progress is an approximate comparison and does not prove the cars used an identical racing line.

RaceOS creates 201 inspection points, giving 200 segments of 0.5 percent each. At a supported point, time and x and y positions can be interpolated between neighboring source samples no more than one second apart. Throttle and brake use the preceding sample. Unsupported intervals are not bridged.

## Cumulative delta and local gain

At one progress point, cumulative delta is B's elapsed time minus A's elapsed time. The color comes from the change in that delta across the next supported segment. A car may still be ahead overall while losing time locally in a corner.

| Comparison overlay | Meaning for lap B |
| --- | --- |
| Green | Gains more than 0.010 seconds over that segment |
| Red | Loses more than 0.010 seconds over that segment |
| Neutral | Change within the 0.010 second tolerance |

For example, a cumulative delta moving from -0.200 to -0.150 seconds means B remains ahead but loses 0.050 seconds locally. That segment is red. This color key belongs to lap comparison; the replay track uses the different throttle and brake key explained earlier.

## Inspecting a point

Hover near the circuit or use the keyboard and touch compatible distance slider. The readout shows progress, approximate metres, cumulative delta and each lap's speed, throttle and brake state. Map colors are drawn on reference lap A positions, using the same circuit projection as the existing track view.

Recorded sample endpoints can differ from official lap timing. The curve is not forced to end at the reported lap delta. The view is labeled approximate because the source is prepared and distance alignment and within sample interpolation introduce additional assumptions.

<!-- PAGE -->
# 9 Reading the Python backend

Start with `run.py`, then follow one route in `src/raceos/api.py`. Next read the provider and remote replay code. Study the calculation modules after you understand the dictionaries passed between them. Types describe expected fields; they do not add another service or database.

| File under src/raceos | Main responsibility |
| --- | --- |
| `api.py` | Routes, request validation, health and serving the built dashboard |
| `providers/tracinginsights.py` | Session metadata, source columns and UTC conversion |
| `remote_cache.py` | HTTPS, compressed files, limits, locking and prefetch |
| `remote_replay.py` | Current lap samples, car frames, outline and lap quality |
| `engineering.py` | Tyres, pit visits, weather and issued messages |
| `race_timing.py` | Starting grid before timing begins, then sector order and same line gaps |
| `analysis.py` | Completed lap choices, timing deltas and input percentages |
| `distance_comparison.py` | Normalized distance and supported comparison segments |
| `data.py` and `contracts.py` | Numeric and UTC helpers, quality profiles and record validation |
| `storage.py` and `replay.py` | SQLite archive, reference replay and shared completion rules |
| `providers/fastf1.py` | Earlier FastF1 import adapter |
| `cli.py`, `prepare.py`, `report.py` | Server command, archive preparation and import reports |

## A simple eligibility rule

The refactored `eligible` function first checks for missing or generated data, then verifies the timing window. Its final condition reads:

```python
return utc_datetime(start) < utc_datetime(finish) <= at
```

This says that the start is before the finish, and the finish is no later than the clock. Earlier `if` statements reject missing dates and nonpositive duration. Straightforward conditions make the rule easier to explain than one long Boolean expression.

The input calculation now names its totals `active_s` and `known_s`, instead of relying on positions zero and one in a list. Distance alignment names the segment count and comments why a data gap starts a new region. These changes improve readability without removing validation or changing the response fields.

<!-- PAGE -->
# 10 Reading the frontend

The frontend lives under `frontend/src`. React components render parts of the page. Hooks hold reusable state and request logic. TypeScript interfaces describe the JSON objects received from Python, so missing or misspelled fields are easier to catch during a build.

| File or component | Main responsibility |
| --- | --- |
| `App.tsx` | Navigation and the overall page layout |
| `SessionControls.tsx` | One event selector and replay driver and lap controls |
| `hooks/useArchive.ts` | Session bookmarks, backend health and refresh |
| `hooks/useReplay.ts` | Clock, requests, seeking, playback and cancellation |
| `ReplayWorkspace.tsx` | Assembles the map and engineering panels |
| `TrackView.tsx` | SVG outline, cars, input trail and label controls |
| `DriverPanel.tsx` and `TyreStint.tsx` | Selected driver readouts and tyres |
| `RaceTiming.tsx` and `SessionConditions.tsx` | Timing tower, weather and race control |
| `PerformanceAnalysis.tsx` | Completed lap choices and comparison results |
| `LapComparisonTrack.tsx` | Gain and loss overlay and point inspection |
| `api.ts`, `replay.ts`, `data.ts`, `types.ts` | Requests, projection, formatting and data shapes |
| `styles.css` | Layout, colors and desktop and mobile styling |

## What the readability review changed

Each React state declaration now occupies its own statement in the two main hooks and comparison view. Lap comparison chooses default drivers and laps through explicit steps. It checks A and B completion separately before showing results. The summary uses a named quicker lap instead of a deeply nested display expression.

The track comparison uses ordinary `if` statements for gain and loss colors and a small brake label helper. An unused paginated frontend API helper and its unused Page type were removed. The later cleanup removed obsolete chart helpers, their tests, unused icons and 95 CSS rules. Session selection and replay preparation now use clearer conditions, named variables and ordinary loops.

The project still uses real engineering concepts such as asynchronous requests, cancellation, binary search and cache locks where they are needed. These are explained rather than deliberately weakened. The goal is code a student can study, modify and accurately explain, with no unnecessary framework or clever shorthand.

<!-- PAGE -->
# 11 Verification and local project setup

## What was checked

The cleanup passed 147 Python tests, 8 frontend tests and 28 real data browser scenarios. Five tests for the deleted chart helpers were removed. The added trail tests cover sudden position jumps, time gaps, invalid points and coordinate-unit independence. The TypeScript and Vite production build passed. Browser checks covered actual Monza sessions, driver changes, playback, backward seeking, pit and weather state, timing, comparison colors and slider values, errors, recovery and mobile layout.

The Python tests check calculations and failure cases such as uneven sample intervals, missing channels, duplicate timestamps, gaps and future lap requests. Frontend tests check time formatting, projection, clock arithmetic and input colors. Real data browser scenarios check how the pieces work together in installed headless Edge.

Clean setup verification uses a separate source snapshot with no environment, frontend dependencies, build, archive or saved sessions. It exercises locked installation, repeat setup reuse, dependency consistency and the offline browser smoke test. Temporary setup files and logs remain on E: during validation. A Starlette TestClient deprecation warning exists, but it does not fail the current tests.

## Run the main checks on Windows

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:smoke
```

The smoke check uses its own empty database and an intercepted empty schedule. It tests fresh startup without depending on remote F1 publication. The larger `test:browser` script opens its required Monza sessions when needed and uses a recorded pit-exit fixture. It needs internet for uncached files; the fresh clone CI smoke test works offline.

## Environments and GitHub

`.venv` isolates Python packages for this project. `frontend/node_modules` does the equivalent job for JavaScript dependencies. Requirements and npm lock files record the verified dependency versions, so a different computer can install the same stack. `run.py` stores setup fingerprints to avoid repeating unchanged installation and build steps.

The local Git repository tracks code, tests, configuration and documentation. It excludes downloaded data, environments, dependencies, builds and `.env` files. A small Git setting trusts this exact E drive folder because the filesystem does not record ownership. Publishing the source does not automatically start a web server.

The source is published in the diabloque/F1-Race-OS- GitHub repository. GitHub Actions checks setup, the build, tests and browser smoke on a clean Linux runner using Python 3.11 and Node 24. Results appear in the Actions tab. See `docs/GITHUB_SETUP.md` for cloning and later updates.

<!-- PAGE -->
# 12 Limits and useful next steps

## Interpret the data carefully

Prepared public data is not the same as private team telemetry. Positions can contain upstream interpolation, some channels are missing and source publication varies. Brake pressure is unavailable. Missing values stay unknown. Out of range throttle readings are preserved and flagged rather than treated as extra physical pedal travel above 100 percent.

Replay filters by recorded event time. Original live delivery delays are unavailable, so the project does not recreate exactly when every message would have arrived at a live team's computer. Timing tower gaps use matching sector crossings. They are not continuous official gaps, and final penalties or classifications can differ.

Lap differences can reflect tyres, fuel, traffic, weather and track conditions. Input percentages depend on covered time and a stated hold rule. Distance alignment is approximate. None of these calculations alone establishes tyre wear, a driver's skill or the reason one car was faster.

## What remains outside this local version

The original vision also discussed strategy simulation, tyre degradation models, lift and coast estimates, alerts, machine learning, an AI assistant, CarTwin and additional motorsport sources. Those are future modules, not hidden completed features. A live feed and hosted deployment would also require separate work. The implemented local version concentrates on historical replay, engineering context and completed lap analysis.

To present this version, demonstrate opening a session, following a driver, seeking backward, reading timing and tyres and comparing two completed laps. Explain the source, cache and missing data rules. The README includes screenshots and a short demonstration sequence. The source repository is ready for a reviewer to clone, install and run locally.

## Terms used in this guide

| Term | Meaning here |
| --- | --- |
| Telemetry | Time stamped observations such as speed and pedal input |
| UTC | One common time standard used for the replay clock |
| Stint | A recorded run associated with tyre set information |
| API | HTTP routes used by the browser to request data |
| JSON | The structured text format exchanged by the source and API |
| Cache | Saved downloads that can be reused and evicted |
| Interpolation | Estimating an intermediate value between supported samples |
| Coverage | The fraction of a time or distance window supported by data |

The README and `docs/CODE_GUIDE.md` provide a shorter route back into the source. Obsolete phase reports and earlier implementation details remain available in Git history. This guide explains the current implementation and the changes made to reach it.