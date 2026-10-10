"""Looping video background for the main window.

QtMultimedia decodes on its own threads, so playback does not block the
GUI thread.  A dark gradient is always painted underneath and shows
through at low opacity, so the app looks deliberate whether or not the
video decodes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from animevault.ui import theme as theme_tokens

logger = logging.getLogger(__name__)

#: Opacity of the video, keeping the dark UI legible on top.
DEFAULT_OPACITY = 0.32


def media_path(filename: str = "background.mp4") -> Path:
    """Absolute path to a bundled media file."""
    return Path(__file__).resolve().parent.parent / "resources" / "media" / filename


class _VideoPlayer(QObject):
    """Wraps QMediaPlayer, converting video frames into QPixmaps.

    A custom QVideoSink subclass is used because Qt 6 has no signal that
    carries decoded frames; ``videoFrameChanged`` gives us each frame to
    convert and hand to the widget.
    """

    frame_ready = Signal(object)   # QPixmap
    playback_failed = Signal(str)

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path

    def start(self) -> bool:
        """Start looping, muted playback.  Returns False if unavailable."""
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except Exception as exc:
            self.playback_failed.emit(f"QtMultimedia unavailable: {exc}")
            return False

        if not Path(self._path).exists():
            self.playback_failed.emit(f"Missing media file: {self._path}")
            return False

        # VideoSink lives in QtMultimedia, not QtMultimediaWidgets.
        try:
            from PySide6.QtMultimedia import QVideoSink
        except Exception as exc:
            self.playback_failed.emit(f"QVideoSink unavailable: {exc}")
            return False

        try:
            self._sink = QVideoSink(self)
            self._sink.videoFrameChanged.connect(self._on_frame)

            self._player = QMediaPlayer(self)
            self._player.setVideoSink(self._sink)

            # Muted: this is decoration, and an unexpected soundtrack
            # during normal use would be intrusive.
            try:
                audio = QAudioOutput(self)
                audio.setVolume(0.0)
                self._player.setAudioOutput(audio)
                self._audio = audio
            except Exception as exc:
                logger.debug("Could not attach muted audio output: %s", exc)

            self._player.setSource(QUrl.fromLocalFile(str(Path(self._path).resolve())))
            self._player.setLoops(QMediaPlayer.Loops.Infinite)
            self._player.errorOccurred.connect(
                lambda err, msg="": self.playback_failed.emit(
                    f"{msg or 'playback error'} (code {err})"
                )
            )
            self._player.play()
            logger.info("Background video playing: %s", self._path)
            return True
        except Exception as exc:
            logger.warning("Could not start background video: %s", exc)
            self.playback_failed.emit(str(exc))
            return False

    def _on_frame(self, frame) -> None:
        """Convert a QVideoFrame to a QImage, then a QPixmap."""
        try:
            image = frame.toImage()
            if image.isNull():
                return
            self.frame_ready.emit(QPixmap.fromImage(image))
        except Exception as exc:
            logger.debug("Frame conversion failed: %s", exc)

    def set_paused(self, paused: bool) -> None:
        player = getattr(self, "_player", None)
        if player is not None:
            player.pause() if paused else player.play()

    def stop(self) -> None:
        player = getattr(self, "_player", None)
        if player is not None:
            try:
                player.stop()
            except Exception:
                pass


class VideoBackground(QWidget):
    """Paints a looping, muted video behind the rest of the UI.

    Ignores mouse input and stays behind every sibling, so it never
    interferes with the app.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        opacity: float = DEFAULT_OPACITY,
        filename: str = "background.mp4",
    ) -> None:
        super().__init__(parent)
        self._opacity = max(0.0, min(1.0, opacity))
        self._pixmap: Optional[QPixmap] = None
        self._player: Optional[_VideoPlayer] = None
        self._status = "starting"
        self._effects_reduced = False

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        path = media_path(filename)
        if not path.exists():
            logger.info("No background video at %s; gradient only", path)
            self._status = "missing"
            return

        self._player = _VideoPlayer(str(path), self)
        self._player.frame_ready.connect(self._on_frame)
        self._player.playback_failed.connect(self._on_failed)
        if self._player.start():
            self._status = "playing"
        else:
            self._status = "failed"

    # ── Slots ──────────────────────────────────────────────────────

    def _on_frame(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def _on_failed(self, reason: str) -> None:
        logger.info("Background video unavailable: %s", reason)
        self._status = "failed"
        self.update()

    @property
    def status(self) -> str:
        """One of: playing, failed, missing, starting."""
        return self._status

    def set_effects_reduced(self, reduced: bool) -> None:
        """Pause decorative video and remove its glow while effects are reduced."""
        self._effects_reduced = bool(reduced)
        if self._player is not None:
            self._player.set_paused(self._effects_reduced)
        self.update()

    def shutdown(self) -> None:
        """Stop playback and release decoder resources."""
        if self._player is not None:
            self._player.stop()
            self._player = None

    # ── Painting ───────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Paint a solid base for reduced-effects mode, otherwise the theme gradient.
        if self._effects_reduced:
            painter.fillRect(self.rect(), QColor(theme_tokens.BG_DEEP))
        else:
            gradient = QLinearGradient(0, 0, 0, max(1, self.height()))
            gradient.setColorAt(0.0, QColor(theme_tokens.BG_DEEP))
            gradient.setColorAt(1.0, QColor(theme_tokens.BG_PANEL))
            painter.fillRect(self.rect(), gradient)

        if not self._effects_reduced and self._pixmap is not None and not self._pixmap.isNull():
            painter.setOpacity(self._opacity)
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(-x, -y, scaled)
            painter.setOpacity(1.0)
        elif not self._effects_reduced:
            # Soft cyan glow so the empty state still looks designed.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(34, 211, 238, 16))
            radius = int(self.width() * 0.55)
            painter.drawEllipse(
                int(self.width() * 0.2), int(self.height() * 0.6), radius, radius
            )

        painter.end()