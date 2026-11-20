import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import type { useReplay } from '../hooks/useReplay';

interface Result {
  answer: string;
  at_utc: string;
  evidence: { tool: string; arguments: Record<string, unknown>; data: unknown }[];
}

export function RaceAnalyst({
  sessionId,
  replay,
}: {
  sessionId: string;
  replay: ReturnType<typeof useReplay>;
}) {
  const [configured, setConfigured] = useState(false);
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    request<{ configured: boolean }>('/api/analyst/status', controller.signal)
      .then((status) => setConfigured(status.configured))
      .catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    active.current?.abort();
    setResult(null);
    setError('');
    setBusy(false);
    return () => active.current?.abort();
  }, [sessionId]);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (!replay.frame || !question.trim() || busy) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const answer = await request<Result>(
        `/api/sessions/${encodeURIComponent(sessionId)}/analyst`,
        controller.signal,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            at: replay.frame.at_utc,
            driver_number: replay.driverNumber,
            question: question.trim(),
          }),
        },
      );
      if (!controller.signal.aborted) setResult(answer);
    } catch (err) {
      if (!controller.signal.aborted) setError((err as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return (
    <section className="panel analyst-panel" aria-label="AI race analyst">
      <div className="panel-heading">
        <div>
          <h2>AI race analyst</h2>
          <p>Ask about the session at the current replay time.</p>
        </div>
      </div>
      <div className="analyst-body">
        {!configured && (
          <p>
            To get started, add your Gemini API key to <code>data/gemini-key.txt</code> in the
            RaceOS folder, then refresh this page.
          </p>
        )}
        <form onSubmit={ask}>
          <label htmlFor="analyst-question">Your question</label>
          <textarea
            id="analyst-question"
            value={question}
            maxLength={1200}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Where did Norris lose time compared with Verstappen?"
          />
          <button
            className="secondary-button"
            disabled={!configured || !replay.frame || !question.trim() || busy}
          >
            {busy ? 'Checking race data?' : 'Ask analyst'}
          </button>
        </form>
        {!replay.frame && (
          <p>Open a session and move the replay to the moment you want to analyze.</p>
        )}
        {error && (
          <p className="warning-text" role="alert">
            {error}
          </p>
        )}
        {result && (
          <div className="analyst-result">
            <p className="analyst-answer">{result.answer}</p>
            <p>Replay time: {result.at_utc}</p>
            <details>
              <summary>Data checked ({result.evidence.length})</summary>
              {result.evidence.map((item, index) => (
                <div key={index}>
                  <strong>{item.tool.replaceAll('_', ' ')}</strong>
                  <pre>
                    {JSON.stringify({ arguments: item.arguments, data: item.data }, null, 2)}
                  </pre>
                </div>
              ))}
            </details>
          </div>
        )}
      </div>
    </section>
  );
}
