import { useEffect, useRef, useState } from 'react';

import { ApiClientError, postChat } from '../../lib/api';
import { getStructuredAction } from '../../lib/structured';
import { ChatMessage } from '../../types';

const SESSION_KEY = 'hera.chat.session.v1';
const MAX_RETAINED_MESSAGES = 24;

function messageId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `message-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function loadSession(): { conversationId: string | null; messages: ChatMessage[] } {
  try {
    const raw = globalThis.sessionStorage?.getItem(SESSION_KEY);
    if (!raw) {
      return { conversationId: null, messages: [] };
    }
    const parsed = JSON.parse(raw) as { conversationId?: unknown; messages?: unknown };
    return {
      conversationId: typeof parsed.conversationId === 'string' ? parsed.conversationId : null,
      messages: Array.isArray(parsed.messages) ? (parsed.messages as ChatMessage[]).slice(-MAX_RETAINED_MESSAGES) : [],
    };
  } catch {
    return { conversationId: null, messages: [] };
  }
}

function saveSession(conversationId: string | null, messages: ChatMessage[]) {
  try {
    globalThis.sessionStorage?.setItem(
      SESSION_KEY,
      JSON.stringify({
        conversationId,
        messages: messages.slice(-MAX_RETAINED_MESSAGES),
      }),
    );
  } catch {
    // Session storage is optional; chat still works without browser persistence.
  }
}

export function useChat() {
  const initial = loadSession();
  const [conversationId, setConversationId] = useState<string | null>(initial.conversationId);
  const [messages, setMessages] = useState<ChatMessage[]>(initial.messages);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<ApiClientError | null>(null);
  const [failedText, setFailedText] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => saveSession(conversationId, messages), [conversationId, messages]);

  async function deliver(text: string, appendUserMessage: boolean): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || sendingRef.current) {
      return;
    }
    sendingRef.current = true;
    setIsSending(true);
    setError(null);
    setFailedText(null);
    if (appendUserMessage) {
      const userMessage: ChatMessage = {
        id: messageId(),
        role: 'user',
        content: trimmed,
      };
      setMessages((current) => [
        ...current,
        userMessage,
      ].slice(-MAX_RETAINED_MESSAGES));
    }

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await postChat(
        {
          message: trimmed,
          conversation_id: conversationId,
          locale: 'vi-VN',
          user_context: { channel: 'hospital_web' },
        },
        { signal: controller.signal },
      );
      setConversationId(response.conversation_id);
      const assistantMessage: ChatMessage = {
        id: messageId(),
        role: 'assistant',
        content: response.answer_vi,
        citations: response.citations,
        intent: response.intent,
        responseType: response.response_type,
        grounded: response.grounded,
        dataClassification: response.data_classification,
        warnings: response.warnings,
        structuredRecordIds: response.structured_record_ids,
        actions: response.actions,
        emergency: response.emergency,
        requiresHandoff: response.requires_handoff,
        metadata: response.metadata,
        structuredAction: getStructuredAction(response.metadata),
        requestId: response.request_id,
      };
      setMessages((current) => [
        ...current,
        assistantMessage,
      ].slice(-MAX_RETAINED_MESSAGES));
    } catch (caught) {
      const normalized =
        caught instanceof ApiClientError
          ? caught
          : new ApiClientError('Không thể xử lý câu hỏi. Vui lòng thử lại.');
      if (normalized.code !== 'REQUEST_CANCELLED') {
        setError(normalized);
        setFailedText(trimmed);
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      sendingRef.current = false;
      setIsSending(false);
    }
  }

  function sendMessage(text: string): Promise<void> {
    return deliver(text, true);
  }

  function retry(): Promise<void> {
    return failedText ? deliver(failedText, false) : Promise.resolve();
  }

  function resetConversation() {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    setError(null);
    setFailedText(null);
    try {
      globalThis.sessionStorage?.removeItem(SESSION_KEY);
    } catch {
      // Ignore storage failures.
    }
  }

  return {
    messages,
    isSending,
    error,
    canRetry: Boolean(failedText && error?.retryable),
    sendMessage,
    retry,
    resetConversation,
  };
}
