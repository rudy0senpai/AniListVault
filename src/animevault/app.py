"""Application factory — creates and configures the QApplication."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from animevault.database import initialize_database
from animevault.migration import run_migrations

ICON_PATH = Path(__file__).resolve().parent / "resources" / "media" / "app.ico"


def create_app() -> QApplication:
    """Create (or retrieve) the QApplication and ensure the DB is ready.

    Returns
    -------
    QApplication
        The singleton QApplication instance.
    """
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
    from animevault.ui.theme import ThemeManager

    manager = ThemeManager.instance(app)
    manager.restore()
    manager.set_reduce_effects(manager.reduce_effects)

    # Make sure the database and schema exist before the first window
    # is shown, then bring the schema up to the current version.
    initialize_database()
    run_migrations()

    return app
