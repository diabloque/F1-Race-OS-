import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, openSync, closeSync, readFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '../..');
const tmp = path.join(root, 'data/tmp');
mkdirSync(tmp, { recursive: true });
const folder = mkdtempSync(path.join(tmp, 'smoke-'));
const socket = net.createServer();
await new Promise((resolve) => socket.listen(0, '127.0.0.1', resolve));
const port = socket.address().port;
await new Promise((resolve) => socket.close(resolve));
const base = `http://127.0.0.1:${port}`;
const env = { ...process.env, TEMP: folder, TMP: folder, TMPDIR: folder };
process.env.TEMP = process.env.TMP = process.env.TMPDIR = folder;
const python = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const logPath = path.join(folder, 'server.log');
const log = openSync(logPath, 'w');
const backend = spawn(
  python,
  ['-m', 'raceos', 'serve', '--port', String(port), '--db', path.join(folder, 'empty.sqlite3')],
  { cwd: root, env, windowsHide: true, stdio: ['ignore', log, log] },
);
let browser;
const errors = [];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
try {
  let ready = false;
  for (let i = 0; i < 100; i++) {
    if (backend.exitCode != null) throw new Error(readFileSync(logPath, 'utf8'));
    try {
      if ((await fetch(base + '/api/health')).ok) {
        ready = true;
        break;
      }
    } catch {}
    await sleep(200);
  }
  assert.ok(ready, 'Backend starts from an empty archive.');
  assert.equal((await (await fetch(base + '/api/library')).json()).total, 0);
  assert.equal((await fetch(base + '/docs')).status, 200);
  browser = await chromium.launch({
    headless: true,
    channel:
      process.env.RACEOS_BROWSER_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : undefined),
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', (error) => errors.push(error.message));
  // Keep fresh-clone CI independent of source publication and network availability.
  await page.route(
    (url) => url.pathname === '/api/remote/events',
    (route) => route.fulfill({ json: { year: 2026, items: [] } }),
  );
  assert.equal((await page.goto(base, { waitUntil: 'networkidle' })).status(), 200);
  await page.getByRole('heading', { name: 'Race workspace', exact: true }).waitFor();
  await page.getByRole('heading', { name: 'Track data unavailable', exact: true }).waitFor();
  assert.equal(await page.getByRole('alert').count(), 0);
  await page.getByText('Backend connected', { exact: true }).waitFor();
  const navigation = page.getByRole('navigation', { name: 'Workspace navigation' });
  assert.equal(await navigation.getByRole('button').count(), 2);
  assert.equal(await page.getByText('Data quality', { exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Lap comparison', exact: true }).count(), 0);
  assert.equal(await page.getByRole('slider', { name: 'Replay timeline', exact: true }).count(), 1);
  await page.getByRole('link', { name: 'Lap comparison', exact: true }).click();
  await page.getByRole('heading', { name: 'Lap comparison', exact: true }).waitFor();
  await page.getByRole('heading', { name: 'Race workspace', exact: true }).waitFor();
  await page.getByRole('heading', { name: 'Waiting for the replay clock', exact: true }).waitFor();
  assert.ok(await page.getByRole('button', { name: 'Compare laps', exact: true }).isDisabled());
  await page.getByRole('button', { name: 'Session library', exact: true }).click();
  await page.getByRole('heading', { name: 'Your archive is empty', exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: path.join(folder, 'fresh-start-mobile.png'), fullPage: true });
  assert.deepEqual(errors, []);
  console.log(
    'PASS fresh startup: API, root dashboard, empty library, unified workspace, comparison guards, mobile layout, no JavaScript errors',
  );
} finally {
  if (browser) await browser.close();
  if (backend.exitCode == null) {
    const exited = new Promise((resolve) => backend.once('exit', resolve));
    backend.kill();
    await exited;
  }
  closeSync(log);
}
