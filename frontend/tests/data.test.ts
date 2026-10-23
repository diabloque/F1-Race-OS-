import test from 'node:test';
import assert from 'node:assert/strict';
import { bestLap, lapTime, nearestSample, tracePath } from '../src/data';
import type { Lap, Sample } from '../src/types';

const origin = Date.parse('2025-09-06T14:00:00Z');
const sample = (seconds: number, speed: number | null = 100): Sample => ({
  source: 'fastf1',
  driver_number: 4,
  timestamp_utc: new Date(origin + seconds * 1000).toISOString(),
  speed_kmh: speed,
  throttle_pct: 104,
  brake_pressed: false,
  gear: 4,
  rpm: 10000,
  drs_code: 9,
  sample_index: 0,
  quality_flags: [],
});

test('lap times round correctly across minute boundaries and preserve unknowns', () => {
  assert.equal(lapTime(78.869), '1:18.869');
  assert.equal(lapTime(59.9996), '1:00.000');
  assert.equal(lapTime(null), '—');
});
test('default lap uses the fastest duration with a known telemetry boundary', () => {
  const laps: Lap[] = [
    {
      source: 'fastf1',
      driver_number: 4,
      lap_number: 1,
      lap_duration_s: null,
      lap_start_utc: new Date(origin).toISOString(),
    },
    {
      source: 'fastf1',
      driver_number: 4,
      lap_number: 2,
      lap_duration_s: 80,
      lap_start_utc: new Date(origin).toISOString(),
    },
    { source: 'fastf1', driver_number: 4, lap_number: 3, lap_duration_s: 79, lap_start_utc: null },
  ];
  assert.equal(bestLap(laps)?.lap_number, 2);
});
test('cursor follows elapsed time rather than assuming evenly spaced samples', () => {
  const rows = [sample(0), sample(0.24), sample(2.1)];
  assert.equal(nearestSample(rows, 0.6, origin), 1);
  assert.equal(nearestSample(rows, 2, origin), 2);
  assert.equal(nearestSample(rows, -10, origin), 0);
  assert.equal(nearestSample(rows, 100, origin), 2);
});
test('plots break across missing measurements and sampling gaps', () => {
  const rows = [sample(0), sample(0.24), sample(0.5, null), sample(0.7), sample(3)];
  const path = tracePath(rows, (row) => row.speed_kmh, origin, 4, 400);
  assert.equal((path.match(/M/g) ?? []).length, 3);
  assert.equal((path.match(/L/g) ?? []).length, 1);
});
test('throttle plotting keeps flagged values above 100', () => {
  assert.equal(
    tracePath([sample(0)], (row) => row.throttle_pct, origin, 1, 110),
    'M48.00,27.89',
  );
});
test('state channels use steps and retain unknown braking as a gap', () => {
  const rows = [
    sample(0),
    { ...sample(0.24), brake_pressed: true },
    { ...sample(0.5), brake_pressed: null },
    sample(0.7),
  ];
  const path = tracePath(
    rows,
    (row) => (row.brake_pressed == null ? null : Number(row.brake_pressed)),
    origin,
    1,
    1,
    true,
  );
  assert.equal((path.match(/M/g) ?? []).length, 2);
  assert.ok(path.includes('H268.80V22.00'));
  assert.ok(!path.includes('L'));
});
