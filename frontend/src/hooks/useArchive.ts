import { useEffect, useState } from 'react';
import { request } from '../api';
import type { Session } from '../types';
export function useArchive() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    request<{ items: Session[] }>('/api/library', controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        const records = result.items;
        setSessions(records);
        setSessionId((previous) => {
          if (records.some((item) => item.id === previous)) return previous;
          const latestRace = [...records].reverse().find((item) => item.name === 'Race');
          return latestRace?.id ?? records.at(-1)?.id ?? '';
        });
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision]);
  function addSession(session: Session) {
    setSessions((previous) => [...previous.filter((item) => item.id !== session.id), session]);
    setSessionId(session.id);
  }
  return {
    addSession,
    sessions,
    sessionId,
    setSessionId,
    error,
    loading,
    revision,
    refresh: () => setRevision((value) => value + 1),
  };
}
