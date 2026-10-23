import type { ReplayFrame } from '../replay';

const utcTime = (timestamp: string) => new Date(timestamp).toISOString().slice(11, 19) + ' UTC';
export function SessionConditions({ frame }: { frame: ReplayFrame | null }) {
  const weather = frame?.weather;
  const weatherReady = frame?.weather_status === 'ready';
  const controlReady = frame?.race_control_status === 'ready';
  const value = (number: number | null | undefined, suffix: string) =>
    number == null ? '\u2014' : `${number.toFixed(1)}${suffix}`;
  return (
    <div className="session-conditions">
      <section
        className="weather-panel panel"
        aria-label="Weather observation"
        data-testid="weather-panel"
        data-observed-at={weather?.timestamp_utc ?? ''}
      >
        <div className="panel-heading">
          <div>
            <h2>Weather</h2>
            <p>
              {weather
                ? `Observed ${utcTime(weather.timestamp_utc)}`
                : weatherReady
                  ? 'No report at this replay time'
                  : 'Weather data unavailable'}
            </p>
          </div>
          {weather && (
            <span className={weather.stale ? 'outline-badge weather-stale' : 'outline-badge'}>
              {weather.stale ? 'OLDER REPORT' : 'OBSERVATION'}
            </span>
          )}
        </div>
        <dl className="weather-readings">
          <div>
            <dt>TRACK</dt>
            <dd data-testid="track-temperature">{value(weather?.track_temp_c, '\u00b0C')}</dd>
          </div>
          <div>
            <dt>AIR</dt>
            <dd>{value(weather?.air_temp_c, '\u00b0C')}</dd>
          </div>
          <div>
            <dt>RAIN</dt>
            <dd>
              {weather?.rainfall == null
                ? '\u2014'
                : weather.rainfall
                  ? 'Reported'
                  : 'None reported'}
            </dd>
          </div>
          <div>
            <dt>WIND</dt>
            <dd>
              {value(weather?.wind_speed_ms, ' m/s')}
              {weather?.wind_direction_deg != null && (
                <small>{Math.round(weather.wind_direction_deg)}&deg;</small>
              )}
            </dd>
          </div>
        </dl>
        {weather?.stale && (
          <p className="condition-note">
            Last report {Math.floor(weather.age_s / 60)} minutes ago.
          </p>
        )}
      </section>
      <section className="race-control-panel panel" aria-label="Race control">
        <div className="panel-heading">
          <div>
            <h2>Race control</h2>
            <p>Flags, safety cars, and official messages</p>
          </div>
          <span className="outline-badge">{frame?.race_control?.length ?? 0} MESSAGES</span>
        </div>
        <ol className="race-control-messages" data-testid="race-control-messages">
          {frame?.race_control?.map((message) => (
            <li
              key={message.id}
              data-issued-at={message.timestamp_utc}
              data-message-id={message.id}
            >
              <time>{utcTime(message.timestamp_utc)}</time>
              <div>
                {message.flag && (
                  <span className="message-flag" data-flag={message.flag}>
                    {message.flag.replaceAll('_', ' ')}
                  </span>
                )}
                <p>{message.message}</p>
                {(message.driver_number || message.sector) && (
                  <small>
                    {message.driver_number ? `Car ${message.driver_number}` : ''}
                    {message.driver_number && message.sector ? ' \u00b7 ' : ''}
                    {message.sector ? `Sector ${message.sector}` : ''}
                  </small>
                )}
              </div>
            </li>
          ))}
        </ol>
        {!frame?.race_control?.length && (
          <p className="condition-note">
            {controlReady
              ? 'No messages issued at this replay time.'
              : 'Race-control data unavailable.'}
          </p>
        )}
      </section>
    </div>
  );
}
