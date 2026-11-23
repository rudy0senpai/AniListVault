/** @type {import('react').FC} */
const App = () => {
  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__icon" aria-hidden="true">◆</span>
          <h1 className="app-header__title">AnimeVault</h1>
        </div>
        <nav className="app-header__nav" aria-label="Main">
          <a className="nav__link" href="#library">Library</a>
          <a className="nav__link" href="#overview">Overview</a>
          <a className="nav__link" href="#recommend">Recommendations</a>
          <a className="nav__link" href="#settings">Settings</a>
        </nav>
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

      <main className="app-main" aria-live="polite">
        <section className="glass-panel">
          <h2 className="glass-panel__title">Welcome to the new shell</h2>
          <p className="glass-panel__body">
            React is rendering. The backing FastAPI service is untouched; only the
            UI layer is being migrated. Phases follow Phase 0's migration plan.
          </p>
        </section>
      </main>

      <footer className="app-footer">
        <span>AnimeVault — React + Electron + FastAPI foundation</span>
      </footer>
    </div>
  );
};

export default App;
