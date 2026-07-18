import { ShieldCheck } from 'lucide-react';

import { WarningList } from '../WarningList';
import { BhytLookup } from '../../types';
import { formatVnd, withoutDatasetYear } from '../../lib/structured';
import { NoDataCard } from './NoDataCard';

export function BhytContributionCard({ result }: { result: BhytLookup }) {
  return (
    <section className="result-card result-card-bhyt" aria-label="Mức đóng bảo hiểm y tế hộ gia đình">
      <header className="result-card-header">
        <div>
          <span className="eyebrow">Mức đóng hộ gia đình</span>
          <h3>Mức đóng BHYT hộ gia đình</h3>
        </div>
        <span className="classification-badge classification-badge-current">
          Dữ liệu mới nhất
        </span>
      </header>
      <div className="result-context-row">
        <span>
          <ShieldCheck size={15} aria-hidden="true" />
          Dữ liệu chính sách đã cung cấp cho dự án
        </span>
      </div>
      {result.tiers.length === 0 ? (
        <NoDataCard message="Không tìm thấy bậc đóng phù hợp với ngày được hỏi." />
      ) : (
        <div className="table-scroll" tabIndex={0} aria-label="Bảng mức đóng BHYT, có thể cuộn ngang">
          <table className="result-table">
            <caption className="sr-only">Các mức đóng BHYT hộ gia đình</caption>
            <thead>
              <tr>
                <th scope="col">Thành viên</th>
                <th scope="col">Tỷ lệ</th>
                <th scope="col">Hằng tháng</th>
                <th scope="col">12 tháng</th>
              </tr>
            </thead>
            <tbody>
              {result.tiers.map((tier) => (
                <tr key={tier.tier_order}>
                  <th scope="row">{withoutDatasetYear(tier.member_label)}</th>
                  <td>{tier.rate_text ? withoutDatasetYear(tier.rate_text) : 'Theo nguồn công bố'}</td>
                  <td>{formatVnd(tier.monthly_amount_vnd)}</td>
                  <td>{formatVnd(tier.annual_amount_vnd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <WarningList warnings={[withoutDatasetYear(result.warning)]} />
    </section>
  );
}
