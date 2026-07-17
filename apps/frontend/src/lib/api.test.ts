import { describe, expect, it } from 'vitest';

import { API_BASE_URL, ApiClientError } from './api';

describe('api helpers', () => {
  it('uses a versioned backend base URL', () => {
    expect(API_BASE_URL.endsWith('/api/v1')).toBe(true);
  });

  it('keeps status on ApiClientError', () => {
    const error = new ApiClientError('Nope', 503);

    expect(error.message).toBe('Nope');
    expect(error.status).toBe(503);
  });
});

