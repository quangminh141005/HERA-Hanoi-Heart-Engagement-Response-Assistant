import { AlertTriangle } from 'lucide-react';

export function WarningList({ warnings }: { warnings: Array<string | null | undefined> }) {
  const visible = [...new Set(warnings.filter((item): item is string => Boolean(item?.trim())))];
  if (visible.length === 0) {
    return null;
  }
  return (
    <div className="warning-list" role="note" aria-label="Lưu ý quan trọng">
      <AlertTriangle size={18} aria-hidden="true" />
      <ul>
        {visible.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}
