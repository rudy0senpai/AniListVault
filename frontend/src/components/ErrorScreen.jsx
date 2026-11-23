/** Error state (backend unreachable). */
export default function ErrorScreen({ message = 'The library backend is unreachable.', onRetry }) {
  return (
    <div className="error">
      <div className="error__icon" aria-hidden="true">✕</div>
      <h2 className="error__title">Could not reach the backend</h2>
      <p className="error__msg">{message}</p>
      {onRetry && (
        <button className="neu-button" onClick={onRetry}>
          <svg className="error__retry" viewBox="0 0 20 20" aria-hidden="true">
            <path fill="currentColor" d="M10 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm0 14a6 6 0 1 1 0-12 6 6 0 0 1 0 12z" />
          </svg>
          Retry
        </button>
      )}
    </div>
  );
}
