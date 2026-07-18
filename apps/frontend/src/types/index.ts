export type DataClassification =
  | 'official_current'
  | 'partial_official_snapshot'
  | 'review_only'
  | string;

export interface Citation {
  source_id: string;
  title: string;
  url?: string | null;
  excerpt?: string | null;
  publisher?: string | null;
  source_page?: number | null;
  source_sha256?: string | null;
  effective_from?: string | null;
  week_start?: string | null;
  week_end?: string | null;
}

export interface ServicePriceRecord {
  service_record_id: string;
  price_id: string;
  display_name: string;
  facility_code: string;
  amount_vnd: number;
  amount_raw?: string | null;
  section?: string | null;
  note?: string | null;
}

export interface ServicePriceLookup {
  query: string;
  facility_code?: string | null;
  as_of_date?: string | null;
  classification: DataClassification;
  warning: string;
  records: ServicePriceRecord[];
  citations: Citation[];
}

export interface BhytTierRecord {
  tier_order: number;
  member_label: string;
  rate_text?: string | null;
  monthly_amount_vnd?: number | null;
  annual_amount_vnd?: number | null;
}

export interface BhytLookup {
  as_of_date: string;
  policy_id: string;
  classification: DataClassification;
  policy_scope: 'household_contribution' | string;
  warning: string;
  tiers: BhytTierRecord[];
  citations: Citation[];
}

export interface ScheduleEntryRecord {
  schedule_entry_id: string;
  service_date: string;
  facility_code: string;
  room_label?: string | null;
  unit_label?: string | null;
  provider_text?: string | null;
  published_hours_raw?: string | null;
  duty_status: string;
  assignee_type: string;
  approval_status?: string | null;
}

export interface ScheduleLookup {
  week_start: string;
  facility_code?: string | null;
  doctor_query?: string | null;
  room_query?: string | null;
  classification: DataClassification;
  warning: string;
  records: ScheduleEntryRecord[];
  citations: Citation[];
  coverage: Record<string, unknown>;
}

export type StructuredAction =
  | { kind: 'service_price'; data: ServicePriceLookup }
  | { kind: 'bhyt_household_contribution'; data: BhytLookup }
  | { kind: 'schedule'; data: ScheduleLookup };

export interface ChatMetadata extends Record<string, unknown> {
  structured_action?: unknown;
  guardrail_violation?: unknown;
  reason?: unknown;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  locale?: string;
  consent_to_store?: boolean;
  client_context?: Record<string, unknown>;
  user_context?: Record<string, unknown>;
}

export interface ChatAction {
  type: 'call' | 'open_url' | string;
  channel_id: string;
  label_vi: string;
  target: string;
}

export interface ChatResponse {
  request_id: string;
  conversation_id: string;
  response: string;
  answer_vi: string;
  response_type: string;
  intent: string;
  grounded: boolean;
  data_classification: DataClassification;
  citations: Citation[];
  warnings: string[];
  structured_record_ids: string[];
  actions: ChatAction[];
  requires_handoff: boolean;
  emergency: boolean;
  metadata: ChatMetadata;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  intent?: string;
  responseType?: string;
  grounded?: boolean;
  dataClassification?: DataClassification;
  warnings?: string[];
  structuredRecordIds?: string[];
  actions?: ChatAction[];
  emergency?: boolean;
  requiresHandoff?: boolean;
  metadata?: ChatMetadata;
  structuredAction?: StructuredAction | null;
  requestId?: string;
}

export interface FeedbackRequest {
  request_id: string;
  helpful: boolean;
  reason_code?: 'inaccurate' | 'outdated' | 'unclear' | 'incomplete' | 'unsafe' | 'other';
  comment?: string;
}

export interface FeedbackResponse {
  feedback_id: string;
  request_id: string;
  accepted: boolean;
  created_at: string;
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message_vi: string;
    request_id?: string;
    retryable?: boolean;
  };
}
