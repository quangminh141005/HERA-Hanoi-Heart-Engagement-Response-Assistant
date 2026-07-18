import { ChatPanel } from '../features/chat/ChatPanel';
import { BookingPanel } from '../features/booking/BookingPanel';

export function HomeRoute() {
  return (
    <>
      <ChatPanel />
      <BookingPanel />
    </>
  );
}

