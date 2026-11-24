"""Application update checker for AnimeVault."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

# GitHub releases endpoint
_RELEASES_URL = os.environ.get(
    "ANIMEVAULT_GITHUB_RELEASES",
    "https://api.github.com/repos/rudy0senpai/AniListVault/releases/latest",
)

_LICENSES = {
    "PySide6": "BSD-style license",
    "SQLite": "Public Domain",
    "scikit-learn": "BSD-style license",
    "React": "MIT license",
    "Vite": "MIT license",
    "react-dom": "MIT license",
}


def check_for_updates() -> Tuple[bool, str]:
    """Check for updates from GitHub releases.

    Returns:
        Tuple of (has_update: bool, version_string: str)
    """
    try:
        req = urllib.request.Request(
            _RELEASES_URL,
            headers={"User-Agent": "AnimeVault", "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "")
            return (latest != os.environ.get("ANIMEVAULT_VERSION", ""), latest)
    except Exception as exc:
        logger.exception("Update check failed: %s", exc)
        return (False, f"Error checking for updates: {exc}")


def view_licenses() -> None:
    """Display the project's open-source licenses.

    Shows a dialog with license information for the project's key dependencies.
    """
    lines = ["AnimeVault Open Source Licenses", "=" * 35, ""]
    for dep, license_info in _LICENSES.items():
        lines.append(f"• {dep} — {license_info}")
    lines.append("")
    lines.append("Full details: https://github.com/rudy0senpai/AniListVault")
    print("\n".join(lines))


class UpdateService:
    """Application update checker."""

    def __init__(self, app: Any | None = None) -> None:
        self._app = app
        self._releases_url = os.environ.get("ANIMEVAULT_GITHUB_RELEASES", _RELEASES_URL)

    def check_for_updates(self) -> Tuple[bool, str]:
        """Check for updates. Returns (has_update, version_string)."""
        try:
            req = urllib.request.Request(
                self._releases_url,
                headers={"User-Agent": "AnimeVault", "Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest = data.get("tag_name", "")
                return (latest != os.environ.get("ANIMEVAULT_VERSION", ""), latest)
        except Exception as exc:
            logger.exception("Update check failed: %s", exc)
            return (False, f"Error checking for updates: {exc}")

    def view_licenses(self) -> None:
        """Display open-source licenses."""
        lines = ["AnimeVault Open Source Licenses", "=" * 35, ""]
        for dep, license_info in _LICENSES.items():
            lines.append(f"• {dep} — {license_info}")
        lines.append("")
        lines.append("Full details: https://github.com/rudy0senpai/AniListVault")
        print("\n".join(lines))
