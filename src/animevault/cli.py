"""Command-line entry point for AnimeVault."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from animevault.app import create_app
from animevault.database import initialize_database
from animevault.main_window import MainWindow


def main() -> int:
    """Run the AnimeVault GUI application.

    Returns
    -------
    int
        Process exit code (0 on normal exit).
    """
    initialize_database()

    app = create_app()

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
