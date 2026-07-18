import { DataClassification } from '../types';

const LABELS: Record<string, string> = {
  official_current: 'Nguồn hiện hành',
  // Compatibility with older API records: the supplied dataset is treated as
  // the current demo source, so legacy classifications must not leak to users.
  official_historical: 'Nguồn đã cung cấp',
  secondary_historical: 'Nguồn đã cung cấp',
  partial_official_snapshot: 'Lịch công bố theo tuần',
  review_only: 'Đang chờ xác minh',
};

export function ClassificationBadge({ value }: { value: DataClassification }) {
  const tone =
    value === 'official_current'
      ? 'current'
      : value === 'official_historical' || value === 'secondary_historical'
        ? 'provided'
        : value === 'review_only'
          ? 'review'
          : 'partial';
  return <span className={`classification-badge classification-badge-${tone}`}>{LABELS[value] ?? value}</span>;
}
