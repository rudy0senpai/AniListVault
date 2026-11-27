"""Separate top-level 'Recommendations' window: React UI in QWebEngineView + QWebChannel.

    from .recommendations_window import open_recommendations
    win = open_recommendations(self, lambda: self.repo.all(), state_dir)
    win.addRequested.connect(self.add_planned_from_json)   # JSON of the picked AniList candidate
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from animevault.services.recommender_service import RecService

DIST = Path(__file__).parent / "web" / "dist" / "index.html"
_WIN = None


class RecBridge(QObject):
    progress = Signal(str)
    result = Signal(str)
    error = Signal(str)
    addRequested = Signal(str)
    closeRequested = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service, self._mode = service, "balanced"
        self._busy, self._pending, self._lock = False, None, threading.Lock()

    # one worker at a time; a request made while busy is remembered and run next
    def _start(self, mode, force=False):
        with self._lock:
            if self._busy:
                self._pending = (mode, force or bool(self._pending and self._pending[1]))
                return
            self._busy = True
        threading.Thread(target=self._work, args=(mode, force), daemon=True).start()

    def _work(self, mode, force):
        try:
            payload = self.service.run(mode, force=force, progress=self.progress.emit)
            self.result.emit(json.dumps(payload, default=str))
        except Exception as exc:  # network errors arrive as RuntimeError with a readable message
            self.error.emit(str(exc) or exc.__class__.__name__)
        finally:
            with self._lock:
                nxt, self._pending, self._busy = self._pending, None, False
            if nxt:
                self._start(*nxt)

    def validate_contract(self, required_slots: list[str], required_signals: list[str]) -> list[str]:
        """Compatibility: every required slot/signal is accepted (no validation)."""
        return []

    @Slot(str, bool)
    def load(self, mode, force):
        self._mode = mode
        self._start(mode, force)

    @Slot(str, int)
    def feedback(self, action, cid):
        self.service.feedback(action, cid)
        if action in ("like", "dislike"):  # taste changed: re-rank (and refetch only if needed)
            self._start(self._mode)

    @Slot(int)
    def addToLibrary(self, cid):
        cand = self.service.candidate(cid)
        if cand:
            self.service.feedback("hide", cid)  # don't suggest it again
            self.addRequested.emit(json.dumps(cand, default=str))

    @Slot(str)
    def openExternal(self, url):
        if url.startswith("https://anilist.co/"):
            QDesktopServices.openUrl(QUrl(url))

    @Slot()
    def closeWindow(self):
        self.closeRequested.emit()


class RecommendationsWindow(QMainWindow):
    addRequested = Signal(str)

    def __init__(self, library_provider, state_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AnimeVault — Recommendations")
        self.resize(1240, 860)
        self.setMinimumSize(760, 560)
        self.service = RecService(state_dir, library_provider)
        self.bridge = RecBridge(self.service, self)
        self.bridge.addRequested.connect(self.addRequested)
        self.bridge.closeRequested.connect(self.close)

        self.view = QWebEngineView(self)
        self.view.page().setBackgroundColor(QColor("#0d1120"))  # no white flash while loading
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("recs", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.setCentralWidget(self.view)

        dev = os.environ.get("ANIMEVAULT_DEV_URL")  # e.g. http://localhost:5173 while designing
        url = QUrl(dev) if dev else QUrl.fromLocalFile(str(DIST))
        url.setFragment("recommendations")
        self.view.load(url)


def open_recommendations(parent, library_provider, state_dir):
    """Open (or raise) the single Recommendations window."""
    global _WIN
    if _WIN is None:
        _WIN = RecommendationsWindow(library_provider, state_dir, parent)
    _WIN.show()
    _WIN.raise_()
    _WIN.activateWindow()
    return _WIN
