import { ChatRequest, ChatResponse } from '../types';

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ??
  'http://localhost:8000/api/v1';

export async function postChat(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      locale: 'vi',
      user_context: {},
      ...request,
    }),
  });

  if (!response.ok) {
    let message = 'Unable to reach HERA. Please try again.';
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === 'string') {
        message = payload.detail;
      }
    } catch {
      message = response.statusText || message;
    }
    throw new ApiClientError(message, response.status);
  }

  return (await response.json()) as ChatResponse;
}

