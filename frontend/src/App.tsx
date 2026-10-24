import { useState } from 'react';
import { useArchive } from './hooks/useArchive';
import { useReplay } from './hooks/useReplay';
import { Blank, Icon } from './components/Common';
import { SessionControls } from './components/SessionControls';
import { ReplayWorkspace } from './components/ReplayWorkspace';
import { PerformanceAnalysis } from './components/PerformanceAnalysis';
type Screen = 'replay' | 'sessions';
export default function App() {
  const [screen, setScreen] = useState<Screen>('replay');
  const archive = useArchive();
  const replay = useReplay(archive.sessionId, archive.revision);
  const session = archive.sessions.find((session) => session.id === archive.sessionId);
  const currentCar = replay.frame?.drivers.find((driver) => driver.number === replay.driverNumber);
  const title = screen === 'replay' ? 'Race workspace' : 'Session library';
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
              ['replay', 'Race workspace'],
              ['sessions', 'Session library'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              className={screen === key ? 'nav-item active' : 'nav-item'}
              aria-current={screen === key ? 'page' : undefined}
              onClick={() => setScreen(key)}
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
                  ? 'Replay the session and compare completed laps in one place.'
                  : 'Your sessions, ready for a closer look.'}
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
            showReplayControls={screen === 'replay'}
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
              <ReplayWorkspace replay={replay} sessionName={session?.name} />
              <PerformanceAnalysis sessionId={archive.sessionId} replay={replay} />
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
