export function lapTime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const totalMilliseconds = Math.round(seconds * 1000);
  const minutes = Math.floor(totalMilliseconds / 60000);
  const remainingSeconds = Math.floor(totalMilliseconds / 1000) % 60;
  const milliseconds = totalMilliseconds % 1000;
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`;
}
