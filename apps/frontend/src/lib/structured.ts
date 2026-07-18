import {
  BhytLookup,
  BhytTierRecord,
  ChatAction,
  ChatMetadata,
  ChatResponse,
  Citation,
  ScheduleEntryRecord,
  ScheduleLookup,
  ServicePriceLookup,
  ServicePriceRecord,
  StructuredAction,
} from '../types';

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNullableString(value: unknown): value is string | null | undefined {
  return value === null || value === undefined || isString(value);
}

function isNullableVnd(value: unknown): value is number | null | undefined {
  return value === null
    || value === undefined
    || (typeof value === 'number' && Number.isFinite(value) && value >= 0);
}

function isNullablePositiveInteger(value: unknown): value is number | null | undefined {
  return value === null
    || value === undefined
    || (typeof value === 'number' && Number.isInteger(value) && value > 0);
}

function isIsoCalendarDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

function isNullableIsoCalendarDate(value: unknown): value is string | null | undefined {
  return value === null || value === undefined || isIsoCalendarDate(value);
}

export function isCitation(value: unknown): value is Citation {
  return (
    isRecord(value) &&
    isString(value.source_id) &&
    isString(value.title) &&
    isNullableString(value.url) &&
    isNullableString(value.excerpt) &&
    isNullableString(value.publisher) &&
    isNullablePositiveInteger(value.source_page) &&
    isNullableString(value.source_sha256) &&
    isNullableIsoCalendarDate(value.effective_from) &&
    isNullableIsoCalendarDate(value.week_start) &&
    isNullableIsoCalendarDate(value.week_end)
  );
}

function isCitationList(value: unknown): value is Citation[] {
  return Array.isArray(value) && value.every(isCitation);
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isChatAction(value: unknown): value is ChatAction {
  return (
    isRecord(value) &&
    isString(value.type) &&
    isString(value.channel_id) &&
    isString(value.label_vi) &&
    isString(value.target)
  );
}

function isChatActionList(value: unknown): value is ChatAction[] {
  return Array.isArray(value) && value.every(isChatAction);
}

function isServicePriceRecord(value: unknown): value is ServicePriceRecord {
  return (
    isRecord(value) &&
    isString(value.service_record_id) &&
    isString(value.price_id) &&
    isString(value.display_name) &&
    isString(value.facility_code) &&
    typeof value.amount_vnd === 'number' &&
    Number.isFinite(value.amount_vnd) &&
    value.amount_vnd >= 0 &&
    isNullableString(value.amount_raw) &&
    isNullableString(value.section) &&
    isNullableString(value.note)
  );
}

function isServicePriceLookup(value: unknown): value is ServicePriceLookup {
  return (
    isRecord(value) &&
    isString(value.query) &&
    isNullableString(value.facility_code) &&
    isNullableIsoCalendarDate(value.as_of_date) &&
    isString(value.classification) &&
    isString(value.warning) &&
    Array.isArray(value.records) &&
    value.records.every(isServicePriceRecord) &&
    isCitationList(value.citations)
  );
}

function isBhytTier(value: unknown): value is BhytTierRecord {
  return (
    isRecord(value) &&
    typeof value.tier_order === 'number' &&
    Number.isInteger(value.tier_order) &&
    value.tier_order > 0 &&
    isString(value.member_label) &&
    isNullableString(value.rate_text) &&
    isNullableVnd(value.monthly_amount_vnd) &&
    isNullableVnd(value.annual_amount_vnd)
  );
}

function isBhytLookup(value: unknown): value is BhytLookup {
  return (
    isRecord(value) &&
    isIsoCalendarDate(value.as_of_date) &&
    isString(value.policy_id) &&
    isString(value.classification) &&
    isString(value.policy_scope) &&
    isString(value.warning) &&
    Array.isArray(value.tiers) &&
    value.tiers.every(isBhytTier) &&
    isCitationList(value.citations)
  );
}

function isScheduleEntry(value: unknown): value is ScheduleEntryRecord {
  return (
    isRecord(value) &&
    isString(value.schedule_entry_id) &&
    isIsoCalendarDate(value.service_date) &&
    isString(value.facility_code) &&
    isNullableString(value.room_label) &&
    isNullableString(value.unit_label) &&
    isNullableString(value.provider_text) &&
    isNullableString(value.published_hours_raw) &&
    isString(value.duty_status) &&
    isString(value.assignee_type) &&
    isNullableString(value.approval_status)
  );
}

function isScheduleLookup(value: unknown): value is ScheduleLookup {
  return (
    isRecord(value) &&
    isIsoCalendarDate(value.week_start) &&
    isNullableString(value.facility_code) &&
    isNullableString(value.doctor_query) &&
    isNullableString(value.room_query) &&
    isString(value.classification) &&
    isString(value.warning) &&
    Array.isArray(value.records) &&
    value.records.every(isScheduleEntry) &&
    isCitationList(value.citations) &&
    isRecord(value.coverage)
  );
}

export function getStructuredAction(metadata: ChatMetadata): StructuredAction | null {
  const value = metadata.structured_action;
  if (isServicePriceLookup(value)) {
    return { kind: 'service_price', data: value };
  }
  if (isBhytLookup(value)) {
    return { kind: 'bhyt_household_contribution', data: value };
  }
  if (isScheduleLookup(value)) {
    return { kind: 'schedule', data: value };
  }
  return null;
}

export function parseChatResponse(value: unknown): ChatResponse {
  if (!isRecord(value)) {
    throw new TypeError('Phản hồi API không phải một đối tượng JSON.');
  }
  if (
    !isString(value.conversation_id) ||
    !isString(value.request_id) ||
    !isString(value.response) ||
    !isString(value.answer_vi) ||
    !isString(value.response_type) ||
    !isString(value.intent) ||
    typeof value.grounded !== 'boolean' ||
    !isString(value.data_classification) ||
    !isCitationList(value.citations) ||
    !isStringList(value.warnings) ||
    !isStringList(value.structured_record_ids) ||
    !isChatActionList(value.actions) ||
    typeof value.requires_handoff !== 'boolean' ||
    typeof value.emergency !== 'boolean' ||
    !isRecord(value.metadata)
  ) {
    throw new TypeError('Phản hồi API thiếu trường bắt buộc.');
  }

  return {
    request_id: value.request_id,
    conversation_id: value.conversation_id,
    response: value.response,
    answer_vi: value.answer_vi,
    response_type: value.response_type,
    intent: value.intent,
    grounded: value.grounded,
    data_classification: value.data_classification,
    citations: value.citations,
    warnings: value.warnings,
    structured_record_ids: value.structured_record_ids,
    actions: value.actions,
    requires_handoff: value.requires_handoff,
    emergency: value.emergency,
    metadata: value.metadata,
  };
}

export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  try {
    const base = globalThis.location?.origin ?? 'http://localhost';
    const parsed = new URL(value, base);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return null;
    }
    return parsed.href;
  } catch {
    return null;
  }
}

/**
 * Price and BHYT files are presented as the project's current supplied data.
 * Remove date/year labels only in that context; doctor schedules keep their
 * exact dates because the date is required to choose the correct session.
 */
export function withoutDatasetYear(value: string): string {
  return value
    .replace(
      /(?:áp dụng|hiệu lực)\s+từ\s+\d{1,2}[\/-]\d{1,2}[\/-](?:19|20)\d{2}\b/giu,
      'Áp dụng',
    )
    .replace(
      /(?:áp dụng|hiệu lực)\s+từ\s+(?:19|20)\d{2}-\d{2}-\d{2}\b/giu,
      'Áp dụng',
    )
    .replace(/\b\d{1,2}[\/-]\d{1,2}[\/-](?:19|20)\d{2}\b/giu, '')
    .replace(/\b(?:19|20)\d{2}-\d{2}-\d{2}\b/gu, '')
    .replace(/\b(?:năm|year)\s+(?:19|20)\d{2}\b/giu, '')
    .replace(/\b(?:19|20)\d{2}\b/gu, '')
    .replace(/\s+([,.;:])/gu, '$1')
    .replace(/\s{2,}/gu, ' ')
    .trim();
}

export function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Nguồn không công bố';
  }
  return `${new Intl.NumberFormat('vi-VN').format(value)} ₫`;
}

export function formatDate(value: string): string {
  if (!isIsoCalendarDate(value)) {
    return value;
  }
  const parsed = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(parsed);
}

export function mergeCitations(...groups: Array<Citation[] | undefined>): Citation[] {
  const seen = new Set<string>();
  return groups.flatMap((group) => group ?? []).filter((citation) => {
    const key = `${citation.source_id}:${citation.title}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}
