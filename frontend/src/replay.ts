import type { Driver, Sample } from './types';
export interface Point {
  x: number;
  y: number;
}
export interface Position extends Point {
  timestamp_utc: string;
  status: string | null;
  dx?: number;
  dy?: number;
}
export interface CompletedLap {
  lap_number: number;
  lap_duration_s: number | null;
  completed_at_utc: string;
}
export interface ReplayDriver extends Driver {
  team_color?: string | null;
  position_samples: number | null;
  laps: { lap_number: number; start_utc: string }[];
}
export interface TyreState {
  compound: string | null;
  stint: number | null;
  age_laps: number | null;
  fresh: boolean | null;
  pit_visits: number | null;
  in_pit: boolean | null;
  observed_at_utc: string | null;
}
export interface CarState extends Driver {
  tyres?: TyreState | null;
  team_color?: string | null;
  telemetry: Sample | null;
  position: Position | null;
  telemetry_age_s: number | null;
  position_age_s: number | null;
  current_lap_number: number | null;
  lap_started_utc: string | null;
  completed_laps: number;
  last_lap: CompletedLap | null;
  best_lap: CompletedLap | null;
}
export interface ReplayCatalog {
  prepared?: boolean;
  source?: string;
  session_id: string;
  start_utc: string;
  end_utc: string;
  duration_s: number;
  initial_utc: string;
  initial_driver_number: number;
  drivers: ReplayDriver[];
}
export interface Track {
  session_id: string;
  points: Point[];
  approximate: boolean;
  note?: string;
}
export interface TrailPoint extends Point {
  timestamp_utc: string;
  throttle_pct: number | null;
  brake_pressed: boolean | null;
}
export interface RaceTimingRow extends Pick<Driver, 'number' | 'code' | 'name' | 'team'> {
  team_color?: string | null;
  position: number | null;
  lap_number: number | null;
  sector: number | null;
  timing_at_utc: string | null;
  gap_to_leader_s: number | null;
  interval_s: number | null;
}
export interface RaceTiming {
  basis: 'sector_crossings';
  rows: RaceTimingRow[];
}
export interface WeatherObservation {
  timestamp_utc: string;
  age_s: number;
  stale: boolean;
  air_temp_c: number | null;
  track_temp_c: number | null;
  rainfall: boolean | null;
  wind_speed_ms: number | null;
  wind_direction_deg: number | null;
}
export interface RaceControlMessage {
  id: number;
  timestamp_utc: string;
  message: string;
  category: string | null;
  flag: string | null;
  scope: string | null;
  sector: string | null;
  driver_number: string | null;
}
export type Availability = 'ready' | 'missing' | 'unavailable' | 'invalid';
export interface ReplayFrame {
  weather?: WeatherObservation | null;
  weather_status?: Availability;
  race_control?: RaceControlMessage[];
  race_control_status?: Availability;
  prepared?: boolean;
  source?: string;
  session_id: string;
  at_utc: string;
  elapsed_s: number;
  focus_driver_number: number;
  drivers: CarState[];
  completed_laps: CompletedLap[];
  trail: TrailPoint[];
  race_timing?: RaceTiming | null;
}
export function clampTime(seconds: number, duration: number): number {
  return Number.isFinite(seconds) ? Math.max(0, Math.min(duration, seconds)) : 0;
}
export function advanceTime(anchor: number, realSeconds: number, speed: number, duration: number) {
  return clampTime(anchor + Math.max(0, realSeconds) * speed, duration);
}
export function clockLabel(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds * 1000));
  const hours = Math.floor(total / 3600000),
    minutes = Math.floor(total / 60000) % 60;
  const remainder = Math.floor(total / 1000) % 60;
  return `${hours ? `${hours}:` : ''}${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}.${String(total % 1000).padStart(3, '0')}`;
}
export interface TrackLayout {
  rotate: boolean;
  minX: number;
  minY: number;
  scale: number;
  offsetX: number;
  offsetY: number;
}
export function fitTrack(points: Point[]): TrackLayout {
  const xs = points.map((point) => point.x),
    ys = points.map((point) => point.y);
  const rotate = Math.max(...ys) - Math.min(...ys) > Math.max(...xs) - Math.min(...xs);
  const horizontal = points.map((point) => (rotate ? point.y : point.x));
  const vertical = points.map((point) => (rotate ? -point.x : point.y));
  const minX = Math.min(...horizontal),
    minY = Math.min(...vertical);
  const width = Math.max(1, Math.max(...horizontal) - minX),
    height = Math.max(1, Math.max(...vertical) - minY);
  const scale = Math.min(840 / width, 450 / height);
  return {
    rotate,
    minX,
    minY,
    scale,
    offsetX: (1000 - width * scale) / 2,
    offsetY: (600 - height * scale) / 2,
  };
}
export function project(point: Point, layout: TrackLayout): Point {
  const horizontal = layout.rotate ? point.y : point.x,
    vertical = layout.rotate ? -point.x : point.y;
  return {
    x: layout.offsetX + (horizontal - layout.minX) * layout.scale,
    y: 600 - layout.offsetY - (vertical - layout.minY) * layout.scale,
  };
}
export function driverColor(driver: { team_color?: string | null; number: number }): string {
  return driver.team_color && /^[0-9a-f]{6}$/i.test(driver.team_color)
    ? `#${driver.team_color}`
    : `hsl(${(driver.number * 47) % 360} 75% 65%)`;
}
export function inputColor(point: {
  throttle_pct: number | null;
  brake_pressed: boolean | null;
}): string {
  if (point.brake_pressed === true) return '#ff776d';
  if (
    point.brake_pressed == null ||
    point.throttle_pct == null ||
    point.throttle_pct < 0 ||
    point.throttle_pct > 100
  )
    return '#708096';
  return point.throttle_pct > 15 ? '#66d7b0' : '#f5bf62';
}
