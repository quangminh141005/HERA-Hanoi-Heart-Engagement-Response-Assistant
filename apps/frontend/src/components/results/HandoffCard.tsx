import { ExternalLink, Headphones, PhoneCall, ShieldX } from 'lucide-react';

import { safeExternalUrl } from '../../lib/structured';
import { ChatAction } from '../../types';

function actionHref(action: ChatAction): string | null {
  if (action.type === 'call') {
    if (!/^[+\d][\d\s().-]*$/.test(action.target)) {
      return null;
    }
    return `tel:${action.target.replace(/[^+\d]/g, '')}`;
  }
  if (action.type === 'open_url') {
    return safeExternalUrl(action.target);
  }
  return null;
}

export function HandoffCard({
  actions,
  refusal = false,
}: {
  actions: ChatAction[];
  refusal?: boolean;
}) {
  const Icon = refusal ? ShieldX : Headphones;
  const visibleActions = actions.flatMap((action) => {
    const href = actionHref(action);
    return href ? [{ action, href }] : [];
  });
  return (
    <section className={`handoff-card${refusal ? ' handoff-card-refusal' : ''}`} role="note">
      <Icon size={20} aria-hidden="true" />
      <div>
        <h3>{refusal ? 'Không thể trả lời an toàn từ dữ liệu hiện có' : 'Cần kênh hỗ trợ chính thức'}</h3>
        <p>
          {refusal
            ? 'HERA sẽ không đoán thông tin còn thiếu. Vui lòng dùng kênh liên hệ chính thức của bệnh viện.'
            : 'Vui lòng làm theo kênh liên hệ được nêu trong câu trả lời. HERA không tự tạo số điện thoại hoặc đường dẫn.'}
        </p>
        {visibleActions.length > 0 ? (
          <div className="handoff-actions" aria-label="Kênh hỗ trợ chính thức">
            {visibleActions.map(({ action, href }) => {
              const ActionIcon = action.type === 'call' ? PhoneCall : ExternalLink;
              return (
                <a
                  href={href}
                  key={`${action.channel_id}:${href}`}
                  rel={action.type === 'open_url' ? 'noreferrer' : undefined}
                  target={action.type === 'open_url' ? '_blank' : undefined}
                >
                  <ActionIcon size={16} aria-hidden="true" />
                  {action.label_vi}
                </a>
              );
            })}
          </div>
        ) : null}
      </div>
    </section>
  );
}
