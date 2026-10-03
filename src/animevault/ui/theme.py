"""Dark theme: colour palette, QSS stylesheet and badge helpers.

Kept in one module so the visual language is defined in a single place
rather than scattered across widgets.  Qt stylesheets cannot express
everything (notably gradients on arbitrary widgets), so the palette is
also exposed as Python constants for custom painting.
"""

from __future__ import annotations

# ── Palette ───────────────────────────────────────────────────────

BG_DEEP = "#0d1117"        # window background
BG_PANEL = "#151b23"       # panels, cards
BG_PANEL_HI = "#1c232d"    # hover / raised
BG_INPUT = "#11161d"       # inputs, search field

BORDER = "#232b36"
BORDER_HI = "#2f3a47"

ACCENT = "#22d3ee"         # cyan — primary accent
ACCENT_DIM = "#0891b2"
ACCENT_DEEP = "#0e7490"

TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#9aa7b4"
TEXT_MUTED = "#6b7784"
TEXT_ON_ACCENT = "#04222a"

DANGER = "#f87171"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"

# ── Tier badge colours (SSS gold → F grey) ───────────────────────

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

# ── Status badge colours ──────────────────────────────────────────

STATUS_COLORS: dict[str, tuple[str, str]] = {
    # status → (background, foreground)
    "watching": ("#0e7490", "#67e8f9"),
    "completed": ("#14532d", "#86efac"),
    "plan_to_watch": ("#1e3a5f", "#93c5fd"),
    "on_hold": ("#713f12", "#fcd34d"),
    "dropped": ("#4c1d1d", "#fca5a5"),
}


def tier_color(tier: str | None) -> str:
    return TIER_COLORS.get((tier or "").upper(), TEXT_MUTED)


def status_colors(status: str) -> tuple[str, str]:
    return STATUS_COLORS.get(status, ("#1f2937", TEXT_SECONDARY))


def tier_badge_style(tier: str | None) -> str:
    """QSS for a tier badge; unassigned gets a muted outline."""
    if not tier:
        return (
            f"background:transparent; border:1px solid {BORDER_HI};"
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


# ── Application stylesheet ────────────────────────────────────────

def build_stylesheet() -> str:
    """Return the application-wide Qt stylesheet."""
    return f"""
QWidget {{
    background-color: {BG_DEEP};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13pt;
}}

QMainWindow, QDialog {{ background-color: {BG_DEEP}; }}

/* ── Header ─────────────────────────────────────────────── */
#headerBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER};
}}
#appTitle {{
    font-size: 18pt;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
#appIcon {{
    font-size: 20pt;
    color: {ACCENT};
}}

/* ── Nav tabs ───────────────────────────────────────────── */
QPushButton#navTab {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 16px;
    color: {TEXT_SECONDARY};
    font-weight: 600;
}}
QPushButton#navTab:hover {{
    background: {BG_PANEL_HI};
    color: {TEXT_PRIMARY};
}}
QPushButton#navTab:checked {{
    background: {ACCENT};
    color: {TEXT_ON_ACCENT};
    border: 1px solid {ACCENT};
}}

/* ── Secondary toolbar ──────────────────────────────────── */
#toolBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER};
}}
QPushButton#toolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px 12px;
    color: {TEXT_SECONDARY};
    font-weight: 500;
}}
QPushButton#toolButton:hover {{
    background: {BG_PANEL_HI};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HI};
}}
QPushButton#dangerButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px 12px;
    color: {DANGER};
    font-weight: 500;
}}
QPushButton#dangerButton:hover {{
    background: rgba(248, 113, 113, 0.14);
    border: 1px solid {DANGER};
}}
QPushButton#dangerButton:disabled {{
    color: {TEXT_MUTED};
    background: transparent;
    border: 1px solid transparent;
}}

/* ── Primary action ─────────────────────────────────────── */
QPushButton#primaryButton {{
    background: {ACCENT};
    color: {TEXT_ON_ACCENT};
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{ background: #3ddcf3; }}
QPushButton#primaryButton:pressed {{ background: {ACCENT_DIM}; }}

/* ── Search ─────────────────────────────────────────────── */
QLineEdit#searchField {{
    background: {BG_INPUT};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 9px 14px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit#searchField:focus {{
    border: 1px solid {ACCENT};
    background: {BG_PANEL};
}}
QLineEdit#searchField::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── Filter / type / sort combos ────────────────────────── */
QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER_HI};
    border-radius: 8px;
    padding: 8px 12px;
    color: {TEXT_PRIMARY};
    min-width: 92px;
}}
QComboBox:hover {{ border: 1px solid {ACCENT_DIM}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {BG_PANEL};
    border: 1px solid {BORDER_HI};
    selection-background-color: {ACCENT_DIM};
    color: {TEXT_PRIMARY};
    outline: none;
}}

/* ── Cards ──────────────────────────────────────────────── */
QFrame#mediaCard {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#mediaCard:hover {{
    border: 1px solid {ACCENT_DIM};
    background: {BG_PANEL_HI};
}}
QFrame#mediaCard[selected="true"] {{
    border: 2px solid {ACCENT};
    background: {BG_PANEL_HI};
}}
#cardTitle {{
    font-size: 13pt;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
#cardMeta {{
    font-size: 11pt;
    color: {TEXT_SECONDARY};
}}
#cardProgressText {{
    font-size: 10pt;
    color: {TEXT_MUTED};
}}
#sectionHeader {{
    font-size: 15pt;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
#sectionCount {{
    font-size: 12pt;
    color: {TEXT_MUTED};
}}

/* ── Progress bar ───────────────────────────────────────── */
QProgressBar {{
    background: {BG_INPUT};
    border: none;
    border-radius: 3px;
    height: 5px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ── Sidebar ────────────────────────────────────────────── */
#sidebar {{
    background: {BG_PANEL};
    border-left: 1px solid {BORDER};
}}
#panelTitle {{
    font-size: 13pt;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
#statLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12pt;
}}
#statValue {{ color: {TEXT_PRIMARY}; font-size: 13pt; font-weight: 700; }}
#statDot {{ font-size: 12pt; }}

/* ── Scrollbars ─────────────────────────────────────────── */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_HI};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #3d4a59; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_HI};
    border-radius: 5px;
    min-width: 30px;
}}

/* ── Inputs in dialogs ──────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER_HI};
    border-radius: 7px;
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLabel#formLabel {{ color: {TEXT_SECONDARY}; font-weight: 600; }}
QLabel#sectionLabel {{
    color: {ACCENT};
    font-size: 11pt;
    font-weight: 700;
}}

QCheckBox {{ color: {TEXT_SECONDARY}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER_HI};
    border-radius: 4px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {BG_PANEL};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SECONDARY};
    padding: 8px 16px;
    border: none;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}

QToolTip {{
    background: {BG_PANEL_HI};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HI};
    padding: 5px;
    border-radius: 5px;
}}

QMenu {{
    background: {BG_PANEL_HI};
    border: 1px solid {BORDER_HI};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{
    padding: 7px 22px 7px 14px;
    border-radius: 5px;
    color: {TEXT_PRIMARY};
}}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::separator {{
    height: 1px;
    background: {BORDER_HI};
    margin: 4px 8px;
}}

QMessageBox, QInputDialog {{ background: {BG_PANEL}; }}
QProgressDialog {{ background: {BG_PANEL}; }}
"""