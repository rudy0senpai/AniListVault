/** Connection / readiness status banner. */
import { useMemo } from 'react';

const PHASE_LABELS = {
  checking: 'Checking backend…',
  loading: 'Loading library…',
  ok: 'Connected',
  error: 'Backend error',
  disconnected: 'Disconnected',
};

export default function StatusPanel({ phase, loading, backendOk, library, error }) {
  const label = useMemo(() => PHASE_LABELS[phase] ?? phase, [phase]);

  if (loading && phase === 'checking') {
    return (
      <div className="status-banner status-banner--war" role="status">
        <span className="spinner ring--active" aria-hidden="true" />
        <span>{label}</span>
      </div>
    );
  }

  if (backendOk && library) {
    return (
      <div className="status-banner status-banner--ok" role="status">
        <span aria-hidden="true">●</span>
        <span>Connected · {library.total_records ?? 0} records</span>
      </div>
    );
  }

  if (backendOk && (!library || library.total_records === 0)) {
    return (
      <div className="status-banner status-banner--war" role="status">
        <span>No library data yet — run an import to populate.</span>
      </div>
    );
  }

  if (phase === 'disconnected') {
    return (
      <div className="status-banner status-banner--err" role="status">
        <span aria-hidden="true">●</span>
        <span>Backend offline — no backend response</span>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="status-banner status-banner--err" role="alert">
        <span>Error: {error ?? 'unknown'}</span>
      </div>
    );
  }

  return null;
}
