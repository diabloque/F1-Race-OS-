# RaceOS

RaceOS is a local motorsport engineering workspace with historical track replay.
The dashboard now loads **TracingInsights prepared data remotely**, one driver
lap at a time. Races and qualifying are supported; practice sessions are excluded.
FastF1 ingestion and the existing SQLite archive remain available as reference tools.

For a beginner walkthrough of the finished app, its architecture and the code,
read the [project guide](docs/RACEOS_PROJECT_GUIDE.md) or open the
[Word guide](docs/RaceOS%20Project%20Guide.docx).

## Run

Install **Python 3.11** and **Node.js 24 LTS**, then open a terminal in this folder:

```powershell
python run.py
```

The first run creates `.venv`, installs locked dependencies, builds the dashboard,
and opens **http://127.0.0.1:8000/**. Later runs reuse the setup and rebuild changed
frontend files. Keep the terminal open; press **Ctrl+C** to stop the server.
Internet is needed for first setup and to download uncached session data.
Project environments, dependency caches, temporary files, and data stay inside
this folder. For this workspace the folder is `E:\Personal project\F1 RaceOs`.

Options: `python run.py --setup-only`, `--no-browser`, or `--port 8001`.
If dependencies or setup files were manually removed, delete `data/setup.json`
and run again. On Windows, `py -3.11 run.py` also works. On macOS/Linux, use
`python3 run.py` if `python` is unavailable. The Python server serves the compiled
React frontend; a separate Node server is unnecessary for normal use.

`/docs` contains the developer API documentation. For development after setup,
`.venv/Scripts/python.exe -m raceos serve` starts just the server on Windows;
use `.venv/bin/python` on macOS/Linux. Restart after backend edits.

## Open a session

Use the single selection bar to choose a year, Grand Prix, and **Race** or
**Qualifying**, then click **Open session**. Follow Driver and Jump to Lap are
in the same bar and become available for the opened session. The list contains
finished sessions from 2018 through the current year. Publication and data
coverage can vary; missing files produce an explanatory error.

The session library saves small bookmarks. Driver and lap metadata load first;
telemetry loads only for the active lap of each car. Upcoming laps are buffered
near boundaries. Seeking elsewhere fetches the required lap files. There is no
bulk season import or new SQLite telemetry import in this workflow.

This working folder has saved Monza race/qualifying bookmarks; a fresh checkout
starts with an empty library. For a first demo, open 2025 Italian Grand Prix qualifying. Use Play/Pause, 0.25x-16x speed, ten-second steps, lap jumps, or the timeline.
Select any car or use the Driver menu to follow its inputs.

## Storage

- New downloaded JSON is compressed under `data/remote/cache`.
- This cache is capped at **200 MiB** (209,715,200 bytes). Old cached files are
  evicted automatically. Reopening an evicted lap downloads it again.
- `data/remote/sessions.json` holds small saved-session bookmarks.
- Decoded data is also bounded in memory. Browser API responses use `no-store`.
- Cache, logs, test/browser profiles, and project files stay under the project on E:.

The cap applies to the **new remote cache**. Existing FastF1 cache, exported JSON,
SQLite archive, and earlier backups have been retained separately. They are not
removed or counted inside that cap. Source changes were backed up in
`data/tracinginsights-backup`; no new copy of the large SQLite archive was made.

## Data meaning

TracingInsights files are prepared from FastF1 and other sources. Positions and
some channels contain upstream interpolation; RaceOS labels them as prepared data.
The source's lap-start dates and relative sample times establish one shared UTC
clock. Replay holds recorded samples without further interpolation or extrapolation.
The separate completed-lap comparison interpolates time and position along distance.
Every returned replay sample is at or before the replay clock; samples over one second old stay unknown.
Original live delivery delays are unavailable.

A static circuit outline comes from a complete prepared reference lap. Lap results
and best times appear after completion and disappear appropriately on backward
seeks. Car status flags absent from the prepared source remain unknown; a valid
position is not described as proof that a car is OnTrack.

Throttle shows 0-100 pedal input. Brake shows Applied/Released; pressure is
unavailable. DRS/Overtake Mode statistics have been removed from the dashboard.
The dashboard has two screens: Race workspace and Session library. Telemetry
validation and missing-data handling remain active behind the scenes.

Races include a **Race timing** tower below the circuit. It shows order at the
latest recorded sector lines, gap to the leader, and interval to the car ahead,
in seconds. Click a driver in the tower to follow that car. Gaps compare the
same lap and sector for both cars; they are not continuously measured live gaps.
Missing comparisons stay unknown, and backward seeks restore earlier timings.
Before the first recorded timing line, positions and intervals remain blank.
Qualifying does not show race standings. See [timing details](docs/RACE_TIMING.md).

## Engineering view

The selected driver's **Tyres & stint** section shows compound, tyre age in
completed laps, stint number, whether the set started fresh or was reused, and
completed pit-lane visits. It marks a recorded pit-lane visit while it is in
progress. Pit visits count matched entry/exit records; they do not prove that a
car stopped or changed tyres.

Weather shows the latest recorded track/air temperatures, rainfall report, and
wind at the replay clock. Reports older than two virtual minutes are marked as
older observations. Race control shows up to 50 messages already issued at that
time, including flags, safety cars, and penalties. Missing optional data remains
unavailable without stopping replay. Backward seeking restores previous state.
See [Phase 5 results](docs/PHASE5_RESULTS.md).

## Lap comparison

Open **Race workspace** in the sidebar to use track replay and lap comparison
together. There is one session selection bar and one replay timeline. The circuit,
focused driver, timings, and conditions remain above the comparison section.
Use the track panel's **Lap comparison** link to jump down, or **Back to replay**
to return. These links preserve playback and the selected session.

Advance the shared replay clock until laps have finished, choose a driver and
completed lap for **A** and **B**, then select **Compare laps**. Compare two
drivers or two laps from one driver. The existing timeline controls both parts
of the workspace; backward seeking hides comparisons for unfinished laps.

The timing table shows recorded lap/sector times and **B minus A** differences.
A negative difference means B was quicker. Input comparisons show full throttle
(99-100%) and braking, weighted by elapsed time rather than sample counts.
Percentages use covered telemetry time; active seconds and coverage are shown
for each channel. Unknown values and gaps longer than one second are excluded.
Missing sectors stay unknown. Backward seeking hides results for unfinished laps.
The comparison track aligns normalized recorded distance: green shows where B
locally gains time and red where B loses time. Hover the circuit or move the
distance slider to inspect cumulative B minus A, speed, throttle, and braking.
This is approximate: prepared positions and distance alignment do not establish
identical physical racing lines. Missing intervals are not connected.
See [Phase 6 comparison results](docs/PHASE6_RESULTS.md).

## GitHub and checks

Everything is being finished locally first. The repository includes a GitHub
Actions workflow for locked setup, Python/frontend tests, and an offline browser
smoke test. It runs after a future push or pull request; adding files locally
does not run GitHub Actions or host the app.

See [GitHub setup](docs/GITHUB_SETUP.md) for the upload steps and
[Phase 7 results](docs/PHASE7_RESULTS.md) for local verification. Downloaded data,
`.venv`, `node_modules`, builds, browser profiles, and caches are excluded from Git.
Fresh checkouts load selected sessions remotely; no initial FastF1 import is required.

## APIs

| Route                                                                                    | Purpose                                  |
| ---------------------------------------------------------------------------------------- | ---------------------------------------- |
| `GET /api/library`                                                                       | Saved remote session bookmarks           |
| `GET /api/remote/events?year=2025`                                                       | Completed race/qualifying choices        |
| `POST /api/remote/open`                                                                  | Open `{year, round, session}`            |
| `GET /api/remote/cache`                                                                  | Current cache size and limit             |
| `GET /api/sessions/{id}/replay`                                                          | Replay window and lap-start targets      |
| `GET /api/sessions/{id}/track`                                                           | Prepared approximate circuit outline     |
| `GET /api/sessions/{id}/replay/frame?at=<UTC>&driver_number=4`                           | One shared-clock snapshot                |
| `GET /api/sessions/{id}/drivers/4/quality?lap_number=2`                                  | Prepared lap quality                     |
| `GET /api/sessions/{id}/analysis/laps?at=<UTC>`                                          | Completed timed laps at the replay clock |
| `GET /api/sessions/{id}/analysis/compare?at=<UTC>&driver_a=4&lap_a=2&driver_b=1&lap_b=2` | Completed lap and input comparison       |

Remote IDs look like `ti-2022-16-R`. Replay responses identify `tracinginsights`.
Legacy FastF1 archive IDs and read APIs continue to work with source `fastf1`.
`/api/sessions` lists that legacy stored archive; the dashboard uses `/api/library`.
Legacy `raceos ingest`, `import`, and `prepare-replay` commands are still available
for reference work. They are not the dashboard's remote loading path.

## Edit and verify

See [the code guide](docs/CODE_GUIDE.md) and
[the remote-source update](docs/TRACINGINSIGHTS_UPDATE.md).

```powershell
npm --prefix frontend run dev
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:smoke
```

Vite development serves at http://127.0.0.1:5173 and proxies the backend on port 8000. Browser checks use installed headless Edge and a temporary server on a free
port with an isolated empty archive and no remote-data dependency. Optional
`npm --prefix frontend run test:browser` runs the larger real-data scenarios;
it needs locally prepared Monza bookmarks and `data/phase5-validation.json`.
These scenarios save screenshots/evidence under `data/remote-replay-*`.
Black and Prettier are the development formatters. All new code uses ordinary
Python functions/classes, HTTP JSON requests, and React components. The adapter
reads TracingInsights files directly, so installing the larger tif1 package is
unnecessary.

References: [TracingInsights datasets](https://github.com/TracingInsights/2026),
[tif1 approach](https://github.com/TracingInsights/tif1),
[data definitions](https://github.com/TracingInsights/2026/blob/main/DATA_REFERENCE.md),
and [FastF1](https://github.com/theOehrly/Fast-F1).
