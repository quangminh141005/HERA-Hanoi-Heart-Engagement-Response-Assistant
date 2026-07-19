import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createBookingHold,
  confirmBookingHold,
  getAnonymousSessionId,
  listBookingDoctors,
  listBookingSessions,
  releaseBookingHold,
} from './api';

const session = {
  booking_session_id: 'BSESSION-1',
  doctor_id: 'DOCTOR-1',
  doctor_name: 'BS. Nguyễn An',
  service_date: '2026-06-08',
  session_key: 'morning',
  facility_code: 'CS1',
  room_label: 'P.101',
  capacity_limit: 20,
  occupied_count: 3,
  remaining_count: 17,
  status: 'open',
  prototype_only: true,
  hospital_appointment_confirmed: false,
};

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: vi.fn().mockResolvedValue(payload),
  } as unknown as Response;
}

describe('booking API', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    globalThis.sessionStorage.clear();
  });

  it('keeps a sufficiently long anonymous session id within the browser tab', () => {
    const first = getAnonymousSessionId();
    const second = getAnonymousSessionId();
    expect(first.length).toBeGreaterThanOrEqual(8);
    expect(second).toBe(first);
  });

  it('sends server-side session filters with the expected field names', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      reference_date: '2026-06-08',
      capacity_scope: 'doctor_date_session',
      capacity_source: 'project_mvp_default',
      warning: 'Chỉ là bản demo.',
      records: [session],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await listBookingSessions({
      doctorQuery: 'Nguyễn An',
      fromDate: '2026-06-08',
      toDate: '2026-06-08',
      sessionKey: 'morning',
    });

    expect(result.records[0]?.remaining_count).toBe(17);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/booking-sessions?');
    expect(url).toContain('doctor_query=Nguy%E1%BB%85n+An');
    expect(url).toContain('from_date=2026-06-08');
    expect(url).toContain('to_date=2026-06-08');
    expect(url).toContain('session_key=morning');
    expect(init.method).toBe('GET');
  });

  it('loads doctor options from booking sessions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      reference_date: '2026-06-08',
      capacity_source: 'project_mvp_default',
      warning: 'Chỉ là bản demo.',
      records: [{
        doctor_id: 'DOCTOR-1',
        doctor_name: 'BS. Nguyễn An',
        facility_codes: ['CS1'],
        room_labels: ['P.101'],
        unit_labels: ['Khoa khám bệnh Tự nguyện 1'],
        next_service_date: '2026-06-08',
        session_keys: ['morning'],
        open_session_count: 2,
        remaining_count: 18,
      }],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await listBookingDoctors('Nguyễn');

    expect(result.records[0]?.doctor_name).toBe('BS. Nguyễn An');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/booking-doctors?doctor_query=Nguy%E1%BB%85n');
    expect(init.method).toBe('GET');
  });

  it('creates a hold with the anonymous-session header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      hold_id: 'HOLD-1',
      hold_token: 'secret-token',
      status: 'held',
      expires_at: '2099-01-01T00:05:00Z',
      capacity_limit: 20,
      capacity_scope: 'doctor_date_session',
      capacity_source: 'project_mvp_default',
      remaining_count: 16,
      hospital_appointment_confirmed: false,
      warning: 'Chỉ là bản demo.',
      idempotent_replay: false,
    }, 201));
    vi.stubGlobal('fetch', fetchMock);

    await createBookingHold(
      {
        booking_session_id: 'BSESSION-1',
        idempotency_key: 'hold-action-123',
        patient: {
          full_name: 'Nguyen Van A',
          phone_number: '0912345678',
          cccd_number: '001001000001',
          bhyt_card_number: 'DN40101000001',
        },
      },
      'anonymous-session-123',
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-Anonymous-Session-ID': 'anonymous-session-123',
    });
    expect(JSON.parse(String(init.body))).toEqual({
      booking_session_id: 'BSESSION-1',
      idempotency_key: 'hold-action-123',
      patient: {
        full_name: 'Nguyen Van A',
        phone_number: '0912345678',
        cccd_number: '001001000001',
        bhyt_card_number: 'DN40101000001',
      },
    });
  });

  it('releases only with the hold bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      hold_id: 'HOLD-1',
      status: 'released',
      expires_at: '2099-01-01T00:05:00Z',
      hospital_appointment_confirmed: false,
      warning: 'Chỉ là bản demo.',
    }));
    vi.stubGlobal('fetch', fetchMock);

    await releaseBookingHold('HOLD-1', 'secret-token');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/booking-holds/HOLD-1');
    expect(init.method).toBe('DELETE');
    expect(init.headers).toMatchObject({ Authorization: 'Bearer secret-token' });
  });

  it('confirms a demo hold with the hold bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      hold_id: 'HOLD-1',
      status: 'confirmed',
      expires_at: '2099-01-01T00:05:00Z',
      hospital_appointment_confirmed: false,
      warning: 'Tự duyệt demo.',
    }));
    vi.stubGlobal('fetch', fetchMock);

    await confirmBookingHold('HOLD-1', 'secret-token');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/v1/booking-holds/HOLD-1/confirm');
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ Authorization: 'Bearer secret-token' });
  });

  it('rejects a malformed successful response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ records: [] })));
    await expect(listBookingSessions()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });

  it('rejects unsafe capacity scope and impossible session counters', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      reference_date: '2026-06-08',
      capacity_scope: 'global',
      capacity_source: 'untrusted',
      warning: 'Không hợp lệ.',
      records: [{ ...session, occupied_count: 21, remaining_count: -1 }],
    })));

    await expect(listBookingSessions()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });

  it('rejects a hold response unless it is an isolated held prototype slot', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
      hold_id: 'HOLD-1',
      hold_token: 'secret-token',
      status: 'confirmed',
      expires_at: '2099-01-01T00:05:00Z',
      capacity_limit: 20,
      capacity_scope: 'doctor_date_session',
      capacity_source: 'project_mvp_default',
      remaining_count: 16,
      hospital_appointment_confirmed: false,
      warning: 'Chỉ là bản demo.',
      idempotent_replay: false,
    })));

    await expect(createBookingHold(
      {
        booking_session_id: 'BSESSION-1',
        idempotency_key: 'hold-action-123',
        patient: {
          full_name: 'Nguyen Van A',
          phone_number: '0912345678',
        },
      },
      'anonymous-session-123',
    )).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
  });
});
