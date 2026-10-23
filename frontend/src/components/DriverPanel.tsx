import { lapTime } from '../data';
import { TyreStint } from './TyreStint';
import { clockLabel, driverColor } from '../replay';
import type { CarState, ReplayDriver } from '../replay';

interface Props {
  driver?: ReplayDriver;
  car?: CarState;
  at?: string;
}

export function DriverPanel({ driver, car, at }: Props) {
  const sample = car?.telemetry;
  const throttle = sample?.throttle_pct;
  const validThrottle = throttle != null && throttle >= 0 && throttle <= 100;
  const brake = sample?.brake_pressed;
  const elapsed =
    at && car?.lap_started_utc ? (Date.parse(at) - Date.parse(car.lap_started_utc)) / 1000 : null;
  const number = (value: number | null | undefined) =>
    value == null ? '--' : Math.round(value).toLocaleString();

  return (
    <aside className="track-sidebar focused-driver-panel" aria-label="Selected driver details">
      <div
        className="focused-driver-heading"
        style={{ borderTopColor: driver ? driverColor(driver) : undefined }}
      >
        <span className="tiny-label">FOLLOWING ONE DRIVER</span>
        <div className="focused-driver-name">
          <strong>{driver?.code ?? '--'}</strong>
          <span>#{driver?.number ?? '--'}</span>
        </div>
        <p>{driver?.name ?? 'Choose a driver'}</p>
        <small>{driver?.team ?? '--'}</small>
      </div>
      <div className="focused-car-stats" aria-label="Current car telemetry">
        <div>
          <span>SPEED</span>
          <strong data-testid="speed-readout">
            {number(sample?.speed_kmh)}
            <small>km/h</small>
          </strong>
        </div>
        <div>
          <span>GEAR</span>
          <strong>{number(sample?.gear)}</strong>
        </div>
        <div>
          <span>ENGINE RPM</span>
          <strong>{number(sample?.rpm)}</strong>
        </div>
      </div>
      <section className="pedal-input throttle-input" aria-label="Throttle input">
        <div className="pedal-heading">
          <h3>Throttle input</h3>
          <strong data-testid="throttle-readout">
            {validThrottle ? `${Math.round(throttle)}%` : 'Unavailable'}
          </strong>
        </div>
        <div
          className="pedal-meter"
          role={validThrottle ? 'meter' : undefined}
          aria-label="Accelerator pedal position"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={validThrottle ? throttle : undefined}
        >
          <i style={{ width: `${validThrottle ? throttle : 0}%` }} />
        </div>
        <div className="pedal-scale">
          <span>Released</span>
          <span>Fully pressed</span>
        </div>
        <p>How far the accelerator pedal is pressed. 0% is released; 100% is full throttle.</p>
        {throttle != null && !validThrottle && (
          <p className="warning-text">The recorded pedal reading is unavailable.</p>
        )}
      </section>
      <section className="pedal-input brake-input" aria-label="Brake input">
        <div className="pedal-heading">
          <h3>Brake input</h3>
          <strong data-testid="brake-readout" className={brake === true ? 'brake-applied' : ''}>
            {brake == null ? 'Unavailable' : brake ? 'Applied' : 'Released'}
          </strong>
        </div>
        <div className="brake-states" aria-hidden="true">
          <span className={brake === false ? 'active-released' : ''}>Released</span>
          <span className={brake === true ? 'active-applied' : ''}>Applied</span>
        </div>
        <p>
          Shows whether the driver is pressing the brake pedal. Braking pressure is unavailable.
        </p>
      </section>
      <TyreStint tyres={car?.tyres} />
      <div className="focused-lap-stats">
        <div>
          <span>CURRENT LAP</span>
          <strong data-testid="current-lap">
            {car?.current_lap_number ? `Lap ${car.current_lap_number}` : 'Between laps'}
          </strong>
          <small>{elapsed == null ? '--' : `${clockLabel(elapsed)} elapsed`}</small>
        </div>
        <div>
          <span>BEST COMPLETED</span>
          <strong data-testid="best-completed-lap">{lapTime(car?.best_lap?.lap_duration_s)}</strong>
          <small>
            {car?.best_lap ? `Lap ${car.best_lap.lap_number}` : 'Available after a lap finishes'}
          </small>
        </div>
      </div>
    </aside>
  );
}
