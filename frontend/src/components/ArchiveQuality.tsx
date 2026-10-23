import { useEffect, useState } from 'react';
import { request } from '../api';
import type { Quality } from '../types';
import { QualityReport } from './QualityReport';
export function ArchiveQuality({
  sessionId,
  driverNumber,
  driverCode,
  lapNumber,
}: {
  sessionId: string;
  driverNumber: number;
  driverCode?: string;
  lapNumber: number;
}) {
  const [quality, setQuality] = useState<Quality | null>(null),
    [error, setError] = useState('');
  useEffect(() => {
    setQuality(null);
    setError('');
    if (!sessionId || !driverNumber) return;
    const controller = new AbortController();
    request<{ profile: Quality }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/drivers/${driverNumber}/quality?lap_number=${lapNumber}`,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setQuality(result.profile);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [sessionId, driverNumber, lapNumber]);
  return (
    <>
      <div className="archive-quality-note">
        PREPARED LAP REPORT - these counts describe the selected lap file, including its complete
        contents independently of the replay clock.
      </div>
      {error && <p role="alert">{error}</p>}
      <QualityReport
        quality={quality}
        driverCode={driverCode}
        sourceLabel="TracingInsights"
        scopeLabel={`Lap ${lapNumber} - prepared samples`}
        prepared
      />
    </>
  );
}
