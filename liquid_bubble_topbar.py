"""Native PySide6 Liquid Bubble top bar for AnimeVault.

This is a self-contained replacement for the existing desktop top-area widgets:
dynamic summary strip, action toolbar, and search/filter row. The host application owns brand/category navigation.
It deliberately has no React, JavaScript, QWebChannel, or web-engine dependency.

Integration overview:
    topbar = LiquidBubbleTopBar(..., parent=main_window)
    topbar.category_changed.connect(main_window._on_category_changed)
    topbar.add_requested.connect(main_window._on_add)
    topbar.search_changed.connect(main_window._on_search_changed)
    ...

See README.md in this package for the complete signal-to-handler mapping.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from PySide6.QtCore import Qt, Signal, QSize, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QLinearGradient, QBrush, QPen, QRadialGradient, QPainterPath
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


DEFAULT_CATEGORIES = {
    "anime": "Anime",
    "manga": "Manga",
    "manhwa": "Manhwa",
    "manhua": "Manhua",
}

DEFAULT_SUMMARY_FIELDS = (
    ("anime_total", "Anime"),
    ("anime_watching", "Watching"),
    ("anime_completed", "Completed"),
    ("anime_planned", "Plan to Watch"),
    ("manga_total", "Manga"),
    ("manhwa_total", "Manhwa"),
    ("manhua_total", "Manhua"),
)

PALETTE = {
    "base": "#101522",
    "surface": "#151e30",
    "surface_hi": "#1d2940",
    "surface_hover": "#26344d",
    "border": "#35455f",
    "border_soft": "#52617a",
    "mint": "#72e6d0",
    "mint_hi": "#a0f5e7",
    "mint_text": "#082b2a",
    "violet": "#c3a0ff",
    "pink": "#ff9eaf",
    "text": "#f1f4fb",
    "muted": "#9eacc3",
    "disabled": "#64718a",
}


class BubbleButton(QToolButton):
    """Native 3D bubble button with animated hover lift and cursor-following sheen."""
    def __init__(self, text: str, *, variant: str = "normal", parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setMinimumHeight(40)
        self.setMaximumHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setProperty("bubbleVariant", variant)
        self._hover = 0.0
        self._press = 0.0
        self._mouse_pos = None
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet("QToolButton { background: transparent; border: 0; padding: 0; }")
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(230)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"pressProgress", self)
        self._press_anim.setDuration(110)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 105))
        self.setGraphicsEffect(shadow)
        self._shadow = shadow
        self.setMinimumWidth(max(72, self.fontMetrics().horizontalAdvance(text) + 34))

    def getHoverProgress(self): return self._hover
    def setHoverProgress(self, value):
        self._hover = float(value)
        self._shadow.setBlurRadius(18 + 9 * self._hover)
        self._shadow.setOffset(0, 4 + 2 * self._hover)
        self.update()
    hoverProgress = Property(float, getHoverProgress, setHoverProgress)

    def getPressProgress(self): return self._press
    def setPressProgress(self, value):
        self._press = float(value)
        self.update()
    pressProgress = Property(float, getPressProgress, setPressProgress)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        self._mouse_pos = None
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self._mouse_pos = event.position().toPoint()
        self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press)
        self._press_anim.setEndValue(1.0)
        self._press_anim.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press)
        self._press_anim.setEndValue(0.0)
        self._press_anim.start()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 3, -2, -4)
        rect.translate(0, -round(self._hover * 2.0 - self._press * 1.5))
        radius = min(22.0, rect.height() / 2.0)
        variant = self.property("bubbleVariant") or "normal"
        colors = {
            "normal": (QColor(245,239,226,82), QColor(94,86,83,190), QColor(39,39,48,230), QColor(255,245,224,150)),
            "primary": (QColor(235,255,215,225), QColor(151,177,105,230), QColor(72,96,54,245), QColor(255,255,225,235)),
            "danger": (QColor(230,170,177,200), QColor(133,75,88,230), QColor(73,40,53,245), QColor(255,214,215,190)),
            "icon": (QColor(245,239,226,95), QColor(95,83,89,190), QColor(37,37,48,235), QColor(255,245,224,175)),
        }
        top, mid, bottom, edge = colors.get(variant, colors["normal"])
        if not self.isEnabled():
            top.setAlpha(35); mid.setAlpha(65); bottom.setAlpha(110); edge.setAlpha(45)
        painter.setPen(QPen(QColor(0,0,0,90), 1))
        painter.setBrush(QColor(10,12,20,65))
        painter.drawRoundedRect(rect.adjusted(0,2,0,2), radius, radius)
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, top)
        grad.setColorAt(.18, QColor(255,255,255,35 + int(35*self._hover)))
        grad.setColorAt(.48, mid)
        grad.setColorAt(1, bottom)
        painter.setPen(QPen(edge, 1.15 + self._hover*.55))
        painter.setBrush(grad)
        painter.drawRoundedRect(rect, radius, radius)
        shine = QRadialGradient(rect.left()+rect.width()*.27, rect.top()+rect.height()*.08, rect.width()*.72)
        shine.setColorAt(0, QColor(255,255,255,105+int(75*self._hover)))
        shine.setColorAt(.35, QColor(255,255,255,25+int(20*self._hover)))
        shine.setColorAt(1, QColor(255,255,255,0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shine)
        painter.drawRoundedRect(rect.adjusted(1,1,-1,-1), radius-1, radius-1)
        if self._mouse_pos is not None and self.underMouse():
            spot = QRadialGradient(self._mouse_pos, max(36, rect.width()*.55))
            spot.setColorAt(0, QColor(255,255,255,95))
            spot.setColorAt(1, QColor(255,255,255,0))
            painter.setBrush(spot)
            painter.drawRoundedRect(rect, radius, radius)
        if self.isChecked():
            painter.setPen(QPen(QColor(239,244,190,220), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(2,2,-2,-2), radius-2, radius-2)
        painter.setPen(QColor(255,250,239,245 if self.isEnabled() else 105))
        painter.setFont(self.font())
        text_rect = rect.adjusted(12,2,-12,-2)
        if self.menu() is not None: text_rect.adjust(0,0,-7,0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())
        if self.menu() is not None:
            cx, cy = rect.right()-12, rect.center().y()+1
            painter.setPen(QPen(QColor(255,250,239,210),1.5))
            painter.drawLine(cx-3,cy-2,cx,cy+1)
            painter.drawLine(cx,cy+1,cx+3,cy-2)
        painter.end()


class SummaryPill(QFrame):
    """Small KPI pill matching the compact summary strip in the reference."""

    def __init__(self, label: str, value: int | str = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BubbleSummaryPill")
        self.setMinimumWidth(142)
        self.setMinimumHeight(39)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 5, 12, 5)
        row.setSpacing(8)
        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("BubbleSummaryValue")
        self.value_label.setMinimumWidth(18)
        self.caption_label = QLabel(label)
        self.caption_label.setObjectName("BubbleSummaryCaption")
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.value_label)
        row.addStretch(1)
        row.addWidget(self.caption_label)

    def set_value(self, value: int | str) -> None:
        self.value_label.setText(str(value))


class LiquidBubbleTopBar(QFrame):
    """Replaceable, all-Python AnimeVault top bar.

    Signals are intentionally semantic rather than coupled to MainWindow, making
    this widget straightforward to reuse or wire to existing handlers.
    """

    category_changed = Signal(str)
    dashboard_requested = Signal()
    recommendations_requested = Signal()
    help_action = Signal(str)
    tools_action = Signal(str)
    upload_action = Signal(str)
    export_action = Signal(str)
    delete_requested = Signal()
    fetch_missing_requested = Signal()
    retry_failed_requested = Signal()
    add_requested = Signal()
    search_changed = Signal(str)
    tier_changed = Signal(str)
    status_changed = Signal(str)
    media_format_changed = Signal(str)
    sort_changed = Signal(str)

    def __init__(
        self,
        *,
        categories: Mapping[str, str] | None = None,
        summary_fields: Sequence[tuple[str, str]] = DEFAULT_SUMMARY_FIELDS,
        tier_options: Iterable[str] = ("All",),
        status_options: Iterable[str] = ("All",),
        format_options: Iterable[str] = ("All",),
        sort_options: Sequence[tuple[str, str]] = (("Title A–Z", "title"),),
        initial_category: str = "anime",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LiquidBubbleTopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.categories = dict(categories or DEFAULT_CATEGORIES)
        self._summary_fields = tuple(summary_fields)
        self._summary_pills: dict[str, SummaryPill] = {}
        self._current_category = initial_category
        self._delete_button: BubbleButton | None = None
        self._retry_button: BubbleButton | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 9)
        root.setSpacing(8)
        self.setMinimumWidth(520)

        root.addWidget(self._build_summary_row())
        root.addWidget(self._build_actions_row())
        root.addWidget(self._build_search_row(
            tier_options=tier_options,
            status_options=status_options,
            format_options=format_options,
            sort_options=sort_options,
        ))

        # Public widget handles for straightforward MainWindow integration.
        # These also allow an incremental migration of existing handlers that
        # already expect the original controls to be present on MainWindow.
        self.summary_pills = self._summary_pills
        self.add_button = self._add_button
        self.search_field = self._search_field
        self.tier_combo = self._tier_combo
        self.status_combo = self._status_combo
        self.format_combo = self._format_combo
        self.sort_combo = self._sort_combo
        self.delete_button = self._delete_button
        self.retry_button = self._retry_button

        self.setStyleSheet(self.styleSheet() + _topbar_qss())
        self.set_category(initial_category)

    # ---- row builders -------------------------------------------------

    def _build_summary_row(self) -> QWidget:
        """Dynamic KPI strip without branding or settings controls.

        KPI labels and values are plain transparent text inside glass capsules.
        Hosts can update values at runtime through set_summary().
        """
        host = QWidget(self)
        host.setObjectName("BubbleSummaryRow")
        row = QHBoxLayout(host)
        row.setContentsMargins(1, 0, 1, 0)
        row.setSpacing(9)

        scroll = QScrollArea(host)
        scroll.setObjectName("BubbleSummaryScroll")
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(48)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("BubbleSummaryContent")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(1, 2, 5, 2)
        layout.setSpacing(8)
        for key, label in self._summary_fields:
            pill = SummaryPill(label, 0, content)
            self._summary_pills[key] = pill
            layout.addWidget(pill)
        layout.addStretch(1)
        scroll.setWidget(content)
        self._summary_scroll = scroll
        row.addWidget(scroll, 1)

        return host

    def _build_actions_row(self) -> QWidget:
        host = QWidget()
        host.setObjectName("BubbleActionsRow")
        row = QHBoxLayout(host)
        row.setContentsMargins(1, 0, 1, 0)
        row.setSpacing(7)

        tools = self._make_menu_button("Tools", [
            ("Library Dashboard", "dashboard"),
            ("Fetch Missing Data", "fetch_missing"),
            ("Refresh Anime Data", "refresh_all"),
            (None, None),
            ("Cloud Sync…", "cloud_sync"),
        ], self.tools_action)
        # Keep the generic tools_action signal while also exposing a dedicated
        # dashboard signal for hosts that want to wire that destination directly.
        if tools.menu() is not None and tools.menu().actions():
            tools.menu().actions()[0].triggered.connect(self.dashboard_requested.emit)
        row.addWidget(tools)

        rec = BubbleButton("🎯  Recommendations", variant="primary", parent=host)
        rec.setMinimumWidth(194)
        rec.clicked.connect(self.recommendations_requested.emit)
        row.addWidget(rec)

        help_button = self._make_menu_button("Help", [
            ("About AnimeVault", "about"),
            ("Documentation (README)", "open_readme"),
        ], self.help_action)
        row.addWidget(help_button)
        row.addSpacing(10)

        upload = self._make_menu_button("⇧  Upload", [
            ("Import Excel (.xlsx)…", "xlsx"),
            ("Import CSV (.csv)…", "csv"),
            ("Import SQL Dump (.sql)…", "sql"),
        ], self.upload_action)
        row.addWidget(upload)

        export = self._make_menu_button("⇩  Export", [
            ("Export to CSV…", "csv"),
            ("Export to Excel (.xlsx)…", "xlsx"),
            ("Export to OpenDocument (.ods)…", "ods"),
            ("Export to SQL Dump…", "sql"),
        ], self.export_action)
        row.addWidget(export)

        delete = BubbleButton("▤  Delete", variant="danger", parent=host)
        delete.setEnabled(False)
        delete.clicked.connect(self.delete_requested.emit)
        self._delete_button = delete
        row.addWidget(delete)

        fetch = BubbleButton("⟳  Fetch Missing Data", variant="normal", parent=host)
        fetch.clicked.connect(self.fetch_missing_requested.emit)
        row.addWidget(fetch)

        retry = BubbleButton("↻  Retry Failed", variant="normal", parent=host)
        retry.setEnabled(False)
        retry.clicked.connect(self.retry_failed_requested.emit)
        self._retry_button = retry
        row.addWidget(retry)
        row.addStretch(1)
        host.adjustSize()
        host.setMinimumWidth(host.sizeHint().width())
        scroll = QScrollArea(self)
        scroll.setObjectName("BubbleActionsScroll")
        scroll.setWidget(host)
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(53)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _build_search_row(
        self,
        *,
        tier_options: Iterable[str],
        status_options: Iterable[str],
        format_options: Iterable[str],
        sort_options: Sequence[tuple[str, str]],
    ) -> QWidget:
        host = QWidget()
        host.setObjectName("BubbleSearchRow")
        row = QHBoxLayout(host)
        row.setContentsMargins(1, 0, 1, 0)
        row.setSpacing(10)

        add = BubbleButton("＋  Add Anime", variant="primary", parent=host)
        add.setMinimumWidth(136)
        add.clicked.connect(self.add_requested.emit)
        self._add_button = add
        row.addWidget(add)

        search = QLineEdit(host)
        search.setObjectName("BubbleSearch")
        search.setPlaceholderText("Search Anime…")
        search.setClearButtonEnabled(True)
        search.setMinimumWidth(220)
        search.setMinimumHeight(42)
        search.textChanged.connect(self.search_changed.emit)
        self._search_field = search
        row.addWidget(search, 1)

        self._tier_combo = self._make_combo(tier_options, "Filter by tier")
        self._tier_combo.currentTextChanged.connect(self.tier_changed.emit)
        row.addWidget(self._tier_combo)

        self._status_combo = self._make_combo(status_options, "Filter by status")
        self._status_combo.currentTextChanged.connect(self.status_changed.emit)
        row.addWidget(self._status_combo)

        self._format_combo = self._make_combo(format_options, "Filter by format")
        self._format_combo.currentTextChanged.connect(self.media_format_changed.emit)
        row.addWidget(self._format_combo)

        sort = QComboBox(host)
        sort.setObjectName("BubbleCombo")
        for label, value in sort_options:
            sort.addItem(label, value)
        sort.setMinimumWidth(150)
        sort.setMaximumWidth(210)
        sort.setMinimumHeight(42)
        sort.setToolTip("Sort order")
        sort.currentIndexChanged.connect(lambda index: self.sort_changed.emit(str(sort.itemData(index) or "title")))
        self._sort_combo = sort
        row.addWidget(sort)
        host.adjustSize()
        host.setMinimumWidth(host.sizeHint().width())
        scroll = QScrollArea(self)
        scroll.setObjectName("BubbleSearchScroll")
        scroll.setWidget(host)
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedHeight(53)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    @staticmethod
    def _make_combo(options: Iterable[str], tooltip: str) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("BubbleCombo")
        values = list(options)
        combo.addItems(values or ["All"])
        combo.setMinimumWidth(118)
        combo.setMaximumWidth(180)
        combo.setMinimumHeight(42)
        combo.setToolTip(tooltip)
        return combo

    def _make_menu_button(
        self,
        label: str,
        entries: Sequence[tuple[str | None, str | None]],
        signal: Signal,
    ) -> QToolButton:
        button = BubbleButton(label, variant="normal", parent=self)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.setObjectName("BubbleMenu")
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        for text, value in entries:
            if text is None:
                menu.addSeparator()
                continue
            action = QAction(text, menu)
            action.triggered.connect(lambda checked=False, item=value: signal.emit(str(item)))
            menu.addAction(action)
        button.setMenu(menu)
        button.setArrowType(Qt.ArrowType.DownArrow)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        button.setMinimumWidth(max(button.sizeHint().width(), self.fontMetrics().horizontalAdvance(label) + 48))
        return button

    # ---- public API ---------------------------------------------------

    def set_category(self, category: str, *, emit: bool = False) -> None:
        """Set the active media type from the host application's existing nav row."""
        if category not in self.categories:
            return
        changed = category != self._current_category
        self._current_category = category
        label = self.categories[category]
        self._add_button.setText(f"＋  Add {label}")
        self._search_field.setPlaceholderText(f"Search {label}…")
        if emit and changed:
            self.category_changed.emit(category)

    def category(self) -> str:
        return self._current_category

    def set_summary(self, values: Mapping[str, int | str]) -> None:
        for key, value in values.items():
            pill = self._summary_pills.get(key)
            if pill is not None:
                pill.set_value(value)

    def set_delete_enabled(self, enabled: bool) -> None:
        if self._delete_button is not None:
            self._delete_button.setEnabled(bool(enabled))

    def set_retry_enabled(self, enabled: bool) -> None:
        if self._retry_button is not None:
            self._retry_button.setEnabled(bool(enabled))

    def set_add_label(self, label: str) -> None:
        self._add_button.setText(label)

    def set_search_text(self, text: str) -> None:
        self._search_field.setText(text)

    def set_filter_options(
        self,
        *,
        tier: Iterable[str] | None = None,
        status: Iterable[str] | None = None,
        media_format: Iterable[str] | None = None,
    ) -> None:
        for combo, values in (
            (self._tier_combo, tier),
            (self._status_combo, status),
            (self._format_combo, media_format),
        ):
            if values is None:
                continue
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(list(values) or ["All"])
            index = combo.findText(current)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)

    def set_filter_values(self, *, tier: str | None = None, status: str | None = None,
                          media_format: str | None = None, sort_value: str | None = None) -> None:
        pairs = ((self._tier_combo, tier), (self._status_combo, status), (self._format_combo, media_format))
        for combo, value in pairs:
            if value is not None:
                combo.blockSignals(True)
                index = combo.findText(value)
                if index >= 0:
                    combo.setCurrentIndex(index)
                combo.blockSignals(False)
        if sort_value is not None:
            self._sort_combo.blockSignals(True)
            index = self._sort_combo.findData(sort_value)
            if index >= 0:
                self._sort_combo.setCurrentIndex(index)
            self._sort_combo.blockSignals(False)


# ---- Styling -----------------------------------------------------------

def _button_qss(variant: str) -> str:
    """Warm translucent glass controls inspired by the Settings reference."""
    common = f"""
    QToolButton {{
        color: {PALETTE['text']};
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(255,255,255,42), stop:0.12 rgba(255,255,255,15),
            stop:0.52 rgba(63,58,58,155), stop:1 rgba(24,27,36,190));
        border: 1px solid rgba(226,215,196,105);
        border-top-color: rgba(255,255,255,175);
        border-radius: 16px; padding: 8px 14px; min-height: 22px;
        font-size: 10pt; font-weight: 650; spacing: 7px;
    }}
    QToolButton:hover {{
        color: white;
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(255,255,255,65), stop:0.25 rgba(185,163,126,75),
            stop:1 rgba(73,54,61,210));
        border-color: rgba(245,231,210,210);
    }}
    QToolButton:pressed, QToolButton:checked {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(213,225,156,115), stop:1 rgba(104,121,57,185));
        border: 2px solid rgba(226,235,173,220); padding: 7px 13px;
    }}
    QToolButton:disabled {{ color: rgba(235,226,215,90); background: rgba(35,32,38,100); border-color: rgba(190,174,157,45); }}
    QToolButton:focus {{ border: 2px solid rgba(222,190,210,220); }}
    """
    if variant == "primary":
        common += """
        QToolButton { color: #fff9e8; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(229,239,174,220),stop:0.16 rgba(174,191,105,220),stop:0.55 rgba(114,132,65,225),stop:1 rgba(64,79,42,235)); border: 1px solid rgba(244,248,204,225); border-top-color: white; font-weight: 750; }
        QToolButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(246,248,202,245),stop:1 rgba(143,163,84,245)); }
        QToolButton:pressed { background: rgba(88,108,52,245); }
        """
    elif variant == "danger":
        common += """
        QToolButton { color: #fff0ed; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(198,139,143,205),stop:0.45 rgba(119,65,76,220),stop:1 rgba(70,39,51,235)); border: 1px solid rgba(240,190,190,180); font-weight: 750; }
        QToolButton:hover { background: rgba(171,91,108,235); border-color: white; }
        QToolButton:disabled { color: rgba(255,225,225,80); background: rgba(88,53,61,100); }
        """
    elif variant == "icon":
        common += "QToolButton { border-radius: 22px; padding: 4px; font-size: 13pt; }"
    return common


def _topbar_qss() -> str:
    p = PALETTE
    return f"""
    QFrame#LiquidBubbleTopBar {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 rgba(82,111,25,218), stop:0.24 rgba(73,82,43,205),
            stop:0.52 rgba(63,55,48,205), stop:0.76 rgba(103,48,65,218), stop:1 rgba(111,35,62,225));
        border: 1px solid rgba(226,218,194,145); border-top: 1px solid rgba(255,255,255,205); border-radius: 23px;
    }}
    QWidget#BubbleBrandRow, QWidget#BubbleActionsRow, QWidget#BubbleSearchRow {{ background: transparent; }}
    QLabel#BubbleBrandMark {{ color: #d8ed9b; font-size: 21px; font-weight: 800; }}
    QLabel#BubbleBrandTitle {{ color: #f0d4ed; font-size: 19px; font-weight: 800; letter-spacing: 0.2px; }}
    QFrame#BubbleSegmentGroup {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,62),stop:0.18 rgba(255,255,255,20),stop:1 rgba(30,28,35,110)); border: 1px solid rgba(238,226,208,155); border-top-color: rgba(255,255,255,210); border-radius: 19px; }}
    QPushButton#BubbleCategoryTab {{ color: rgba(255,245,229,210); background: transparent; border: 1px solid transparent; border-radius: 14px; padding: 7px 17px; min-width: 65px; min-height: 27px; font-size: 10pt; font-weight: 650; }}
    QPushButton#BubbleCategoryTab:hover {{ color: white; background: rgba(255,255,255,38); border: 1px solid rgba(255,255,255,85); }}
    QPushButton#BubbleCategoryTab:checked {{ color: #fffde9; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(235,241,187,135),stop:0.35 rgba(170,184,111,125),stop:1 rgba(72,91,51,175)); border: 1px solid rgba(241,245,200,205); }}
    QScrollArea#BubbleSummaryScroll, QScrollArea#BubbleActionsScroll, QScrollArea#BubbleSearchScroll {{ background: transparent; border: none; }}
    QWidget#BubbleActionsRow, QWidget#BubbleSearchRow {{ background: transparent; }}
    QWidget#BubbleSummaryContent, QWidget#BubbleSummaryRow {{ background: transparent; }}
    QFrame#BubbleSummaryPill {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,47),stop:0.18 rgba(255,255,255,12),stop:0.55 rgba(44,42,43,140),stop:1 rgba(24,26,33,175)); border: 1px solid rgba(224,213,192,120); border-top-color: rgba(255,255,255,180); border-radius: 15px; }}
    QLabel#BubbleSummaryValue {{ color: #e4efa8; background: transparent; border: 0; padding: 0; font-size: 10pt; font-weight: 800; }}
    QLabel#BubbleSummaryCaption {{ color: rgba(255,244,229,225); background: transparent; border: 0; padding: 0; font-size: 9pt; }}
    QLineEdit#BubbleSearch, QComboBox#BubbleCombo {{ color: {p['text']}; background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,48),stop:0.16 rgba(255,255,255,12),stop:1 rgba(31,30,38,165)); border: 1px solid rgba(224,212,196,125); border-top-color: rgba(255,255,255,180); border-radius: 15px; padding: 8px 14px; min-height: 26px; font-size: 10pt; selection-background-color: #78864c; selection-color: white; }}
    QLineEdit#BubbleSearch:focus, QComboBox#BubbleCombo:focus {{ border: 2px solid rgba(232,208,222,225); padding: 7px 13px; }}
    QLineEdit#BubbleSearch::placeholder {{ color: rgba(255,239,224,155); }}
    QComboBox#BubbleCombo::drop-down {{ border: 0; width: 26px; }}
    QComboBox#BubbleCombo QAbstractItemView {{ color: {p['text']}; background: rgba(48,43,48,248); border: 1px solid rgba(231,215,197,180); selection-background-color: rgba(144,151,91,220); selection-color: white; outline: none; padding: 5px; }}
    QMenu#BubbleMenu {{ color: {p['text']}; background: rgba(49,43,45,246); border: 1px solid rgba(231,215,197,190); border-top-color: rgba(255,255,255,205); border-radius: 15px; padding: 7px; font-size: 10pt; }}
    QMenu#BubbleMenu::item {{ padding: 9px 22px; border-radius: 10px; min-width: 205px; }}
    QMenu#BubbleMenu::item:selected {{ color: white; background: rgba(147,157,91,125); border: 1px solid rgba(224,231,170,145); }}
    QMenu#BubbleMenu::separator {{ height: 1px; background: rgba(230,216,196,75); margin: 5px 8px; }}
    QScrollBar:horizontal {{ height: 5px; background: transparent; margin: 0 2px; }}
    QScrollBar::handle:horizontal {{ background: rgba(239,226,205,145); border-radius: 2px; min-width: 25px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


__all__ = ["LiquidBubbleTopBar", "BubbleButton", "SummaryPill", "DEFAULT_CATEGORIES", "DEFAULT_SUMMARY_FIELDS"]
