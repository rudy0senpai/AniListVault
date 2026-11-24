"""Application factory — creates and configures the QApplication."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from animevault.database import initialize_database
from animevault.migration import run_migrations

ICON_PATH = Path(__file__).resolve().parent / "resources" / "media" / "app.ico"


# Module-level singleton (thread-safe).
_app = None


def create_app() -> QApplication:
    """Create (or retrieve) the QApplication and ensure the DB is ready.

    Returns
    -------
    QApplication
        The singleton QApplication instance.
    """
    global _app
    if _app is not None:
        return _app
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Stable identifiers for QSettings, also when a QApplication already exists.
    app.setApplicationName("AnimeVault")
    app.setOrganizationName("AnimeVault")

    # Window / taskbar / installer icon.
    if ICON_PATH.exists():
        icon = QIcon(str(ICON_PATH))
        if not icon.isNull():
            app.setWindowIcon(icon)

    # Restore appearance before any window is constructed or shown.
    from animevault.ui.theme import (
        liquid_glass,
        reduce_effects,
        set_liquid_glass,
        set_reduce_effects,
    )

    # Sync appearance preferences from QSettings (no theme switching exists).
    set_reduce_effects(reduce_effects(app))
    set_liquid_glass(liquid_glass(app))

    # Make sure the database and schema exist before the first window is shown.
    initialize_database()
    run_migrations()

    _app = app
    return _app


def get_app() -> QApplication:
    """Return the current QApplication singleton (creates one if needed)."""
    return create_app()
