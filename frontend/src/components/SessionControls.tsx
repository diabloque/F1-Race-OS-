import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { request } from '../api';
import type { Session } from '../types';
import type { ReplayCatalog } from '../replay';

interface RaceEvent {
  round: number;
  event: string;
  location: string;
  sessions: { name: 'Race' | 'Qualifying'; scheduled_start_utc: string }[];
}
interface Props {
  sessions: Session[];
  sessionId: string;
  catalog: ReplayCatalog | null;
  driverNumber: number;
  currentLap?: number | null;
  showReplayControls: boolean;
  onLoaded: (session: Session) => void;
  onDriver: (number: number) => void;
  onLap: (number: number) => void;
}
export function SessionControls({
  sessions,
  sessionId,
  catalog,
  driverNumber,
  currentLap,
  showReplayControls,
  onLoaded,
  onDriver,
  onLap,
}: Props) {
  const session = sessions.find((item) => item.id === sessionId);
  const [year, setYear] = useState(new Date().getFullYear() - 1);
  const [events, setEvents] = useState<RaceEvent[]>([]);
  const [round, setRound] = useState(0);
  const [kind, setKind] = useState('Race');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);

  // Library navigation and remote opens use the same visible selection.
  useEffect(() => {
    active.current?.abort();
    setBusy(false);
    setError('');
    if (session) {
      setYear(session.year);
      setRound(session.round ?? 0);
      setKind(session.name);
    }
  }, [sessionId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setEvents([]);
    setError('');
    request<{ items: RaceEvent[] }>(`/api/remote/events?year=${year}`, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setEvents(result.items);
        setRound((previous) => {
          if (result.items.some((item) => item.round === previous)) return previous;
          const monza = result.items.find((item) => item.location === 'Monza');
          return monza?.round ?? result.items[0]?.round ?? 0;
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [year]);

  const event = events.find((item) => item.round === round);
  const availableKind = event?.sessions.some((item) => item.name === kind)
    ? kind
    : (event?.sessions[0]?.name ?? kind);
  const matchesSession =
    session?.year === year && session?.round === round && session?.name === availableKind;
  const ready = !busy && !loading && matchesSession && catalog?.session_id === sessionId;
  const driver = catalog?.drivers.find((item) => item.number === driverNumber);

  async function openSession(event: FormEvent) {
    event.preventDefault();
    setError('');
    const saved = sessions.find(
      (item) => item.year === year && item.round === round && item.name === availableKind,
    );
    if (saved) {
      onLoaded(saved);
      return;
    }
    setBusy(true);
    const controller = new AbortController();
    active.current = controller;
    try {
      const opened = await request<Session>('/api/remote/open', controller.signal, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year, round, session: availableKind }),
      });
      if (!controller.signal.aborted) onLoaded(opened);
    } catch (error) {
      if (!controller.signal.aborted) setError((error as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section
      className="session-controls"
      aria-label="Session selection"
      data-session-id={sessionId}
    >
      <form
        className={
          showReplayControls ? 'session-controls-form' : 'session-controls-form library-controls'
        }
        onSubmit={openSession}
      >
        <label className="year-select">
          <span>YEAR</span>
          <select
            aria-label="Year"
            value={year}
            disabled={busy}
            onChange={(event) => {
              setYear(Number(event.target.value));
              setRound(0);
              setEvents([]);
            }}
          >
            {Array.from(
              { length: new Date().getFullYear() - 2017 },
              (_, i) => new Date().getFullYear() - i,
            ).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="event-select">
          <span>GRAND PRIX</span>
          <select
            aria-label="Grand Prix"
            value={round}
            disabled={loading || busy}
            onChange={(event) => setRound(Number(event.target.value))}
          >
            {!events.length && (
              <option value={0}>{loading ? 'Loading calendar...' : 'No completed events'}</option>
            )}
            {events.map((item) => (
              <option key={item.round} value={item.round}>
                {item.event}
              </option>
            ))}
          </select>
        </label>
        <label className="session-type-select">
          <span>SESSION</span>
          <select
            aria-label="Session type"
            value={availableKind}
            disabled={loading || busy}
            onChange={(event) => setKind(event.target.value)}
          >
            {event?.sessions.map((item) => (
              <option key={item.name}>{item.name}</option>
            ))}
          </select>
        </label>
        <div className="session-open">
          <button className="secondary-button" type="submit" disabled={busy || loading || !round}>
            {busy ? 'Opening session...' : 'Open session'}
          </button>
        </div>
        {showReplayControls && (
          <>
            <label className="driver-select">
              <span>FOLLOW DRIVER</span>
              <select
                aria-label="Driver"
                value={ready ? driverNumber : 0}
                disabled={!ready}
                onChange={(event) => onDriver(Number(event.target.value))}
              >
                {!ready ? (
                  <option value={0}>
                    {busy ? 'Opening session...' : 'Open session to choose'}
                  </option>
                ) : (
                  catalog?.drivers.map((item) => (
                    <option key={item.number} value={item.number}>
                      {item.code} - {item.name}
                      {item.position_samples === 0 ? ' - no positions' : ''}
                    </option>
                  ))
                )}
              </select>
            </label>
            <label className="lap-select">
              <span>JUMP TO LAP</span>
              <select
                aria-label="Jump to lap"
                value={ready ? (currentLap ?? '') : ''}
                disabled={!ready || !driver?.laps.length}
                onChange={(event) => {
                  if (event.target.value) onLap(Number(event.target.value));
                }}
              >
                <option value="">Choose a lap start</option>
                {ready &&
                  driver?.laps.map((lap) => (
                    <option key={lap.lap_number} value={lap.lap_number}>
                      Lap {lap.lap_number}
                    </option>
                  ))}
              </select>
            </label>
          </>
        )}
      </form>
      {busy && (
        <p className="session-notice" role="status">
          Loading driver details and the circuit...
        </p>
      )}
      {!busy && !loading && catalog && !matchesSession && (
        <p className="session-notice">Open the selected session to follow its drivers.</p>
      )}
      {error && (
        <p className="session-notice warning-text" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
