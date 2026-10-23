import { clockLabel } from '../replay';
interface Props {
  elapsed: number;
  duration: number;
  playing: boolean;
  speed: number;
  disabled: boolean;
  onSeek: (value: number) => void;
  onPlay: () => void;
  onSpeed: (value: number) => void;
}
export function ReplayControls({
  elapsed,
  duration,
  playing,
  speed,
  disabled,
  onSeek,
  onPlay,
  onSpeed,
}: Props) {
  return (
    <div className="replay-controls">
      <div className="playback-row">
        <div className="playback-buttons">
          <button
            className="transport-button"
            aria-label="Jump to start"
            disabled={disabled}
            onClick={() => onSeek(0)}
          >
            |&lt;
          </button>
          <button
            className="transport-button"
            aria-label="Back 10 seconds"
            disabled={disabled}
            onClick={() => onSeek(elapsed - 10)}
          >
            -10s
          </button>
          <button
            className="play-button"
            aria-label={playing ? 'Pause replay' : 'Play replay'}
            disabled={disabled}
            onClick={onPlay}
          >
            {playing ? 'Pause' : 'Play'}
            <span aria-hidden="true">{playing ? 'II' : '>'}</span>
          </button>
          <button
            className="transport-button"
            aria-label="Forward 10 seconds"
            disabled={disabled}
            onClick={() => onSeek(elapsed + 10)}
          >
            +10s
          </button>
          <button
            className="transport-button"
            aria-label="Jump to end"
            disabled={disabled}
            onClick={() => onSeek(duration)}
          >
            &gt;|
          </button>
        </div>
        <div className="playback-clock">
          <span>SESSION TIME</span>
          <strong data-testid="replay-time" data-seconds={elapsed}>
            {clockLabel(elapsed)}
          </strong>
          <small>/ {clockLabel(duration)}</small>
        </div>
        <label className="speed-control">
          <span>PLAYBACK</span>
          <select
            aria-label="Playback speed"
            value={speed}
            onChange={(event) => onSpeed(Number(event.target.value))}
          >
            {[0.25, 0.5, 1, 2, 4, 8, 16].map((value) => (
              <option key={value} value={value}>
                {value}x
              </option>
            ))}
          </select>
        </label>
      </div>
      <input
        type="range"
        className="replay-timeline"
        aria-label="Replay timeline"
        aria-valuetext={clockLabel(elapsed)}
        min="0"
        max={Math.max(0.001, duration)}
        step="0.001"
        value={elapsed}
        disabled={disabled}
        onChange={(event) => onSeek(Number(event.target.value))}
      />
      <div className="timeline-hints">
        <span>Seek anywhere - scrubbing pauses playback</span>
        <span>{playing ? 'PLAYING' : 'PAUSED'}</span>
      </div>
    </div>
  );
}
