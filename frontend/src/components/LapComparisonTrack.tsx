import { useMemo, useState } from 'react';
import { fitTrack, project, type Track } from '../replay';

interface AlignedSample {
  time_s: number;
  x: number | null;
  y: number | null;
  speed_kmh: number | null;
  throttle_pct: number | null;
  brake_pressed: boolean | null;
  sample_at_utc: string;
}
interface DistancePoint {
  progress: number;
  distance_m: number;
  a: AlignedSample | null;
  b: AlignedSample | null;
  delta_s: number | null;
  gain_s: number | null;
  segment_valid: boolean;
}
export interface DistanceAlignment {
  available: boolean;
  approximate: boolean;
  note: string;
  coverage_pct: number;
  points: DistancePoint[];
}
function signed(value: number | null) {
  if (value == null) return '\u2014';
  return `${value > 0 ? '+' : ''}${value.toFixed(3)} s`;
}
function brakeLabel(applied: boolean | null | undefined) {
  if (applied == null) return '\u2014';
  return applied ? 'applied' : 'released';
}

export function LapComparisonTrack({
  alignment,
  track,
  labelA,
  labelB,
}: {
  alignment: DistanceAlignment;
  track: Track | null;
  labelA: string;
  labelB: string;
}) {
  const [index, setIndex] = useState(0);
  const points = alignment.points;
  const layout = useMemo(
    () => fitTrack(track?.points.length ? track.points : [{ x: 0, y: 0 }]),
    [track],
  );
  const plotted = useMemo(
    () =>
      points.map((point) =>
        point.a?.x != null && point.a.y != null
          ? project({ x: point.a.x, y: point.a.y }, layout)
          : null,
      ),
    [points, layout],
  );
  const selected = points[Math.min(index, points.length - 1)];
  const marker = plotted[Math.min(index, plotted.length - 1)];
  return (
    <section className="panel comparison-track" aria-label="Distance aligned track comparison">
      <div className="panel-heading">
        <div>
          <h2>Time gained around the lap</h2>
          <p>Approximate comparison along normalized recorded distance.</p>
        </div>
        <span className="outline-badge">DISTANCE ALIGNED</span>
      </div>
      {alignment.available && selected ? (
        <>
          <div className="comparison-track-legend">
            <span>
              <i style={{ background: '#66d7b0' }} />
              Green: B gains time
            </span>
            <span>
              <i style={{ background: '#ff776d' }} />
              Red: B loses time
            </span>
          </div>
          <svg
            viewBox="0 0 1000 600"
            className="comparison-track-map"
            role="img"
            aria-label="Circuit colored by local time gain for lap B"
            onPointerMove={(event) => {
              const svg = event.currentTarget;
              const transform = svg.getScreenCTM();
              if (!transform) return;
              const cursor = new DOMPoint(event.clientX, event.clientY).matrixTransform(
                transform.inverse(),
              );
              let nearest = -1,
                distance = Infinity;
              plotted.forEach((point, i) => {
                if (!point) return;
                const squared = (point.x - cursor.x) ** 2 + (point.y - cursor.y) ** 2;
                if (squared < distance) {
                  nearest = i;
                  distance = squared;
                }
              });
              if (nearest >= 0) setIndex(nearest);
            }}
          >
            <polyline
              points={(track?.points ?? [])
                .map((point) => {
                  const p = project(point, layout);
                  return `${p.x},${p.y}`;
                })
                .join(' ')}
              fill="none"
              stroke="#314153"
              strokeWidth="12"
              strokeLinejoin="round"
            />
            {points.map((point, i) => {
              const before = plotted[i - 1],
                after = plotted[i];
              if (!i || !before || !after || !point.segment_valid) return null;
              let color = '#8ba2b8';
              let change = 'steady';
              if (point.gain_s != null && point.gain_s < -0.01) {
                color = '#66d7b0';
                change = 'gain';
              } else if (point.gain_s != null && point.gain_s > 0.01) {
                color = '#ff776d';
                change = 'loss';
              }
              return (
                <line
                  key={i}
                  x1={before.x}
                  y1={before.y}
                  x2={after.x}
                  y2={after.y}
                  stroke={color}
                  strokeWidth="7"
                  strokeLinecap="round"
                  data-gain={change}
                />
              );
            })}
            {marker && (
              <circle
                cx={marker.x}
                cy={marker.y}
                r="11"
                fill="#f5f9ff"
                stroke="#122131"
                strokeWidth="4"
              />
            )}
          </svg>
          <div className="comparison-distance-control">
            <label htmlFor="comparison-distance">
              Lap distance{' '}
              <strong data-testid="comparison-progress">
                {(selected.progress * 100).toFixed(1)}% &middot; ~
                {Math.round(selected.distance_m).toLocaleString()} m
              </strong>
            </label>
            <input
              id="comparison-distance"
              aria-label="Comparison distance"
              type="range"
              min="0"
              max={points.length - 1}
              step="1"
              value={Math.min(index, points.length - 1)}
              onChange={(event) => setIndex(Number(event.target.value))}
            />
          </div>
          <div className="comparison-distance-readout" aria-live="polite">
            <div>
              <span>OVERALL B &minus; A HERE</span>
              <strong data-testid="distance-delta">{signed(selected.delta_s)}</strong>
              <small>Negative means B has arrived sooner.</small>
            </div>
            {(
              [
                ['A', labelA, selected.a],
                ['B', labelB, selected.b],
              ] as const
            ).map(([side, label, sample]) => (
              <div key={side}>
                <span>
                  {side} &middot; {label}
                </span>
                <strong>
                  {sample?.speed_kmh == null ? '\u2014' : `${Math.round(sample.speed_kmh)} km/h`}
                </strong>
                <small>
                  Throttle{' '}
                  {sample?.throttle_pct == null ? '\u2014' : `${Math.round(sample.throttle_pct)}%`}{' '}
                  &middot; Brake {brakeLabel(sample?.brake_pressed)}
                </small>
              </div>
            ))}
          </div>
          <p className="comparison-help">
            Hover the circuit or move the distance slider. Colors show local changes over each 0.5%
            segment; changes under 0.010 s stay neutral. Supported comparison:{' '}
            {alignment.coverage_pct.toFixed(1)}%. Times and positions between samples are
            interpolated; inputs use the preceding reading. Recorded endpoints may differ from the
            official lap time.
          </p>
        </>
      ) : (
        <p className="comparison-help">
          Track comparison unavailable: {alignment.note} Recorded timing and input comparisons
          remain available below.
        </p>
      )}
    </section>
  );
}
