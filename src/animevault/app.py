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
        app.setApplicationName("AnimeVault")
        app.setOrganizationName("AnimeVault")

    # Window / taskbar / installer icon.
    if ICON_PATH.exists():
        icon = QIcon(str(ICON_PATH))
        if not icon.isNull():
            app.setWindowIcon(icon)

    # Apply the dark visual theme.
    from animevault.ui.theme import build_stylesheet

    app.setStyleSheet(build_stylesheet())

    # Make sure the database and schema exist before the first window
    # is shown, then bring the schema up to the current version.
    initialize_database()
    run_migrations()

    return app
