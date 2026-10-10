"""Central theme registry, runtime theme manager, QSS and badge helpers.

Theme colors stay in this module so existing UI imports remain compatible.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeDefinition:
    id: str
    name: str
    category: str
    description: str
    background: str
    panel: str
    panel_hover: str
    input: str
    border: str
    border_hover: str
    accent: str
    accent_dim: str
    accent_deep: str
    text: str
    text_secondary: str
    text_muted: str
    text_on_accent: str
    danger: str = "#f87171"
    success: str = "#4ade80"
    warning: str = "#fbbf24"


# Stable IDs are suitable for QSettings and future user-defined theme files.
_THEME_ROWS = [
    ("minimal-simple", "Minimal Simple", "CORE", "Clean, restrained dark surfaces.", "#111318", "#181b21", "#20242c", "#15181e", "#2b303a", "#3a414d", "#4f8cff", "#3975df", "#285bb8", "#f5f7fa", "#b5bdc8", "#818a97", "#ffffff"),
    ("minimal-light", "Minimal Light", "CORE", "Bright neutral surfaces and clear blue accents.", "#f5f6f8", "#ffffff", "#edf0f4", "#f8f9fb", "#d9dee7", "#b8c1cf", "#2878e5", "#1e63c2", "#174e9b", "#202632", "#505b6b", "#707b8a", "#ffffff"),
    ("amoled-dark", "AMOLED Dark", "CORE", "Near-black OLED-friendly surfaces.", "#000000", "#08090b", "#121417", "#070809", "#202329", "#333841", "#5b91ff", "#3f70d4", "#2c55a9", "#f5f7fa", "#adb4bf", "#727a86", "#ffffff"),
    ("anime-night", "Anime Night", "ANIME", "Midnight navy with cool blue highlights.", "#101326", "#191d36", "#24294a", "#14182d", "#303657", "#444d78", "#7c83ff", "#5d63d8", "#454bb3", "#f2f2ff", "#b4b8d6", "#858bad", "#ffffff"),
    ("japanese-sunset", "Japanese Sunset", "ANIME", "Dusk purple balanced with warm sunset orange.", "#171424", "#241d32", "#33263d", "#1c1729", "#40344c", "#59465e", "#ff9a62", "#df7545", "#b45734", "#fff4ee", "#d1b9bd", "#a48d9a", "#241424"),
    ("forest-shrine", "Forest Shrine", "ANIME", "Deep forest greens and muted natural tones.", "#101813", "#19241c", "#243329", "#141d17", "#2d3d31", "#405644", "#8daf72", "#6b9255", "#4e713d", "#eff5eb", "#b7c5b1", "#879883", "#142015"),
    ("sakura-blue", "Sakura Blue", "ANIME", "Blue night surfaces with soft sakura pink.", "#101827", "#192438", "#24324a", "#141f30", "#2d3b52", "#40536f", "#f09ac8", "#d273a7", "#ad5489", "#f5f6ff", "#c0c8dd", "#909bb5", "#271824"),
    ("sakura-light", "Sakura Light", "ANIME", "Elegant white, blush and pale blue.", "#fbf8fc", "#ffffff", "#f6edf6", "#fbf9fc", "#e8dce9", "#d6c3da", "#c45d9b", "#a94782", "#873669", "#302634", "#665b6b", "#887c8d", "#ffffff"),
    ("moonlight-glass", "Moonlight Glass", "GLASS", "Cool moonlit blues with layered surfaces.", "#101828", "#19263a", "#24354b", "#142033", "#344761", "#4b6686", "#8cc8ff", "#67a9e4", "#4888c4", "#f2f7ff", "#bdcce0", "#8b9bb2", "#142033"),
    ("sunset-glass", "Sunset Glass", "GLASS", "Warm rose, violet and amber accents.", "#21172a", "#302039", "#422a49", "#271b31", "#503b59", "#6c4c72", "#ff9b8e", "#e67878", "#c35b67", "#fff3f3", "#d8bdcf", "#a990a7", "#2b1b2b"),
    ("cyber-anime", "Cyber Anime", "GLASS", "Dark library surfaces with restrained neon accents.", "#10121d", "#191c2b", "#252a3c", "#141725", "#34384d", "#4e5470", "#ff4f87", "#d73672", "#aa2357", "#f7f5ff", "#c2bfd6", "#918ea8", "#ffffff"),
    ("warm-library", "Warm Library", "SPECIAL", "Parchment cream and archival brown.", "#211d18", "#302920", "#40372b", "#27221c", "#4d4133", "#645442", "#d6ad68", "#b58b4a", "#8d6935", "#f8f0df", "#d0c0a6", "#a9967b", "#251d12"),
    ("one-piece", "One Piece-inspired", "SPECIAL", "Nautical parchment, ocean blue and warm gold.", "#17202a", "#222d36", "#303d46", "#1d2831", "#394954", "#506472", "#e4b95e", "#c69639", "#9d7428", "#f7f1e5", "#c7c2b4", "#969184", "#282114"),
    ("nyarch", "Nyarch-inspired", "SPECIAL", "Aubergine surfaces with pastel pink and lavender.", "#1a1423", "#261d32", "#362743", "#201829", "#443650", "#5c496c", "#f29bd8", "#d477bc", "#b15898", "#faf2ff", "#d1bfdc", "#a590b4", "#281b2b"),
    ("ubuntu", "Ubuntu-inspired", "SPECIAL", "Aubergine and orange in a warm desktop palette.", "#1b111b", "#291b29", "#38243a", "#211722", "#473447", "#604960", "#f28c28", "#d66b19", "#ad4f12", "#f7eef7", "#cbbdca", "#9b8c9b", "#281708"),
    ("arch-linux", "Arch Linux-inspired", "SPECIAL", "Technical dark navy with Arch-blue highlights.", "#101820", "#192630", "#243541", "#141e27", "#2d414e", "#425d6c", "#1793d1", "#1176aa", "#0d5b85", "#eef7fc", "#b6c9d3", "#849aa6", "#ffffff"),
    ("kali-linux", "Kali Linux-inspired", "SPECIAL", "Graphite and dark navy with cool blue accents.", "#11151b", "#1b222c", "#283341", "#151b23", "#303b48", "#465665", "#4da3ff", "#3181d3", "#2463a6", "#f1f5fa", "#b7c2cf", "#8793a1", "#ffffff"),
    ("nvidia-green", "NVIDIA Green-inspired", "SPECIAL", "Black graphite with vivid green highlights.", "#0d0f0e", "#171a18", "#222724", "#121513", "#2b332e", "#414d46", "#76b900", "#5e9500", "#477100", "#f2f5f2", "#bac4bc", "#87938a", "#11180a"),
]
THEMES: dict[str, ThemeDefinition] = {
    row[0]: ThemeDefinition(*row) for row in _THEME_ROWS
}
DEFAULT_THEME_ID = "minimal-simple"

# Existing constant imports remain source-compatible. ThemeManager updates
# these module attributes when switching; QSS is generated from the same tokens.
BG_DEEP = "#111318"
BG_PANEL = "#181b21"
BG_PANEL_HI = "#20242c"
BG_INPUT = "#15181e"
BORDER = "#2b303a"
BORDER_HI = "#3a414d"
ACCENT = "#4f8cff"
ACCENT_DIM = "#3975df"
ACCENT_DEEP = "#285bb8"
TEXT_PRIMARY = "#f5f7fa"
TEXT_SECONDARY = "#b5bdc8"
TEXT_MUTED = "#818a97"
TEXT_ON_ACCENT = "#ffffff"
DANGER = "#f87171"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
_ACTIVE_THEME = THEMES[DEFAULT_THEME_ID]
_REDUCE_EFFECTS = False


def _activate_tokens(theme: ThemeDefinition) -> None:
    global BG_DEEP, BG_PANEL, BG_PANEL_HI, BG_INPUT, BORDER, BORDER_HI
    global ACCENT, ACCENT_DIM, ACCENT_DEEP, TEXT_PRIMARY, TEXT_SECONDARY
    global TEXT_MUTED, TEXT_ON_ACCENT, DANGER, SUCCESS, WARNING, _ACTIVE_THEME
    BG_DEEP, BG_PANEL, BG_PANEL_HI, BG_INPUT = theme.background, theme.panel, theme.panel_hover, theme.input
    BORDER, BORDER_HI = theme.border, theme.border_hover
    ACCENT, ACCENT_DIM, ACCENT_DEEP = theme.accent, theme.accent_dim, theme.accent_deep
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED = theme.text, theme.text_secondary, theme.text_muted
    TEXT_ON_ACCENT = theme.text_on_accent
    DANGER, SUCCESS, WARNING = theme.danger, theme.success, theme.warning
    _ACTIVE_THEME = theme


class ThemeManager(QObject):
    """Applies shared QSS themes and stores preferences in QSettings."""
    theme_changed = Signal(str)
    effects_changed = Signal(bool)
    _instance = None

    def __init__(self, app: QApplication | None = None):
        super().__init__()
        self.app = app or QApplication.instance()
        self.settings = QSettings("AnimeVault", "AnimeVault")
        self.theme_id = DEFAULT_THEME_ID

    @classmethod
    def instance(cls, app: QApplication | None = None) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls(app)
        elif app is not None:
            cls._instance.app = app
        return cls._instance

    def restore(self) -> str:
        saved = self.settings.value("appearance/theme_id", DEFAULT_THEME_ID, type=str)
        return self.apply_theme(saved, persist=False)

    def apply_theme(self, theme_id: str, *, persist: bool = True) -> str:
        """Apply a registered theme; unknown IDs safely select Minimal Simple."""
        theme = THEMES.get(theme_id, THEMES[DEFAULT_THEME_ID])
        _activate_tokens(theme)
        self.theme_id = theme.id
        if self.app is None:
            self.app = QApplication.instance()
        if self.app is not None:
            self.app.setStyleSheet(build_stylesheet())
        if persist:
            self.settings.setValue("appearance/theme_id", theme.id)
            self.settings.sync()
        self.theme_changed.emit(theme.id)
        return theme.id

    @property
    def active_theme(self) -> ThemeDefinition:
        return THEMES.get(self.theme_id, THEMES[DEFAULT_THEME_ID])

    @property
    def reduce_effects(self) -> bool:
        return self.settings.value("appearance/reduce_effects", False, type=bool)

    def set_reduce_effects(self, enabled: bool) -> None:
        global _REDUCE_EFFECTS
        _REDUCE_EFFECTS = bool(enabled)
        self.settings.setValue("appearance/reduce_effects", _REDUCE_EFFECTS)
        self.settings.sync()
        if self.app is None:
            self.app = QApplication.instance()
        if self.app is not None:
            self.app.setStyleSheet(build_stylesheet())
        self.effects_changed.emit(_REDUCE_EFFECTS)



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
QPushButton#primaryButton:hover {{ background: {ACCENT_DIM}; }}
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
    background: {BG_PANEL if _REDUCE_EFFECTS else BG_PANEL_HI};
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
/* Let the window's video background show through the card area. */
#gridHost {{ background: transparent; }}
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
QScrollBar::handle:vertical:hover {{ background: {BORDER_HI}; }}
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