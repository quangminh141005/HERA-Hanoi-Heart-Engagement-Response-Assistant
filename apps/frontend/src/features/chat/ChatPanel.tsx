import { ExternalLink, PhoneCall, Send, ShieldAlert } from 'lucide-react';
import { FormEvent, useMemo, useRef, useState } from 'react';

import { ErrorState, EmptyState, LoadingState } from '../../components/FeedbackStates';
import { StatusPill } from '../../components/StatusPill';
import { postChat } from '../../lib/api';
import { ChatMessage } from '../../types';

const STARTER_MESSAGES = [
  'Quy trình khám ngoại trú tại Khu Tự nguyện 1 như thế nào?',
  'Tôi muốn đặt lịch khám tim mạch',
  'BHYT cần giấy tờ gì khi đi khám?',
];

export function ChatPanel() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const lastAssistant = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant'),
    [messages],
  );

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
    };

    setMessages((current) => [...current, userMessage]);
    setDraft('');
    setError(null);
    setIsSending(true);

    try {
      const response = await postChat({
        message: trimmed,
        conversation_id: conversationId,
        locale: 'vi',
      });
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.response,
          citations: response.citations,
          intent: response.intent,
          emergency: response.emergency,
          requiresHandoff: response.requires_handoff,
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to send message.');
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage(draft);
  }

  return (
    <section className="chat-layout" aria-label="HERA chat">
      <aside className="context-panel">
        <StatusPill tone="safe">MVP shell</StatusPill>
        <h1>HERA customer-care assistant</h1>
        <p>
          A safe chat surface for official hospital QA, emergency detection,
          appointment handoff, and future hospital API integrations.
        </p>
        <div className="quick-prompts" aria-label="Suggested prompts">
          {STARTER_MESSAGES.map((message) => (
            <button
              className="quick-prompt"
              key={message}
              type="button"
              onClick={() => void sendMessage(message)}
            >
              {message}
            </button>
          ))}
        </div>
        <a className="contact-link" href="tel:115">
          <PhoneCall size={18} aria-hidden="true" />
          <span>Emergency 115</span>
        </a>
      </aside>

      <section className="chat-panel">
        <div className="chat-header">
          <div>
            <h2>Conversation</h2>
            <p>Vietnamese-first support with grounded-answer safeguards.</p>
          </div>
          {lastAssistant?.emergency ? (
            <StatusPill tone="warning">Emergency detected</StatusPill>
          ) : (
            <StatusPill>Ready</StatusPill>
          )}
        </div>

        <div className="message-list" aria-live="polite">
          {messages.length === 0 ? (
            <EmptyState message="Start with a hospital process, BHYT, appointment, or emergency-symptom question." />
          ) : (
            messages.map((message) => (
              <article className={`message message-${message.role}`} key={message.id}>
                <div className="message-meta">
                  <strong>{message.role === 'user' ? 'You' : 'HERA'}</strong>
                  {message.intent ? <span>{message.intent}</span> : null}
                </div>
                <p>{message.content}</p>
                {message.emergency ? (
                  <div className="safety-callout">
                    <ShieldAlert size={18} aria-hidden="true" />
                    <span>Emergency routing is prioritized over normal QA.</span>
                  </div>
                ) : null}
                {message.citations && message.citations.length > 0 ? (
                  <div className="citations">
                    {message.citations.map((citation) => (
                      <a
                        href={citation.url ?? '#'}
                        key={citation.source_id}
                        rel="noreferrer"
                        target={citation.url ? '_blank' : undefined}
                      >
                        <ExternalLink size={14} aria-hidden="true" />
                        {citation.title}
                      </a>
                    ))}
                  </div>
                ) : null}
              </article>
            ))
          )}
          {isSending ? <LoadingState label="HERA is checking safety and sources" /> : null}
          {error ? <ErrorState message={error} /> : null}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            aria-label="Message"
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Nhập câu hỏi của bạn..."
            ref={inputRef}
            rows={3}
            value={draft}
          />
          <button disabled={!draft.trim() || isSending} type="submit">
            <Send size={18} aria-hidden="true" />
            <span>Send</span>
          </button>
        </form>
      </section>
    </section>
  );
}

