type StatusTone = 'neutral' | 'safe' | 'warning';

export function StatusPill({
  children,
  tone = 'neutral',
}: {
  children: string;
  tone?: StatusTone;
}) {
  return <span className={`status-pill status-pill-${tone}`}>{children}</span>;
}

