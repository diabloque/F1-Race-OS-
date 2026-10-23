# FastF1 source update

RaceOS 0.3.1 uses FastF1 as its only active data source. This is a maintenance
update after Phase 3; historical replay remains Phase 4.

- Ingestion downloads or reuses one FastF1 bundle and saves a quality report.
- Saved-bundle imports read `fastf1.json` only.
- API source queries accept FastF1 only. Catalogs and counts exclude archived
  provider records.
- The dashboard has session, driver, and lap selectors; there is no source selector.
- Old OpenF1 files and database rows remain archived without becoming a fallback.
- The database schema and existing FastF1 session IDs stay compatible.

The frontend now separates data loading, charts, controls, quality presentation,
and page layout. Clear formatting and ordinary loops/conditions improve
readability. [The code guide](CODE_GUIDE.md) explains how the pieces fit together.
Black and Prettier are development formatters, not additional application services.

Quality notes explain that totals cover the whole driver session and throttle 104
can indicate unavailable source data. Original samples and flags are preserved.

Verification evidence is saved in `data/fastf1-tests.xml` and
`data/fastf1-browser.json`, with desktop and mobile screenshots under `data/`.


## Completed verification

- 51 backend tests passed, including removed-provider rejection, transaction
  rollback, older FastF1 years, and preservation of legacy database records.
- 6 frontend data/plot checks passed.
- TypeScript checking and the production Vite build passed.
- 10 real-data headless Edge browser scenarios passed with zero JavaScript errors.
- Desktop and mobile screenshots were visually reviewed; selectors have no source field.
- Black and Prettier formatting checks passed.
- The actual saved pilot worked with `raceos ingest --offline`; `raceos import`
  skipped all three existing FastF1 bundles. Overall database row counts stayed unchanged.
- Runtime and installed package metadata both report version 0.3.1.

The active archive contains 2 sessions, 3 selected-driver
imports, and 52,310 FastF1 telemetry samples. Another 52,310 old
OpenF1 telemetry samples remain archived and are excluded from the application.

Existing terminal servers need a restart to load the new Python code. Stop the
server with Ctrl+C, run `python -m raceos serve` using the project virtual
environment, then refresh http://127.0.0.1:8000/.
