import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdirSync, openSync, writeFileSync, closeSync, readFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '../..');
const data = path.join(root, 'data');
const temporary = path.join(data, 'tmp');
mkdirSync(temporary, { recursive: true });
// Keep browser profiles, server logs, and screenshots beside this project.
process.env.TEMP = temporary;
process.env.TMP = temporary;
const socket = net.createServer();
await new Promise((resolve) => socket.listen(0, '127.0.0.1', resolve));
const port = socket.address().port;
await new Promise((resolve) => socket.close(resolve));
const base = `http://127.0.0.1:${port}`;
const python = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const log = openSync(path.join(data, 'remote-replay-preview.log'), 'w');
const backend = spawn(python, ['-m', 'raceos', 'serve', '--port', String(port)], {
  cwd: root,
  windowsHide: true,
  stdio: ['ignore', log, log],
  env: process.env,
});
const checks = [],
  errors = [];
const checkpoint = (name) => {
  checks.push(name);
  console.log(`PASS ${name}`);
};
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let browser, page;
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (backend.exitCode != null)
      throw new Error('Preview exited: see data/remote-replay-preview.log.');
    try {
      if ((await fetch(base + '/api/health')).ok) break;
    } catch {}
    if (attempt === 99) throw new Error('Preview did not start.');
    await delay(200);
  }
  const get = async (route) => {
    const response = await fetch(base + route);
    assert.equal(response.status, 200, route);
    return response.json();
  };
  assert.equal((await get('/api/health')).version, '0.4.1');
  const sessions = (await get('/api/library')).items;
  const monza = sessions.find(
    (s) => s.year === 2025 && s.location === 'Monza' && s.name === 'Qualifying',
  );
  const second = sessions.find(
    (s) => s.year === 2024 && s.location === 'Monza' && s.name === 'Qualifying',
  );
  assert.ok(monza && second, 'Both cached Monza sessions must be prepared.');
  const prefix = `/api/sessions/${monza.id}`;
  const metadata = await get(prefix + '/replay');
  assert.equal(metadata.drivers.length, 20);
  assert.equal(metadata.source, 'tracinginsights');
  assert.equal(metadata.prepared, true);
  browser = await chromium.launch({
    headless: true,
    channel:
      process.env.RACEOS_BROWSER_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : undefined),
  });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1120 } });
  page = await context.newPage();
  page.setDefaultTimeout(90000);
  page.setDefaultNavigationTimeout(90000);
  page.on('pageerror', (error) => errors.push(error.message));
  const response = await page.goto(base, { waitUntil: 'networkidle' });
  assert.equal(response.status(), 200);
  await page.getByRole('heading', { name: 'Race workspace', exact: true }).waitFor();
  const openSession = async (session) => {
    await page
      .getByRole('combobox', { name: 'Year', exact: true })
      .selectOption(String(session.year));
    await page.waitForFunction((round) => {
      const select = document.querySelector('select[aria-label="Grand Prix"]');
      return (
        select &&
        !select.disabled &&
        [...select.options].some((option) => option.value === String(round))
      );
    }, session.round);
    await page
      .getByRole('combobox', { name: 'Grand Prix', exact: true })
      .selectOption(String(session.round));
    await page
      .getByRole('combobox', { name: 'Session type', exact: true })
      .selectOption(session.name);
    const previous = await page
      .getByRole('region', { name: 'Session selection', exact: true })
      .getAttribute('data-session-id');
    if (previous !== session.id) {
      assert.ok(await page.getByRole('combobox', { name: 'Driver', exact: true }).isDisabled());
    }
    await page.getByRole('button', { name: 'Open session', exact: true }).click();
    await page.waitForFunction((id) => {
      const panel = document.querySelector('.session-controls');
      const driver = document.querySelector('select[aria-label="Driver"]');
      return panel?.dataset.sessionId === id && driver && !driver.disabled;
    }, session.id);
    await page.getByRole('group', { name: 'Circuit track', exact: true }).waitFor();
    await page.waitForFunction(() =>
      document.querySelector('[data-testid="replay-utc"]')?.textContent.includes('UTC'),
    );
  };
  assert.equal(
    await page.getByRole('region', { name: 'Session selection', exact: true }).count(),
    1,
  );
  assert.equal(await page.getByRole('combobox', { name: 'Session', exact: true }).count(), 0);
  assert.equal(await page.locator('.remote-session-picker').count(), 0);
  await page.waitForFunction(
    () => !document.querySelector('select[aria-label="Grand Prix"]')?.disabled,
  );
  const activeId = await page.locator('.session-controls').getAttribute('data-session-id');
  const activeSession = sessions.find((session) => session.id === activeId);
  assert.equal(
    await page.getByRole('combobox', { name: 'Year', exact: true }).inputValue(),
    String(activeSession.year),
  );
  assert.equal(
    await page.getByRole('combobox', { name: 'Grand Prix', exact: true }).inputValue(),
    String(activeSession.round),
  );
  assert.equal(
    await page.getByRole('combobox', { name: 'Session type', exact: true }).inputValue(),
    activeSession.name,
  );
  checkpoint(
    'One unified selection bar matches the active replay with no duplicate session selector',
  );
  await openSession(monza);
  await page.getByRole('group', { name: 'Circuit track', exact: true }).waitFor();
  assert.equal(await page.getByRole('combobox', { name: 'Driver', exact: true }).inputValue(), '4');
  assert.equal(
    await page.getByRole('combobox', { name: 'Driver', exact: true }).locator('option').count(),
    20,
  );
  assert.equal(await page.getByRole('img', { name: 'Speed telemetry trace' }).count(), 0);
  checkpoint('Root page shows actual circuit geometry and all 20 remote drivers');

  const seconds = async () =>
    Number(await page.getByTestId('replay-time').getAttribute('data-seconds'));
  const changeTimeline = async (value) =>
    page.getByRole('slider', { name: 'Replay timeline' }).evaluate((element, next) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(
        element,
        String(next),
      );
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
    }, value);
  const seek = async (value) => {
    await changeTimeline(value);
    await page.waitForFunction((target) => {
      const clock = document.querySelector('[data-testid="replay-time"]');
      const utc = document.querySelector('[data-testid="replay-utc"]');
      return (
        Math.abs(Number(clock?.getAttribute('data-seconds')) - target) < 0.002 &&
        utc?.textContent.includes('UTC')
      );
    }, value);
    assert.equal(await page.getByRole('button', { name: 'Play replay', exact: true }).count(), 1);
  };
  const initial = (Date.parse(metadata.initial_utc) - Date.parse(metadata.start_utc)) / 1000;
  const target = initial + 35;
  const expectedAt = new Date(Date.parse(metadata.start_utc) + target * 1000).toISOString();
  const expected = await get(
    prefix + `/replay/frame?at=${encodeURIComponent(expectedAt)}&driver_number=4`,
  );
  const checkEngineering = async (frame) => {
    const car = frame.drivers.find((car) => car.number === frame.focus_driver_number);
    const label = car.tyres?.compound;
    const compound = label
      ? label.charAt(0) + label.slice(1).toLowerCase().replaceAll('_', ' ')
      : 'Unknown';
    assert.equal(await page.getByTestId('tyre-compound').textContent(), compound);
    assert.equal(
      await page.getByTestId('tyre-age').textContent(),
      String(car.tyres?.age_laps ?? '\u2014'),
    );
    assert.equal(
      await page.getByTestId('tyre-stint').textContent(),
      String(car.tyres?.stint ?? '\u2014'),
    );
    assert.equal(
      await page.getByTestId('pit-visits').textContent(),
      String(car.tyres?.pit_visits ?? '\u2014'),
    );
    const tyreDate = await page
      .getByRole('region', { name: 'Tyres and stint', exact: true })
      .getAttribute('data-observed-at');
    assert.ok(!tyreDate || Date.parse(tyreDate) <= Date.parse(frame.at_utc));
    assert.equal(
      await page.getByTestId('track-temperature').textContent(),
      frame.weather?.track_temp_c == null
        ? '\u2014'
        : `${frame.weather.track_temp_c.toFixed(1)}\u00b0C`,
    );
    const weatherDate = await page.getByTestId('weather-panel').getAttribute('data-observed-at');
    assert.ok(!weatherDate || Date.parse(weatherDate) <= Date.parse(frame.at_utc));
    const messages = await page
      .getByTestId('race-control-messages')
      .locator('li')
      .evaluateAll((nodes) =>
        nodes.map((node) => ({ id: Number(node.dataset.messageId), time: node.dataset.issuedAt })),
      );
    assert.deepEqual(
      messages.map((message) => message.id),
      frame.race_control.map((message) => message.id),
    );
    assert.ok(messages.every((message) => Date.parse(message.time) <= Date.parse(frame.at_utc)));
  };
  await seek(target);
  await checkEngineering(expected);
  checkpoint(
    'Tyres, weather observations, and issued race-control messages match the qualifying replay clock',
  );
  const nor = expected.drivers.find((d) => d.number === 4);
  const marker = page.getByTestId('car-4');
  assert.equal(Number(await marker.getAttribute('data-x')), nor.position.x);
  assert.equal(Number(await marker.getAttribute('data-y')), nor.position.y);
  assert.equal(
    await page.getByTestId('speed-readout').textContent(),
    Math.round(nor.telemetry.speed_kmh).toLocaleString('en-US') + 'km/h',
  );
  const markers = await page
    .locator('[data-testid^="car-"]')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-at')));
  assert.ok(
    markers.length > 0 && markers.every((time) => Date.parse(time) <= Date.parse(expectedAt)),
  );
  const rows = await page
    .getByTestId('completed-laps')
    .locator('[data-completed-at]')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.completedAt));
  assert.ok(rows.every((time) => Date.parse(time) <= Date.parse(expectedAt)));
  const trail = await page
    .getByTestId('input-trail')
    .evaluateAll((nodes) => nodes.map((n) => n.dataset.at));
  assert.ok(trail.length > 0 && trail.every((time) => Date.parse(time) <= Date.parse(expectedAt)));
  assert.equal(await page.getByTestId('drs-readout').count(), 0);
  assert.equal(await page.getByTestId('overtake-readout').count(), 0);
  assert.equal(await page.getByRole('region', { name: 'Race timing', exact: true }).count(), 0);
  checkpoint('Map markers, inputs, trail, and lap results match the same past-only API snapshot');

  const damaged = structuredClone(expected);
  const badIndex = Math.floor(damaged.trail.length / 2);
  assert.ok(badIndex > 2 && damaged.trail.length > badIndex + 2);
  damaged.trail[badIndex].x += 1000000;
  damaged.trail[badIndex].y += 1000000;
  damaged.elapsed_s = target + 0.001;
  damaged.at_utc = new Date(Date.parse(expected.at_utc) + 1).toISOString();
  await page.route('**/replay/frame?*', (route) => route.fulfill({ json: damaged }));
  await seek(target + 0.001);
  const drawn = await page
    .getByTestId('input-trail')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-at')));
  assert.ok(drawn.length > 0);
  assert.ok(!drawn.includes(damaged.trail[badIndex].timestamp_utc));
  assert.ok(!drawn.includes(damaged.trail[badIndex + 1].timestamp_utc));
  await page.unroute('**/replay/frame?*');
  await seek(target);
  checkpoint(
    'An impossible position jump breaks both adjacent trail lines without changing the recorded inputs or replay clock',
  );

  assert.equal(
    await page.getByRole('complementary', { name: 'Selected driver details' }).count(),
    1,
  );
  assert.equal(await page.getByTestId('speed-readout').count(), 1);
  assert.equal(await page.getByTestId('throttle-readout').count(), 1);
  assert.equal(await page.getByTestId('brake-readout').count(), 1);
  await page.getByText('Braking pressure is unavailable.', { exact: false }).waitFor();
  const outlineBefore = await page.getByTestId('circuit-outline').getAttribute('points');
  const visibleLabels = () =>
    page
      .locator('.driver-map-label')
      .evaluateAll((nodes) => nodes.filter((n) => getComputedStyle(n).opacity === '1').length);
  assert.equal(await visibleLabels(), 1);
  await page.getByRole('checkbox', { name: 'Show all driver labels' }).check();
  assert.equal(await visibleLabels(), markers.length);
  await page.getByRole('checkbox', { name: 'Show all driver labels' }).uncheck();
  await page.getByRole('checkbox', { name: 'Selected car only' }).check();
  assert.equal(await page.locator('[data-testid^="car-"]').count(), 1);
  assert.equal(await page.getByTestId('circuit-outline').getAttribute('points'), outlineBefore);
  await page.getByRole('checkbox', { name: 'Selected car only' }).uncheck();
  checkpoint('One driver panel shows unique readouts and map controls reduce traffic clutter');

  await seek(target + 600);
  await seek(target);
  assert.equal(Number(await marker.getAttribute('data-x')), nor.position.x);
  assert.equal(
    await page.getByTestId('speed-readout').textContent(),
    Math.round(nor.telemetry.speed_kmh).toLocaleString('en-US') + 'km/h',
  );
  checkpoint('Backward seeking restores the same recorded coordinates and readouts');

  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await delay(1200);
  await page.getByRole('button', { name: 'Pause replay', exact: true }).click();
  await delay(250);
  const paused = await seconds();
  assert.ok(paused > target + 0.5 && paused < target + 3);
  await delay(450);
  assert.equal(await seconds(), paused);
  await page.getByRole('combobox', { name: 'Playback speed' }).selectOption('4');
  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await delay(1200);
  await page.getByRole('button', { name: 'Pause replay', exact: true }).click();
  await delay(250);
  const accelerated = await seconds();
  assert.ok(accelerated > paused + 3 && accelerated < paused + 9);
  checkpoint('Play, pause, and 4x speed advance one elapsed-time clock');

  const beforeFocus = await seconds();
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/replay/frame?') && r.url().includes('driver_number=1') && r.ok(),
    ),
    page.getByRole('combobox', { name: 'Driver', exact: true }).selectOption('1'),
  ]);
  assert.equal(await seconds(), beforeFocus);
  assert.equal(await page.getByRole('combobox', { name: 'Driver', exact: true }).inputValue(), '1');
  await page.getByRole('combobox', { name: 'Driver', exact: true }).selectOption('4');
  await delay(250);
  checkpoint('Following another driver preserves the session clock');

  const results = await get(
    prefix + `/replay/frame?at=${encodeURIComponent(metadata.end_utc)}&driver_number=4`,
  );
  const result = results.completed_laps.find((lap) => lap.lap_number === 2);
  const timed = { lap_number: result.lap_number };
  const finish = Date.parse(result.completed_at_utc);
  const finishSeconds = (finish - Date.parse(metadata.start_utc)) / 1000;
  await seek(finishSeconds - 0.01);
  assert.equal(
    await page
      .getByTestId('completed-laps')
      .getByText(`Lap ${timed.lap_number}`, { exact: true })
      .count(),
    0,
  );
  await seek(finishSeconds + 0.01);
  assert.equal(
    await page
      .getByTestId('completed-laps')
      .getByText(`Lap ${timed.lap_number}`, { exact: true })
      .count(),
    1,
  );
  await page.getByRole('combobox', { name: 'Jump to lap' }).selectOption(String(timed.lap_number));
  await delay(300);
  assert.equal(
    await page
      .getByTestId('completed-laps')
      .getByText(`Lap ${timed.lap_number}`, { exact: true })
      .count(),
    0,
  );
  checkpoint('Lap result appears after its finish and disappears when seeking before it');

  await seek(metadata.duration_s - 0.15);
  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await page.getByRole('button', { name: 'Play replay', exact: true }).waitFor();
  assert.ok(Math.abs((await seconds()) - metadata.duration_s) < 0.002);
  await page.getByRole('button', { name: 'Jump to start' }).click();
  await page.waitForFunction(
    () =>
      Number(
        document.querySelector('[data-testid="replay-time"]')?.getAttribute('data-seconds'),
      ) === 0,
  );
  await delay(250);
  assert.equal(await page.getByTestId('best-completed-lap').textContent(), '\u2014');
  checkpoint('Playback stops at the end and start resets future lap results');

  await openSession(second);
  await page.getByRole('group', { name: 'Circuit track', exact: true }).waitFor();
  assert.equal(
    await page.getByRole('combobox', { name: 'Driver', exact: true }).locator('option').count(),
    20,
  );
  assert.equal(await page.getByRole('button', { name: 'Data quality', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Session library', exact: true }).click();
  await page
    .locator('.session-tile')
    .filter({ hasText: '2025 SEASON' })
    .filter({ hasText: 'Qualifying' })
    .click();
  await page.getByRole('group', { name: 'Circuit track', exact: true }).waitFor();
  await page.waitForFunction(
    () =>
      document.querySelector('select[aria-label="Year"]')?.value === '2025' &&
      !document.querySelector('select[aria-label="Grand Prix"]')?.disabled,
  );
  assert.equal(
    await page.getByRole('combobox', { name: 'Session type', exact: true }).inputValue(),
    'Qualifying',
  );
  checkpoint('Both full-grid sessions and library navigation work without a data quality page');

  await page.route('**/replay/frame?*', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Replay temporarily unavailable' }),
    }),
  );
  await changeTimeline(target + 10);
  await page.getByRole('alert').filter({ hasText: 'Replay temporarily unavailable' }).waitFor();
  await page.unroute('**/replay/frame?*');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await page.getByRole('alert').waitFor({ state: 'hidden' });
  await page.getByRole('group', { name: 'Circuit track' }).waitFor();
  checkpoint('Replay errors are visible and retry recovers');

  const race = sessions.find(
    (session) => session.year === 2022 && session.name === 'Race' && session.location === 'Monza',
  );
  assert.ok(race, 'A real Monza race must be imported.');
  const racePrefix = `/api/sessions/${race.id}`;
  const raceMetadata = await get(racePrefix + '/replay');
  assert.equal(raceMetadata.drivers.length, 20);
  assert.equal(raceMetadata.source, 'tracinginsights');
  await openSession(race);
  await seek(0);
  const gridFrame = await get(
    racePrefix + `/replay/frame?at=${encodeURIComponent(raceMetadata.start_utc)}&driver_number=4`,
  );
  assert.equal(gridFrame.race_timing.basis, 'starting_grid');
  assert.equal(gridFrame.race_timing.grid_status, 'ready');
  assert.equal(gridFrame.race_timing.rows[0].code, 'LEC');
  assert.ok(
    gridFrame.race_timing.rows.every(
      (row) => row.gap_to_leader_s == null && row.interval_s == null,
    ),
  );
  await page.getByTestId('timing-phase').filter({ hasText: 'Starting grid -' }).waitFor();
  const initialRows = await page
    .getByTestId('race-timing')
    .locator('tbody tr')
    .evaluateAll((nodes) =>
      nodes.map((node) => ({
        number: Number(node.dataset.driver),
        position: node.dataset.position ? Number(node.dataset.position) : null,
      })),
    );
  assert.deepEqual(
    initialRows,
    gridFrame.race_timing.rows.map((row) => ({ number: row.number, position: row.position })),
  );
  assert.equal(
    await page.getByTestId('race-timing').getByText('Leader', { exact: true }).count(),
    0,
  );
  await page
    .getByRole('region', { name: 'Race timing', exact: true })
    .screenshot({ path: path.join(data, 'starting-grid-desktop.png') });
  checkpoint(
    'Starting grid appears immediately in grid order with blank gaps and no premature Leader label',
  );
  const raceTime =
    (Date.parse(raceMetadata.initial_utc) - Date.parse(raceMetadata.start_utc)) / 1000 + 150;
  await seek(raceTime);
  const raceAt = new Date(Date.parse(raceMetadata.start_utc) + raceTime * 1000).toISOString();
  const raceFrame = await get(
    racePrefix + `/replay/frame?at=${encodeURIComponent(raceAt)}&driver_number=4`,
  );
  const raceCar = raceFrame.drivers.find((driver) => driver.number === 4);
  assert.ok(raceFrame.race_timing.rows.some((row) => row.interval_s > 0));
  assert.equal(raceFrame.race_timing.rows.filter((row) => row.position != null).length, 20);

  assert.equal(Number(await page.getByTestId('car-4').getAttribute('data-x')), raceCar.position.x);
  assert.equal(
    await page.getByTestId('speed-readout').textContent(),
    Math.round(raceCar.telemetry.speed_kmh).toLocaleString('en-US') + 'km/h',
  );
  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await delay(800);
  await page.getByRole('button', { name: 'Pause replay', exact: true }).click();
  await delay(200);
  assert.ok((await seconds()) > raceTime);
  await seek(raceTime);
  checkpoint('Real Monza race replays all 20 drivers with source coordinates and working playback');
  const checkTiming = async (frame) => {
    const actual = await page
      .getByTestId('race-timing')
      .locator('tbody tr')
      .evaluateAll((nodes) =>
        nodes.map((node) => ({
          number: Number(node.dataset.driver),
          position: node.dataset.position ? Number(node.dataset.position) : null,
          timing_at_utc: node.dataset.timingAt || null,
          gap_to_leader_s: node.dataset.gap ? Number(node.dataset.gap) : null,
          interval_s: node.dataset.interval ? Number(node.dataset.interval) : null,
        })),
      );
    assert.equal(actual.length, 20);
    assert.deepEqual(
      actual,
      frame.race_timing.rows.map((row) => ({
        number: row.number,
        position: row.position,
        timing_at_utc: row.timing_at_utc,
        gap_to_leader_s: row.gap_to_leader_s,
        interval_s: row.interval_s,
      })),
    );
    assert.ok(
      actual.every(
        (row) =>
          row.timing_at_utc == null || Date.parse(row.timing_at_utc) <= Date.parse(frame.at_utc),
      ),
    );
  };
  await checkEngineering(raceFrame);
  const pitAudit = JSON.parse(readFileSync(path.join(data, 'phase5-validation.json'), 'utf8'));
  const pitExit = pitAudit.pit_exit_seconds;
  const pitFrame = async (seconds) =>
    get(
      racePrefix +
        `/replay/frame?at=${encodeURIComponent(new Date(Date.parse(raceMetadata.start_utc) + seconds * 1000).toISOString())}&driver_number=4`,
    );
  const beforePit = await pitFrame(pitExit - 0.001);
  await seek(pitExit - 0.001);
  await checkEngineering(beforePit);
  assert.equal(await page.getByTestId('tyre-compound').textContent(), 'Medium');
  assert.equal(await page.getByTestId('pit-visits').textContent(), '0');
  assert.equal(await page.getByTestId('pit-status').textContent(), 'In pit lane');
  const afterPit = await pitFrame(pitExit);
  await seek(pitExit);
  await checkEngineering(afterPit);
  assert.equal(await page.getByTestId('tyre-compound').textContent(), 'Soft');
  assert.equal(await page.getByTestId('tyre-age').textContent(), '2');
  assert.equal(await page.getByTestId('tyre-stint').textContent(), '2');
  assert.equal(await page.getByTestId('pit-visits').textContent(), '1');
  assert.equal(await page.getByTestId('pit-status').count(), 0);
  await seek(pitExit - 0.001);
  await checkEngineering(beforePit);
  checkpoint(
    'A real pit exit reveals the used soft set and completed visit only at its timestamp; backward seeks restore the old set',
  );
  await page.route('**/replay/frame?*', async (route) => {
    const response = await route.fetch();
    const frame = await response.json();
    await route.fulfill({
      response,
      json: {
        ...frame,
        weather: null,
        weather_status: 'missing',
        race_control: [],
        race_control_status: 'unavailable',
      },
    });
  });
  await seek(raceTime + 1);
  await page.getByText('Weather data unavailable', { exact: true }).waitFor();
  await page.getByText('Race-control data unavailable.', { exact: true }).waitFor();
  assert.ok((await page.locator('[data-testid^="car-"]').count()) > 0);
  await page.unroute('**/replay/frame?*');
  await seek(raceTime);
  await checkEngineering(raceFrame);
  checkpoint(
    'Missing optional weather and race-control data leaves the track and driver replay usable',
  );
  await checkTiming(raceFrame);
  await seek(raceTime + 120);
  await seek(raceTime);
  await checkTiming(raceFrame);
  const follow = raceFrame.race_timing.rows.find((row) => row.number !== 4);
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/replay/frame?') &&
        response.url().includes(`driver_number=${follow.number}`) &&
        response.ok(),
    ),
    page.getByRole('button', { name: `Follow ${follow.name}`, exact: true }).click(),
  ]);
  assert.equal(
    await page.getByRole('combobox', { name: 'Driver', exact: true }).inputValue(),
    String(follow.number),
  );
  assert.equal(await seconds(), raceTime);
  assert.equal(await page.getByTestId('drs-readout').count(), 0);
  checkpoint(
    'Race timing matches all 20 API rows, stays past-only on backward seeks, and selects a driver without changing the clock',
  );
  await page.getByRole('combobox', { name: 'Driver', exact: true }).selectOption('4');

  await openSession({ id: 'ti-2018-14-R', year: 2018, round: 14, name: 'Race' });
  const kinds = await page
    .getByRole('combobox', { name: 'Session type', exact: true })
    .locator('option')
    .allTextContents();
  assert.deepEqual(new Set(kinds), new Set(['Race', 'Qualifying']));
  assert.ok((await page.locator('[data-testid^="car-"]').count()) > 0);
  checkpoint('The unified picker opens a 2018 race remotely and offers no practice sessions');
  await openSession(race);
  await seek(raceTime);
  await checkEngineering(raceFrame);
  const analysisTime = raceTime + 600;
  await seek(analysisTime);
  const navigation = page.getByRole('navigation', { name: 'Workspace navigation' });
  assert.equal(await navigation.getByRole('button').count(), 2);
  assert.equal(
    await navigation.getByRole('button', { name: 'Lap comparison', exact: true }).count(),
    0,
  );
  assert.equal(await page.getByRole('slider', { name: 'Replay timeline', exact: true }).count(), 1);
  assert.equal(await page.getByTestId('replay-utc').count(), 1);
  assert.equal(
    await page.getByRole('region', { name: 'Session selection', exact: true }).count(),
    1,
  );
  assert.equal(await page.getByRole('region', { name: 'Track replay', exact: true }).count(), 1);
  assert.equal(await page.getByRole('region', { name: 'Lap comparison', exact: true }).count(), 1);
  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await page.getByRole('link', { name: 'Lap comparison', exact: true }).click();
  await page.waitForFunction(
    (before) =>
      Number(document.querySelector('[data-testid="replay-time"]')?.getAttribute('data-seconds')) >
      before + 0.2,
    analysisTime,
  );
  assert.equal(await page.getByRole('button', { name: 'Pause replay', exact: true }).count(), 1);
  assert.equal(
    await navigation
      .getByRole('button', { name: 'Race workspace', exact: true })
      .getAttribute('aria-current'),
    'page',
  );
  await page.getByRole('button', { name: 'Pause replay', exact: true }).click();
  await seek(analysisTime);
  checkpoint(
    'Replay and comparison share one workspace, selection bar, and clock; section links preserve playback',
  );
  await page.getByRole('link', { name: 'Lap comparison', exact: true }).click();
  await page.getByRole('heading', { name: 'Lap comparison', exact: true }).waitFor();
  await page.waitForFunction(() =>
    [...(document.querySelector('select[aria-label="Comparison lap A"]')?.options ?? [])].some(
      (option) => option.value === '2',
    ),
  );
  await page.getByRole('combobox', { name: 'Comparison driver A', exact: true }).selectOption('4');
  await page.getByRole('combobox', { name: 'Comparison lap A', exact: true }).selectOption('2');
  await page.getByRole('combobox', { name: 'Comparison driver B', exact: true }).selectOption('1');
  await page.getByRole('combobox', { name: 'Comparison lap B', exact: true }).selectOption('2');
  const analysisAt = new Date(
    Date.parse(raceMetadata.start_utc) + analysisTime * 1000,
  ).toISOString();
  const expectedAnalysis = await get(
    racePrefix +
      `/analysis/compare?at=${encodeURIComponent(analysisAt)}&driver_a=4&lap_a=2&driver_b=1&lap_b=2`,
  );
  await page.getByRole('button', { name: 'Compare laps', exact: true }).click();
  await page.getByTestId('comparison-results').waitFor();
  const deltaLabel = (value) =>
    value == null ? '\u2014' : `${value > 0 ? '+' : ''}${value.toFixed(3)} s`;
  assert.equal(
    await page.getByTestId('lap-delta').textContent(),
    deltaLabel(expectedAnalysis.lap_delta_s),
  );
  assert.equal(
    await page.getByTestId('full_throttle-a').textContent(),
    `${expectedAnalysis.a.full_throttle.percent.toFixed(1)}%`,
  );
  assert.equal(
    await page.getByTestId('braking-b').textContent(),
    `${expectedAnalysis.b.braking.percent.toFixed(1)}%`,
  );
  const sectors = await page.locator('.comparison-table').first().locator('tbody tr').all();
  for (let index = 0; index < 3; index++)
    assert.equal(
      await sectors[index + 1].locator('td').last().textContent(),
      deltaLabel(expectedAnalysis.sector_deltas_s[index]),
    );
  checkpoint(
    'Lap comparison shows real driver/sector deltas and time-weighted input percentages matching the API',
  );
  assert.equal(expectedAnalysis.alignment.available, true);
  const alignment = expectedAnalysis.alignment;
  assert.equal(alignment.points.length, 201);
  assert.ok((await page.locator('line[data-gain="gain"]').count()) > 0);
  assert.ok((await page.locator('line[data-gain="loss"]').count()) > 0);
  await page.getByRole('slider', { name: 'Comparison distance', exact: true }).fill('100');
  assert.equal(
    await page.getByTestId('distance-delta').textContent(),
    deltaLabel(alignment.points[100].delta_s),
  );
  assert.ok((await page.getByTestId('comparison-progress').textContent()).includes('50.0%'));
  await page.locator('.comparison-track-map').hover({ position: { x: 200, y: 200 } });
  assert.notEqual(
    await page.getByRole('slider', { name: 'Comparison distance', exact: true }).inputValue(),
    '100',
  );
  checkpoint(
    'Distance track shows local gains/losses; slider delta matches the API and pointer inspection works',
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page
    .locator('.performance-view')
    .screenshot({ path: path.join(data, 'phase6-comparison-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    'Lap comparison overflows on mobile.',
  );
  await page
    .locator('.performance-view')
    .screenshot({ path: path.join(data, 'phase6-comparison-mobile.png') });
  await page.setViewportSize({ width: 1600, height: 1120 });
  checkpoint('Lap comparison and the expanded navigation fit desktop and mobile');
  await seek(0);
  assert.equal(await page.getByTestId('comparison-results').count(), 0);
  assert.equal(await page.getByTestId('completed-laps').locator('.lap-row').count(), 0);
  await page.getByRole('heading', { name: 'No completed timed laps yet', exact: true }).waitFor();
  const rejected = await fetch(
    base +
      racePrefix +
      `/analysis/compare?at=${encodeURIComponent(raceMetadata.start_utc)}&driver_a=4&lap_a=2&driver_b=1&lap_b=2`,
  );
  assert.equal(rejected.status, 422);
  assert.ok(await page.getByRole('button', { name: 'Compare laps', exact: true }).isDisabled());
  checkpoint(
    'Seeking before lap completion hides results and choices, and the API rejects a guessed future lap',
  );
  await seek(analysisTime);
  await page.waitForFunction(
    () => !document.querySelector('select[aria-label="Comparison driver B"]')?.disabled,
  );
  await page.getByRole('combobox', { name: 'Comparison driver B', exact: true }).selectOption('4');
  await page.getByRole('combobox', { name: 'Comparison lap B', exact: true }).selectOption('3');
  assert.equal(await page.getByTestId('comparison-results').count(), 0);
  await page.getByRole('button', { name: 'Compare laps', exact: true }).click();
  await page.getByTestId('comparison-results').waitFor();
  await page
    .getByTestId('lap-comparison-summary')
    .getByText('A: NOR lap 2', { exact: false })
    .waitFor();
  assert.ok(
    (await page.getByTestId('lap-comparison-summary').textContent()).includes('B: NOR lap 3'),
  );
  checkpoint('The same driver can be compared across two completed laps');
  await openSession(second);
  assert.equal(await page.getByTestId('comparison-results').count(), 0);
  await page.getByRole('heading', { name: 'Lap comparison', exact: true }).waitFor();
  await openSession(race);
  checkpoint(
    'Changing the shared session clears previous comparison results while keeping both sections together',
  );
  await seek(raceTime);
  const cache = await get('/api/remote/cache');
  assert.ok(cache.used_bytes <= cache.limit_bytes);
  assert.equal(cache.limit_bytes, 200 * 1024 * 1024);
  checkpoint('Remote telemetry stays within the 200 MB disk cache limit');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(data, 'remote-replay-dashboard.png'), fullPage: true });
  await page.screenshot({ path: path.join(data, 'unified-workspace-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    'Mobile layout overflows horizontally.',
  );
  await page.screenshot({ path: path.join(data, 'remote-replay-mobile.png'), fullPage: true });
  await page.screenshot({ path: path.join(data, 'unified-workspace-mobile.png') });
  assert.deepEqual(errors, []);
  checkpoint('Desktop and mobile layouts render without overflow or JavaScript errors');
  writeFileSync(
    path.join(data, 'remote-replay-browser.json'),
    JSON.stringify(
      {
        checks,
        javascript_errors: errors,
        browser: 'installed headless Edge',
        version: '0.4.1',
        desktop_screenshot: 'data/remote-replay-dashboard.png',
        mobile_screenshot: 'data/remote-replay-mobile.png',
      },
      null,
      2,
    ) + String.fromCharCode(10),
  );
  console.log(`Verified ${checks.length} browser scenarios.`);
} catch (error) {
  if (page)
    await page
      .screenshot({ path: path.join(data, 'remote-replay-failure.png'), fullPage: true })
      .catch(() => {});
  throw error;
} finally {
  if (browser) await browser.close();
  backend.kill();
  await new Promise((resolve) => {
    if (backend.exitCode != null) resolve();
    else {
      backend.once('exit', resolve);
      setTimeout(resolve, 5000);
    }
  });
  closeSync(log);
}
