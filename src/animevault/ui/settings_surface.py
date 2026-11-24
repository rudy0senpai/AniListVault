"""Settings surface wrapper component.

Connects the LiquidGlass settings panel to the Qt bridge for persistence
and actions. This is the proper entry point for opening the settings panel
from the application's navigation.
"""

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot, Qt
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QWidget, QMenuBar, QPushButton, QFrame, QSizePolicy, QHBoxLayout,
)

from .web_view import LibraryBridge
from .LiquidGlass import BubbleButton, BubbleMenu
from .LiquidSettings import Settings

logger = logging.getLogger(__name__)


class SettingsSurface(QDialog):
    """A dialog containing the LiquidGlass settings panel.

    Opened from the application's main window, this dialog hosts the
    React settings component inside a QWebEngineView, with the Qt
    bridge connecting to the backend services.
    """

    settingsChanged = Signal(dict)
    settingsApplied = Signal(dict)
    actionTriggered = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(900)
        self.setMinimumHeight(650)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Build the dialog layout
        self._build_ui()
        self._init_bridge()
        self._load_settings()

    def _build_ui(self):
        """Create the dialog with a web view and a title bar."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar with close button
        title_bar = self._create_title_bar()
        layout.addWidget(title_bar)

        # Web view
        self._web_view = QWebEngineView()
        self._web_view.setMinimumSize(880, 580)
        self._web_view.setStyleSheet("background: #0b1020;")
        layout.addWidget(self._web_view)

        # Bottom action bar
        self._action_bar = QHBoxLayout()
        self._action_bar.setContentsMargins(8, 8, 8, 8)
        self._apply_button = BubbleButton("Apply", variant="accent", style_sheet="min-width:100px;")
        self._apply_button.clicked.connect(self._on_apply)
        self._action_bar.addWidget(self._apply_button)
        self._close_button = BubbleButton("Close", style_sheet="min-width:100px;")
        self._close_button.clicked.connect(self.close)
        self._action_bar.addWidget(self._close_button)
        layout.addLayout(self._action_bar)

        # Store references
        self._apply_button_hidden = False

    def _create_title_bar(self):
        """Create the title bar with a dropdowns menu."""
        bar = QFrame()
        bar.setStyleSheet("background: rgba(19,26,46,0.8); border-bottom: 1px solid rgba(255,255,255,0.12);")
        bar.setFixedHeight(48)
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 4, 16, 4)

        # Title
        self._title_label = QPushButton("Settings")
        self._title_label.setStyleSheet("""
            QPushButton {
                background: none; color: #e6ecfa; font-size: 15px;
                font-weight: 600; border: none; padding: 0;
            }
            QPushButton:hover { color: #b79cf5; }
        """)
        layout.addWidget(self._title_label)

        layout.addStretch()

        # Dropdown menus (File, Tools, Help, etc.)
        self._menus = {}
        self._build_menus()

        return bar

    def _build_menus(self):
        """Rebuild the menu dropdowns (File/Tools/Help/etc)."""
        # Clear existing
        for menu in self._menus.values():
            menu.deleteLater()
        self._menus.clear()

        # Build a container for the menus
        self._menu_container = QWidget()
        self._menu_container.setStyleSheet("background: transparent;")
        menu_layout = QVBoxLayout(self._menu_container)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(0)
        self._menu_container.setLayout(menu_layout)

        # File menu (removed — empty)
        # Tools menu
        tools_menu = self._create_menu("Tools")
        for label, action in [
            ("Library Dashboard", "dashboard"),
            ("Fetch Missing Data", "fetch_missing"),
            ("Refresh Anime Data", "refresh_all"),
            ("Cloud Sync", "cloud_sync"),
        ]:
            item = BubbleButton(label, style_sheet="min-width:180px;")
            item.clicked.connect(lambda checked, a=action: self._on_menu_action(a))
            tools_layout = QVBoxLayout()
            tools_layout.setContentsMargins(0, 0, 0, 0)
            tools_layout.setSpacing(2)
            item.setLayout(tools_layout)
            tools_layout.addWidget(item)
            menu_layout.addWidget(item)

        # Help menu
        help_menu = self._create_menu("Help")
        for label, action in [
            ("Documentation (README)", "open_readme"),
            ("About AnimeVault", "about"),
        ]:
            item = BubbleButton(label, style_sheet="min-width:180px;")
            item.clicked.connect(lambda checked, a=action: self._on_menu_action(a))
            help_layout = QVBoxLayout()
            help_layout.setContentsMargins(0, 0, 0, 0)
            help_layout.setSpacing(2)
            item.setLayout(help_layout)
            help_layout.addWidget(item)
            menu_layout.addWidget(item)

        # Upload menu
        upload_menu = self._create_menu("Upload")
        for label, action in [
            ("Upload Excel (.xlsx)", "import_xlsx"),
            ("Upload CSV (.csv)", "import_csv"),
            ("Upload SQL Dump (.sql)", "import_sql"),
        ]:
            item = BubbleButton(label, style_sheet="min-width:180px;")
            item.clicked.connect(lambda checked, a=action: self._on_menu_action(a))
            upload_layout = QVBoxLayout()
            upload_layout.setContentsMargins(0, 0, 0, 0)
            upload_layout.setSpacing(2)
            item.setLayout(upload_layout)
            upload_layout.addWidget(item)
            menu_layout.addWidget(item)

        # Export menu
        export_menu = self._create_menu("Export")
        for label, action in [
            ("Export to CSV", "export_csv"),
            ("Export to Excel (.xlsx)", "export_xlsx"),
            ("Export to OpenDocument (.ods)", "export_ods"),
            ("Export to SQL Dump", "export_sql"),
        ]:
            item = BubbleButton(label, style_sheet="min-width:180px;")
            item.clicked.connect(lambda checked, a=action: self._on_menu_action(a))
            export_layout = QVBoxLayout()
            export_layout.setContentsMargins(0, 0, 0, 0)
            export_layout.setSpacing(2)
            item.setLayout(export_layout)
            export_layout.addWidget(item)
            menu_layout.addWidget(item)

        # Delete, Select, Fetch Missing Data, Retry Failed buttons
        actions = [
            ("Delete", "delete_selected", "danger"),
            ("Select", "toggle_selection_mode"),
            ("Fetch Missing Data", "fetch_missing"),
            ("Retry Failed", "retry_failed"),
        ]
        for label, action, *variant in actions:
            btn = BubbleButton(label, variant=variant[0] if variant else "glass")
            btn.clicked.connect(lambda checked, a=action: self._on_menu_action(a))
            self._menu_container.layout().addWidget(btn)

        # Add the menu container to a layout
        menu_wrapper = QWidget()
        menu_wrapper.setStyleSheet("background: transparent;")
        menu_layout = QVBoxLayout(menu_wrapper)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(0)
        menu_layout.addWidget(self._menu_container)
        self._menu_container.setLayout(menu_layout)

        # Add the menu container to the title bar
        layout.addWidget(menu_wrapper)

    def _create_menu(self, label):
        """Create a menu dropdown button."""
        # Use a simple button as the menu trigger
        btn = BubbleButton(label, style_sheet="min-width:100px;")
        menu = self._create_simple_menu(label)
        btn.setMenu(menu)
        btn.setPopupMode(BubbleButton.MenuButtonPopup)
        self._menus[label] = menu
        return menu

    def _create_simple_menu(self, label):
        """Create a simple popup menu."""
        return QMenu(label, self)

    def _on_menu_action(self, action):
        """Handle menu action from the toolbar."""
        self.actionTriggered.emit(action)

    def _init_bridge(self):
        """Initialize the Qt bridge for the web view."""
        self.bridge = LibraryBridge(self)
        self.channel = QWebChannel(self._web_view.page())
        self.channel.registerObject("bridge", self.bridge)
        self._web_view.page().setWebChannel(self.channel)

        # Connect bridge signals to our handlers
        self.bridge.settingsChanged.connect(self._on_settings_changed)
        self.bridge.settingsApplied.connect(self._on_settings_applied)
        self.bridge.actionTriggered.connect(self._on_action_triggered)

        # Load the React app
        self._load_react_app()

    def _load_react_app(self):
        """Load the React settings app in the web view."""
        import os
        from pathlib import Path

        # Get the path to the built frontend
        frontend_dir = Path(__file__).parent / "web" / "dist"
        if not frontend_dir.exists():
            logger.warning("Frontend dist not found at %s", frontend_dir)
            return

        index_html = frontend_dir / "index.html"
        if not index_html.exists():
            logger.warning("index.html not found at %s", index_html)
            return

        # Construct the URL
        from PySide6.QtGui import QColor
        from PySide6.QtCore import QUrl, QUrlQuery

        url = QUrl.fromLocalFile(str(index_html.resolve()))
        query = QUrlQuery(url)
        query.addQueryItem("surface", "settings")
        url.setQuery(query)
        self._web_view.setPage(self._create_page())

        # Set the initial URL
        self._web_view.setUrl(url)

    def _create_page(self):
        """Create a QWebEnginePage with the web channel."""
        from PySide6.QtWebEngineWidgets import QWebEnginePage

        page = QWebEnginePage(self._web_view)
        self.channel = QWebChannel(page)
        # The bridge is registered on the page
        self.channel.registerObject("bridge", self.bridge)
        page.setWebChannel(self.channel)
        return page

    def _on_settings_changed(self, settings_json):
        """Handle settings change from the React component."""
        try:
            settings = json.loads(settings_json)
            self.settingsChanged.emit(settings)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Invalid settings JSON: %s", exc)

    def _on_settings_applied(self, settings_json):
        """Handle settings applied from the React component."""
        try:
            settings = json.loads(settings_json)
            self.settingsApplied.emit(settings)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Invalid settings JSON: %s", exc)

    def _on_action_triggered(self, action_id):
        """Handle a settings action (backup, cache clear, update, licenses)."""
        logger.info("Settings action triggered: %s", action_id)

        # Map action IDs to backend service calls
        if action_id == "data.backupNow":
            self._on_back_up_database()
        elif action_id == "data.clearCache":
            self._on_clear_cache()
        elif action_id == "about.update":
            self._on_check_for_updates()
        elif action_id == "about.licenses":
            self._on_view_licenses()

    def _on_back_up_database(self):
        """Handle immediate database backup."""
        from animevault.services.backup_service import BackupService
        backup_service = BackupService()
        backup_path = backup_service.backup()
        if backup_path:
            self._show_notification(f"Backup created: {backup_path.name}")
        else:
            self._show_notification("Backup failed", level="error")

    def _on_clear_cache(self):
        """Handle cache clearing."""
        from animevault.services.cache_service import CacheService
        cache_service = CacheService()
        count = cache_service.clear()
        self._show_notification(f"Cache cleared ({count} files removed)")

    def _on_check_for_updates(self):
        """Check for updates."""
        from animevault.services.update_service import UpdateService
        update_service = UpdateService()
        has_update, version = update_service.check_for_updates()
        if has_update:
            self._show_notification(f"Update available: {version}")
        else:
            self._show_notification("You are on the latest version")

    def _on_view_licenses(self):
        """Display open-source licenses."""
        from animevault.services.update_service import UpdateService
        update_service = UpdateService()
        update_service.view_licenses()

    def _show_notification(self, message, level="info"):
        """Show an in-app notification."""
        self.status_message = message
        # This is a placeholder — actual notification would use the
        # NotificationService. For simplicity, we'll show a message
        # in the status bar of the parent window.
        if self.parent() is not None:
            self.parent().statusMessage(message, level)

    def _on_apply(self):
        """Handle the Apply button click."""
        self.bridge.apply_settings()
        self.settingsApplied.emit(json.dumps({"status": "applied"}))

    def open(self):
        """Open the settings panel."""
        super().open()
        # Focus the web view after opening
        self._web_view.setFocus()

    def reject(self):
        """Handle dialog rejection (close)."""
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Clean up on close."""
        self._apply_button = None
        self._web_view = None
        super().closeEvent(event)


class SettingsSurfaceFactory:
    """Factory for creating settings surfaces."""

    @staticmethod
    def create_settings_surface(parent: QWidget | None = None) -> SettingsSurface:
        """Create and return a new settings surface dialog."""
        return SettingsSurface(parent)
