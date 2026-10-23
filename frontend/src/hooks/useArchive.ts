import { useEffect, useState } from 'react';
import { request } from '../api';
import type { Health, Session } from '../types';
export function useArchive() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    Promise.all([
      request<{ items: Session[] }>('/api/library', controller.signal).then(
        (result) => result.items,
      ),
      request<Health>('/api/health', controller.signal),
    ])
      .then(([records, status]) => {
        if (controller.signal.aborted) return;
        setSessions(records);
        setHealth(status);
        setSessionId((previous) =>
          records.some((item) => item.id === previous)
            ? previous
            : ([...records].reverse().find((item) => item.name === 'Race')?.id ??
              records.at(-1)?.id ??
              ''),
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setError(error.message);
          setHealth(null);
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
    health,
    error,
    loading,
    revision,
    refresh: () => setRevision((value) => value + 1),
  };
}
