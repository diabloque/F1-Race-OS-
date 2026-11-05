import type { ReactNode } from 'react';

const iconPaths = {
  telemetry: 'M3 15h3l3-9 4 13 3-8h5',
  sessions: 'M4 5h16v14H4z M4 9h16 M8 3v4 M16 3v4',
  refresh: 'M20 8a8 8 0 1 0 1 7 M20 3v5h-5',
  arrow: 'M5 12h14 M14 7l5 5-5 5',
  chevron: 'm8 5 7 7-7 7',
};

type IconName = keyof typeof iconPaths;

export function Icon({ name, size = 19 }: { name: IconName; size?: number }) {
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
      <path d={iconPaths[name]} />
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
