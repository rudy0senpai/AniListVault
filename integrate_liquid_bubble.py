#!/usr/bin/env python3
from __future__ import annotations
import ast, re, shutil
from datetime import datetime
from pathlib import Path

ROOT=Path.cwd()
UI=ROOT/"src"/"animevault"/"ui"
MAIN=UI/"main_window.py"
COMPONENT=Path(__file__).with_name("liquid_bubble_topbar.py")
if not MAIN.is_file() or not COMPONENT.is_file():
    raise SystemExit("Run from AniListVault root with liquid_bubble_topbar.py beside this script.")
source=MAIN.read_text(encoding="utf-8")
ast.parse(source)
for marker in ("def _build_ui(self)", "def _build_header(self)", "def _build_toolbar(self)",
               "def _build_search_row(self)", "def _update_header_summary(self, animes, literature)"):
    if marker not in source:
        raise SystemExit(f"Repository source mismatch: {marker}")
backup=MAIN.with_name("main_window.py.before-liquid-bubble-"+datetime.now().strftime("%Y%m%d-%H%M%S")+".bak")
shutil.copy2(MAIN,backup)
shutil.copy2(COMPONENT,UI/"liquid_bubble_topbar.py")

def replace_method(text, name, replacement):
    pat=re.compile(rf"(?ms)^    def {re.escape(name)}\b.*?(?=^    def |\Z)")
    result,count=pat.subn(replacement.rstrip()+"\n\n",text,count=1)
    if count!=1: raise RuntimeError(f"Cannot replace {name}")
    return result

imp="from animevault.ui.liquid_bubble_topbar import LiquidBubbleTopBar"
if imp not in source:
    anchor="from animevault.ui.settings_panel import SettingsPanel"
    if anchor not in source: raise SystemExit("Import anchor missing")
    source=source.replace(anchor,anchor+"\n"+imp,1)

header='''    def _build_header(self) -> QWidget:
        # Keep the host-owned AnimeVault brand/category/settings row.
        header = QWidget()
        header.setObjectName("headerBar")
        header.setFixedHeight(50)
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 5, 18, 5)
        row.setSpacing(12)
        icon = QLabel("◐")
        icon.setObjectName("appIcon")
        row.addWidget(icon)
        title = RadialGradientLabel("AnimeVault")
        title.setObjectName("appTitle")
        row.addWidget(title)
        row.addSpacing(10)
        self._nav_buttons: dict[str, QPushButton] = {}
        for category in (MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA):
            button = QPushButton(CATEGORY_LABELS[category])
            button.setObjectName("navTab")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, c=category: self._on_category_changed(c))
            self._nav_buttons[category] = button
            row.addWidget(button)
        self._nav_buttons[self._category].setChecked(True)
        row.addStretch(1)
        settings = QPushButton("⚙")
        settings.setObjectName("settingsButton")
        settings.setFixedSize(38, 38)
        settings.setToolTip("Settings")
        settings.clicked.connect(self._show_settings_panel)
        row.addWidget(settings)
        return header
'''
toolbar='''    def _build_toolbar(self) -> QWidget:
        # Native PySide6 Bubble toolbar; no duplicate legacy toolbar/search widgets.
        topbar = LiquidBubbleTopBar(
            tier_options=["All", *list(TIERS), "Unassigned"],
            status_options=["All", *list(VALID_STATUSES)],
            format_options=type_options(self._category),
            sort_options=SORT_OPTIONS,
            initial_category=self._category,
            parent=self,
        )
        self._topbar = topbar
        self._summary_kpis = topbar.summary_pills
        self._add_button = topbar.add_button
        self._search_field = topbar.search_field
        self._filter_combo = topbar.tier_combo
        self._status_combo = topbar.status_combo
        self._type_combo = topbar.format_combo
        self._sort_combo = topbar.sort_combo
        self._delete_button = topbar.delete_button
        self._retry_failed_button = topbar.retry_button
        self._select_button = None

        topbar.recommendations_requested.connect(self._show_recommendations)
        topbar.dashboard_requested.connect(self._show_dashboard)
        topbar.add_requested.connect(self._on_add)
        topbar.delete_requested.connect(self._on_delete_selected)
        topbar.fetch_missing_requested.connect(lambda: self._on_bulk_enrich(False))
        topbar.retry_failed_requested.connect(self._retry_failed_enrichment)

        topbar.help_action.connect(
            lambda action: self._show_about() if action == "about" else
            self._show_readme() if action == "open_readme" else None
        )
        topbar.upload_action.connect(
            lambda kind: self._on_import_xlsx() if kind == "xlsx" else
            self._on_import_csv() if kind == "csv" else
            self._on_import_sql() if kind == "sql" else None
        )
        topbar.export_action.connect(
            lambda kind: self._on_export(kind) if kind in {"csv", "xlsx", "ods", "sql"} else None
        )

        def handle_tool_action(action: str) -> None:
            # The dashboard has a dedicated signal to avoid opening twice.
            actions = {
                "fetch_missing": lambda: self._on_bulk_enrich(False),
                "refresh_all": lambda: self._on_bulk_enrich(True),
                "cloud_sync": self._on_cloud_sync,
            }
            callback = actions.get(action)
            if callback is not None:
                callback()
        topbar.tools_action.connect(handle_tool_action)

        topbar.search_changed.connect(self._on_search_changed)
        topbar.tier_changed.connect(self._on_filter_tier_changed)
        topbar.status_changed.connect(self._on_filter_status_changed)
        topbar.media_format_changed.connect(self._on_filter_type_changed)
        topbar.sort_changed.connect(
            lambda value: self._on_sort_changed(self._sort_combo.findData(value))
        )
        topbar.set_category(self._category)
        return topbar
'''
navbar='''    def _build_navbar(self) -> QWidget:
        # Category navigation is owned by the existing native MainWindow header.
        placeholder = QWidget()
        placeholder.setFixedHeight(0)
        return placeholder
'''
search='''    def _build_search_row(self) -> QWidget:
        # Search and filters are integrated into LiquidBubbleTopBar.
        placeholder = QWidget()
        placeholder.setFixedHeight(0)
        return placeholder
'''
toggle='''    def _toggle_selection_mode(self) -> None:
        # Selection mode remains available to existing card/bridge workflows,
        # but there is deliberately no visible Select control in this toolbar.
        self._select_mode = not self._select_mode
        if self._web_view is not None:
            self._web_view.bridge.setSelectionMode(self._select_mode)
            self._delete_button.setEnabled(False)
        else:
            self._on_select_toggled(self._select_mode)
'''
summary='''    def _update_header_summary(self, animes, literature) -> None:
        # Populate KPI values from real model records on every refresh.
        statuses = Counter(str(getattr(item, "status", "") or "").casefold() for item in animes)
        counts = Counter(str(getattr(item, "category", "") or "").casefold() for item in literature)
        values = {
            "anime_total": len(animes),
            "anime_watching": statuses["watching"],
            "anime_completed": statuses["completed"],
            "anime_planned": statuses["plan_to_watch"],
            "manga_total": counts[MEDIA_MANGA],
            "manhwa_total": counts[MEDIA_MANHWA],
            "manhua_total": counts[MEDIA_MANHUA],
        }
        if getattr(self, "_topbar", None) is not None:
            self._topbar.set_summary(values)
'''
source=replace_method(source,"_build_header",header)
source=replace_method(source,"_build_navbar",navbar)
source=replace_method(source,"_build_toolbar",toolbar)
source=replace_method(source,"_build_search_row",search)
source=replace_method(source,"_update_header_summary",summary)
source=replace_method(source,"_toggle_selection_mode",toggle)
source=source.replace("        outer.addWidget(toolbar)\n        outer.addWidget(self._build_search_row())\n",
                      "        outer.addWidget(toolbar)\n",1)
if "outer.addWidget(self._build_search_row())" in source:
    raise SystemExit("Legacy search row still inserted.")
needle='''        self._search_field.setPlaceholderText(
            f"Search {CATEGORY_LABELS[category]}..."
        )
        self._add_button.setText(f"＋  Add {CATEGORY_LABELS[category]}")
'''
rep=needle+'''        if getattr(self, "_topbar", None) is not None:
            self._topbar.set_category(category)
            self._topbar.set_filter_options(media_format=type_options(category))
'''
if needle not in source:
    raise SystemExit("Category update block missing")
source=source.replace(needle,rep,1)

# Select was intentionally removed; keep legacy card/web selection code safe.
source=source.replace(
'''            self._select_button.setText("✓  Selecting" if enabled else "✓  Select")
            return
''',
'''            if self._select_button is not None:
                self._select_button.setText("✓  Selecting" if enabled else "✓  Select")
            return
''',1)
source=source.replace(
'''        self._select_button.setText("✓  Selecting" if enabled else "✓  Select")

    # ── Data loading''',
'''        if self._select_button is not None:
            self._select_button.setText("✓  Selecting" if enabled else "✓  Select")

    # ── Data loading''',1)

ast.parse(source)
MAIN.write_text(source,encoding="utf-8")
print("Integrated. Backup:",backup)
