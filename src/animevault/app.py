"""Application factory — creates and configures the QApplication."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from animevault.database import initialize_database


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

    # Make sure the database and schema exist before the first window
    # is shown.
    initialize_database()

    return app
