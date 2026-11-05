import { useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { advanceTime, clampTime } from '../replay';
import type { ReplayCatalog, ReplayFrame, Track } from '../replay';
export function useReplay(sessionId: string, revision: number) {
  const [catalog, setCatalog] = useState<ReplayCatalog | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [frame, setFrame] = useState<ReplayFrame | null>(null);
  const [driverNumber, setDriverNumber] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [seekRevision, setSeekRevision] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const clock = useRef(0);
  // Load static context, without preloading future telemetry or lap results.
  useEffect(() => {
    setPlaying(false);
    setFrame(null);
    setCatalog(null);
    setTrack(null);
    setError('');
    if (!sessionId) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const base = `/api/sessions/${encodeURIComponent(sessionId)}`;
    Promise.all([
      request<ReplayCatalog>(`${base}/replay`, controller.signal),
      request<Track>(`${base}/track`, controller.signal),
    ])
      .then(([metadata, circuit]) => {
        if (controller.signal.aborted) return;
        clock.current = clampTime(
          (Date.parse(metadata.initial_utc) - Date.parse(metadata.start_utc)) / 1000,
          metadata.duration_s,
        );
        setElapsed(clock.current);
        setDriverNumber(metadata.initial_driver_number);
        setCatalog(metadata);
        setTrack(circuit);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setError(error.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [sessionId, revision]);
  // Await each snapshot so delayed requests cannot overtake a seek or driver change.
  useEffect(() => {
    if (!catalog || catalog.session_id !== sessionId || !driverNumber) return;
    const metadata = catalog;
    const controller = new AbortController();
    const anchor = clock.current;
    const started = performance.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let bufferedMs = 0;
    async function tick() {
      let seconds = clock.current;
      if (playing) {
        const realSeconds = (performance.now() - started - bufferedMs) / 1000;
        seconds = advanceTime(anchor, realSeconds, speed, metadata.duration_s);
      }
      const at = new Date(Date.parse(metadata.start_utc) + seconds * 1000).toISOString();
      const requested = performance.now();
      const buffering = setTimeout(() => {
        if (!controller.signal.aborted) setLoading(true);
      }, 400);
      try {
        const result = await request<ReplayFrame>(
          `/api/sessions/${encodeURIComponent(sessionId)}/replay/frame?at=${encodeURIComponent(at)}&driver_number=${driverNumber}`,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        const waited = performance.now() - requested;
        if (waited > 400) bufferedMs += waited;
        clock.current = result.elapsed_s;
        setElapsed(result.elapsed_s);
        setFrame(result);
        setError('');
        setLoading(false);
        if (seconds >= metadata.duration_s) setPlaying(false);
        else if (playing) timer = setTimeout(tick, 150);
      } catch (error) {
        if (!controller.signal.aborted) {
          setError((error as Error).message);
          setLoading(false);
          setPlaying(false);
        }
      } finally {
        clearTimeout(buffering);
      }
    }
    void tick();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [sessionId, catalog, driverNumber, playing, speed, seekRevision]);
  function seek(seconds: number) {
    if (!catalog) return;
    clock.current = clampTime(seconds, catalog.duration_s);
    setElapsed(clock.current);
    setPlaying(false);
    setFrame(null);
    setLoading(true);
    setSeekRevision((value) => value + 1);
  }
  function togglePlay() {
    if (!catalog) return;
    if (!playing && clock.current >= catalog.duration_s) seek(0);
    setPlaying((value) => !value);
  }
  function chooseDriver(number: number) {
    if (number !== driverNumber) setDriverNumber(number);
  }
  function jumpToLap(number: number) {
    const lap = catalog?.drivers
      .find((driver) => driver.number === driverNumber)
      ?.laps.find((lap) => lap.lap_number === number);
    if (lap && catalog) seek((Date.parse(lap.start_utc) - Date.parse(catalog.start_utc)) / 1000);
  }
  return {
    catalog: catalog?.session_id === sessionId ? catalog : null,
    track: track?.session_id === sessionId ? track : null,
    frame: frame?.session_id === sessionId ? frame : null,
    driverNumber,
    elapsed,
    playing,
    speed,
    error,
    loading,
    seek,
    togglePlay,
    chooseDriver,
    jumpToLap,
    setSpeed,
  };
}
