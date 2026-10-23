import { useState } from 'react';
import { useArchive } from './hooks/useArchive';
import { useReplay } from './hooks/useReplay';
import { Blank, Icon } from './components/Common';
import { SessionControls } from './components/SessionControls';
import { ReplayWorkspace } from './components/ReplayWorkspace';
import { ArchiveQuality } from './components/ArchiveQuality';
import { PerformanceAnalysis } from './components/PerformanceAnalysis';
type Screen = 'replay' | 'sessions' | 'quality' | 'analysis';
export default function App() {
  const [screen, setScreen] = useState<Screen>('replay');
  const archive = useArchive(),
    replay = useReplay(archive.sessionId, archive.revision);
  const session = archive.sessions.find((session) => session.id === archive.sessionId);
  const driver = replay.catalog?.drivers.find((driver) => driver.number === replay.driverNumber);
  const currentCar = replay.frame?.drivers.find((driver) => driver.number === replay.driverNumber);
  const title =
    screen === 'replay'
      ? 'Track replay'
      : screen === 'sessions'
        ? 'Session library'
        : screen === 'analysis'
          ? 'Lap comparison'
          : 'Data quality';
  const error = archive.error || replay.error;
  function chooseSession(id: string) {
    archive.setSessionId(id);
    setScreen('replay');
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand" aria-label="RaceOS homepage">
          <img src="/favicon.svg" alt="" />
          <strong>
            Race<span>OS</span>
          </strong>
          <small>ENGINEERING WORKSPACE</small>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {(
            [
              ['replay', 'Track replay'],
              ['analysis', 'Lap comparison'],
              ['sessions', 'Session library'],
              ['quality', 'Data quality'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              className={screen === key ? 'nav-item active' : 'nav-item'}
              aria-current={screen === key ? 'page' : undefined}
              onClick={() => {
                if (key === 'analysis' && replay.playing) replay.togglePlay();
                setScreen(key);
              }}
            >
              <Icon name={key === 'replay' ? 'telemetry' : key} />
              {label}
              {screen === key && <span className="nav-marker" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-archive">
          <span className="tiny-label">SAVED SESSIONS</span>
          <strong>{archive.sessions.length} sessions</strong>
          <p>
            Remote historical data.
            <br />
            One replay clock.
          </p>
          <button onClick={() => setScreen('sessions')}>
            Browse sessions <Icon name="arrow" size={16} />
          </button>
        </div>
        <div className="sidebar-footer">
          <span className={archive.health ? 'status-dot' : 'status-dot disconnected'} />
          <div>
            <strong>{archive.health ? 'Backend connected' : 'Connecting to backend'}</strong>
            <span>Local workspace - {archive.health?.version ?? 'RaceOS'}</span>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <span>Workspace</span>
            <Icon name="chevron" size={13} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <span className="archive-badge">
              <span className="status-dot" />
              HISTORICAL REPLAY
            </span>
            <a href="/docs" target="_blank" rel="noreferrer" className="api-link">
              API docs
            </a>
          </div>
        </header>
        <div className="page-content">
          <div className="page-title">
            <div>
              <span className="eyebrow">RACEOS / ENGINEERING</span>
              <h1>{title}</h1>
              <p>
                {screen === 'replay'
                  ? 'Follow the cars. Read the inputs. Replay every corner.'
                  : screen === 'sessions'
                    ? 'Your sessions, ready for a closer look.'
                    : screen === 'analysis'
                      ? 'Compare completed laps, sector gains, and driver inputs.'
                      : 'Understand the measurements behind the replay.'}
              </p>
            </div>
            <button
              className="secondary-button refresh-button"
              aria-label="Refresh data"
              onClick={archive.refresh}
            >
              <Icon name="refresh" />
              Refresh
            </button>
          </div>
          <SessionControls
            sessions={archive.sessions}
            sessionId={archive.sessionId}
            catalog={replay.catalog}
            driverNumber={replay.driverNumber}
            currentLap={currentCar?.current_lap_number}
            showReplayControls={screen === 'replay' || screen === 'quality'}
            onLoaded={(session) => {
              archive.addSession(session);
              setScreen('replay');
            }}
            onDriver={replay.chooseDriver}
            onLap={replay.jumpToLap}
          />
          {error && (
            <div className="error-banner" role="alert">
              <strong>Data could not be loaded.</strong>
              <span>{error}</span>
              <button onClick={archive.refresh}>Try again</button>
            </div>
          )}
          {screen === 'sessions' ? (
            <div className="session-library">
              {!archive.sessions.length && (
                <Blank title={archive.loading ? 'Loading the archive...' : 'Your archive is empty'}>
                  Choose a year, Grand Prix, and Race or Qualifying above, then open the session.
                </Blank>
              )}
              {archive.sessions.map((item) => (
                <button
                  className="session-tile"
                  key={item.id}
                  onClick={() => chooseSession(item.id)}
                >
                  <span className="session-tile-top">
                    <span>{item.year} SEASON</span>
                    <Icon name="arrow" />
                  </span>
                  <strong>{item.location}</strong>
                  <span className="session-tile-type">{item.name}</span>
                  <span className="session-tile-date">
                    {new Date(item.scheduled_start_utc).toLocaleDateString('en-GB', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                      timeZone: 'UTC',
                    })}
                  </span>
                  <span className="session-tile-bottom">
                    {item.driver_count ?? item.sources[0]?.telemetry_drivers.length ?? 0} session
                    drivers <span>Open replay</span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <>
              {screen === 'analysis' ? (
                <PerformanceAnalysis sessionId={archive.sessionId} replay={replay} />
              ) : screen === 'quality' ? (
                <ArchiveQuality
                  sessionId={archive.sessionId}
                  driverNumber={replay.driverNumber}
                  driverCode={driver?.code}
                  lapNumber={
                    currentCar?.current_lap_number ?? currentCar?.last_lap?.lap_number ?? 1
                  }
                />
              ) : (
                <ReplayWorkspace
                  replay={replay}
                  location={session?.location}
                  sessionName={session?.name}
                />
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              RACEOS <i /> MOTORSPORT ENGINEERING PLATFORM
            </span>
            <span>TracingInsights - prepared historical replay</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
