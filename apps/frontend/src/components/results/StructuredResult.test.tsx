import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StructuredResult } from './StructuredResult';

describe('StructuredResult', () => {
  it('renders the provided price data as the newest demo table without a legacy year label', () => {
    render(
      <StructuredResult
        action={{
          kind: 'service_price',
          data: {
            query: 'khám bệnh',
            classification: 'official_current',
            warning: 'legacy warning intentionally not rendered',
            records: [
              {
                service_record_id: 'service-2025',
                price_id: 'price-2025-1',
                display_name: 'Giá Khám bệnh',
                facility_code: 'CS1',
                amount_vnd: 50600,
                section: 'Khám bệnh',
                note: 'Theo danh mục được cung cấp năm 2025',
              },
            ],
            citations: [],
          },
        }}
      />,
    );
    expect(screen.getByText('Giá Khám bệnh')).toBeInTheDocument();
    expect(screen.getByText('50.600 ₫')).toBeInTheDocument();
    expect(screen.getByText(/Bảng giá đã cung cấp \/ Dữ liệu mới nhất/i)).toBeInTheDocument();
    expect(screen.queryByText(/2025/)).not.toBeInTheDocument();
    expect(screen.queryByText(/dấu vết bản ghi/i)).not.toBeInTheDocument();
  });

  it('renders all BHYT household tiers and the scope warning', () => {
    render(
      <StructuredResult
        action={{
          kind: 'bhyt_household_contribution',
          data: {
            as_of_date: '2026-07-17',
            policy_id: 'BHYT-HOUSEHOLD-2026-CURRENT',
            classification: 'official_current',
            policy_scope: 'household_contribution',
            warning: 'Đây không phải quyền lợi cá nhân.',
            tiers: [
              {
                tier_order: 1,
                member_label: 'Người thứ nhất',
                rate_text: '4,5%',
                monthly_amount_vnd: 113850,
                annual_amount_vnd: 1366200,
              },
            ],
            citations: [],
          },
        }}
      />,
    );
    expect(screen.getByRole('table', { name: /mức đóng BHYT/i })).toBeInTheDocument();
    expect(screen.getByText('1.366.200 ₫')).toBeInTheDocument();
    expect(screen.getByText('Đây không phải quyền lợi cá nhân.')).toBeInTheDocument();
    expect(screen.getByText('Dữ liệu mới nhất')).toBeInTheDocument();
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();
  });

  it('renders schedule records as working hours, not availability', () => {
    render(
      <StructuredResult
        action={{
          kind: 'schedule',
          data: {
            week_start: '2026-06-08',
            facility_code: 'CS1',
            classification: 'partial_official_snapshot',
            warning: 'Lịch làm việc không đồng nghĩa còn suất khám.',
            records: [
              {
                schedule_entry_id: 'schedule-1',
                service_date: '2026-06-08',
                facility_code: 'CS1',
                room_label: 'Phòng khám số 1',
                unit_label: 'Khu tự nguyện',
                provider_text: 'BS Nguyễn Văn A',
                published_hours_raw: '7.00-16.30',
                duty_status: 'scheduled_named',
                assignee_type: 'named',
              },
            ],
            citations: [],
            coverage: { documents_discovered: 3 },
          },
        }}
      />,
    );
    expect(screen.getByText('BS Nguyễn Văn A')).toBeInTheDocument();
    expect(screen.getByText('Lịch làm việc không đồng nghĩa còn suất khám.')).toBeInTheDocument();
    expect(screen.queryByText(/còn 19 chỗ/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('08/06/2026').length).toBeGreaterThan(0);
  });
});
