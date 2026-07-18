import { Building2, CalendarDays, Clock3, MapPin, Stethoscope } from 'lucide-react';

import { ClassificationBadge } from '../ClassificationBadge';
import { WarningList } from '../WarningList';
import { ScheduleEntryRecord, ScheduleLookup } from '../../types';
import { formatDate } from '../../lib/structured';
import { NoDataCard } from './NoDataCard';

const STATUS_LABELS: Record<string, string> = {
  scheduled_named: 'Có phân công',
  generic_assignment: 'Phân công chung',
  non_doctor_activity: 'Hoạt động khác',
  closed: 'Nghỉ',
  not_published: 'Chưa công bố',
};

function CoverageSummary({ coverage }: { coverage: Record<string, unknown> }) {
  const items = [
    ['documents_discovered', 'Tài liệu phát hiện'],
    ['documents_accepted', 'Tài liệu hợp lệ'],
    ['entries_generated', 'Dòng lịch'],
    ['entry_count', 'Dòng lịch'],
  ] as const;
  const visible = items.filter(([key]) => typeof coverage[key] === 'number');
  if (visible.length === 0) {
    return null;
  }
  return (
    <dl className="coverage-summary">
      {visible.map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>{String(coverage[key])}</dd>
        </div>
      ))}
    </dl>
  );
}

function ScheduleRecord({ record }: { record: ScheduleEntryRecord }) {
  return (
    <article className="schedule-record">
      <div className="schedule-date">
        <CalendarDays size={17} aria-hidden="true" />
        <strong>{formatDate(record.service_date)}</strong>
        <span>{STATUS_LABELS[record.duty_status] ?? record.duty_status}</span>
      </div>
      <dl>
        <div>
          <dt><Building2 size={15} aria-hidden="true" /> Cơ sở</dt>
          <dd>{record.facility_code}</dd>
        </div>
        {record.unit_label ? (
          <div>
            <dt><MapPin size={15} aria-hidden="true" /> Đơn vị</dt>
            <dd>{record.unit_label}</dd>
          </div>
        ) : null}
        {record.room_label ? (
          <div>
            <dt><MapPin size={15} aria-hidden="true" /> Phòng</dt>
            <dd>{record.room_label}</dd>
          </div>
        ) : null}
        <div>
          <dt><Stethoscope size={15} aria-hidden="true" /> Phân công</dt>
          <dd>{record.provider_text || 'Nguồn không công bố tên cụ thể'}</dd>
        </div>
        {record.published_hours_raw ? (
          <div>
            <dt><Clock3 size={15} aria-hidden="true" /> Khung giờ công bố</dt>
            <dd>{record.published_hours_raw}</dd>
          </div>
        ) : null}
      </dl>
      <details className="record-id">
        <summary>Dấu vết bản ghi</summary>
        <code>{record.schedule_entry_id}</code>
      </details>
    </article>
  );
}

export function ScheduleResultCard({ result }: { result: ScheduleLookup }) {
  const primary = result.records.slice(0, 8);
  const remaining = result.records.slice(8);
  return (
    <section className="result-card result-card-schedule" aria-label="Lịch làm việc được công bố">
      <header className="result-card-header">
        <div>
          <span className="eyebrow">Lịch làm việc</span>
          <h3>Tuần bắt đầu {formatDate(result.week_start)}</h3>
        </div>
        <ClassificationBadge value={result.classification} />
      </header>
      <CoverageSummary coverage={result.coverage} />
      {result.records.length === 0 ? (
        <NoDataCard message="Không tìm thấy lịch phù hợp trong tuần và bộ lọc được hỏi." />
      ) : (
        <div className="schedule-records">
          {primary.map((record) => <ScheduleRecord key={record.schedule_entry_id} record={record} />)}
          {remaining.length > 0 ? (
            <details className="more-records">
              <summary>Xem thêm {remaining.length} dòng lịch</summary>
              <div className="schedule-records schedule-records-more">
                {remaining.map((record) => <ScheduleRecord key={record.schedule_entry_id} record={record} />)}
              </div>
            </details>
          ) : null}
        </div>
      )}
      <WarningList warnings={[result.warning]} />
    </section>
  );
}
