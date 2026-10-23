import type { Lap, Sample } from './types';

export function lapTime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const totalMilliseconds = Math.round(seconds * 1000);
  const minutes = Math.floor(totalMilliseconds / 60000);
  const remainingSeconds = Math.floor(totalMilliseconds / 1000) % 60;
  const milliseconds = totalMilliseconds % 1000;
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`;
}

export function bestLap(laps: Lap[]): Lap | undefined {
  let best: Lap | undefined;
  for (const lap of laps) {
    if (lap.lap_duration_s == null || lap.lap_start_utc == null) continue;
    if (!best || lap.lap_duration_s < best.lap_duration_s!) best = lap;
  }
  return best;
}

export function nearestSample(samples: Sample[], elapsed: number, origin: number): number {
  if (!samples.length) return 0;
  const target = origin + elapsed * 1000;
  // Binary search keeps cursor movement quick for thousands of samples.
  let low = 0;
  let high = samples.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (Date.parse(samples[middle].timestamp_utc) < target) low = middle + 1;
    else high = middle;
  }
  if (low > 0) {
    const distanceBefore = target - Date.parse(samples[low - 1].timestamp_utc);
    const distanceAfter = Date.parse(samples[low].timestamp_utc) - target;
    if (distanceBefore <= distanceAfter) return low - 1;
  }
  return low;
}

export function tracePath(
  samples: Sample[],
  value: (sample: Sample) => number | null,
  origin: number,
  duration: number,
  maximum: number,
  step = false,
): string {
  let path = '';
  let previousTime: number | null = null;
  for (const sample of samples) {
    const time = (Date.parse(sample.timestamp_utc) - origin) / 1000;
    const quantity = value(sample);
    if (quantity == null || !Number.isFinite(quantity)) {
      previousTime = null;
      continue;
    }
    const x = (48 + (time / Math.max(duration, 0.001)) * 920).toFixed(2);
    const y = (130 - (quantity / maximum) * 108).toFixed(2);
    // SVG commands: M starts a segment, L draws a line, H/V draw a step.
    if (previousTime == null || time - previousTime > 1) path += `M${x},${y} `;
    else if (step) path += `H${x}V${y} `;
    else path += `L${x},${y} `;
    previousTime = time;
  }
  return path.trim();
}
