import { CitationDrawer } from '../../components/CitationDrawer';
import { ClassificationBadge } from '../../components/ClassificationBadge';
import { EmergencyCard } from '../../components/results/EmergencyCard';
import { HandoffCard } from '../../components/results/HandoffCard';
import { StructuredResult } from '../../components/results/StructuredResult';
import { WarningList } from '../../components/WarningList';
import { mergeCitations, withoutDatasetYear } from '../../lib/structured';
import { ChatMessage } from '../../types';
import { FeedbackControls } from './FeedbackControls';

const INTENT_LABELS: Record<string, string> = {
  service_price: 'Tra bảng giá',
  service_price_current: 'Tra bảng giá',
  service_price_historical: 'Tra bảng giá',
  insurance: 'BHYT',
  bhyt_household_contribution: 'Mức đóng BHYT hộ gia đình',
  doctor_schedule: 'Lịch bác sĩ',
  schedule: 'Lịch làm việc',
  emergency: 'Cấp cứu',
  appointment: 'Đặt khám',
  booking: 'Đặt khám',
  hospital_contact: 'Thông tin liên hệ',
  working_hours: 'Giờ làm việc',
  procedure: 'Thủ tục',
  greeting: 'Chào hỏi',
  thanks: 'Cảm ơn',
  unsupported: 'Ngoài phạm vi',
};

const CURRENT_DATASET_INTENTS = new Set([
  'service_price',
  'service_price_current',
  'service_price_historical',
  'insurance',
  'bhyt_household_contribution',
]);

export function AssistantMessage({ message }: { message: ChatMessage }) {
  const structuredCitations = message.structuredAction?.data.citations;
  const citations = mergeCitations(message.citations, structuredCitations);
  const refusal =
    message.intent === 'unsupported' || Boolean(message.metadata?.guardrail_violation);
  const currentDataset = message.structuredAction?.kind === 'service_price'
    || message.structuredAction?.kind === 'bhyt_household_contribution'
    || Boolean(message.intent && CURRENT_DATASET_INTENTS.has(message.intent));
  const visibleContent = currentDataset
    ? withoutDatasetYear(message.content)
    : message.content;
  const visibleWarnings = currentDataset
    ? (message.warnings ?? []).map(withoutDatasetYear).filter(Boolean)
    : (message.warnings ?? []);

  return (
    <article className="message message-assistant">
      <div className="message-meta">
        <strong><img className="agent-icon" src="/icons/hera-agent-192.png" alt="" /> HERA</strong>
        {message.intent ? <span>{INTENT_LABELS[message.intent] ?? message.intent}</span> : null}
        {message.dataClassification ? (
          <ClassificationBadge value={currentDataset ? 'official_current' : message.dataClassification} />
        ) : null}
      </div>
      {message.emergency ? <EmergencyCard /> : null}
      {visibleContent ? <p>{visibleContent}</p> : null}
      {message.structuredAction ? <StructuredResult action={message.structuredAction} /> : null}
      {!message.structuredAction ? <WarningList warnings={visibleWarnings} /> : null}
      {!message.emergency && (message.requiresHandoff || refusal || Boolean(message.actions?.length)) ? (
        <HandoffCard actions={message.actions ?? []} refusal={refusal} />
      ) : null}
      <CitationDrawer citations={citations} currentDataset={currentDataset} />
      {message.requestId ? <FeedbackControls requestId={message.requestId} /> : null}
    </article>
  );
}
