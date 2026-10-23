# TracingInsights remote replay update

Updated: 2026-10-21. RaceOS version: 0.4.1.

The dashboard now opens remotely hosted TracingInsights prepared files instead
of requiring a full FastF1 session import into SQLite. The existing FastF1
archive and commands remain available for reference.

## Using the dashboard

Run `.\.venv\Scripts\python.exe -m raceos serve` from the project directory,
then open http://127.0.0.1:8000/.

Use the single selection bar to choose a year, Grand Prix, and
Race or Qualifying, then select **Open session**. The same bar contains Follow
Driver and Jump to Lap; it stays synchronized with library selections. Practice sessions are excluded.
The calendar covers 2018 through the current year; individual files depend on
upstream publication and coverage. A calendar entry does not guarantee that
all of its telemetry has been published.

The library now contains bookmarks for the 2018 and 2022 Monza races and
2024/2025 Monza qualifying. The circuit layout, focused driver panel, and
throttle/brake color key remain in place.

## Loading and storage

The adapter requests the public JSON directly, using jsDelivr with raw GitHub
as a fallback. No tif1 package installation is required. It loads driver and lap
metadata first, followed by the active lap files needed for the replay clock.
Upcoming laps are prefetched near lap boundaries. Seeking downloads the files
needed for the destination rather than importing an entire session.

New downloads are gzip-compressed under `data/remote/cache` on E:. The cache
has a 200 MiB limit (209,715,200 bytes) and evicts older downloaded cache files
when necessary. Evicted laps are downloaded again when requested. Decoded
files and normalized samples also have memory limits. Saved sessions are small
bookmarks in `data/remote/sessions.json`.

After the real-data and browser checks, the cache held 374 files totaling
18,643,606 bytes, about 17.8 MiB. This is a measured test footprint, not a fixed
size for every race. No new telemetry rows were imported into SQLite.

The 200 MiB cap applies only to the new remote cache. The previous FastF1 cache,
SQLite archive, exports, and backups remain separate and have not been deleted.
The source backup is `data/tracinginsights-backup`; this update did not make a
new copy of the large SQLite archive.

## Replay and data meaning

TracingInsights supplies prepared data derived from FastF1 and other sources.
Some values and positions are interpolated upstream. RaceOS labels this source
as prepared data; it cannot reconstruct the original measurement cadence or
live delivery delays from these files.

Lap-start dates and relative sample times establish a shared UTC clock for
all cars. Snapshot samples are at or before that clock. RaceOS does not add
interpolation or extrapolation; samples more than one second old remain
unknown. Missing position status stays unknown. Cars without a current valid
lap/position are hidden rather than extrapolated after retirement or finish.
A complete reference lap supplies the static approximate circuit outline.

Lap results and best times appear only once the lap has completed. Backward
seeks recompute that state. Prefetching does not expose future samples or
results. Playback shows a buffering state while needed files download.

Prepared DRS is binary: 1 is Open and 0 is Closed. It is stored separately from
legacy FastF1 DRS codes. Missing states stay unknown. Brake is Applied/Released;
these files do not supply brake pressure. The quality view reports the selected
prepared lap rather than downloading the entire session.

Upstream files can be corrected over time, and later downloads after cache
eviction can reflect those corrections. Replays depend on source availability;
this is not a complete offline archive or a live timing service.

## Main changes

- `src/raceos/remote_cache.py`: HTTP downloads, compressed cache, bounded memory,
  fallback URLs, and prefetching.
- `src/raceos/providers/tracinginsights.py`: calendar, session bookmarks, prepared
  driver/lap/sample parsing, and shared-clock validation.
- `src/raceos/remote_replay.py`: track geometry, snapshots, completed-lap state,
  and selected-lap quality.
- `frontend/src/components/SessionControls.tsx`: unified session loading, driver,
  and lap selection.
- Existing API and React hooks dispatch remote replay requests and display
  prepared-source provenance and buffering.

See `CODE_GUIDE.md` for the code walkthrough and the README for API routes.

## Verification

- 81 Python tests passed, including remote parsing, clock alignment, DRS,
  cache limits, failure handling, and API validation.
- 11 frontend tests passed. TypeScript and the production build passed.
- 14 real-data browser scenarios passed using installed headless Edge.
  These covered playback, seeking, driver selection, pause/speed, DRS,
  completed-lap visibility, qualifying, retry after an error, and the picker.
- The picker opened the 2018 Monza race, which was not previously bookmarked.
  It offered only Race and Qualifying. Desktop and mobile screenshots were
  inspected; no JavaScript errors or horizontal overflow were reported.
- A separate real-data audit read all 53 Norris lap files from the 2022 Monza
  race and checked the 20-driver grid at eight times from start to finish.
  It checked past-only sample timestamps, completed results, deterministic
  backward seeking, quality, and qualifying metadata. This was not an
  exhaustive audit of every lap for every driver.
- Existing SQLite counts remained unchanged: three sessions, 60 driver/session
  records, 1,562 laps, 1,359,520 telemetry rows, and 1,398,320 positions.

Evidence is saved under `data/remote-validation.json`,
`data/remote-replay-browser.json`, `data/remote-replay-dashboard.png`, and
`data/remote-replay-mobile.png`. Tests use temporary files and browser profiles
under the project on E:.

References: [TracingInsights datasets](https://github.com/TracingInsights/2026),
[tif1](https://github.com/TracingInsights/tif1), and
[data definitions](https://github.com/TracingInsights/2026/blob/main/DATA_REFERENCE.md).

## Unified selection follow-up

The separate remote loader and saved-session dropdown were merged into one
responsive bar. Saved sessions remain accessible through the library and reopen
without another remote-open request. Driver and lap controls are disabled while
a different session is selected but not yet opened. The production build and
15 browser scenarios passed, including synchronized selections, playback,
library navigation, and desktop/mobile layouts.
