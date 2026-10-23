import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { lapTime } from '../data';
import type { useReplay } from '../hooks/useReplay';
import { ReplayControls } from './ReplayControls';
import { Blank } from './Common';
import { LapComparisonTrack, type DistanceAlignment } from './LapComparisonTrack';

interface LapChoice {
  lap_number: number;
  lap_time_s: number;
  completed_at_utc: string;
}
interface DriverChoice {
  number: number;
  code: string;
  name: string;
  laps: LapChoice[];
}
interface Choices {
  session_id: string;
  drivers: DriverChoice[];
}
interface InputMetric {
  active_s: number;
  known_s: number;
  percent: number | null;
  coverage_pct: number;
}
interface AnalyzedLap {
  driver_number: number;
  code: string;
  name: string;
  lap_number: number;
  completed_at_utc: string;
  lap_time_s: number;
  sector_times_s: (number | null)[];
  window_s: number;
  full_throttle: InputMetric;
  braking: InputMetric;
  warnings: string[];
}
interface Comparison {
  alignment: DistanceAlignment;
  session_id: string;
  a: AnalyzedLap;
  b: AnalyzedLap;
  lap_delta_s: number;
  sector_deltas_s: (number | null)[];
}

export function PerformanceAnalysis({
  sessionId,
  replay,
}: {
  sessionId: string;
  replay: ReturnType<typeof useReplay>;
}) {
  const { frame, catalog } = replay;
  const [choices, setChoices] = useState<Choices | null>(null);
  const [loading, setLoading] = useState(false),
    [loadError, setLoadError] = useState('');
  const [a, setA] = useState({ driver: 0, lap: 0 }),
    [b, setB] = useState({ driver: 0, lap: 0 });
  const [result, setResult] = useState<{ key: string; data: Comparison } | null>(null);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  // Refresh choices when completed laps change, rather than on every playback frame.
  const completedKey =
    frame?.drivers
      .map((car) => `${car.number}:${car.last_lap?.completed_at_utc ?? ''}`)
      .join('|') ?? '';
  useEffect(() => {
    setLoadError('');
    if (!frame || !sessionId) {
      setChoices(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    request<Choices>(
      `/api/sessions/${encodeURIComponent(sessionId)}/analysis/laps?at=${encodeURIComponent(frame.at_utc)}`,
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setChoices(value);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setLoadError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [sessionId, completedKey]);

  const drivers =
    choices?.session_id === sessionId && frame
      ? choices.drivers
          .map((driver) => ({
            ...driver,
            laps: driver.laps.filter(
              (lap) => Date.parse(lap.completed_at_utc) <= Date.parse(frame.at_utc),
            ),
          }))
          .filter((driver) => driver.laps.length)
      : [];
  const driverA =
    drivers.find((driver) => driver.number === a.driver) ??
    drivers.find((driver) => driver.number === replay.driverNumber) ??
    drivers[0];
  const driverB =
    drivers.find((driver) => driver.number === b.driver) ??
    drivers.find((driver) => driver.number !== driverA?.number) ??
    driverA;
  const lapA = driverA?.laps.find((lap) => lap.lap_number === a.lap) ?? driverA?.laps.at(-1);
  const lapB =
    driverB?.laps.find((lap) => lap.lap_number === b.lap) ??
    (driverA === driverB
      ? [...(driverB?.laps ?? [])].reverse().find((lap) => lap.lap_number !== lapA?.lap_number)
      : undefined) ??
    driverB?.laps.at(-1);
  const key = `${sessionId}:${driverA?.number}:${lapA?.lap_number}:${driverB?.number}:${lapB?.lap_number}`;
  const shown =
    result?.key === key &&
    result.data.session_id === sessionId &&
    frame &&
    [result.data.a, result.data.b].every(
      (lap) => Date.parse(lap.completed_at_utc) <= Date.parse(frame.at_utc),
    )
      ? result.data
      : null;

  async function compare() {
    if (!frame || !driverA || !driverB || !lapA || !lapB) return;
    setA({ driver: driverA.number, lap: lapA.lap_number });
    setB({ driver: driverB.number, lap: lapB.lap_number });
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError('');
    setResult(null);
    const params = new URLSearchParams({
      at: frame.at_utc,
      driver_a: String(driverA.number),
      lap_a: String(lapA.lap_number),
      driver_b: String(driverB.number),
      lap_b: String(lapB.lap_number),
    });
    try {
      const data = await request<Comparison>(
        `/api/sessions/${encodeURIComponent(sessionId)}/analysis/compare?${params}`,
        controller.signal,
      );
      if (!controller.signal.aborted) setResult({ key, data });
    } catch (error) {
      if (!controller.signal.aborted) setError((error as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const delta = (value: number | null) =>
    value == null ? '\u2014' : `${value > 0 ? '+' : ''}${value.toFixed(3)} s`;
  const selector = (side: 'A' | 'B', driver?: DriverChoice, lap?: LapChoice) => (
    <fieldset>
      <legend>LAP {side}</legend>
      <label>
        <span>DRIVER</span>
        <select
          aria-label={`Comparison driver ${side}`}
          value={driver?.number ?? ''}
          disabled={!drivers.length || busy}
          onChange={(event) => {
            (side === 'A' ? setA : setB)({ driver: Number(event.target.value), lap: 0 });
            setError('');
          }}
        >
          {!drivers.length && <option value="">No completed laps yet</option>}
          {drivers.map((item) => (
            <option key={item.number} value={item.number}>
              {item.code} - {item.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>COMPLETED LAP</span>
        <select
          aria-label={`Comparison lap ${side}`}
          value={lap?.lap_number ?? ''}
          disabled={!driver || busy}
          onChange={(event) => {
            (side === 'A' ? setA : setB)({
              driver: driver!.number,
              lap: Number(event.target.value),
            });
            setError('');
          }}
        >
          {!driver && <option value="">Waiting for completion</option>}
          {driver?.laps.map((item) => (
            <option key={item.lap_number} value={item.lap_number}>
              Lap {item.lap_number} - {lapTime(item.lap_time_s)}
            </option>
          ))}
        </select>
      </label>
    </fieldset>
  );
  return (
    <div className="performance-view">
      <section className="panel comparison-clock" aria-label="Comparison replay clock">
        <div className="panel-heading">
          <div>
            <h2>Replay clock</h2>
            <p>Only laps completed by this moment can be compared.</p>
          </div>
          <time className="outline-badge" data-testid="replay-utc">
            {frame
              ? new Date(frame.at_utc).toISOString().slice(11, 23) + ' UTC'
              : 'Loading clock...'}
          </time>
        </div>
        <ReplayControls
          elapsed={replay.elapsed}
          duration={catalog?.duration_s ?? 0}
          playing={replay.playing}
          speed={replay.speed}
          disabled={!catalog}
          onSeek={replay.seek}
          onPlay={replay.togglePlay}
          onSpeed={replay.setSpeed}
        />
      </section>
      <section className="panel comparison-picker" aria-label="Lap comparison selection">
        <div className="panel-heading">
          <div>
            <h2>Choose two laps</h2>
            <p>Compare drivers, or compare two laps from the same driver.</p>
          </div>
          <span className="outline-badge">COMPLETED LAPS</span>
        </div>
        <div className="comparison-selections">
          {selector('A', driverA, lapA)}
          {selector('B', driverB, lapB)}
          <button
            className="secondary-button"
            disabled={!lapA || !lapB || !frame || busy}
            onClick={compare}
          >
            {busy ? 'Comparing...' : 'Compare laps'}
          </button>
        </div>
        {(loadError || error) && (
          <p className="comparison-error" role="alert">
            {loadError || error}
          </p>
        )}
        {loading && (
          <p className="comparison-help" role="status">
            Loading completed laps...
          </p>
        )}
      </section>
      {shown ? (
        <div
          className="comparison-results"
          data-testid="comparison-results"
          data-completed-a={shown.a.completed_at_utc}
          data-completed-b={shown.b.completed_at_utc}
        >
          <LapComparisonTrack
            alignment={shown.alignment}
            track={replay.track}
            labelA={`${shown.a.code} lap ${shown.a.lap_number}`}
            labelB={`${shown.b.code} lap ${shown.b.lap_number}`}
          />
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Lap &amp; sector times</h2>
                <p>B minus A: negative means B is quicker.</p>
              </div>
            </div>
            <div className="comparison-summary" data-testid="lap-comparison-summary">
              <strong>
                {shown.lap_delta_s === 0
                  ? 'Same recorded lap time'
                  : `${shown.lap_delta_s < 0 ? `${shown.b.code} lap ${shown.b.lap_number}` : `${shown.a.code} lap ${shown.a.lap_number}`} is ${Math.abs(shown.lap_delta_s).toFixed(3)} s quicker`}
              </strong>
              <span>
                A: {shown.a.code} lap {shown.a.lap_number} &middot; B: {shown.b.code} lap{' '}
                {shown.b.lap_number}
              </span>
            </div>
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Timing</th>
                  <th>Lap A</th>
                  <th>Lap B</th>
                  <th>B &minus; A</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>Lap time</th>
                  <td>{lapTime(shown.a.lap_time_s)}</td>
                  <td>{lapTime(shown.b.lap_time_s)}</td>
                  <td data-testid="lap-delta">{delta(shown.lap_delta_s)}</td>
                </tr>
                {shown.sector_deltas_s.map((value, index) => (
                  <tr key={index}>
                    <th>Sector {index + 1}</th>
                    <td>
                      {shown.a.sector_times_s[index] == null
                        ? '\u2014'
                        : `${shown.a.sector_times_s[index]!.toFixed(3)} s`}
                    </td>
                    <td>
                      {shown.b.sector_times_s[index] == null
                        ? '\u2014'
                        : `${shown.b.sector_times_s[index]!.toFixed(3)} s`}
                    </td>
                    <td
                      className={
                        value != null && value < 0
                          ? 'quicker-delta'
                          : value != null && value > 0
                            ? 'slower-delta'
                            : ''
                      }
                    >
                      {delta(value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="comparison-help">
              Missing sectors stay unknown. Recorded laps may include pit laps or laps later deleted
              by officials.
            </p>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Driver inputs</h2>
                <p>Time weighted percentages of covered telemetry time.</p>
              </div>
            </div>
            <table className="comparison-table input-comparison">
              <thead>
                <tr>
                  <th>Input</th>
                  <th>{shown.a.code} &middot; A</th>
                  <th>{shown.b.code} &middot; B</th>
                </tr>
              </thead>
              <tbody>
                {(['full_throttle', 'braking'] as const).map((channel) => (
                  <tr key={channel}>
                    <th>{channel === 'full_throttle' ? 'Full throttle' : 'Braking'}</th>
                    {[shown.a, shown.b].map((lap, index) => (
                      <td key={index}>
                        <strong data-testid={`${channel}-${index === 0 ? 'a' : 'b'}`}>
                          {lap[channel].percent == null
                            ? '\u2014'
                            : `${lap[channel].percent!.toFixed(1)}%`}
                        </strong>
                        <div className="comparison-meter" aria-hidden="true">
                          <i style={{ width: `${lap[channel].percent ?? 0}%` }} />
                        </div>
                        <small>
                          {lap[channel].active_s.toFixed(2)} s &middot;{' '}
                          {lap[channel].coverage_pct.toFixed(1)}% coverage
                        </small>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="comparison-help">
              Full throttle is 99&ndash;100%. Brake is applied/released. Gaps over one second and
              unknown readings are excluded; no brake pressure is inferred.
            </p>
            {[shown.a, shown.b].map(
              (lap, index) =>
                lap.warnings.length > 0 && (
                  <div className="comparison-warnings" key={index}>
                    <strong>
                      {index === 0 ? 'A' : 'B'} &middot; {lap.code} lap {lap.lap_number}
                    </strong>
                    {lap.warnings.map((warning) => (
                      <p key={warning}>{warning}</p>
                    ))}
                  </div>
                ),
            )}
          </section>
        </div>
      ) : (
        <section className="panel">
          <Blank
            title={
              !frame
                ? 'Waiting for the replay clock'
                : !drivers.length
                  ? 'No completed timed laps yet'
                  : 'Ready to compare'
            }
          >
            {!drivers.length
              ? 'Advance the replay until a timed lap finishes, then choose the laps above.'
              : 'Choose Lap A and Lap B, then select Compare laps.'}
          </Blank>
        </section>
      )}
    </div>
  );
}
