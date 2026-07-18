import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as bookingApi from './api';
import { BookingPanel, formatCountdown, secondsUntil } from './BookingPanel';

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
  status: 'open' as const,
  prototype_only: true,
  hospital_appointment_confirmed: false as const,
};

describe('BookingPanel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('formats the hold countdown without going below zero', () => {
    expect(formatCountdown(305)).toBe('05:05');
    expect(formatCountdown(-2)).toBe('00:00');
    expect(secondsUntil('2026-06-08T00:00:05Z', Date.parse('2026-06-08T00:00:00Z'))).toBe(5);
  });

  it('shows capacity, creates a hold, counts down, and releases it', async () => {
    vi.spyOn(bookingApi, 'listBookingSessions').mockResolvedValue({
      reference_date: '2026-06-08',
      capacity_scope: 'doctor_date_session',
      capacity_source: 'project_mvp_default',
      warning: 'Đây chỉ là bản demo.',
      records: [session],
    });
    vi.spyOn(bookingApi, 'createBookingHold').mockResolvedValue({
      hold_id: 'HOLD-1',
      hold_token: 'secret-token',
      status: 'held',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      capacity_limit: 20,
      capacity_scope: 'doctor_date_session',
      capacity_source: 'project_mvp_default',
      remaining_count: 16,
      hospital_appointment_confirmed: false,
      warning: 'Đây chỉ là bản demo.',
      idempotent_replay: false,
    });
    const release = vi.spyOn(bookingApi, 'releaseBookingHold').mockResolvedValue({
      hold_id: 'HOLD-1',
      status: 'released',
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      hospital_appointment_confirmed: false,
      warning: 'Đây chỉ là bản demo.',
    });
    const user = userEvent.setup();

    render(<BookingPanel />);

    expect(await screen.findByText('BS. Nguyễn An')).toBeInTheDocument();
    expect(screen.getByText('Còn 17/20')).toBeInTheDocument();
    expect(screen.getByText(/không phải hệ thống đặt khám chính thức/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /chọn ca này/i }));
    expect(await screen.findByText('Xác nhận giữ chỗ')).toBeInTheDocument();
    await user.type(screen.getByLabelText(/họ tên/i), 'Nguyen Van A');
    await user.type(screen.getByLabelText(/số điện thoại/i), '0912345678');
    await user.type(screen.getByLabelText(/cccd/i), '001001000001');
    await user.type(screen.getByLabelText(/mã thẻ bhyt/i), 'DN40101000001');
    await user.click(screen.getByRole('button', { name: /xác nhận giữ chỗ 5 phút/i }));
    expect(await screen.findByText('Đang giữ chỗ tạm')).toBeInTheDocument();
    expect(screen.getByText(/^\d{2}:\d{2}$/)).toBeInTheDocument();
    expect(screen.getByText(/chưa phải lịch hẹn được Bệnh viện xác nhận/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /hủy chỗ đang giữ/i }));
    await waitFor(() => expect(release).toHaveBeenCalledWith('HOLD-1', 'secret-token'));
    expect(await screen.findByText('Đã hủy giữ chỗ')).toBeInTheDocument();
  });

  it('shows the future schedule range in date order and disables a closed session', async () => {
    vi.spyOn(bookingApi, 'listBookingSessions').mockResolvedValue({
      reference_date: '2026-06-08',
      capacity_scope: 'doctor_date_session',
      capacity_source: 'project_mvp_default',
      warning: 'Đây chỉ là bản demo.',
      records: [
        {
          ...session,
          booking_session_id: 'BSESSION-FUTURE',
          doctor_id: 'DOCTOR-FUTURE',
          doctor_name: 'BS. Tuần Sau',
          service_date: '2026-06-15',
        },
        {
          ...session,
          booking_session_id: 'BSESSION-CLOSED',
          doctor_id: 'DOCTOR-CLOSED',
          doctor_name: 'BS. Ngày Đầu',
          status: 'closed',
        },
      ],
    });
    const createHold = vi.spyOn(bookingApi, 'createBookingHold');
    const user = userEvent.setup();

    render(<BookingPanel />);

    expect(await screen.findByText(/Khoảng lịch phù hợp: 08\/06\/2026 – 15\/06\/2026/)).toBeInTheDocument();
    const doctorHeadings = screen.getAllByRole('heading', { level: 3 }).map((node) => node.textContent);
    expect(doctorHeadings.indexOf('BS. Ngày Đầu')).toBeLessThan(doctorHeadings.indexOf('BS. Tuần Sau'));
    const closedButton = screen.getByRole('button', { name: /ca không nhận giữ chỗ/i });
    expect(closedButton).toBeDisabled();
    await user.click(closedButton);
    expect(createHold).not.toHaveBeenCalled();
  });
});
