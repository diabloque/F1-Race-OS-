export type Source = 'fastf1' | 'tracinginsights';
export interface Session {
  driver_count?: number;
  id: string;
  year: number;
  round?: number;
  location: string;
  name: string;
  scheduled_start_utc: string;
  default_source: Source;
  sources: {
    source: Source;
    telemetry_drivers: { driver_number: number; sample_count: number }[];
  }[];
}
export interface Driver {
  number: number;
  code: string;
  name: string;
  team: string | null;
  telemetry_available: boolean;
  telemetry_samples: number | null;
}
export interface Lap {
  source: Source;
  driver_number: number;
  lap_number: number;
  lap_duration_s: number | null;
  lap_start_utc: string | null;
}
export interface Sample {
  source: Source;
  driver_number: number;
  timestamp_utc: string;
  speed_kmh: number | null;
  throttle_pct: number | null;
  brake_pressed: boolean | null;
  gear: number | null;
  rpm: number | null;
  drs_code: number | null;
  drs_open?: boolean | null;
  sample_index: number;
  quality_flags: string[];
}
export interface Quality {
  telemetry_samples: number;
  gaps_over_1s: number;
  missing_by_channel: Record<string, number>;
  out_of_range_by_channel: Record<string, number>;
  warnings: string[];
}
export interface Health {
  status: string;
  version: string;
  counts: Record<string, number>;
}
