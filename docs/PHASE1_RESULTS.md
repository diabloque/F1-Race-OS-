# Phase 1 completion

The real-data proof loaded **2025 Monza qualifying** for **Lando Norris (NOR / #4)**
from both OpenF1 and FastF1. Source files, FastF1 caches, exports, normalized records,
and a detailed report are saved locally under `data/`.

| Finding | OpenF1 | FastF1 |
|---|---:|---:|
| Drivers | 20 | 20 |
| Session lap records | 315 | 315 |
| Norris lap records | 21 | 21 |
| Norris telemetry samples | 17,452 | 17,452 |
| Median sampling interval | 0.240 s | 0.240 s |
| Longest sampling gap | 1.321 s | 1.321 s |
| Gaps longer than one second | 43 | 43 |
| Duplicate timestamps | 0 | 0 |
| Out-of-order timestamps | 0 | 0 |
| Throttle values outside 0–100 | 4,536 | 4,536 |
| Brake states left unknown | 4,538 | 0 |

The driver lists and scheduled session start times agree. All **15 corresponding
laps with known durations** agree to the stored precision. Six Norris lap records
do not have known durations and are retained without entering that comparison.
Equal counts and lap times do not mean both sources are independent or their
telemetry samples match at every timestamp.

## Data quality findings

Both sources contain **4,536 throttle samples with value 104**. RaceOS retains and
flags these records. It does not silently clamp them to 100 or calculate throttle
percentages from them in this phase.

OpenF1 brake values were 0 (11,725 samples), 100 (1,189 samples), and 104 (4,538
samples). Its documented state mapping defines 0 and 100. RaceOS therefore leaves
104 as an unknown normalized brake state while retaining the original records.
FastF1 supplies boolean brake values and has no missing brake states in this pilot.
This is a source-semantics discrepancy, not evidence that the samples were absent.

The sources also contain 43 sampling gaps longer than one second. There is no
interpolation, cross-provider merge, or fabricated replacement in Phase 1.

## Validation

- The online command successfully retrieved both providers' real session data.
- `python -m raceos ingest --offline` successfully repeated the comparison using saved bundles.
- 20 offline automated checks passed, covering UTC timestamps, missing values,
  braking semantics, sampling anomalies, original-response caching, rate-limit
  retries, ambiguous session rejection, provider mismatches, corresponding-lap
  matching, and offline execution without provider calls.
- `python -m pip check` reported no broken requirements.

The detailed generated report is at
`data/2025-monza-qualifying-nor-9ab87e0b/reports/comparison.md`, with structured
results in `comparison.json`. The report is regenerated on each command run.

## Proposed next step

Phase 2 adds database-backed imports and API endpoints. The two adapters remain
separate, with an explicit source preference and documented quality handling.
FastF1's boolean braking is useful for historical analysis; OpenF1 exposes a simple
API for race-state channels. The throttle encoding needs an explicit policy before
calculating full-throttle metrics. Replay must later define when lap/stint results
become available rather than exposing final results at their starting timestamps.

Phase 2 has not been started and requires user approval.
