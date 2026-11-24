import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import type { useReplay } from '../hooks/useReplay';
import { pitStrategy, pressureModel, temperatureModel } from '../strategy';

interface Pace {
  excluded_laps: number;
  stints: {
    stint: number;
    compound: string;
    laps: number;
    slope_s_per_lap: number | null;
    points: { lap: number; age: number; recorded_s: number; corrected_s: number }[];
  }[];
}

function NumberField({
  label,
  value,
  set,
  min,
  max,
  step = 1,
}: {
  label: string;
  value: number;
  set: (value: number) => void;
  min: number;
  max: number;
  step?: number;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);
  return (
    <label className="strategy-input">
      {label}
      <input
        type="number"
        value={draft}
        min={min}
        max={max}
        step={step}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const n = Number(draft);
          const bounded =
            draft.trim() !== '' && Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : value;
          set(step === 1 ? Math.round(bounded) : bounded);
          setDraft(String(step === 1 ? Math.round(bounded) : bounded));
        }}
      />
    </label>
  );
}

export function StrategyLab({
  sessionId,
  sessionName,
  replay,
}: {
  sessionId: string;
  sessionName?: string;
  replay: ReturnType<typeof useReplay>;
}) {
  const [fuel, setFuel] = useState(100);
  const [burn, setBurn] = useState(1.7);
  const [effect, setEffect] = useState(0.03);
  const [pace, setPace] = useState<Pace | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [start, setStart] = useState(70);
  const [air, setAir] = useState(25);
  const heating = 10;
  const low = 95;
  const high = 115;
  const graining = 0.02;
  const overheat = 0.02;
  const pressure = 1.6;
  const weight = 8000;
  const downforce = 12000;
  const [speed, setSpeed] = useState(250);
  const [laps, setLaps] = useState(20);
  const [early, setEarly] = useState(4);
  const [late, setLate] = useState(8);
  const oldPace = 95;
  const oldAge = 15;
  const oldDeg = 0.12;
  const newPace = 93.5;
  const newDeg = 0.09;
  const pitLoss = 22;
  const outLoss = 2;
  const traffic = 0;
  const lateTraffic = 0;
  const activeRequest = useRef<AbortController | null>(null);
  const [section, setSection] = useState('pace');

  useEffect(() => {
    activeRequest.current?.abort();
    setPace(null);
    setError('');
    setLoading(false);
    return () => activeRequest.current?.abort();
  }, [sessionId, replay.driverNumber, fuel, burn, effect]);
  async function loadPace() {
    if (!sessionId || !replay.driverNumber) return;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setError('');
    setPace(null);
    const params = new URLSearchParams({
      driver_number: String(replay.driverNumber),
      fuel_start: String(fuel),
      fuel_burn: String(burn),
      fuel_effect: String(effect),
    });
    try {
      const result = await request<Pace>(
        `/api/sessions/${encodeURIComponent(sessionId)}/strategy/pace?${params}`,
        controller.signal,
      );
      if (!controller.signal.aborted) setPace(result);
    } catch (problem) {
      if (!controller.signal.aborted)
        setError(problem instanceof Error ? problem.message : 'Could not load pace data.');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  const thermal = temperatureModel(start, air, heating, low, high, 20, graining, overheat);
  const pressureResult = pressureModel(
    pressure,
    start,
    thermal[thermal.length - 1].temperature,
    weight,
    downforce,
    speed,
  );
  const validStops = early < late && late < laps;
  const a = pitStrategy(
    laps,
    early,
    oldPace,
    oldAge,
    oldDeg,
    newPace,
    newDeg,
    pitLoss,
    outLoss,
    traffic,
  );
  const b = pitStrategy(
    laps,
    late,
    oldPace,
    oldAge,
    oldDeg,
    newPace,
    newDeg,
    pitLoss,
    outLoss,
    lateTraffic,
  );
  const difference = a[laps - 1] - b[laps - 1];
  const crossover = a.findIndex(
    (total, i) => i >= late - 1 && total < b[i] && a[i - 1] >= b[i - 1],
  );
  return (
    <section className="panel strategy-lab" id="strategy-lab">
      <div className="panel-heading">
        <div>
          <h2>Strategy Lab</h2>
          <p>Explore the full session and test your own assumptions.</p>
        </div>
      </div>
      <div className="strategy-tabs" role="group" aria-label="Strategy tools">
        {(
          [
            ['pace', 'Pace degradation'],
            ['thermal', 'Tyre simulation'],
            ['pit', 'Pit strategy'],
          ] as const
        ).map(([id, label]) => (
          <button
            type="button"
            className={section === id ? 'active' : ''}
            key={id}
            onClick={() => setSection(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {section === 'pace' && (
        <div className="strategy-content">
          <h3>Fuel-corrected pace</h3>
          <p>
            See how the selected driver’s lap times changed on each set of tyres. RaceOS uses
            recorded laps and an example fuel estimate.
          </p>
          <details className="strategy-settings">
            <summary>Fuel assumptions</summary>
            <p>
              These example fuel values are not recorded measurements. You can change them here.
            </p>
            <div className="strategy-fields">
              <NumberField
                label="Starting fuel (kg)"
                value={fuel}
                set={setFuel}
                min={0}
                max={200}
              />
              <NumberField
                label="Fuel burned per lap (kg)"
                value={burn}
                set={setBurn}
                min={0}
                max={10}
                step={0.1}
              />
              <NumberField
                label="Fuel effect (s/kg)"
                value={effect}
                set={setEffect}
                min={0}
                max={0.1}
                step={0.001}
              />
            </div>
          </details>
          <button
            className="secondary-button"
            disabled={!sessionId || !replay.driverNumber || sessionName !== 'Race' || loading}
            onClick={loadPace}
          >
            {loading ? 'Analyzing...' : 'Analyze selected driver'}
          </button>
          {sessionName !== 'Race' && (
            <p>Open a race session and select a driver to analyze pace.</p>
          )}
          {error && <p role="alert">{error}</p>}
          {pace && (
            <>
              <p>
                {pace.excluded_laps} laps excluded for missing data, pit stops, generated timing, or
                unusual times. A stint needs at least three usable laps with different tyre ages.
              </p>
              {pace.stints.length ? (
                <div className="strategy-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Stint</th>
                        <th>Compound</th>
                        <th>Laps</th>
                        <th>Estimated trend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pace.stints.map((stint) => (
                        <tr key={`${stint.stint}-${stint.compound}`}>
                          <td>{stint.stint}</td>
                          <td>{stint.compound}</td>
                          <td>{stint.laps}</td>
                          <td>
                            {stint.slope_s_per_lap === null
                              ? 'Not enough data'
                              : `${stint.slope_s_per_lap > 0 ? '+' : ''}${stint.slope_s_per_lap.toFixed(3)} s/lap`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>No usable stint data is available for this driver.</p>
              )}
              <p>
                A positive number means laps tended to get slower; a negative number means they
                tended to get faster. Traffic, safety cars and weather also affect lap times, so
                this does not measure tyre wear directly.
              </p>
            </>
          )}
        </div>
      )}
      {section === 'thermal' && (
        <div className="strategy-content">
          <h3>Tyre simulation</h3>
          <p>
            See how a tyre might warm up, and how temperature and speed could affect grip, pressure
            and load. These are illustrative estimates, not measurements from the race.
          </p>
          <div className="strategy-fields">
            <NumberField
              label="Starting tyre temperature (°C)"
              value={start}
              set={setStart}
              min={0}
              max={200}
            />
            <NumberField label="Air temperature (°C)" value={air} set={setAir} min={-20} max={60} />
            <NumberField label="Speed (km/h)" value={speed} set={setSpeed} min={0} max={400} />
          </div>
          <div className="strategy-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Lap</th>
                  <th>Simulated tyre temperature</th>
                  <th>Estimated grip</th>
                </tr>
              </thead>
              <tbody>
                {thermal
                  .filter((row) => [1, 5, 10, 15, 20].includes(row.lap))
                  .map((row) => (
                    <tr key={row.lap}>
                      <td>{row.lap}</td>
                      <td>{row.temperature.toFixed(1)} °C</td>
                      <td>{row.grip.toFixed(1)}%</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <p>Using the simulated tyre temperature after lap 20 and the chosen speed:</p>
          <div className="strategy-result">
            <span>
              Estimated tyre pressure <strong>{pressureResult.finalPressure.toFixed(2)} bar</strong>
            </span>
            <span>
              Estimated load on all tyres <strong>{pressureResult.load.toFixed(0)} N</strong>
            </span>
            <span>
              Estimated total contact area{' '}
              <strong>
                {pressureResult.contactArea === null
                  ? 'Unavailable'
                  : `${pressureResult.contactArea.toFixed(0)} cm²`}
              </strong>
            </span>
          </div>
          <p>
            The model uses example tyre properties and car forces. Real tyre temperature, pressure,
            grip and contact area are not provided by the session data.
          </p>
        </div>
      )}
      {section === 'pit' && (
        <div className="strategy-content">
          <h3>Undercut vs overcut</h3>
          <p>
            See what might happen if a driver stops earlier or later. This example uses assumed lap
            times and pit losses; it does not predict the real race.
          </p>
          <div className="strategy-fields">
            <NumberField label="Remaining laps" value={laps} set={setLaps} min={3} max={100} />
            <NumberField
              label="Early stop after lap"
              value={early}
              set={setEarly}
              min={1}
              max={99}
            />
            <NumberField label="Late stop after lap" value={late} set={setLate} min={1} max={99} />
          </div>
          <p>Stop laps are counted from the start of this example, not the race.</p>
          {validStops ? (
            <div className="strategy-result">
              <span>
                At the finish{' '}
                <strong>
                  {Math.abs(difference) < 0.005
                    ? 'Equal'
                    : `${difference < 0 ? 'Early' : 'Late'} stop faster by ${Math.abs(difference).toFixed(2)} s`}
                </strong>
              </span>
              <span>
                Early stop moves ahead{' '}
                {crossover >= 0
                  ? `on remaining lap ${crossover + 1}`
                  : 'No later crossover in this scenario'}
              </span>
            </div>
          ) : (
            <p role="alert">
              Choose an early stop before the late stop, and leave at least one lap after the late
              stop.
            </p>
          )}
          <p>
            This example assumes a 22-second pit loss, a 2-second out-lap loss and no traffic. It
            uses fixed example tyre pace and wear, not data from the selected race.
          </p>
        </div>
      )}
    </section>
  );
}
