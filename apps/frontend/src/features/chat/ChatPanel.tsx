import { CalendarCheck, PhoneCall, RotateCcw, Send, UserRound } from 'lucide-react';
import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

import { EmptyState, ErrorState, LoadingState } from '../../components/FeedbackStates';
import { StatusPill } from '../../components/StatusPill';
import { WelcomeDisclaimer } from '../../components/WelcomeDisclaimer';
import { AssistantMessage } from './AssistantMessage';
import { useChat } from './useChat';

const CHAT_MAX_CHARS = 2_000;
const COLLAPSED_MESSAGE_LIMIT = 10;
const STARTER_MESSAGES = [
  'Dịch vụ “Giá Khám bệnh” đang niêm yết bao nhiêu?',
  'Mức đóng BHYT hộ gia đình hiện nay là bao nhiêu?',
  'Lịch bác sĩ cơ sở 1 hôm nay',
  'Tuần sau bác sĩ nào có lịch tại cơ sở 2?',
  'Tôi cần chuẩn bị giấy tờ gì khi đi khám?',
  'Thủ tục tái khám tại bệnh viện như thế nào?',
];

function PromptButtons({ disabled, onSelect }: { disabled: boolean; onSelect: (message: string) => void }) {
  return (
    <div className="quick-prompts" aria-label="Câu hỏi gợi ý">
      {STARTER_MESSAGES.map((message) => (
        <button
          className="quick-prompt"
          disabled={disabled}
          key={message}
          type="button"
          onClick={() => onSelect(message)}
        >
          {message}
        </button>
      ))}
    </div>
  );
}

export function ChatPanel({ compact = false }: { compact?: boolean }) {
  const { messages, isSending, error, canRetry, sendMessage, retry, resetConversation } = useChat();
  const [draft, setDraft] = useState('');
  const [showFullHistory, setShowFullHistory] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const lastAssistant = useMemo(
    () => [...messages].reverse().find((message) => message.role === 'assistant'),
    [messages],
  );
  const hiddenMessageCount = Math.max(0, messages.length - COLLAPSED_MESSAGE_LIMIT);
  const visibleMessages = showFullHistory ? messages : messages.slice(-COLLAPSED_MESSAGE_LIMIT);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [visibleMessages, isSending, error]);

  function submitText(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isSending) {
      return;
    }
    setDraft('');
    setShowFullHistory(false);
    void sendMessage(trimmed).finally(() => inputRef.current?.focus());
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitText(draft);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submitText(draft);
    }
  }

  function reset() {
    setShowFullHistory(false);
    resetConversation();
  }

  return (
    <section className={`chat-layout${compact ? ' chat-layout-compact' : ''}`} aria-label="Trò chuyện với HERA">
      {!compact ? (
        <aside className="context-panel">
          <StatusPill tone="safe">Trợ lý thông tin</StatusPill>
          <h1>Hỏi thông tin Bệnh viện Tim Hà Nội</h1>
          <p>
            Tra bảng giá đã cung cấp, mức đóng BHYT hộ gia đình và lịch làm việc từ dữ liệu có nguồn.
          </p>
          <PromptButtons disabled={isSending} onSelect={submitText} />
          <a className="booking-jump-link" href="#booking">
            <CalendarCheck size={18} aria-hidden="true" />
            <span>Xem ca và giữ chỗ bản demo</span>
          </a>
          <a className="contact-link" href="tel:115">
            <PhoneCall size={18} aria-hidden="true" />
            <span>Trường hợp cấp cứu: gọi 115</span>
          </a>
        </aside>
      ) : null}

      <section className="chat-panel">
        <div className="chat-header">
          <div>
            <h2>HERA</h2>
            <p>Trả lời tiếng Việt, hiển thị nguồn và cảnh báo dữ liệu.</p>
          </div>
          <div className="chat-header-actions">
            {lastAssistant?.emergency ? (
              <StatusPill tone="warning">Ưu tiên cấp cứu</StatusPill>
            ) : (
              <StatusPill>Sẵn sàng</StatusPill>
            )}
            {messages.length > 0 ? (
              <button className="reset-button" type="button" onClick={reset}>
                <RotateCcw size={15} aria-hidden="true" />
                Cuộc trò chuyện mới
              </button>
            ) : null}
          </div>
        </div>

        <WelcomeDisclaimer compact={compact} />

        <div className="message-list" aria-live="polite" aria-busy={isSending}>
          {messages.length === 0 ? (
            <div className="empty-conversation">
              <EmptyState message="Hãy chọn một câu hỏi mẫu hoặc nhập câu hỏi hành chính của bạn." />
              {compact ? <PromptButtons disabled={isSending} onSelect={submitText} /> : null}
            </div>
          ) : (
            <>
              {hiddenMessageCount > 0 ? (
                <button
                  className="history-toggle"
                  type="button"
                  onClick={() => setShowFullHistory((value) => !value)}
                >
                  {showFullHistory ? 'Thu gọn lịch sử' : `Xem ${hiddenMessageCount} tin nhắn cũ hơn`}
                </button>
              ) : null}
              {visibleMessages.map((message) =>
                message.role === 'assistant' ? (
                  <AssistantMessage key={message.id} message={message} />
                ) : (
                  <article className="message message-user" key={message.id}>
                    <div className="message-meta">
                      <strong><UserRound size={15} aria-hidden="true" /> Bạn</strong>
                    </div>
                    <p>{message.content}</p>
                  </article>
                ),
              )}
            </>
          )}
          {isSending ? <LoadingState label="HERA đang kiểm tra an toàn và nguồn dữ liệu..." /> : null}
          {error ? (
            <div className="request-error">
              <ErrorState message={error.message} />
              {canRetry ? (
                <button type="button" onClick={() => void retry()}>
                  Thử gửi lại
                </button>
              ) : null}
              {error.requestId ? <small>Mã yêu cầu: {error.requestId}</small> : null}
            </div>
          ) : null}
          <div ref={endRef} />
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <div className="composer-input">
            <textarea
              aria-describedby="composer-help"
              aria-label="Nhập câu hỏi"
              maxLength={CHAT_MAX_CHARS}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Nhập câu hỏi hành chính của bạn..."
              ref={inputRef}
              rows={3}
              value={draft}
            />
            <div className="composer-help" id="composer-help">
              <span>Enter để gửi, Shift + Enter để xuống dòng</span>
              <span>{draft.length}/{CHAT_MAX_CHARS}</span>
            </div>
          </div>
          <button disabled={!draft.trim() || isSending} type="submit">
            <Send size={18} aria-hidden="true" />
            <span>Gửi</span>
          </button>
        </form>
      </section>
    </section>
  );
}
