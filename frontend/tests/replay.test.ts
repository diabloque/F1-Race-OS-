import assert from 'node:assert/strict';
import test from 'node:test';
import { advanceTime, clampTime, clockLabel, fitTrack, inputColor, project } from '../src/replay';

test('virtual clock scales elapsed wall time and clamps at recording boundaries', () => {
  assert.equal(advanceTime(10, 2.5, 4, 100), 20);
  assert.equal(advanceTime(10, 2.5, 0.25, 100), 10.625);
  assert.equal(advanceTime(99, 1, 4, 100), 100);
  assert.equal(advanceTime(10, -2, 4, 100), 10);
  assert.equal(clampTime(-2, 100), 0);
  assert.equal(clampTime(NaN, 100), 0);
});
test('clock keeps millisecond precision across minute and hour boundaries', () => {
  assert.equal(clockLabel(61.125), '01:01.125');
  assert.equal(clockLabel(3661.5), '1:01:01.500');
});
test('track projection preserves aspect ratio and fits the viewport', () => {
  const points = [
    { x: -500, y: -100 },
    { x: 500, y: -100 },
    { x: -500, y: 100 },
  ];
  const layout = fitTrack(points);
  const [a, b, c] = points.map((p) => project(p, layout));
  assert.equal((b.x - a.x) / (a.y - c.y), 5);
  assert.ok([a, b, c].every((p) => p.x >= 0 && p.x <= 1000 && p.y >= 0 && p.y <= 600));
  assert.equal(
    fitTrack([
      { x: 0, y: 0 },
      { x: 100, y: 1000 },
    ]).rotate,
    true,
  );
});
test('braking overrides throttle and unknown inputs remain unknown', () => {
  assert.equal(inputColor({ throttle_pct: 104, brake_pressed: false }), '#708096');
  assert.equal(inputColor({ throttle_pct: null, brake_pressed: null }), '#708096');
  assert.equal(inputColor({ throttle_pct: 50, brake_pressed: null }), '#708096');
  assert.equal(inputColor({ throttle_pct: 99, brake_pressed: true }), '#ff776d');
  assert.equal(inputColor({ throttle_pct: 99, brake_pressed: false }), '#66d7b0');
  assert.equal(inputColor({ throttle_pct: 0, brake_pressed: false }), '#f5bf62');
});
