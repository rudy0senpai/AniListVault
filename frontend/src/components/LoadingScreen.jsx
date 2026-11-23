/** Loading state. */
export default function LoadingScreen({ subtitle = 'Connecting to the library…' }) {
  return (
    <div className="loading">
      <svg className="spinner" viewBox="0 0 36 36" aria-hidden="true">
        <circle
          className="ring"
          cx="18"
          cy="18"
          r="15"
          fill="none"
          stroke="var(--bg-elevated)"
          strokeWidth="3"
        />
        <circle
          className="ring ring--active"
          cx="18"
          cy="18"
          r="15"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="3"
          strokeDasharray="94"
          strokeDashoffset="94"
          strokeLinecap="round"
        />
      </svg>
      <p className="loading__msg"><span className="sr-only">Loading</span>{subtitle}</p>
    </div>
  );
}
