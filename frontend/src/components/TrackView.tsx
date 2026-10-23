import { useMemo, useState } from 'react';
import { driverColor, fitTrack, inputColor, project } from '../replay';
import type { CarState, Track, TrailPoint } from '../replay';
interface Props {
  track: Track;
  cars: CarState[];
  trail: TrailPoint[];
  focus: number;
  onFocus: (number: number) => void;
}
export function TrackView({ track, cars, trail, focus, onFocus }: Props) {
  const [allLabels, setAllLabels] = useState(false);
  const [onlySelected, setOnlySelected] = useState(false);
  const visibleCars = cars
    .filter(
      (car) =>
        car.position &&
        car.position.status !== 'OffTrack' &&
        (!onlySelected || car.number === focus),
    )
    .sort((a, b) => Number(a.number === focus) - Number(b.number === focus));
  const layout = useMemo(() => fitTrack(track.points), [track]);
  const points = useMemo(
    () => track.points.map((point) => project(point, layout)),
    [track, layout],
  );
  const outline = points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ');
  const start = points[0];
  return (
    <div className={allLabels ? 'track-canvas all-driver-labels' : 'track-canvas'}>
      <div className="track-legend" role="note" aria-label="Track color key">
        <div className="track-legend-heading">
          <strong>Track color key</strong>
          <span>Selected driver's replayed lap</span>
        </div>
        <div className="track-legend-items">
          <div>
            <i style={{ background: '#66d7b0' }} />
            <div>
              <strong>Green &middot; Throttle</strong>
              <small>Above 15% throttle, brake released</small>
            </div>
          </div>
          <div>
            <i style={{ background: '#ff776d' }} />
            <div>
              <strong>Red &middot; Braking</strong>
              <small>Brake pedal applied</small>
            </div>
          </div>
          <div>
            <i style={{ background: '#f5bf62' }} />
            <div>
              <strong>Yellow &middot; Low throttle</strong>
              <small>0-15% throttle, brake released</small>
            </div>
          </div>
        </div>
      </div>
      <div className="track-display-options">
        <label>
          <input
            type="checkbox"
            checked={allLabels}
            onChange={(event) => setAllLabels(event.target.checked)}
          />
          Show all driver labels
        </label>
        <label>
          <input
            type="checkbox"
            checked={onlySelected}
            onChange={(event) => setOnlySelected(event.target.checked)}
          />
          Selected car only
        </label>
      </div>
      <svg viewBox="0 0 1000 600" role="group" aria-label="Circuit track">
        <defs>
          <pattern id="track-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#263344" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="1000" height="600" fill="url(#track-grid)" opacity="0.36" />
        <text x="38" y="40" className="map-overline">
          RECORDED CIRCUIT POSITIONS
        </text>
        <text x="960" y="560" textAnchor="end" className="map-watermark">
          RACEOS
        </text>
        <polyline
          points={`${outline} ${outline.split(' ')[0]}`}
          fill="none"
          strokeWidth="20"
          stroke="#080d15"
          strokeLinejoin="round"
        />
        <polyline
          data-testid="circuit-outline"
          points={`${outline} ${outline.split(' ')[0]}`}
          fill="none"
          strokeWidth="12"
          stroke="#334155"
          strokeLinejoin="round"
        />
        <polyline
          points={`${outline} ${outline.split(' ')[0]}`}
          fill="none"
          strokeWidth="1"
          stroke="#7a8ca3"
          strokeOpacity="0.6"
          strokeLinejoin="round"
        />
        {trail.map((point, index) => {
          const previous = trail[index - 1];
          if (
            !previous ||
            Date.parse(point.timestamp_utc) - Date.parse(previous.timestamp_utc) > 1000
          )
            return null;
          const a = project(previous, layout),
            b = project(point, layout);
          return (
            <line
              key={`${point.timestamp_utc}-${index}`}
              data-testid="input-trail"
              data-at={point.timestamp_utc}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={inputColor(point)}
              strokeWidth="5"
              strokeLinecap="round"
            />
          );
        })}
        {start && (
          <g transform={`translate(${start.x} ${start.y})`} className="start-finish">
            <circle r="6" fill="#e7edf6" stroke="#111b29" strokeWidth="3" />
            <text x="12" y="-12">
              START / FINISH
            </text>
          </g>
        )}
        {visibleCars.map((car) => {
          const position = car.position!,
            point = project(position, layout);
          const direction = project(
            { x: position.x + (position.dx ?? 1), y: position.y + (position.dy ?? 0) },
            layout,
          );
          const angle = (Math.atan2(direction.y - point.y, direction.x - point.x) * 180) / Math.PI;
          const color = driverColor(car),
            selected = car.number === focus;
          return (
            <g
              key={car.number}
              role="button"
              tabIndex={0}
              aria-label={`Focus ${car.code}`}
              aria-pressed={selected}
              data-testid={`car-${car.number}`}
              data-x={position.x}
              data-y={position.y}
              data-at={position.timestamp_utc}
              className={selected ? 'car-marker selected-car' : 'car-marker'}
              transform={`translate(${point.x} ${point.y})`}
              onClick={() => onFocus(car.number)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onFocus(car.number);
                }
              }}
            >
              <title>
                {car.code} - {car.name}
              </title>
              {selected && (
                <circle
                  r="22"
                  fill={color}
                  fillOpacity="0.12"
                  stroke={color}
                  strokeOpacity="0.55"
                  strokeWidth="1.5"
                />
              )}
              <g transform={`rotate(${angle})`}>
                <rect x="-8" y="-6" width="4" height="12" rx="1" fill="#04080d" />
                <rect x="5" y="-6" width="4" height="12" rx="1" fill="#04080d" />
                <path
                  d="M-11-3 L4-4 L13 0 L4 4 L-11 3Z"
                  fill={color}
                  stroke="#edf4ff"
                  strokeWidth={selected ? '1.5' : '0.7'}
                />
              </g>
              <text className="driver-map-label" x="0" y="-28" textAnchor="middle" fill={color}>
                {car.code}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
