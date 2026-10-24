import { driverColor } from '../replay';
import type { RaceTiming as Timing } from '../replay';

export function RaceTiming({
  timing,
  lap,
  focus,
  onFocus,
}: {
  timing?: Timing | null;
  lap?: number;
  focus: number;
  onFocus: (number: number) => void;
}) {
  const seconds = (value: number | null) => (value == null ? '\u2014' : `+${value.toFixed(3)}`);
  const started = timing?.basis === 'sector_crossings';
  const hasGrid = timing?.rows.some((row) => row.grid_position != null);
  function observation(row: Timing['rows'][number]) {
    if (row.timing_at_utc) return `L${row.lap_number} \u00b7 S${row.sector}`;
    const label =
      row.grid_position === 0
        ? 'No grid slot'
        : row.grid_position
          ? `Grid P${row.grid_position}`
          : 'Grid unavailable';
    return started ? `${label} \u00b7 awaiting timing` : label;
  }
  return (
    <section className="race-timing panel" aria-label="Race timing">
      <div className="panel-heading">
        <div>
          <h2>Race timing</h2>
          <p>Positions, gap to the leader, and interval to the car ahead</p>
        </div>
        <span className="outline-badge" data-testid="race-lap" aria-label="Current race lap">
          LAP {lap ?? '\u2014'}
        </span>
      </div>
      <p className="timing-wait" data-testid="timing-phase" data-basis={timing?.basis}>
        {started
          ? 'Recorded race order - updates at sector timing lines.'
          : hasGrid
            ? 'Starting grid - waiting for the first recorded timing line.'
            : 'Starting grid unavailable - waiting for recorded timing.'}
      </p>
      <div className="race-timing-scroll">
        <table className="race-timing-table" data-testid="race-timing">
          <thead>
            <tr>
              <th scope="col">Pos</th>
              <th scope="col">Driver</th>
              <th scope="col">Interval</th>
              <th scope="col">Gap</th>
            </tr>
          </thead>
          <tbody>
            {timing?.rows.map((row) => (
              <tr
                key={row.number}
                className={row.number === focus ? 'timing-followed' : ''}
                data-driver={row.number}
                data-position={row.position ?? ''}
                data-timing-at={row.timing_at_utc ?? ''}
                data-gap={row.gap_to_leader_s ?? ''}
                data-interval={row.interval_s ?? ''}
              >
                <td>{row.position ?? '\u2014'}</td>
                <td>
                  <button
                    type="button"
                    aria-label={`Follow ${row.name}`}
                    aria-pressed={row.number === focus}
                    onClick={() => onFocus(row.number)}
                    style={{ borderLeftColor: driverColor(row) }}
                  >
                    <strong>{row.code}</strong>
                    <small>{observation(row)}</small>
                  </button>
                </td>
                <td>{started && row.position === 1 ? 'Leader' : seconds(row.interval_s)}</td>
                <td>{row.position === 1 ? '\u2014' : seconds(row.gap_to_leader_s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="timing-explanation">
        Starting grid is shown until the first recorded sector crossing. Interval is to the car
        ahead; Gap is to the leader, in seconds at the same line. Updates follow available sector
        times; &mdash; means no recorded comparison.
      </p>
    </section>
  );
}
