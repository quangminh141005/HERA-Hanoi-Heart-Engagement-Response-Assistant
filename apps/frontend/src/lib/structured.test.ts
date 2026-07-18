import { describe, expect, it } from 'vitest';

import { getStructuredAction, safeExternalUrl, withoutDatasetYear } from './structured';

describe('structured response guards', () => {
  it('recognizes a price action from chat metadata', () => {
    const action = getStructuredAction({
      structured_action: {
        query: 'khám bệnh',
        facility_code: 'CS1',
        as_of_date: null,
        classification: 'official_current',
        warning: '',
        records: [
          {
            service_record_id: 'service-1',
            price_id: 'price-1',
            display_name: 'Khám bệnh',
            facility_code: 'CS1',
            amount_vnd: 50600,
            amount_raw: '50.600',
            section: 'Khám bệnh',
            note: null,
          },
        ],
        citations: [],
      },
    });
    expect(action?.kind).toBe('service_price');
  });

  it('rejects a malformed structured payload without breaking the plain answer', () => {
    expect(getStructuredAction({ structured_action: { records: 'not-an-array' } })).toBeNull();
  });

  it('blocks non-http citation protocols', () => {
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull();
    expect(safeExternalUrl('https://example.com/source')).toBe('https://example.com/source');
  });

  it('removes supplied-data year labels without changing schedule dates globally', () => {
    expect(withoutDatasetYear('Bảng giá dịch vụ kỹ thuật năm 2025')).toBe(
      'Bảng giá dịch vụ kỹ thuật',
    );
    expect(withoutDatasetYear('Áp dụng từ 01/07/2026 cho hộ gia đình')).toBe(
      'Áp dụng cho hộ gia đình',
    );
  });
});
