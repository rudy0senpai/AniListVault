"""Central design tokens + appearance preferences (single design system).

THIS MODULE REPLACES THE FORMER 26-THEME REGISTRY.  There is exactly one
design system; it is not selectable and not theme-dependent.  The application
keeps user preferences (Reduce Effects, 3D Liquid Glass) that are stored in
QSettings, but there is no palette-switching UI and no per-theme stylesheet.

Consumers import tokens as::

    from animevault.ui.theme import (BG_DEEP, BG_PANEL, ACCENT, TEXT_PRIMARY, ...)
    import animevault.ui.theme as theme_tokens

Tokens are fixed constants (never swapped at runtime) and single-sourced.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

# ── ───────────────────────────── design tokens ───────────────────────────

# Backgrounds & surfaces
BG_DEEP = "#0a0c10"            # graphite base keeps poster artwork vivid
BG_SURFACE = "#121722"         # lifted card and panel surface
BG_PANEL = BG_SURFACE          # primary panel surface (alias of BG_SURFACE)
BG_SURFACE_HI = "#1a2230"      # raised/recessed highlight
BG_INPUT = "#0e121a"           # inset field surface
BG_SCROLL = "#0d1119"          # scrollable content background
GLASS_SURFACE = "rgba(18, 23, 34, 232)"
GLASS_SURFACE_HOVER = "rgba(27, 34, 47, 242)"

# Borders (clear enough to separate glass layers without hard contrast)
BORDER = "#303b4c"             # default border
BORDER_HOVER = "#4b5870"       # hover highlight
BORDER_GLASS = "#48566a"       # glass panel edge

# Accent (pastel cyan/teal primary; violet secondary)
ACCENT = "#a3eee2"             # primary pastel mint/cyan
ACCENT_DIM = "#78d8cb"         # subdued mint for secondary use
ACCENT_DEEP = "#4db7ae"        # deeper mint for emphasis
ACCENT_VIOLET = "#c7b6ff"      # secondary pastel violet
ACCENT_VIOLET_DIM = "#a690f2"  # deeper violet
ACCENT_SKY = "#b9e4ff"         # cool supporting accent
ACCENT_PINK = "#f3bfdc"        # warm supporting accent
ACCENT_AMBER = "#ffe3a3"       # warm KPI accent
GRADIENT_CENTRE = "#f5f2ff"    # radial text highlight
GRADIENT_EDGE = "#8f73d8"        # deeper violet for a visible radial falloff

# Text
TEXT_PRIMARY = "#f4f6fb"       # bright neutral text
TEXT_SECONDARY = "#b4c0d3"     # readable muted blue-grey
TEXT_MUTED = "#8a98ad"         # secondary muted text
TEXT_ON_ACCENT = "#10202a"     # deep graphite on pastel controls

# Semantic (pastel, with distinct dark surfaces)
DANGER = "#ff9ca8"
SUCCESS = "#a7e7b6"
WARNING = "#f6db95"

# ── Tier badge colours (fixed design tokens; not theme-selectable) ───
TIER_COLORS: dict[str, str] = {
    "SSS": "#ffd98a",
    "SS": "#ffbd8f",
    "S": "#f7e7a5",
    "A": "#aee7bd",
    "B": "#9ee8ef",
    "C": "#a6ccff",
    "D": "#c9b5ff",
    "E": "#b6c0cc",
    "F": "#8d99ab",
}

# ── Status badge colours (fixed design tokens; not theme-selectable) ──
STATUS_COLORS: dict[str, tuple[str, str]] = {
    # status → (background, foreground)
    "watching": ("#163e4b", "#a5e9f5"),
    "completed": ("#1b3e2c", "#afe9c1"),
    "plan_to_watch": ("#1c3455", "#b5d5ff"),
    "on_hold": ("#4a3a1a", "#f7dd9a"),
    "dropped": ("#4b272d", "#ffbbc2"),
}



def application_stylesheet() -> str:
    """Return the single dark-glass stylesheet used by the desktop window."""
    return f"""
    QWidget {{
        color: {TEXT_PRIMARY};
        font-size: 10pt;
    }}
    QMainWindow, QDialog {{ background-color: {BG_DEEP}; }}
    QWidget#centralWidget, QWidget#libraryPage, QStackedWidget#mainStack,
    QScrollArea#cardGrid, QScrollArea#overviewScroll, QWidget#gridHost,
    QWidget#qt_scrollarea_viewport {{ background: transparent; border: none; }}
    #headerBar, #toolBar, #searchRow {{
        background-color: {GLASS_SURFACE};
        border-bottom: 1px solid rgba(72, 86, 106, 170);
    }}
    QLabel#appIcon {{ color: {ACCENT_VIOLET}; font-size: 23px; font-weight: 700; }}
    QLabel#appTitle {{ font-size: 22px; font-weight: bold; }}
    QLabel#panelTitle, QLabel#settingsTitle {{ color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700; }}
    QPushButton {{
        color: {TEXT_PRIMARY};
        background-color: rgba(27, 34, 47, 224);
        border: 1px solid {BORDER};
        border-radius: 9px;
        padding: 5px 10px;
    }}
    QPushButton:hover {{ background-color: rgba(47, 58, 77, 238); border-color: {BORDER_HOVER}; }}
    QPushButton:pressed {{ background-color: {BG_SURFACE_HI}; border-color: {ACCENT_DIM}; }}
    QPushButton:disabled {{ color: {TEXT_MUTED}; background-color: rgba(20, 24, 32, 180); }}
    QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {ACCENT_VIOLET}; }}
    QPushButton#navTab {{ background: transparent; border-color: transparent; color: {TEXT_SECONDARY}; padding: 5px 12px; }}
    QPushButton#navTab:hover {{ background: rgba(255, 255, 255, 14); color: {TEXT_PRIMARY}; }}
    QPushButton#navTab:checked {{
        color: {ACCENT}; background: rgba(163, 238, 226, 24);
        border: 1px solid rgba(163, 238, 226, 90);
    }}
    QPushButton#primaryButton {{
        color: {TEXT_ON_ACCENT}; background-color: {ACCENT};
        border: 1px solid {ACCENT_DIM}; font-weight: 700;
    }}
    QPushButton#primaryButton:hover {{ background-color: #baf5ec; border-color: #c7fff5; }}
    QPushButton#primaryButton:pressed {{ background-color: {ACCENT_DEEP}; color: #07171b; }}
    QPushButton#dangerButton {{ color: #2a1117; background-color: {DANGER}; border-color: #ffc2ca; font-weight: 700; }}
    QPushButton#settingsButton {{ border-radius: 20px; padding: 0; }}
    QLineEdit, QComboBox {{
        color: {TEXT_PRIMARY}; background-color: {BG_INPUT};
        border: 1px solid {BORDER}; border-radius: 9px; padding: 6px 10px; min-height: 26px;
        selection-background-color: {ACCENT_DEEP}; selection-color: #07171b;
    }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{
        color: {TEXT_PRIMARY}; background-color: {BG_SURFACE};
        border: 1px solid {BORDER_GLASS}; selection-background-color: rgba(163, 238, 226, 36);
        selection-color: {ACCENT}; outline: 0;
    }}
    QMenu {{ color: {TEXT_PRIMARY}; background-color: {BG_SURFACE}; border: 1px solid {BORDER_GLASS}; padding: 5px; }}
    QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
    QMenu::item:selected {{ color: {TEXT_PRIMARY}; background-color: rgba(163, 238, 226, 30); }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {BORDER_HOVER}; border-radius: 4px; min-height: 26px; }}
    QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QProgressBar {{ background-color: {BG_INPUT}; border: 0; border-radius: 3px; }}
    QProgressBar::chunk {{ background-color: {ACCENT_DIM}; border-radius: 3px; }}
    QToolTip {{ color: {TEXT_PRIMARY}; background-color: {BG_SURFACE}; border: 1px solid {BORDER_GLASS}; padding: 5px 8px; }}
    """


def tier_color(tier: str | None) -> str:
    """Return the fixed colour for a content tier."""
    return TIER_COLORS.get((tier or "").upper(), TEXT_MUTED)


def status_colors(status: str) -> tuple[str, str]:
    """Return the (background, foreground) colour pair for a status."""
    return STATUS_COLORS.get(status, ("#1f2937", TEXT_SECONDARY))


def tier_badge_style(tier: str | None) -> str:
    """QSS for a tier badge; unassigned gets a muted outline."""
    if not tier:
        return (
            f"background:transparent; border:1px solid {BORDER_HOVER};"
            f" color:{TEXT_MUTED}; border-radius:9px;"
            " padding:1px 8px; font-size: 10pt; font-weight:700;"
        )
    c = tier_color(tier)
    return (
        f"background:{c}; color:{TEXT_ON_ACCENT}; border-radius:9px;"
        "padding:1px 8px; font-size: 10pt; font-weight:700;"
    )


def status_badge_style(status: str) -> str:
    bg, fg = status_colors(status)
    return (
        f"background:{bg}; color:{fg}; border-radius:9px;"
        "padding:1px 8px; font-size: 10pt; font-weight:600;"
    )

# ── Accessibility & appearance preferences (QSettings-backed) ───────────
# Retained from the old manager.  These are user preferences, NOT themes:
# they survive theme retirement and keep Reduce Effects + Liquid Glass working.


def _settings(app: QObject | None) -> QSettings:
    if app is None:
        app = QApplication.instance()
    return QSettings("AnimeVault", "AnimeVault")


def reduce_effects(app: QObject | None = None) -> bool:
    """Read the Reduce Effects preference (user setting, not a theme)."""
    return bool(_settings(app).value("appearance/reduce_effects", False, type=bool))


def set_reduce_effects(value: bool, app: QObject | None = None) -> None:
    _settings(app).setValue("appearance/reduce_effects", bool(value))
    _settings(app).sync()


def liquid_glass(app: QObject | None = None) -> bool:
    """Read the 3D Liquid Glass preference (user setting, not a theme)."""
    return bool(_settings(app).value("appearance/liquid_glass", False, type=bool))


def set_liquid_glass(value: bool, app: QObject | None = None) -> None:
    _settings(app).setValue("appearance/liquid_glass", bool(value))
    _settings(app).sync()
