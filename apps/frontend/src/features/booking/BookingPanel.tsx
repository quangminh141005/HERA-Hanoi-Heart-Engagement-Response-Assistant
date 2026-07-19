import {
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Clock3,
  FlaskConical,
  MapPin,
  RefreshCw,
  Search,
  Stethoscope,
  TicketCheck,
  Trash2,
  UserRound,
  Users,
  X,
} from 'lucide-react';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

import { ErrorState, LoadingState } from '../../components/FeedbackStates';
import { ApiClientError } from '../../lib/api';
import { formatDate } from '../../lib/structured';
import {
  BookingSessionFilters,
  confirmBookingHold,
  createBookingHold,
  createIdempotencyKey,
  getAnonymousSessionId,
  listBookingDoctors,
  listBookingSessions,
  releaseBookingHold,
} from './api';
import {
  ActiveBookingHold,
  BookingDoctorOption,
  BookingSessionListResponse,
  BookingSessionSummary,
} from './contracts';

const INITIAL_VISIBLE_COUNT = 12;
const DEMO_AUTO_APPROVE_SECONDS = 10;
const DEMO_EXAM_FEE_VND = 200_000;
const DEMO_SERVICE_FEE_VND = 300_000;

const SESSION_LABELS: Record<string, string> = {
  morning: 'Buổi sáng',
  afternoon: 'Buổi chiều',
  evening: 'Buổi tối',
};

function sessionLabel(value: string): string {
  return SESSION_LABELS[value] ?? value;
}

function addDays(isoDate: string, days: number): string {
  const parsed = new Date(`${isoDate}T00:00:00`);
  parsed.setDate(parsed.getDate() + days);
  return [
    parsed.getFullYear(),
    String(parsed.getMonth() + 1).padStart(2, '0'),
    String(parsed.getDate()).padStart(2, '0'),
  ].join('-');
}

function weekdayLabel(isoDate: string): string {
  return new Intl.DateTimeFormat('vi-VN', { weekday: 'short' })
    .format(new Date(`${isoDate}T00:00:00`));
}

function formatVnd(value: number): string {
  return new Intl.NumberFormat('vi-VN', {
    currency: 'VND',
    maximumFractionDigits: 0,
    style: 'currency',
  }).format(value);
}

function parseOptionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function parseOptionalInteger(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export function secondsUntil(expiresAt: string, nowMs = Date.now()): number {
  const expiresMs = Date.parse(expiresAt);
  if (!Number.isFinite(expiresMs)) {
    return 0;
  }
  return Math.max(0, Math.ceil((expiresMs - nowMs) / 1000));
}

export function formatCountdown(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function SessionCard({
  disabled,
  isHolding,
  onHold,
  session,
}: {
  disabled: boolean;
  isHolding: boolean;
  onHold: (session: BookingSessionSummary) => void;
  session: BookingSessionSummary;
}) {
  const full = session.remaining_count <= 0;
  const closed = session.status !== 'open';
  const unavailable = full || closed;
  return (
    <article className="booking-session-card">
      <header>
        <div>
          <span className="prototype-badge"><FlaskConical size={13} aria-hidden="true" /> Bản demo</span>
          <h3>{session.doctor_name}</h3>
        </div>
        <strong className={unavailable ? 'capacity capacity-full' : 'capacity'}>
          {closed ? 'Ca đã đóng' : full ? 'Đã đủ chỗ' : `Còn ${session.remaining_count}/${session.capacity_limit}`}
        </strong>
      </header>
      <dl>
        <div>
          <dt><CalendarDays size={15} aria-hidden="true" /> Ngày</dt>
          <dd>{formatDate(session.service_date)}</dd>
        </div>
        <div>
          <dt><Clock3 size={15} aria-hidden="true" /> Ca</dt>
          <dd>{sessionLabel(session.session_key)}</dd>
        </div>
        {session.facility_code ? (
          <div>
            <dt><MapPin size={15} aria-hidden="true" /> Cơ sở</dt>
            <dd>{session.facility_code}</dd>
          </div>
        ) : null}
        {session.room_label ? (
          <div>
            <dt><Stethoscope size={15} aria-hidden="true" /> Phòng</dt>
            <dd>{session.room_label}</dd>
          </div>
        ) : null}
      </dl>
      <div className="capacity-meter">
        <progress
          aria-label={`Số chỗ đã dùng: ${session.occupied_count} trên ${session.capacity_limit}`}
          max={session.capacity_limit}
          value={session.occupied_count}
        />
        <small><Users size={14} aria-hidden="true" /> {session.occupied_count} chỗ đang được giữ hoặc đã dùng</small>
      </div>
      <button
        className="hold-button"
        disabled={disabled || unavailable}
        type="button"
        onClick={() => onHold(session)}
      >
        {isHolding ? <RefreshCw className="spin-icon" size={17} aria-hidden="true" /> : <TicketCheck size={17} aria-hidden="true" />}
        {isHolding
          ? 'Đang giữ chỗ...'
          : closed
            ? 'Ca không nhận giữ chỗ'
            : full
              ? 'Ca đã đủ chỗ'
              : 'Chọn ca này'}
      </button>
      <small className="record-hint">Ngưỡng áp dụng cho mỗi bác sĩ, mỗi ngày, mỗi ca.</small>
    </article>
  );
}

function ActiveHoldCard({
  hold,
  onRelease,
  releasing,
  status,
  secondsLeft,
}: {
  hold: ActiveBookingHold;
  onRelease: () => void;
  releasing: boolean;
  status: 'held' | 'confirmed' | 'released' | 'expired';
  secondsLeft: number;
}) {
  const isHeld = status === 'held' && secondsLeft > 0;
  return (
    <section className={`active-hold-card active-hold-${status}`} aria-live="polite">
      <div>
        <span className="eyebrow">Trạng thái giữ chỗ</span>
        <h3>
          {status === 'released'
            ? 'Đã hủy giữ chỗ'
            : status === 'expired'
              ? 'Chỗ giữ tạm đã hết hạn'
              : status === 'confirmed'
                ? 'Đã duyệt trong bản demo'
                : 'Đang giữ chỗ tạm'}
        </h3>
        <p>
          {hold.booking_session.doctor_name} · {formatDate(hold.booking_session.service_date)} ·{' '}
          {sessionLabel(hold.booking_session.session_key)}
        </p>
      </div>
      {status === 'confirmed' ? (
        <div className="hold-countdown hold-approved">
          <CheckCircle2 size={19} aria-hidden="true" />
          <span>Demo approved</span>
        </div>
      ) : null}
      {isHeld ? (
        <div className="hold-countdown">
          <Clock3 size={19} aria-hidden="true" />
          <span>
            Còn <strong>{formatCountdown(secondsLeft)}</strong>
          </span>
        </div>
      ) : null}
      <p className="prototype-warning">
        <FlaskConical size={16} aria-hidden="true" />
        {status === 'confirmed'
          ? 'HERA tự duyệt sau 10 giây để trình diễn demo; chưa phải lịch hẹn được Bệnh viện xác nhận.'
          : 'Đây chỉ là giữ chỗ của bản demo HERA, chưa phải lịch hẹn được Bệnh viện xác nhận.'}
      </p>
      {isHeld ? (
        <button
          className="release-button"
          disabled={releasing || !hold.hold_token}
          type="button"
          onClick={onRelease}
        >
          {releasing ? <RefreshCw className="spin-icon" size={16} aria-hidden="true" /> : <Trash2 size={16} aria-hidden="true" />}
          {releasing ? 'Đang hủy...' : 'Hủy chỗ đang giữ'}
        </button>
      ) : null}
    </section>
  );
}

function BookingPatientModal({
  holding,
  onClose,
  onSubmit,
  patientAddress,
  patientBhyt,
  patientBloodPressure,
  patientCccd,
  patientDob,
  patientGender,
  patientHeartRate,
  patientHeight,
  patientName,
  patientPhone,
  patientReason,
  patientSpo2,
  patientWeight,
  selectedSession,
  setPatientAddress,
  setPatientBhyt,
  setPatientBloodPressure,
  setPatientCccd,
  setPatientDob,
  setPatientGender,
  setPatientHeartRate,
  setPatientHeight,
  setPatientName,
  setPatientPhone,
  setPatientReason,
  setPatientSpo2,
  setPatientWeight,
}: {
  holding: boolean;
  onClose: () => void;
  onSubmit: () => void;
  patientAddress: string;
  patientBhyt: string;
  patientBloodPressure: string;
  patientCccd: string;
  patientDob: string;
  patientGender: string;
  patientHeartRate: string;
  patientHeight: string;
  patientName: string;
  patientPhone: string;
  patientReason: string;
  patientSpo2: string;
  patientWeight: string;
  selectedSession: BookingSessionSummary;
  setPatientAddress: (value: string) => void;
  setPatientBhyt: (value: string) => void;
  setPatientBloodPressure: (value: string) => void;
  setPatientCccd: (value: string) => void;
  setPatientDob: (value: string) => void;
  setPatientGender: (value: string) => void;
  setPatientHeartRate: (value: string) => void;
  setPatientHeight: (value: string) => void;
  setPatientName: (value: string) => void;
  setPatientPhone: (value: string) => void;
  setPatientReason: (value: string) => void;
  setPatientSpo2: (value: string) => void;
  setPatientWeight: (value: string) => void;
}) {
  const estimatedTotal = DEMO_EXAM_FEE_VND + DEMO_SERVICE_FEE_VND;
  return (
    <div className="booking-modal-backdrop" role="presentation">
      <section
        aria-labelledby="booking-modal-title"
        aria-modal="true"
        className="booking-modal"
        role="dialog"
      >
        <header className="booking-modal-header">
          <div>
            <span className="eyebrow">Xác nhận thông tin khám</span>
            <h3 id="booking-modal-title">Xác nhận giữ chỗ</h3>
          </div>
          <button aria-label="Đóng form đặt lịch" type="button" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <form
          className="booking-modal-grid"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <aside className="booking-appointment-summary">
            <h4><ClipboardList size={17} aria-hidden="true" /> Thông tin phòng khám</h4>
            <dl>
              <div><dt>Bác sĩ</dt><dd>{selectedSession.doctor_name}</dd></div>
              <div><dt>Ngày</dt><dd>{formatDate(selectedSession.service_date)}</dd></div>
              <div><dt>Ca</dt><dd>{sessionLabel(selectedSession.session_key)}</dd></div>
              <div><dt>Cơ sở</dt><dd>{selectedSession.facility_code ?? 'Theo lịch công bố'}</dd></div>
              <div><dt>Phòng</dt><dd>{selectedSession.room_label ?? 'Cập nhật tại quầy'}</dd></div>
              <div><dt>Sức chứa</dt><dd>Còn {selectedSession.remaining_count}/{selectedSession.capacity_limit}</dd></div>
            </dl>
            <p>
              Bệnh nhân cần đến trước giờ hẹn tối thiểu 15 phút để đăng ký và đo
              mạch, huyết áp, chiều cao, cân nặng.
            </p>
          </aside>

          <div className="booking-modal-fields">
            <label>
              <span>Họ tên *</span>
              <input autoComplete="name" value={patientName} onChange={(event) => setPatientName(event.target.value)} />
            </label>
            <label>
              <span>Số điện thoại *</span>
              <input autoComplete="tel" inputMode="tel" value={patientPhone} onChange={(event) => setPatientPhone(event.target.value)} />
            </label>
            <label>
              <span>Ngày sinh</span>
              <input type="date" value={patientDob} onChange={(event) => setPatientDob(event.target.value)} />
            </label>
            <label>
              <span>Giới tính</span>
              <select value={patientGender} onChange={(event) => setPatientGender(event.target.value)}>
                <option value="">Chưa chọn</option>
                <option value="female">Nữ</option>
                <option value="male">Nam</option>
                <option value="other">Khác</option>
              </select>
            </label>
            <label>
              <span>CCCD</span>
              <input autoComplete="off" inputMode="numeric" value={patientCccd} onChange={(event) => setPatientCccd(event.target.value)} />
            </label>
            <label>
              <span>Mã thẻ BHYT</span>
              <input autoComplete="off" value={patientBhyt} onChange={(event) => setPatientBhyt(event.target.value.toUpperCase())} />
            </label>
            <label className="booking-field-wide">
              <span>Địa chỉ liên hệ</span>
              <input autoComplete="street-address" value={patientAddress} onChange={(event) => setPatientAddress(event.target.value)} />
            </label>
            <label className="booking-field-wide">
              <span>Lý do khám / triệu chứng chính</span>
              <textarea value={patientReason} onChange={(event) => setPatientReason(event.target.value)} />
            </label>
            <label>
              <span>Chiều cao cm</span>
              <input inputMode="numeric" value={patientHeight} onChange={(event) => setPatientHeight(event.target.value)} />
            </label>
            <label>
              <span>Cân nặng kg</span>
              <input inputMode="decimal" value={patientWeight} onChange={(event) => setPatientWeight(event.target.value)} />
            </label>
            <label>
              <span>Huyết áp</span>
              <input placeholder="120/80" value={patientBloodPressure} onChange={(event) => setPatientBloodPressure(event.target.value)} />
            </label>
            <label>
              <span>Mạch lần/phút</span>
              <input inputMode="numeric" value={patientHeartRate} onChange={(event) => setPatientHeartRate(event.target.value)} />
            </label>
            <label>
              <span>SpO2 %</span>
              <input inputMode="numeric" value={patientSpo2} onChange={(event) => setPatientSpo2(event.target.value)} />
            </label>
          </div>

          <div className="booking-demo-invoice">
            <div>
              <span>Khám theo yêu cầu demo</span>
              <strong>{formatVnd(DEMO_EXAM_FEE_VND)}</strong>
            </div>
            <div>
              <span>Phí dịch vụ theo yêu cầu demo</span>
              <strong>{formatVnd(DEMO_SERVICE_FEE_VND)}</strong>
            </div>
            <div className="booking-demo-total">
              <span>Tạm tính</span>
              <strong>{formatVnd(estimatedTotal)}</strong>
            </div>
            <p>Phiếu này chỉ phục vụ mô phỏng hackathon, chưa phải hóa đơn hoặc xác nhận của Bệnh viện.</p>
          </div>

          <footer className="booking-modal-actions">
            <button className="release-button" type="button" onClick={onClose}>Bỏ chọn</button>
            <button className="hold-button" disabled={holding} type="submit">
              {holding ? <RefreshCw className="spin-icon" size={17} aria-hidden="true" /> : <TicketCheck size={17} aria-hidden="true" />}
              {holding ? 'Đang giữ chỗ...' : 'Xác nhận giữ chỗ 5 phút'}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

export function BookingPanel({ compact = false }: { compact?: boolean }) {
  const [response, setResponse] = useState<BookingSessionListResponse | null>(null);
  const [doctorQuery, setDoctorQuery] = useState('');
  const [serviceDate, setServiceDate] = useState('');
  const [sessionKey, setSessionKey] = useState('');
  const [patientName, setPatientName] = useState('');
  const [patientPhone, setPatientPhone] = useState('');
  const [patientCccd, setPatientCccd] = useState('');
  const [patientBhyt, setPatientBhyt] = useState('');
  const [patientDob, setPatientDob] = useState('');
  const [patientGender, setPatientGender] = useState('');
  const [patientAddress, setPatientAddress] = useState('');
  const [patientReason, setPatientReason] = useState('');
  const [patientHeight, setPatientHeight] = useState('');
  const [patientWeight, setPatientWeight] = useState('');
  const [patientBloodPressure, setPatientBloodPressure] = useState('');
  const [patientHeartRate, setPatientHeartRate] = useState('');
  const [patientSpo2, setPatientSpo2] = useState('');
  const [selectedSession, setSelectedSession] = useState<BookingSessionSummary | null>(null);
  const [doctorOptions, setDoctorOptions] = useState<BookingDoctorOption[]>([]);
  const [appliedFilters, setAppliedFilters] = useState<BookingSessionFilters>({});
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_COUNT);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiClientError | null>(null);
  const [actionError, setActionError] = useState<ApiClientError | null>(null);
  const [holdingSessionId, setHoldingSessionId] = useState<string | null>(null);
  const [activeHold, setActiveHold] = useState<ActiveBookingHold | null>(null);
  const [holdStatus, setHoldStatus] = useState<'held' | 'confirmed' | 'released' | 'expired'>('held');
  const [releasing, setReleasing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [nowMs, setNowMs] = useState(Date.now());
  const idempotencyKeys = useRef(new Map<string, string>());
  const anonymousSessionId = useMemo(() => getAnonymousSessionId(), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    void listBookingSessions(appliedFilters, { signal: controller.signal })
      .then((result) => {
        setResponse(result);
        setVisibleCount(INITIAL_VISIBLE_COUNT);
      })
      .catch((error) => {
        const normalized = error instanceof ApiClientError
          ? error
          : new ApiClientError('Không thể tải danh sách ca khám.');
        if (normalized.code !== 'REQUEST_CANCELLED') {
          setLoadError(normalized);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [appliedFilters, refreshVersion]);

  useEffect(() => {
    const controller = new AbortController();
    void listBookingDoctors(doctorQuery, { signal: controller.signal })
      .then((result) => setDoctorOptions(result.records))
      .catch((error) => {
        if (!(error instanceof ApiClientError) || error.code !== 'REQUEST_CANCELLED') {
          setDoctorOptions([]);
        }
      });
    return () => controller.abort();
  }, [doctorQuery, refreshVersion]);

  const secondsLeft = activeHold && holdStatus === 'held'
    ? secondsUntil(activeHold.expires_at, nowMs)
    : 0;

  useEffect(() => {
    if (!activeHold || holdStatus !== 'held') return undefined;
    setNowMs(Date.now());
    const intervalId = globalThis.setInterval(() => setNowMs(Date.now()), 1_000);
    return () => globalThis.clearInterval(intervalId);
  }, [activeHold, holdStatus]);

  useEffect(() => {
    if (activeHold && holdStatus === 'held' && secondsLeft === 0) {
      setHoldStatus('expired');
      setRefreshVersion((value) => value + 1);
    }
  }, [activeHold, holdStatus, secondsLeft]);

  useEffect(() => {
    if (!activeHold?.hold_token || holdStatus !== 'held') return undefined;
    const timeoutId = globalThis.setTimeout(() => {
      setConfirming(true);
      void confirmBookingHold(activeHold.hold_id, activeHold.hold_token as string)
        .then((result) => {
          setHoldStatus(result.status === 'confirmed' ? 'confirmed' : result.status);
          setRefreshVersion((value) => value + 1);
        })
        .catch((error) => {
          setActionError(error instanceof ApiClientError
            ? error
            : new ApiClientError('Không thể tự duyệt giữ chỗ demo.'));
        })
        .finally(() => setConfirming(false));
    }, DEMO_AUTO_APPROVE_SECONDS * 1000);
    return () => globalThis.clearTimeout(timeoutId);
  }, [activeHold, holdStatus]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: BookingSessionFilters = {
      doctorQuery: doctorQuery.trim() || undefined,
      fromDate: serviceDate || undefined,
      toDate: serviceDate || undefined,
      sessionKey: sessionKey || undefined,
    };
    setAppliedFilters(next);
  }

  async function holdSession(session: BookingSessionSummary) {
    if (holdingSessionId || (activeHold && holdStatus === 'held' && secondsLeft > 0)) return;
    const fullName = patientName.trim();
    const phoneNumber = patientPhone.trim();
    if (fullName.length < 2 || phoneNumber.replace(/\D/g, '').length < 8) {
      setActionError(new ApiClientError('Vui lòng nhập họ tên và số điện thoại hợp lệ trước khi giữ chỗ.'));
      return;
    }
    setHoldingSessionId(session.booking_session_id);
    setActionError(null);
    const idempotencyKey = idempotencyKeys.current.get(session.booking_session_id)
      ?? createIdempotencyKey();
    idempotencyKeys.current.set(session.booking_session_id, idempotencyKey);
    try {
      const hold = await createBookingHold(
        {
          booking_session_id: session.booking_session_id,
          idempotency_key: idempotencyKey,
          patient: {
            full_name: fullName,
            phone_number: phoneNumber,
            cccd_number: patientCccd.trim() || null,
            bhyt_card_number: patientBhyt.trim() || null,
            date_of_birth: patientDob || null,
            gender: patientGender || null,
            address: patientAddress.trim() || null,
            visit_reason: patientReason.trim() || null,
            height_cm: parseOptionalInteger(patientHeight),
            weight_kg: parseOptionalNumber(patientWeight),
            blood_pressure: patientBloodPressure.trim() || null,
            heart_rate_bpm: parseOptionalInteger(patientHeartRate),
            spo2_percent: parseOptionalInteger(patientSpo2),
          },
        },
        anonymousSessionId,
      );
      setActiveHold({ ...hold, booking_session: session });
      setSelectedSession(null);
      setHoldStatus('held');
      setNowMs(Date.now());
      idempotencyKeys.current.delete(session.booking_session_id);
      setRefreshVersion((value) => value + 1);
    } catch (error) {
      setActionError(error instanceof ApiClientError
        ? error
        : new ApiClientError('Không thể giữ chỗ. Vui lòng thử lại.'));
    } finally {
      setHoldingSessionId(null);
    }
  }

  function chooseSession(session: BookingSessionSummary) {
    if (activeHoldBlocksNew) return;
    setActionError(null);
    setSelectedSession(session);
  }

  function resetFilters() {
    setDoctorQuery('');
    setServiceDate('');
    setSessionKey('');
    setSelectedSession(null);
    setActionError(null);
    setAppliedFilters({});
  }

  async function releaseHold() {
    if (!activeHold?.hold_token || releasing) return;
    setReleasing(true);
    setActionError(null);
    try {
      const result = await releaseBookingHold(activeHold.hold_id, activeHold.hold_token);
      setHoldStatus(result.status === 'expired' ? 'expired' : 'released');
      setRefreshVersion((value) => value + 1);
    } catch (error) {
      setActionError(error instanceof ApiClientError
        ? error
        : new ApiClientError('Không thể hủy chỗ đang giữ.'));
    } finally {
      setReleasing(false);
    }
  }

  const activeHoldBlocksNew = Boolean(activeHold && holdStatus === 'held' && secondsLeft > 0);
  const records = useMemo(
    () => [...(response?.records ?? [])].sort((left, right) =>
      left.service_date.localeCompare(right.service_date)
      || left.session_key.localeCompare(right.session_key)
      || left.doctor_name.localeCompare(right.doctor_name, 'vi'),
    ),
    [response],
  );
  const visibleRecords = records.slice(0, visibleCount);
  const timelineDates = response
    ? Array.from({ length: 7 }, (_, index) => addDays(response.reference_date, index))
    : [];
  const dateRange = records.length > 0
    ? `${formatDate(records[0].service_date)} – ${formatDate(records[records.length - 1].service_date)}`
    : null;

  function applyDateShortcut(value: string) {
    setServiceDate(value);
    setAppliedFilters({
      doctorQuery: doctorQuery.trim() || undefined,
      fromDate: value,
      toDate: value,
      sessionKey: sessionKey || undefined,
    });
  }

  return (
    <section className={`booking-panel${compact ? ' booking-panel-compact' : ''}`} id="booking" aria-labelledby="booking-title">
      <header className="booking-heading">
        <div>
          <span className="prototype-badge"><FlaskConical size={14} aria-hidden="true" /> Mô phỏng hackathon</span>
          <h2 id="booking-title">Giữ chỗ khám theo ca</h2>
          <p>Xem ca ở mốc bắt đầu, các ngày sau và tuần tiếp theo trong dữ liệu đã công bố.</p>
          <p>Mỗi bác sĩ chỉ nhận tối đa số người đã cấu hình trong một ngày và một ca.</p>
        </div>
        <button
          className="refresh-booking-button"
          disabled={loading}
          type="button"
          onClick={() => setRefreshVersion((value) => value + 1)}
        >
          <RefreshCw className={loading ? 'spin-icon' : ''} size={17} aria-hidden="true" />
          Làm mới sức chứa
        </button>
      </header>

      <div className="prototype-banner" role="note">
        <FlaskConical size={19} aria-hidden="true" />
        <div>
          <strong>Chức năng nguyên mẫu, không phải hệ thống đặt khám chính thức</strong>
          <p>Giữ chỗ sẽ tự hết hạn. Kết quả không đồng nghĩa Bệnh viện đã xác nhận lịch hẹn.</p>
        </div>
      </div>

      {activeHold ? (
        <>
          <ActiveHoldCard
            hold={activeHold}
            onRelease={() => void releaseHold()}
            releasing={releasing}
            secondsLeft={secondsLeft}
            status={holdStatus}
          />
          {confirming ? (
            <p className="booking-auto-approve-note">
              <RefreshCw className="spin-icon" size={15} aria-hidden="true" />
              HERA đang tự duyệt giữ chỗ demo sau {DEMO_AUTO_APPROVE_SECONDS} giây.
            </p>
          ) : null}
        </>
      ) : null}

      {actionError ? (
        <div className="booking-action-error">
          <ErrorState message={actionError.message} />
          {actionError.requestId ? <small>Mã yêu cầu: {actionError.requestId}</small> : null}
        </div>
      ) : null}

      <form className="booking-filters" onSubmit={applyFilters}>
        <label>
          <span>Tên bác sĩ</span>
          <input
            list="booking-doctor-options"
            type="search"
            value={doctorQuery}
            placeholder="Chọn hoặc gõ tên bác sĩ..."
            onChange={(event) => setDoctorQuery(event.target.value)}
          />
          <datalist id="booking-doctor-options">
            {doctorOptions.map((doctor) => (
              <option
                key={doctor.doctor_id}
                value={doctor.doctor_name}
              >
                {doctor.facility_codes.join(', ') || 'Theo lịch'} · {doctor.remaining_count} chỗ
              </option>
            ))}
          </datalist>
        </label>
        <label>
          <span>Ngày khám</span>
          <input
            min={response?.reference_date}
            type="date"
            value={serviceDate}
            onChange={(event) => setServiceDate(event.target.value)}
          />
        </label>
        <label>
          <span>Ca khám</span>
          <select value={sessionKey} onChange={(event) => setSessionKey(event.target.value)}>
            <option value="">Tất cả ca</option>
            <option value="morning">Buổi sáng</option>
            <option value="afternoon">Buổi chiều</option>
            <option value="evening">Buổi tối</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          <Search size={17} aria-hidden="true" /> Tìm ca
        </button>
        <button className="booking-reset-button" type="button" onClick={resetFilters}>
          <X size={17} aria-hidden="true" /> Xóa lọc
        </button>
      </form>

      {doctorOptions.length > 0 ? (
        <div className="booking-doctor-list" aria-label="Danh sách bác sĩ có lịch">
          <span><UserRound size={15} aria-hidden="true" /> Bác sĩ có lịch từ thời khóa biểu</span>
          {doctorOptions.slice(0, 8).map((doctor) => (
            <button
              key={doctor.doctor_id}
              type="button"
              onClick={() => {
                setDoctorQuery(doctor.doctor_name);
                setAppliedFilters({
                  doctorQuery: doctor.doctor_name,
                  fromDate: serviceDate || undefined,
                  toDate: serviceDate || undefined,
                  sessionKey: sessionKey || undefined,
                });
              }}
            >
              <strong>{doctor.doctor_name}</strong>
              <small>{doctor.facility_codes.join(', ') || 'Theo lịch'} · {doctor.open_session_count} ca · còn {doctor.remaining_count}</small>
            </button>
          ))}
        </div>
      ) : null}

      {timelineDates.length > 0 ? (
        <div className="booking-date-strip" aria-label="Chọn nhanh ngày khám">
          <span>Ngày demo hiện tại</span>
          {timelineDates.map((value, index) => (
            <button
              className={serviceDate === value ? 'booking-date-chip booking-date-chip-active' : 'booking-date-chip'}
              key={value}
              type="button"
              onClick={() => applyDateShortcut(value)}
            >
              <strong>{index === 0 ? 'Hôm nay' : index === 1 ? 'Ngày mai' : weekdayLabel(value)}</strong>
              <small>{formatDate(value)}</small>
            </button>
          ))}
        </div>
      ) : null}

      {selectedSession && !activeHoldBlocksNew ? (
        <BookingPatientModal
          holding={holdingSessionId === selectedSession.booking_session_id}
          onClose={() => setSelectedSession(null)}
          onSubmit={() => void holdSession(selectedSession)}
          patientAddress={patientAddress}
          patientBhyt={patientBhyt}
          patientBloodPressure={patientBloodPressure}
          patientCccd={patientCccd}
          patientDob={patientDob}
          patientGender={patientGender}
          patientHeartRate={patientHeartRate}
          patientHeight={patientHeight}
          patientName={patientName}
          patientPhone={patientPhone}
          patientReason={patientReason}
          patientSpo2={patientSpo2}
          patientWeight={patientWeight}
          selectedSession={selectedSession}
          setPatientAddress={setPatientAddress}
          setPatientBhyt={setPatientBhyt}
          setPatientBloodPressure={setPatientBloodPressure}
          setPatientCccd={setPatientCccd}
          setPatientDob={setPatientDob}
          setPatientGender={setPatientGender}
          setPatientHeartRate={setPatientHeartRate}
          setPatientHeight={setPatientHeight}
          setPatientName={setPatientName}
          setPatientPhone={setPatientPhone}
          setPatientReason={setPatientReason}
          setPatientSpo2={setPatientSpo2}
          setPatientWeight={setPatientWeight}
        />
      ) : null}

      {response ? (
        <div className="booking-data-note">
          <span>Ngày bắt đầu dữ liệu mô phỏng: {formatDate(response.reference_date)}</span>
          {dateRange ? <span>Khoảng lịch phù hợp: {dateRange}</span> : null}
          <span>Phạm vi sức chứa: mỗi bác sĩ · mỗi ngày · mỗi ca</span>
        </div>
      ) : null}

      {loading ? <LoadingState label="Đang tải sức chứa từng ca..." /> : null}
      {!loading && loadError ? (
        <div className="booking-load-error">
          <ErrorState message={loadError.message} />
          <button type="button" onClick={() => setRefreshVersion((value) => value + 1)}>Thử lại</button>
        </div>
      ) : null}
      {!loading && !loadError && records.length === 0 ? (
        <div className="booking-empty">
          <CalendarDays size={20} aria-hidden="true" />
          <p>Không tìm thấy ca mở phù hợp. Hãy đổi bác sĩ, ngày hoặc ca khám.</p>
        </div>
      ) : null}
      {!loading && !loadError && visibleRecords.length > 0 ? (
        <div className="booking-session-grid">
          {visibleRecords.map((session) => (
            <SessionCard
              disabled={activeHoldBlocksNew}
              isHolding={holdingSessionId === session.booking_session_id}
              key={session.booking_session_id}
              onHold={chooseSession}
              session={session}
            />
          ))}
        </div>
      ) : null}
      {!loading && visibleCount < records.length ? (
        <button
          className="load-more-booking"
          type="button"
          onClick={() => setVisibleCount((value) => value + INITIAL_VISIBLE_COUNT)}
        >
          Xem thêm {Math.min(INITIAL_VISIBLE_COUNT, records.length - visibleCount)} ca
        </button>
      ) : null}
      {response?.warning ? <p className="booking-source-warning">{response.warning}</p> : null}
    </section>
  );
}
