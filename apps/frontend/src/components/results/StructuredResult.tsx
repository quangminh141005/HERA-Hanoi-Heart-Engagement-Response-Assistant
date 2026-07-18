import { StructuredAction } from '../../types';
import { BhytContributionCard } from './BhytContributionCard';
import { PriceResultCard } from './PriceResultCard';
import { ScheduleResultCard } from './ScheduleResultCard';

export function StructuredResult({ action }: { action: StructuredAction }) {
  switch (action.kind) {
    case 'service_price':
      return <PriceResultCard result={action.data} />;
    case 'bhyt_household_contribution':
      return <BhytContributionCard result={action.data} />;
    case 'schedule':
      return <ScheduleResultCard result={action.data} />;
  }
}
