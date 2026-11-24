import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pitStrategy, pressureModel, temperatureModel } from '../src/strategy.ts';

test('gas law uses absolute pressure and invalid contact area is unavailable', () => {
  const same = pressureModel(1.6, 25, 25, 8000, 12000, 300);
  assert.ok(Math.abs(same.finalPressure - 1.6) < 1e-9);
  assert.equal(same.load, 20000);
  assert.equal(pressureModel(0.1, 200, -20, 8000, 0, 0).contactArea, null);
});

test('temperature damage is cumulative and adjustable', () => {
  const noDamage = temperatureModel(20, 20, 0, 95, 115, 3, 0, 0);
  const damage = temperatureModel(20, 20, 0, 95, 115, 3, 0.1, 0);
  assert.ok(damage[2].grip < noDamage[2].grip);
  assert.ok(damage[2].damage > damage[0].damage);
});

test('pit loss is applied once and traffic only on the out-lap', () => {
  const base = pitStrategy(4, 2, 100, 0, 0, 90, 0, 20, 2, 3);
  assert.deepEqual(base, [100, 220, 315, 405]);
});
