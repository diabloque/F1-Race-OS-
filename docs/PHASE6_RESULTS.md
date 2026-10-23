# Phase 6: completed-lap comparison milestone

Completed 2026-10-22 in `E:\Personal project\F1 RaceOs`.

The Lap comparison view compares two completed timed laps from one remotely
opened session. It supports different drivers and different laps from the same
driver. It shares the replay clock, pauses playback when opened, and provides
play/seek controls. Compared laps stay selected as playback advances.

## Timing and availability

The view lists only laps with a positive reported time, valid start/end window,
and an end at or before the replay clock. Generated retirement laps are excluded.
The comparison API validates both selections before loading either telemetry
file. A guessed future lap ID is rejected. Backward seeks also hide already
loaded results whose laps are not yet complete at the new clock.

Reported sector times come directly from `s1`, `s2`, and `s3`; missing sectors
stay unknown. Lap and sector deltas are B minus A, so negative means B was
quicker. Values are not forced to sum when the source is incomplete or differs.
The view does not use final deletion/penalty decisions to filter earlier laps.
Recorded pit laps or laps later deleted by officials can therefore be selected;
this is a recorded-time comparison, not an official valid-lap classification.
Known pit entry/exit laps receive a note after completion.

## Input calculations

Percentages are time weighted, not sample-count percentages. For consecutive
samples no more than one second apart, the left sample's input applies across
that interval. Duplicate timestamps have zero duration; the last duplicate
controls the next interval. Larger gaps and invalid/unknown channel states
contribute no known time. No tail extrapolation or post-finish samples are used.

Full throttle means a valid pedal reading from 99 through 100%. Braking means
the source's binary applied state. Brake pressure is not estimated. Each channel
reports active seconds, known seconds, coverage as a percentage of the recorded
lap window, and active percentage of covered time. The UI states the denominator
and shows coverage. Zero coverage produces an unknown percentage. This avoids
silently assuming missing data was zero throttle or released brakes.

The timing window is lap end minus lap start. Reported lap time can differ;
large differences produce a warning. These percentages summarize prepared
sampled data with a stated hold rule, rather than precise pedal transition
measurements. Upstream interpolation remains part of the source.

Lap/sector differences can reflect tyres, fuel, traffic, weather, and other
conditions. They are not isolated measures of driver skill or tyre degradation.
The distance-aligned track overlay is now implemented below. Advanced estimates
and strategy models remain future work.

## Implementation

- `src/raceos/analysis.py`: eligible laps, validated comparison models, timing
  deltas, coverage, and input metrics.
- `src/raceos/providers/tracinginsights.py`: preserves recorded sector times.
- `src/raceos/api.py`: completed-lap choices and comparison routes, both no-store.
- `frontend/src/components/PerformanceAnalysis.tsx`: selectors, shared clock,
  results, and frontend availability guards.
- `frontend/src/App.tsx`: navigation and pausing on entry to comparison.

No dependencies or database services were added. Only selected lap files are
loaded through the existing cache on E:, which remains capped at 200 MiB. The
legacy FastF1/SQLite archive is retained, with no new telemetry imports. The
comparison feature uses remotely opened TracingInsights sessions.

## Verification

115 Python tests passed, including uneven interval weighting, missing channels,
large gaps, duplicate samples, missing sectors, delta sign, self comparison,
future IDs rejected before downloads, missing telemetry, and API validation.
10 frontend tests and the TypeScript production build passed.

23 real-data browser scenarios passed in installed headless Edge. New checks
cover real driver/sector differences and percentages, same-driver comparisons,
backward seeking, a forged future-lap API request, and mobile layout. Desktop
and mobile screenshots were inspected; no JavaScript errors or horizontal
overflow were reported. Existing replay, tyres, weather, race control, and
cache-limit checks also passed.

A separate real-data check compared Norris lap 20 and Verstappen lap 17 from
2025 Monza qualifying. Recorded times are 78.869 and 78.792 seconds: B minus A
is -0.077 seconds. Sector deltas are -0.116, +0.045, and -0.006 seconds. Covered
time is 100% for both input channels in this example. Full throttle is 70.859%
for Norris and 76.085% for Verstappen; braking is 11.664% and 14.062%.

Evidence:

- `data/phase6-validation.json`
- `data/remote-replay-browser.json`
- `data/phase6-comparison-desktop.png`
- `data/phase6-comparison-mobile.png`

Source field definitions: [TracingInsights data reference](https://github.com/TracingInsights/2026/blob/main/DATA_REFERENCE.md).

## Distance overlay update

The comparison now includes the circuit with local time gain/loss segments.
Each completed lap is filtered to its start/end, then its monotonic recorded
`distance` span is normalized to 0-100%. Different recorded path lengths are
therefore compared by progress, not assumed to be identical physical distances.
The slider's approximate metres use the mean of the two observed spans.

201 progress points give 0.5% segments. Time and position are interpolated
between supported source samples; throttle and binary brake hold the preceding
sample. Missing distance, positions, or time gaps longer than one second break
supported segments. Reversed distance or incomplete endpoints disable the map
without hiding recorded timing/input comparisons. No extrapolation is used.

Cumulative delta is B elapsed time minus A elapsed time. Color is the _change_
in that delta over one segment: green when B gains more than 0.010 seconds,
red when B loses more than 0.010 seconds, neutral within that tolerance.
Hover or the keyboard/touch distance slider shows cumulative delta plus each
lap's speed, throttle, and brake state. Missing inputs stay unknown. Sampling
endpoints may differ from reported lap time; the curve is not forced to match.
The original replay track and its throttle/brake legend are unchanged.

Ten additional backend tests cover normalization, local-versus-cumulative delta,
held inputs, interpolation, gaps, missing/reversed/partial distance, duplicate
distances, unavailable geometry, and exclusion of post-finish padding.

The updated production build passed. All 125 Python tests, 10 frontend tests,
and 24 real-data Edge browser scenarios passed. The additional browser scenario
checks gain/loss colors, distance slider agreement with the API, and pointer
inspection. Desktop and 390 px mobile screenshots were inspected; no overflow
or JavaScript errors were found. Existing backward-seek guards cover the whole
comparison, including the track. Evidence is in the existing comparison PNGs
and `data/remote-replay-browser.json`.
