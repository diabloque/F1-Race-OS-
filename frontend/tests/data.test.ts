import test from 'node:test';
import assert from 'node:assert/strict';
import { lapTime } from '../src/data';

test('lap times round correctly across minute boundaries and preserve unknowns', () => {
  assert.equal(lapTime(78.869), '1:18.869');
  assert.equal(lapTime(59.9996), '1:00.000');
  assert.equal(lapTime(0), '0:00.000');
  assert.equal(lapTime(undefined), '\u2014');
  assert.equal(lapTime(Number.NaN), '\u2014');
  assert.equal(lapTime(Number.POSITIVE_INFINITY), '\u2014');
  assert.equal(lapTime(null), '—');
});
