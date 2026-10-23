import type { ReactNode } from 'react';

export function Icon({ name, size = 19 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    telemetry: 'M3 15h3l3-9 4 13 3-8h5',
    analysis: 'M4 19V5 M4 19h17 M7 14l4-6 4 3 5-7 M7 17l4-3 4 2 5-5',
    sessions: 'M4 5h16v14H4z M4 9h16 M8 3v4 M16 3v4',
    quality: 'M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7z M8 12l3 3 5-6',
    refresh: 'M20 8a8 8 0 1 0 1 7 M20 3v5h-5',
    arrow: 'M5 12h14 M14 7l5 5-5 5',
    chevron: 'm8 5 7 7-7 7',
    pin: 'M9 3h6 M10 3v6l-3 4h10l-3-4V3 M12 13v8',
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.telemetry} />
    </svg>
  );
}

export function Blank({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="blank">
      <span className="blank-icon">
        <Icon name="telemetry" size={30} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
