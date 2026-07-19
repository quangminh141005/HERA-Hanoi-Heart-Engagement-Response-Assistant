/** Contract for the isolated booking-capacity prototype. */
export interface BookingSessionSummary {
  booking_session_id: string;
  doctor_id: string;
  doctor_name: string;
  service_date: string;
  session_key: string;
  facility_code: string | null;
  room_label: string | null;
  status: 'open' | 'closed';
  capacity_limit: number;
  occupied_count: number;
  remaining_count: number;
  prototype_only: boolean;
  hospital_appointment_confirmed: false;
}

export interface BookingSessionListResponse {
  reference_date: string;
  capacity_scope: 'doctor_date_session';
  capacity_source: string;
  warning: string;
  records: BookingSessionSummary[];
}

export interface BookingDoctorOption {
  doctor_id: string;
  doctor_name: string;
  facility_codes: string[];
  room_labels: string[];
  unit_labels: string[];
  next_service_date: string;
  session_keys: string[];
  open_session_count: number;
  remaining_count: number;
}

export interface BookingDoctorListResponse {
  reference_date: string;
  capacity_source: string;
  warning: string;
  records: BookingDoctorOption[];
}

export interface BookingHoldRequest {
  booking_session_id: string;
  idempotency_key: string;
  patient: BookingPatientIdentity;
}

export interface BookingPatientIdentity {
  full_name: string;
  phone_number: string;
  cccd_number?: string | null;
  bhyt_card_number?: string | null;
  date_of_birth?: string | null;
  gender?: string | null;
  address?: string | null;
  visit_reason?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  blood_pressure?: string | null;
  heart_rate_bpm?: number | null;
  spo2_percent?: number | null;
}

export interface BookingHoldResponse {
  hold_id: string;
  hold_token: string | null;
  status: 'held';
  expires_at: string;
  capacity_limit: number;
  capacity_scope: 'doctor_date_session';
  capacity_source: string;
  remaining_count: number | null;
  hospital_appointment_confirmed: false;
  warning: string;
  idempotent_replay: boolean;
}

export interface BookingHoldStateResponse {
  hold_id: string;
  status: 'released' | 'expired' | 'confirmed';
  expires_at: string;
  hospital_appointment_confirmed: false;
  warning: string;
}

export interface ActiveBookingHold extends BookingHoldResponse {
  booking_session: BookingSessionSummary;
}
