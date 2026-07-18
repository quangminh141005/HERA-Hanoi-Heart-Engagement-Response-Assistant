import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ChatMessage } from '../../types';
import { AssistantMessage } from './AssistantMessage';

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 'message-1',
    role: 'assistant',
    content: 'Nội dung trả lời.',
    intent: 'greeting',
    citations: [],
    metadata: {},
    ...overrides,
  };
}

describe('AssistantMessage', () => {
  it('prioritizes the emergency card and exposes the 115 call action', () => {
    render(<AssistantMessage message={message({ emergency: true, requiresHandoff: true })} />);
    expect(screen.getByRole('alert', { name: /hướng dẫn cấp cứu/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /gọi 115/i })).toHaveAttribute('href', 'tel:115');
  });

  it('renders a refusal card when guardrails reject a request', () => {
    render(
      <AssistantMessage
        message={message({
          intent: 'unsupported',
          metadata: { guardrail_violation: 'medical_advice' },
        })}
      />,
    );
    expect(screen.getByText(/Không thể trả lời an toàn từ dữ liệu hiện có/i)).toBeInTheDocument();
  });

  it('shows a non-link source safely in the citation drawer', () => {
    render(
      <AssistantMessage
        message={message({ citations: [{ source_id: 'source-1', title: 'Nguồn nội bộ đã duyệt' }] })}
      />,
    );
    expect(screen.getByText('Kiểm tra nguồn (1)')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Nguồn nội bộ đã duyệt/i })).not.toBeInTheDocument();
  });

  it('offers feedback controls when the API returns a request ID', () => {
    render(<AssistantMessage message={message({ requestId: 'request-1' })} />);

    expect(screen.getByRole('button', { name: /câu trả lời hữu ích/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /câu trả lời chưa hữu ích/i })).toBeInTheDocument();
  });

  it('renders only safe official handoff actions returned by the backend', () => {
    render(
      <AssistantMessage
        message={message({
          actions: [
            {
              type: 'call',
              channel_id: 'PHONE-OFFICIAL',
              label_vi: 'Gọi kênh chính thức',
              target: '1900 1082',
            },
            {
              type: 'open_url',
              channel_id: 'UNSAFE',
              label_vi: 'Liên kết không an toàn',
              target: 'javascript:alert(1)',
            },
          ],
        })}
      />,
    );

    expect(screen.getByRole('link', { name: /gọi kênh chính thức/i })).toHaveAttribute(
      'href',
      'tel:19001082',
    );
    expect(screen.queryByRole('link', { name: /liên kết không an toàn/i })).not.toBeInTheDocument();
  });

  it('presents supplied BHYT data as current without leaking dataset years', () => {
    render(
      <AssistantMessage
        message={message({
          content: 'Mức BHYT năm 2026 theo dữ liệu đã cung cấp.',
          intent: 'bhyt_household_contribution',
          dataClassification: 'secondary_historical',
          warnings: ['Áp dụng từ 01/07/2026 cho hộ gia đình.'],
          citations: [
            {
              source_id: 'BHYT-2026-CURRENT',
              title: 'Bảng mức đóng BHYT năm 2026',
              effective_from: '2026-07-01',
              excerpt: 'Áp dụng từ 01/07/2026 cho hộ gia đình.',
            },
          ],
          structuredAction: {
            kind: 'bhyt_household_contribution',
            data: {
              as_of_date: '2026-07-17',
              policy_id: 'BHYT-HOUSEHOLD-2026-CURRENT',
              classification: 'secondary_historical',
              policy_scope: 'household_contribution',
              warning: 'Áp dụng từ 01/07/2026 cho hộ gia đình.',
              tiers: [
                {
                  tier_order: 1,
                  member_label: 'Người thứ nhất',
                  monthly_amount_vnd: 113850,
                  annual_amount_vnd: 1366200,
                },
              ],
              citations: [],
            },
          },
        })}
      />,
    );

    expect(screen.getByText('Nguồn hiện hành')).toBeInTheDocument();
    expect(screen.getByText('Bảng mức đóng BHYT')).toBeInTheDocument();
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();
    expect(screen.queryByText(/dữ liệu lịch sử/i)).not.toBeInTheDocument();
  });

  it('keeps a price clarification visible while removing its dataset year', () => {
    render(
      <AssistantMessage
        message={message({
          content: 'Theo bảng giá năm 2025, vui lòng chọn đúng cơ sở trước khi đối chiếu.',
          intent: 'service_price_current',
          dataClassification: 'official_current',
          structuredAction: {
            kind: 'service_price',
            data: {
              query: 'dịch vụ trùng tên',
              classification: 'official_current',
              warning: 'Cần chọn cơ sở.',
              records: [],
              citations: [],
            },
          },
        })}
      />,
    );

    expect(screen.getByText(/vui lòng chọn đúng cơ sở trước khi đối chiếu/i)).toBeInTheDocument();
    expect(screen.queryByText(/2025/)).not.toBeInTheDocument();
  });
});
