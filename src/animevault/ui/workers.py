"""Background search workers used by the add-media dialog.

Qt widgets must never block on network I/O, so both the anime and the
literature searches run on a QThread and deliver results via signals.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class SearchWorker(QThread):
    """Anime search across providers, off the GUI thread."""

    results_ready = Signal(list)
    search_error = Signal(str)

    def __init__(self, query: str, search_service=None, parent=None) -> None:
        super().__init__(parent)
        self._query = query.strip()

    def run(self) -> None:
        try:
            if not self._query:
                self.results_ready.emit([])
                return
            # Import here so the module stays importable without network deps.
            from animevault.services.search import SearchService

            service = SearchService()
            self.results_ready.emit(service.search(self._query))
        except Exception as exc:
            logger.exception("Anime search failed for %r", self._query)
            self.search_error.emit(str(exc))


class LiteratureSearchWorker(QThread):
    """Manga / manhwa / manhua search, off the GUI thread."""

    results_ready = Signal(list)
    search_error = Signal(str)

    def __init__(self, query: str, parent=None) -> None:
        super().__init__(parent)
        self._query = query.strip()

    def run(self) -> None:
        try:
            if not self._query:
                self.results_ready.emit([])
                return
            from animevault.services.literature_search import LiteratureSearchService

            service = LiteratureSearchService()
            self.results_ready.emit(service.search(self._query))
        except Exception as exc:
            logger.exception("Literature search failed for %r", self._query)
            self.search_error.emit(str(exc))