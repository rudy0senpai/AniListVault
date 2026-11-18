"""Pytest fixtures — provides a fresh temp database per test session."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QSettings

import pytest

from animevault.database import database_path, initialize_database, set_database_path


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch):
    """Redirect the module-level DB path to a temp file for each test.

    This ensures tests never touch the real user database.
    """
    db_file = tmp_path / "test_animevault.db"

    # Clear any cached thread-local connection so a fresh one is created.
    import animevault.database as db_mod

    db_mod._disconnect_cached()

    set_database_path(db_file)
    initialize_database(db_file)

    # Bring the schema to the current version so tests exercise the real
    # columns (tier, rewatches, literature tables, …).
    from animevault.migration import run_migrations

    run_migrations()

    yield db_file

    # Clean up thread-local connection after test
    db_mod._disconnect_cached()


@pytest.fixture(autouse=True)
def reset_theme_manager():
    """Reset ThemeManager singleton to default state for each test."""
    from animevault.ui.theme import ThemeManager, _activate_tokens, THEMES, DEFAULT_THEME_ID
    from animevault.ui import theme as theme_tokens

    # Reset QSettings for liquid_glass so tests start from a known state
    settings = QSettings("AnimeVault", "AnimeVault")
    settings.remove("appearance/liquid_glass")

    # Reset singleton
    ThemeManager._instance = None

    # Reset global theme tokens to default
    default_theme = THEMES[DEFAULT_THEME_ID]
    _activate_tokens(default_theme)
    theme_tokens._REDUCE_EFFECTS = False

    # Re-export the updated tokens to the module
    import animevault.ui.theme as theme_module
    theme_module.BG_DEEP = default_theme.background
    theme_module.BG_PANEL = default_theme.panel
    theme_module.BG_PANEL_HI = default_theme.panel_hover
    theme_module.BG_INPUT = default_theme.input
    theme_module.BORDER = default_theme.border
    theme_module.BORDER_HI = default_theme.border_hover
    theme_module.ACCENT = default_theme.accent
    theme_module.ACCENT_DIM = default_theme.accent_dim
    theme_module.ACCENT_DEEP = default_theme.accent_deep
    theme_module.TEXT_PRIMARY = default_theme.text
    theme_module.TEXT_SECONDARY = default_theme.text_secondary
    theme_module.TEXT_MUTED = default_theme.text_muted
    theme_module.TEXT_ON_ACCENT = default_theme.text_on_accent
    theme_module.DANGER = default_theme.danger
    theme_module.SUCCESS = default_theme.success
    theme_module.WARNING = default_theme.warning

    yield

    # Clean up singleton after test
    ThemeManager._instance = None


@pytest.fixture
def db_conn(isolated_database: Path) -> sqlite3.Connection:
    """Direct connection to the test database for assertions."""
    conn = sqlite3.connect(str(isolated_database))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def migrated_database(isolated_database: Path):
    """Isolated database with all schema migrations applied.

    ``isolated_database`` already migrates, so this is an explicit alias
    for tests that want to state that dependency.
    """
    return isolated_database
