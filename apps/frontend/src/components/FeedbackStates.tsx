export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="feedback-state" role="status">
      <span className="loader" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="feedback-state feedback-state-error" role="alert">
      {message}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="feedback-state">{message}</div>;
}

