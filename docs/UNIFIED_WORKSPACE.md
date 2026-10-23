# Unified race workspace

Implemented 2026-10-23 at the user's request to combine track replay and lap
comparison in one workspace.

## Behavior

The sidebar now has Race workspace, Session library, and Data quality. The race
workspace contains the existing circuit, selected driver panel, completed laps,
timing, conditions, and lap comparison. The comparison remains below the replay
panels. A Lap comparison link in the track header and a Back to replay link in
the comparison header move within the same page.

There is one event selection bar, one set of playback controls, and one replay
UTC readout. Both components receive the same replay state. Section navigation
does not pause or reset playback. Comparison selections are pinned after a
comparison request, independently of the driver currently being followed.
Comparisons remain limited to laps completed at the shared clock. A backward
seek hides future choices and results immediately. A different session cannot
display a comparison belonging to the previous session.

## Implementation

- `App.tsx` removes the separate analysis screen and mounts both components.
- `ReplayWorkspace.tsx` keeps the circuit and controls and adds a section link.
- `PerformanceAnalysis.tsx` removes its duplicated clock/controls and adds the
  in-page heading and return link.
- `styles.css` styles the links and responsive heading without changing map
  projection, input colors, or comparison calculations.
- Browser checks verify one selection bar, timeline, UTC readout, and workspace;
  playback survives section navigation and session changes hide old results.

No backend, schema, or dependency changes were needed. Existing on-demand
loading and cache limits remain in place. Validation results and screenshots
are stored under `data/` on E:.

## Validation

The production frontend build, all 10 frontend tests, the isolated offline
browser smoke check, and all 26 browser scenarios passed. Browser checks cover
the shared timeline, navigation during playback, backward seeking, session
changes, completed-lap comparison, and responsive layouts. Desktop and mobile
screenshots of the workspace and comparison section were visually inspected.
