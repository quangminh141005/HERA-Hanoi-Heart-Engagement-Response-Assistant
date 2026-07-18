import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { useState } from 'react';

import { postFeedback } from '../../lib/api';

type FeedbackState = 'idle' | 'sending' | 'sent' | 'error';

export function FeedbackControls({ requestId }: { requestId: string }) {
  const [state, setState] = useState<FeedbackState>('idle');

  async function submit(helpful: boolean) {
    if (state === 'sending' || state === 'sent') {
      return;
    }
    setState('sending');
    try {
      await postFeedback({
        request_id: requestId,
        helpful,
        ...(helpful ? {} : { reason_code: 'other' as const }),
      });
      setState('sent');
    } catch {
      setState('error');
    }
  }

  if (state === 'sent') {
    return <p className="feedback-receipt" role="status">Cảm ơn góp ý của bạn.</p>;
  }

  return (
    <div className="feedback-controls" aria-label="Đánh giá câu trả lời">
      <span>Câu trả lời này có hữu ích không?</span>
      <button
        aria-label="Câu trả lời hữu ích"
        disabled={state === 'sending'}
        type="button"
        onClick={() => void submit(true)}
      >
        <ThumbsUp size={15} aria-hidden="true" />
      </button>
      <button
        aria-label="Câu trả lời chưa hữu ích"
        disabled={state === 'sending'}
        type="button"
        onClick={() => void submit(false)}
      >
        <ThumbsDown size={15} aria-hidden="true" />
      </button>
      {state === 'error' ? <small role="alert">Chưa gửi được góp ý. Bạn có thể thử lại.</small> : null}
    </div>
  );
}
