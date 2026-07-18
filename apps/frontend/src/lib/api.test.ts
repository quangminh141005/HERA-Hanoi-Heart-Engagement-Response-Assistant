import { afterEach, describe, expect, it, vi } from 'vitest';

import { API_BASE_URL, ApiClientError, normalizeApiError, postChat, postFeedback } from './api';

const successPayload = {
  request_id: 'request-1',
  conversation_id: 'conversation-1',
  response: 'Câu trả lời có nguồn.',
  answer_vi: 'Câu trả lời có nguồn.',
  response_type: 'grounded_answer',
  intent: 'greeting',
  grounded: true,
  data_classification: 'official_current',
  citations: [],
  warnings: [],
  structured_record_ids: [],
  actions: [],
  requires_handoff: false,
  emergency: false,
  metadata: {},
};

function mockResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    headers: new Headers(),
    json: vi.fn().mockResolvedValue(payload),
  } as unknown as Response;
}

describe('api helpers', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uses a same-origin versioned backend base URL by default', () => {
    expect(API_BASE_URL.endsWith('/api/v1')).toBe(true);
  });

  it('keeps status on ApiClientError', () => {
    const error = new ApiClientError('Nope', 503);
    expect(error.message).toBe('Nope');
    expect(error.status).toBe(503);
    expect(error.retryable).toBe(true);
  });

  it('normalizes the target API error envelope', () => {
    const error = normalizeApiError(
      {
        error: {
          code: 'CAPACITY_REACHED',
          message_vi: 'Ca này đã đủ số lượng.',
          request_id: 'request-1',
          retryable: false,
        },
      },
      409,
    );
    expect(error.code).toBe('CAPACITY_REACHED');
    expect(error.message).toBe('Ca này đã đủ số lượng.');
    expect(error.requestId).toBe('request-1');
    expect(error.retryable).toBe(false);
  });

  it('parses the current chat contract and sends Vietnamese context', async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(successPayload));
    vi.stubGlobal('fetch', fetchMock);
    const result = await postChat({ message: 'Xin chào' });
    expect(result.conversation_id).toBe('conversation-1');
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      message: 'Xin chào',
      locale: 'vi-VN',
      user_context: { channel: 'hospital_web' },
    });
  });

  it('fails safely when a successful response has an invalid schema', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse({ response: 'missing fields' })));
    await expect(postChat({ message: 'Xin chào' })).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    });
  });

  it('posts feedback against the chat request ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse(
        {
          feedback_id: 'feedback-1',
          request_id: 'request-1',
          accepted: true,
          created_at: '2026-07-18T00:00:00Z',
        },
        201,
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await postFeedback({ request_id: 'request-1', helpful: true });

    expect(result.accepted).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${API_BASE_URL}/feedback`);
  });
});
