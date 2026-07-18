import { useRef } from 'react';

import { ChatPanel } from '../features/chat/ChatPanel';
import { BookingPanel } from '../features/booking/BookingPanel';
import { useWidgetBridge } from '../lib/embed';

export function WidgetRoute() {
  const rootRef = useRef<HTMLDivElement>(null);
  useWidgetBridge(rootRef);
  return (
    <div className="widget-route" ref={rootRef}>
      <ChatPanel compact />
      <BookingPanel compact />
    </div>
  );
}
