import { RefObject, useEffect } from 'react';

type HostMessage = {
  source: 'hera-host';
  type: 'open' | 'close';
};

function configuredOrigins(): Set<string> {
  const origins = new Set<string>();
  for (const rawValue of (import.meta.env.VITE_EMBED_PARENT_ORIGINS ?? '').split(',')) {
    const value = rawValue.trim();
    if (!value) continue;
    try {
      const parsed = new URL(value);
      if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
        origins.add(parsed.origin);
      }
    } catch {
      // Ignore malformed build-time values instead of weakening postMessage checks.
    }
  }
  return origins;
}

function referrerOrigin(): string | null {
  if (!document.referrer) {
    return null;
  }
  try {
    return new URL(document.referrer).origin;
  } catch {
    return null;
  }
}

function allowedParentOrigin(): string | null {
  const parentOrigin = referrerOrigin();
  if (!parentOrigin) {
    return null;
  }
  const configured = configuredOrigins();
  if (configured.has(parentOrigin)) {
    return parentOrigin;
  }
  // A missing allowlist is fail-closed for cross-origin embedding. Same-origin
  // previews still work for developers without opening the widget to any site.
  return configured.size === 0 && parentOrigin === window.location.origin
    ? parentOrigin
    : null;
}

export function useWidgetBridge(rootRef: RefObject<HTMLElement>) {
  useEffect(() => {
    if (window.parent === window) {
      return;
    }
    const targetOrigin = allowedParentOrigin();
    if (!targetOrigin) {
      return;
    }

    const post = (type: 'ready' | 'height', height?: number) => {
      window.parent.postMessage(
        { source: 'hera-widget', type, ...(height === undefined ? {} : { height }) },
        targetOrigin,
      );
    };
    const onMessage = (event: MessageEvent<unknown>) => {
      if (event.origin !== targetOrigin || typeof event.data !== 'object' || event.data === null) {
        return;
      }
      const message = event.data as Partial<HostMessage>;
      if (message.source !== 'hera-host' || (message.type !== 'open' && message.type !== 'close')) {
        return;
      }
      document.documentElement.dataset.widgetState = message.type;
    };

    post('ready');
    const observer = new ResizeObserver(() => {
      const height = Math.ceil(rootRef.current?.getBoundingClientRect().height ?? 0);
      if (height > 0) {
        post('height', height);
      }
    });
    if (rootRef.current) {
      observer.observe(rootRef.current);
    }
    window.addEventListener('message', onMessage);
    return () => {
      observer.disconnect();
      window.removeEventListener('message', onMessage);
      delete document.documentElement.dataset.widgetState;
    };
  }, [rootRef]);
}
