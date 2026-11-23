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
BG_DEEP = "#0a0c10"            # main background: near-black graphite
BG_SURFACE = "#0f1118"         # primary surface (cards, panels, dialogs)
BG_PANEL = BG_SURFACE          # primary panel surface (alias of BG_SURFACE)
BG_SURFACE_HI = "#161c28"      # raised/recessed highlight (neumorphic)
BG_INPUT = "#08090e"           # frosted input field
BG_SCROLL = "#0d0f16"          # scrollable content background

# Borders (thin, low-contrast)
BORDER = "#2b3140"             # default border
BORDER_HOVER = "#3c4455"       # border highlight (hover)
BORDER_GLASS = "#36404f"       # translucent glass border

# Accent (cyan/teal primary; violet secondary, used sparingly)
ACCENT = "#2dd4bf"             # primary cyan/teal
ACCENT_DIM = "#14b8a6"         # dimmed cyan
ACCENT_DEEP = "#0d9488"        # deep teal
ACCENT_VIOLET = "#8b5cf6"      # secondary violet
ACCENT_VIOLET_DIM = "#7c3aed"  # dimmed violet

# Text
TEXT_PRIMARY = "#f1f5f9"       # soft white
TEXT_SECONDARY = "#94a3b8"     # muted grey-blue
TEXT_MUTED = "#64748b"         # secondary muted
TEXT_ON_ACCENT = "#06121f"     # near-black on bright accent

# Semantic (accessible)
DANGER = "#ef4444"
SUCCESS = "#22c55e"
WARNING = "#eab308"

# ── Tier badge colours (fixed design tokens; not theme-selectable) ───
TIER_COLORS: dict[str, str] = {
    "SSS": "#f0b429",
    "SS": "#fb923c",
    "S": "#facc15",
    "A": "#4ade80",
    "B": "#22d3ee",
    "C": "#60a5fa",
    "D": "#a78bfa",
    "E": "#94a3b8",
    "F": "#64748b",
}

# ── Status badge colours (fixed design tokens; not theme-selectable) ──
STATUS_COLORS: dict[str, tuple[str, str]] = {
    # status → (background, foreground)
    "watching": ("#0e7490", "#67e8f9"),
    "completed": ("#14532d", "#86efac"),
    "plan_to_watch": ("#1e3a5f", "#93c5fd"),
    "on_hold": ("#713f12", "#fcd34d"),
    "dropped": ("#4c1d1d", "#fca5a5"),
}


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
