/** Application header + shell; wires loading / backend-status / error states. */
import { useEffect, useState } from 'react';
import StatusPanel from './StatusPanel';
import NavPlaceholder from './NavPlaceholder';
import LoadingScreen from './LoadingScreen';
import ErrorScreen from './ErrorScreen';
import { apiGet } from '../api';

export default function Shell({ onReady, onLibraryReady }) {
  const [phase, setPhase] = useState('checking'); // checking | loading | ok | error | disconnected
  const [busy, setBusy] = useState(true);
  const [backendOk, setBackendOk] = useState(false);
  const [library, setLibrary] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      try {
        // 1) Confirm the backend answers (secure bridge if Electron exists).
        const health = await apiGet('/api/health');
        if (cancelled) return;
        setBackendOk(true);

        // 2) Read the existing library (SQLite through the new API).
        const summary = await apiGet('/api/library/summary');
        if (cancelled) return;
        setLibrary(summary);

        if (!cancelled) {
          setPhase('ok');
          onReady?.();
          onLibraryReady?.(summary);
        }
      } catch (err) {
        // Do not treat "no library yet" as a backend failure.
        if (cancelled) return;
        const status = err.cause?.status ?? 0;
        if (status >= 500) {
          setPhase('error');
          setError(err.message);
        } else if (status === 0) {
          setPhase('disconnected');
        } else {
          setPhase('ok');
          setLibrary({ total_records: 0, anime: { total: 0 }, literature: { total: 0 } });
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    }

    boot();
    return () => {
      cancelled = true;
    };
  }, []);

  const ready = phase === 'ok';
  const fetching = phase === 'checking' || busy;
  const hasError = phase === 'error';
  const isOffline = phase === 'disconnected';

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__icon" aria-hidden="true">◆</span>
          <h1 className="app-header__title">AnimeVault</h1>
        </div>
        <NavPlaceholder />
        <div className="app-header__search">
          <label className="glass-input" htmlFor="global-search">
            <span className="glass-input__icon" aria-hidden="true">⌕</span>
            <input
              id="global-search"
              className="glass-input__field"
              name="global-search"
              type="search"
              placeholder="Search library…"
            />
          </label>
        </div>
      </header>

      <main className="app-main">
        <StatusPanel
          phase={phase}
          loading={fetching}
          backendOk={backendOk}
          library={library}
          error={error}
        />

        {fetching && <LoadingScreen subtitle="Reading library metadata…" />}

        {isOffline && (
          <div className="glass-panel">
            <h2 className="glass-panel__title">Backend offline</h2>
            <p className="glass-panel__body">
              The FastAPI backend is not reachable. Existing library data is
              preserved, but new reads/writes will fail until it reconnects.
            </p>
          </div>
        )}

        {hasError && (
          <ErrorScreen message={error} onRetry={() => setPhase('checking')} />
        )}

        {ready && library && (
          <section className="glass-panel library-ready" aria-label="Library overview">
            <h2 className="glass-panel__title">Library ready</h2>
            <dl className="stats">
              <div>
                <dt className="stats__k">Total records</dt>
                <dd className="stats__v">{library.total_records ?? 0}</dd>
              </div>
              <div>
                <dt className="stats__k">Anime</dt>
                <dd className="stats__v">{library.anime?.total ?? 0}</dd>
              </div>
              <div>
                <dt className="stats__k">Literature</dt>
                <dd className="stats__v">{library.literature?.total ?? 0}</dd>
              </div>
            </dl>
            <p className="glass-panel__body">
              Existing SQLite records are intact and readable through the new
              React → Electron → FastAPI bridge.
            </p>
          </section>
        )}
      </main>

      <footer className="app-footer">
        <span>React · Electron · FastAPI · SQLite</span>
      </footer>
    </div>
  );
}
