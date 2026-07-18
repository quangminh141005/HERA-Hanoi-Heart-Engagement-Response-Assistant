import { API_BASE_URL, ApiClientError, normalizeApiError } from '../../lib/api';
import { isRecord } from '../../lib/structured';
import {
  BookingHoldRequest,
  BookingHoldResponse,
  BookingHoldStateResponse,
  BookingSessionListResponse,
  BookingSessionSummary,
} from './contracts';

const BOOKING_TIMEOUT_MS = 15_000;
const ANONYMOUS_SESSION_KEY = 'hera.booking.anonymous-session.v1';
const SESSION_ID_PATTERN = /^[A-Za-z0-9._:-]{8,128}$/;

export interface BookingSessionFilters {
  fromDate?: string;
  toDate?: string;
  doctorQuery?: string;
  facilityCode?: string;
  sessionKey?: string;
}

function randomIdentifier(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

export function getAnonymousSessionId(): string {
  try {
    const existing = globalThis.sessionStorage?.getItem(ANONYMOUS_SESSION_KEY);
    if (existing && SESSION_ID_PATTERN.test(existing)) {
      return existing;
    }
    const generated = randomIdentifier('hera-web');
    globalThis.sessionStorage?.setItem(ANONYMOUS_SESSION_KEY, generated);
    return generated;
  } catch {
    return randomIdentifier('hera-web');
  }
}

function isIntegerAtLeast(value: unknown, minimum: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= minimum;
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

function isIsoDateTime(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

export function createIdempotencyKey(): string {
  return randomIdentifier('hold');
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function requestJson(
  path: string,
  init: RequestInit,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<unknown> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(
    () => controller.abort('timeout'),
    options.timeoutMs ?? BOOKING_TIMEOUT_MS,
  );
  const abortFromCaller = () => controller.abort('cancelled');
  options.signal?.addEventListener('abort', abortFromCaller, { once: true });

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw normalizeApiError(payload, response.status, response.headers.get('Retry-After'));
    }
    return payload;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (controller.signal.aborted) {
      const timedOut = !options.signal?.aborted;
      throw new ApiClientError(
        timedOut
          ? 'Danh sách đặt lịch phản hồi quá lâu. Vui lòng thử lại.'
          : 'Yêu cầu đặt lịch đã được hủy.',
        undefined,
        timedOut ? 'REQUEST_TIMEOUT' : 'REQUEST_CANCELLED',
        timedOut,
      );
    }
    throw new ApiClientError('Không thể kết nối dịch vụ giữ chỗ. Vui lòng thử lại.');
  } finally {
    globalThis.clearTimeout(timeoutId);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
}

function isSession(value: unknown): value is BookingSessionSummary {
  return (
    isRecord(value)
    && typeof value.booking_session_id === 'string'
    && typeof value.doctor_id === 'string'
    && typeof value.doctor_name === 'string'
    && isIsoDate(value.service_date)
    && typeof value.session_key === 'string'
    && (value.facility_code === null || typeof value.facility_code === 'string')
    && (value.room_label === null || typeof value.room_label === 'string')
    && isIntegerAtLeast(value.capacity_limit, 1)
    && isIntegerAtLeast(value.occupied_count, 0)
    && value.occupied_count <= value.capacity_limit
    && isIntegerAtLeast(value.remaining_count, 0)
    && value.remaining_count <= value.capacity_limit
    && (value.status === 'open' || value.status === 'closed')
    && value.prototype_only === true
    && value.hospital_appointment_confirmed === false
  );
}

function parseSessionList(value: unknown): BookingSessionListResponse {
  if (
    !isRecord(value)
    || !isIsoDate(value.reference_date)
    || value.capacity_scope !== 'doctor_date_session'
    || typeof value.capacity_source !== 'string'
    || value.capacity_source.length === 0
    || typeof value.warning !== 'string'
    || !Array.isArray(value.records)
    || !value.records.every(isSession)
  ) {
    throw new ApiClientError(
      'Dịch vụ giữ chỗ trả về dữ liệu không đúng định dạng an toàn.',
      200,
      'INVALID_RESPONSE',
      true,
    );
  }
  return value as unknown as BookingSessionListResponse;
}

function parseHold(value: unknown): BookingHoldResponse {
  if (
    !isRecord(value)
    || typeof value.hold_id !== 'string'
    || (value.hold_token !== null && typeof value.hold_token !== 'string')
    || value.status !== 'held'
    || !isIsoDateTime(value.expires_at)
    || !isIntegerAtLeast(value.capacity_limit, 1)
    || (
      value.remaining_count !== null
      && (!isIntegerAtLeast(value.remaining_count, 0) || value.remaining_count > value.capacity_limit)
    )
    || value.capacity_scope !== 'doctor_date_session'
    || typeof value.capacity_source !== 'string'
    || value.capacity_source.length === 0
    || typeof value.warning !== 'string'
    || value.hospital_appointment_confirmed !== false
    || typeof value.idempotent_replay !== 'boolean'
  ) {
    throw new ApiClientError(
      'Dịch vụ giữ chỗ trả về dữ liệu không đúng định dạng an toàn.',
      200,
      'INVALID_RESPONSE',
      true,
    );
  }
  return value as unknown as BookingHoldResponse;
}

function parseHoldState(value: unknown): BookingHoldStateResponse {
  if (
    !isRecord(value)
    || typeof value.hold_id !== 'string'
    || (value.status !== 'released' && value.status !== 'expired')
    || !isIsoDateTime(value.expires_at)
    || typeof value.warning !== 'string'
    || value.hospital_appointment_confirmed !== false
  ) {
    throw new ApiClientError(
      'Dịch vụ giữ chỗ trả về dữ liệu không đúng định dạng an toàn.',
      200,
      'INVALID_RESPONSE',
      true,
    );
  }
  return value as unknown as BookingHoldStateResponse;
}

export async function listBookingSessions(
  filters: BookingSessionFilters = {},
  options: { signal?: AbortSignal } = {},
): Promise<BookingSessionListResponse> {
  const query = new URLSearchParams();
  if (filters.fromDate) query.set('from_date', filters.fromDate);
  if (filters.toDate) query.set('to_date', filters.toDate);
  if (filters.doctorQuery?.trim()) query.set('doctor_query', filters.doctorQuery.trim());
  if (filters.facilityCode?.trim()) query.set('facility_code', filters.facilityCode.trim());
  if (filters.sessionKey) query.set('session_key', filters.sessionKey);
  const suffix = query.size ? `?${query.toString()}` : '';
  const value = await requestJson(`/booking-sessions${suffix}`, { method: 'GET' }, options);
  return parseSessionList(value);
}

export async function createBookingHold(
  request: BookingHoldRequest,
  anonymousSessionId: string,
): Promise<BookingHoldResponse> {
  const value = await requestJson('/booking-holds', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Anonymous-Session-ID': anonymousSessionId,
    },
    body: JSON.stringify(request),
  });
  return parseHold(value);
}

export async function releaseBookingHold(
  holdId: string,
  bearerToken: string,
): Promise<BookingHoldStateResponse> {
  const value = await requestJson(`/booking-holds/${encodeURIComponent(holdId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  return parseHoldState(value);
}
