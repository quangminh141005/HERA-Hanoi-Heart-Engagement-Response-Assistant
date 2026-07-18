import { ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse } from '../types';
import { isRecord, parseChatResponse } from './structured';

// The backend stops ambiguous RAG work at 35s and returns a safe handoff.
// This browser budget leaves only a small transport margin beyond that bound.
const DEFAULT_TIMEOUT_MS = 42_000;
const FEEDBACK_TIMEOUT_MS = 10_000;

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code = 'REQUEST_FAILED',
    public readonly retryable = status === undefined || status >= 500 || status === 429,
    public readonly requestId?: string,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, '') || '/api/v1';

function validationMessage(detail: unknown): string | null {
  if (!Array.isArray(detail)) {
    return null;
  }
  const first = detail.find((item) => isRecord(item) && typeof item.msg === 'string');
  return isRecord(first) && typeof first.msg === 'string'
    ? `Dữ liệu gửi lên chưa hợp lệ: ${first.msg}`
    : null;
}

export function normalizeApiError(
  payload: unknown,
  status: number,
  retryAfterHeader?: string | null,
): ApiClientError {
  let message = 'Không thể kết nối với HERA. Vui lòng thử lại.';
  let code = status === 429 ? 'RATE_LIMITED' : 'REQUEST_FAILED';
  let retryable = status >= 500 || status === 429;
  let requestId: string | undefined;

  if (isRecord(payload) && isRecord(payload.error)) {
    const error = payload.error;
    if (typeof error.message_vi === 'string') {
      message = error.message_vi;
    }
    if (typeof error.code === 'string') {
      code = error.code;
    }
    if (typeof error.retryable === 'boolean') {
      retryable = error.retryable;
    }
    if (typeof error.request_id === 'string') {
      requestId = error.request_id;
    }
  } else if (isRecord(payload)) {
    if (typeof payload.detail === 'string') {
      message = payload.detail;
    } else {
      message = validationMessage(payload.detail) ?? message;
    }
  }

  if (status === 429 && message === 'Không thể kết nối với HERA. Vui lòng thử lại.') {
    message = 'Bạn đang gửi câu hỏi quá nhanh. Vui lòng đợi một chút rồi thử lại.';
  }
  const retryAfter = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined;
  return new ApiClientError(
    message,
    status,
    code,
    retryable,
    requestId,
    Number.isFinite(retryAfter) ? retryAfter : undefined,
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function postChat(
  request: ChatRequest,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<ChatResponse> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(
    () => controller.abort('timeout'),
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );
  const abortFromCaller = () => controller.abort('cancelled');
  options.signal?.addEventListener('abort', abortFromCaller, { once: true });

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        locale: 'vi-VN',
        user_context: { channel: 'hospital_web' },
        ...request,
      }),
      signal: controller.signal,
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw normalizeApiError(payload, response.status, response.headers.get('Retry-After'));
    }
    try {
      return parseChatResponse(payload);
    } catch {
      throw new ApiClientError(
        'HERA nhận được phản hồi không đúng định dạng an toàn.',
        response.status,
        'INVALID_RESPONSE',
        true,
      );
    }
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (controller.signal.aborted) {
      const timedOut = !options.signal?.aborted;
      throw new ApiClientError(
        timedOut ? 'HERA phản hồi quá lâu. Vui lòng thử lại.' : 'Yêu cầu đã được hủy.',
        undefined,
        timedOut ? 'REQUEST_TIMEOUT' : 'REQUEST_CANCELLED',
        timedOut,
      );
    }
    throw new ApiClientError('Không thể kết nối với HERA. Vui lòng thử lại.');
  } finally {
    globalThis.clearTimeout(timeoutId);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
}

export async function postFeedback(request: FeedbackRequest): Promise<FeedbackResponse> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort('timeout'), FEEDBACK_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    });
    const payload = await readJson(response);
    if (!response.ok) {
      throw normalizeApiError(payload, response.status, response.headers.get('Retry-After'));
    }
    if (
      !isRecord(payload) ||
      typeof payload.feedback_id !== 'string' ||
      typeof payload.request_id !== 'string' ||
      payload.accepted !== true ||
      typeof payload.created_at !== 'string'
    ) {
      throw new ApiClientError(
        'HERA nhận được biên nhận góp ý không hợp lệ.',
        response.status,
        'INVALID_RESPONSE',
        true,
      );
    }
    return payload as unknown as FeedbackResponse;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (controller.signal.aborted) {
      throw new ApiClientError(
        'Gửi góp ý quá thời gian chờ. Bạn có thể thử lại.',
        undefined,
        'REQUEST_TIMEOUT',
        true,
      );
    }
    throw new ApiClientError('Không thể gửi góp ý. Bạn có thể thử lại.');
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}
