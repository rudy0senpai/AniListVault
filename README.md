# AnimeVault

A cross-platform desktop anime library manager built with PySide6 and SQLite.

## v0.0.1 — Minimum Viable Library

The first public version. Manually add anime entries, browse your library as cards, and store everything locally in SQLite.

### Features
- Add anime manually via a form dialog (title, Japanese title, episodes, status, score, notes).
- Browse all entries as cards in the main window.
- Data persists across restarts in a local SQLite database.

### Non-Goals (v0.01)
No external APIs (Jikan, AniList, Kitsu, TMDB, AniDB), no metadata enrichment, no poster downloading, no AI, no import/export.

## Development

```bash
# Create environment and install
python -m venv .venv
. .venv/Scripts/Activate.ps1   # PowerShell on Windows
# or: . .venv/bin/activate     # POSIX

pip install -e ".[dev]"

# Run the app
python -m animevault

# Run tests
pytest tests/ -v
```

## License

MIT
