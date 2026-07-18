import { BadgeInfo, Building2 } from 'lucide-react';

import { WarningList } from '../WarningList';
import { ServicePriceLookup } from '../../types';
import { formatVnd, withoutDatasetYear } from '../../lib/structured';
import { NoDataCard } from './NoDataCard';

export function PriceResultCard({ result }: { result: ServicePriceLookup }) {
  return (
    <section className="result-card result-card-price" aria-label="Kết quả tra bảng giá đã cung cấp">
      <header className="result-card-header">
        <div>
          <span className="eyebrow">Tra cứu có cấu trúc</span>
          <h3>Bảng giá dịch vụ kỹ thuật đã cung cấp</h3>
        </div>
        <span className="classification-badge classification-badge-current">
          Bảng giá đã cung cấp / Dữ liệu mới nhất
        </span>
      </header>
      {result.records.length === 0 ? (
        <NoDataCard message="Không tìm thấy dòng giá phù hợp. Hãy nêu rõ tên dịch vụ và cơ sở cần tra." />
      ) : (
        <div className="price-records">
          {result.records.map((record) => (
            <article className="price-record" key={record.price_id}>
              <div className="price-record-title">
                <strong>{withoutDatasetYear(record.display_name)}</strong>
                <span className="price-amount">{formatVnd(record.amount_vnd)}</span>
              </div>
              <div className="record-facts">
                <span>
                  <Building2 size={15} aria-hidden="true" />
                  {record.facility_code}
                </span>
                {record.section ? (
                  <span>
                    <BadgeInfo size={15} aria-hidden="true" />
                    {withoutDatasetYear(record.section)}
                  </span>
                ) : null}
              </div>
              {record.note ? (
                <p className="record-note">Ghi chú nguồn: {withoutDatasetYear(record.note)}</p>
              ) : null}
            </article>
          ))}
        </div>
      )}
      <WarningList warnings={['Mức giá không đồng nghĩa số tiền cuối cùng người bệnh phải trả.']} />
    </section>
  );
}
