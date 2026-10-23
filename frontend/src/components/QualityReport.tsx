import type { Quality } from '../types';
import { Blank } from './Common';

const channelLabels = [
  ['speed_kmh', 'Speed'],
  ['throttle_pct', 'Throttle'],
  ['brake_pressed', 'Brake state'],
  ['gear', 'Gear'],
  ['rpm', 'Engine RPM'],
];

export function QualityReport({
  quality,
  driverCode,
  sourceLabel = 'FastF1',
  scopeLabel = 'whole session',
  prepared = false,
}: {
  quality: Quality | null;
  driverCode?: string;
  sourceLabel?: string;
  scopeLabel?: string;
  prepared?: boolean;
}) {
  return (
    <section className="quality-view panel">
      <div className="panel-heading">
        <div>
          <h2>Source quality</h2>
          <p>
            {driverCode ?? 'Driver'} &middot; {sourceLabel} &middot; {scopeLabel}
          </p>
        </div>
        <span className="outline-badge">
          {quality?.telemetry_samples.toLocaleString() ?? '0'} SAMPLES
        </span>
      </div>
      {quality ? (
        <>
          <table>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Missing / unknown</th>
                <th>Outside expected range</th>
              </tr>
            </thead>
            <tbody>
              {channelLabels.map(([key, label]) => {
                const missing = quality.missing_by_channel[key] ?? 0;
                const outside = quality.out_of_range_by_channel[key] ?? 0;
                return (
                  <tr key={key}>
                    <td>{label}</td>
                    <td className={missing ? 'warning-text' : ''}>{missing.toLocaleString()}</td>
                    <td className={outside ? 'warning-text' : ''}>{outside.toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="quality-notes">
            <strong>{quality.gaps_over_1s} sampling gaps longer than one second</strong>
            <p>
              {prepared
                ? 'Counts cover the complete selected lap file. Positions and car channels can contain upstream interpolation.'
                : 'Counts cover the whole driver session, including pit time and gaps between runs.'}
            </p>
            <p>
              {prepared
                ? 'Prepared data is supplied by TracingInsights from FastF1 and other sources. Derived values remain distinct from original sensor measurements.'
                : 'Throttle 104 can indicate unavailable source data. Original values are preserved and flagged.'}
            </p>
            <p>
              Unknown braking stays unknown, and charts break across missing values and sampling
              gaps.
            </p>
            {quality.warnings.map((warning) => (
              <p key={warning} className="quality-warning">
                • {warning}
              </p>
            ))}
          </div>
        </>
      ) : (
        <Blank title="No quality report loaded">
          Choose a driver with stored telemetry to inspect its source quality.
        </Blank>
      )}
    </section>
  );
}
