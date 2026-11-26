"""Database backup service for AnimeVault.

Creates safe, atomic SQLite backups with configurable scheduling and
retention limits. Never deletes the active database.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from animevault.database import database_path

logger = logging.getLogger(__name__)

# Backup directory defaults to ~/.AnimeVault/backups
_BACKUP_DIR = os.path.expanduser("~/.AnimeVault/backups")
if os.environ.get("ANIMEVAULT_BACKUP_DIR"):
    BACKUP_DIR = Path(os.environ["ANIMEVAULT_BACKUP_DIR"])
elif os.environ.get("APPDATA"):
    BACKUP_DIR = Path(os.environ["APPDATA"]) / "AnimeVault" / "backups"
else:
    BACKUP_DIR = Path(_BACKUP_DIR)


def get_backup_dir() -> Path:
    """Return the backup directory, creating it if needed."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def backup_database() -> Optional[Path]:
    """Create an immediate database backup. Returns the backup path or None."""
    db_path = database_path()
    if not db_path.exists():
        logger.warning("Database not found at %s", db_path)
        return None

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = get_backup_dir() / f"animevault_{timestamp}.backup"

        # Use SQLite's native backup API for a safe, atomic copy
        with sqlite3.connect(str(db_path)) as src:
            with sqlite3.connect(str(backup_path)) as dst:
                src.backup(dst)

        logger.info("Database backup created: %s", backup_path)
        return backup_path
    except Exception as exc:
        logger.exception("Backup failed: %s", exc)
        return None


def schedule_backup(every: str, keep: int = 7) -> bool:
    """Run scheduled backup based on frequency. Returns True if a backup was created.

    Args:
        every: "Daily", "Weekly", or "Monthly"
        keep: Number of backups to retain (unused here, used by purge)
    """
    import time

    now = time.localtime()

    if every == "Daily":
        # Daily backup on a specific time
        backup_database()
        return True
    elif every == "Weekly":
        # Weekly backup (e.g., Monday)
        if time.strftime("%A", now).lower().startswith("monday"):
            backup_database()
            return True
        return False
    elif every == "Monthly":
        # Monthly backup (e.g., 1st of month)
        if now.tm_mday == 1:
            backup_database()
            return True
        return False
    return False


def purge_old_backups(keep: int = 7) -> int:
    """Delete old backups beyond the retention limit. Returns number deleted."""
    if not BACKUP_DIR.is_dir():
        return 0
    try:
        backups = sorted(
            BACKUP_DIR.glob("animevault_*.backup"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        deleted = 0
        for backup in backups[keep:]:
            backup.unlink()
            deleted += 1
        logger.info("Deleted %d old backups (kept %d)", deleted, keep)
        return deleted
    except Exception as exc:
        logger.exception("Backup purge failed: %s", exc)
        return 0
