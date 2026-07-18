import { SearchX } from 'lucide-react';

export function NoDataCard({ message }: { message: string }) {
  return (
    <div className="no-data-card" role="status">
      <SearchX size={19} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
