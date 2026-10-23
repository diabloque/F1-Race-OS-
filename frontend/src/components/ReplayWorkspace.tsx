import { lapTime } from '../data';
import { DriverPanel } from './DriverPanel';
import type { useReplay } from '../hooks/useReplay';
import { Blank } from './Common';
import { ReplayControls } from './ReplayControls';
import { TrackView } from './TrackView';
import { RaceTiming } from './RaceTiming';
import { SessionConditions } from './SessionConditions';
export function ReplayWorkspace({
  replay,
  location,
  sessionName,
}: {
  replay: ReturnType<typeof useReplay>;
  location?: string;
  sessionName?: string;
}) {
  const { catalog, frame, driverNumber, track } = replay;
  const driver = catalog?.drivers.find((driver) => driver.number === driverNumber),
    car = frame?.drivers.find((car) => car.number === driverNumber);
  const sample = car?.telemetry,
    sameFocus = frame?.focus_driver_number === driverNumber;
  const completed = sameFocus ? frame.completed_laps : [];
  const onTrack =
    frame?.drivers.filter((car) => car.position && car.position.status !== 'OffTrack').length ?? 0;
  return (
    <>
      <section className="track-workspace panel">
        <div className="panel-heading">
          <div>
            <h2>
              {location ?? 'Circuit'} track replay{' '}
              <span className="small-tag">{driver?.code ?? '--'}</span>
            </h2>
            <p>Follow a driver around the circuit. Select another car or use the driver menu.</p>
          </div>
          <span className="replay-state-badge">
            <i className={replay.playing ? 'status-dot' : 'status-dot paused-dot'} />
            {replay.loading && replay.playing
              ? 'BUFFERING'
              : replay.playing
                ? 'REPLAYING'
                : 'PAUSED'}
          </span>
        </div>
        <div className="track-layout">
          <div className="track-main">
            {track ? (
              <TrackView
                track={track}
                cars={frame?.drivers ?? []}
                trail={sameFocus ? frame.trail : []}
                focus={driverNumber}
                onFocus={replay.chooseDriver}
              />
            ) : (
              <Blank title={replay.loading ? 'Loading the circuit...' : 'Track data unavailable'}>
                Open a race or qualifying session to load its prepared track positions.
              </Blank>
            )}
            <div className="map-caption">
              <span>
                <i className="status-dot" />
                {onTrack} cars located
              </span>
              <span>Recorded positions - approximate</span>
              <time data-testid="replay-utc">
                {frame
                  ? new Date(frame.at_utc).toISOString().slice(11, 23) + ' UTC'
                  : 'Loading recorded state...'}
              </time>
            </div>
          </div>
          <DriverPanel driver={driver} car={car} at={frame?.at_utc} />
        </div>
        <ReplayControls
          elapsed={replay.elapsed}
          duration={catalog?.duration_s ?? 0}
          playing={replay.playing}
          speed={replay.speed}
          disabled={!catalog}
          onSeek={replay.seek}
          onPlay={replay.togglePlay}
          onSpeed={replay.setSpeed}
        />
        <div className="replay-footnote">
          TracingInsights prepared replay. Missing or stale measurements stay unknown; lap results
          become visible after completion.
        </div>
      </section>
      <div className="bottom-grid">
        <section className="lap-list panel">
          <div className="panel-heading">
            <div>
              <h2>Completed laps</h2>
              <p>{driver?.code ?? 'Driver'} - known at the replay clock</p>
            </div>
            <span className="outline-badge">{completed.length} LAPS</span>
          </div>
          <div className="lap-list-rows" data-testid="completed-laps">
            {completed.length ? (
              completed.map((lap) => (
                <div
                  className="lap-row"
                  key={lap.lap_number}
                  data-completed-at={lap.completed_at_utc}
                >
                  <span>Lap {lap.lap_number}</span>
                  <span>{lapTime(lap.lap_duration_s)}</span>
                  <small>COMPLETED</small>
                </div>
              ))
            ) : (
              <p className="no-completed-laps">
                No lap result is available at this point in the replay.
              </p>
            )}
          </div>
        </section>
        {sessionName === 'Race' ? (
          <RaceTiming
            timing={frame?.race_timing}
            lap={
              frame?.drivers.reduce(
                (latest, car) =>
                  Math.max(latest, car.current_lap_number ?? 0, car.last_lap?.lap_number ?? 0),
                0,
              ) || undefined
            }
            focus={driverNumber}
            onFocus={replay.chooseDriver}
          />
        ) : (
          <section className="quality-summary panel">
            <div className="panel-heading">
              <div>
                <h2>One session clock</h2>
                <p>Every car follows the same recorded event time</p>
              </div>
            </div>
            <p className="quality-description">
              Seek backward or forward to reconstruct that moment. The map, driver inputs, current
              lap, and completed results update together.
            </p>
            <p className="quality-description">
              Positions are interpolated in the prepared source data. Original live delivery delays
              are unavailable; the replay follows recorded event times.
            </p>
            {sample?.quality_flags?.length ? (
              <p className="quality-description warning-text">
                Selected sample:{' '}
                {sample.quality_flags.map((flag) => flag.replaceAll('_', ' ')).join(', ')}
              </p>
            ) : null}
          </section>
        )}
      </div>
      <SessionConditions frame={frame} />
    </>
  );
}
