"""Import / capability checks for the Phase 1 foundation.

These assert nothing crashes at import time and that the required toolchain
(binaries) is available. They do not touch the user database.
"""

from __future__ import annotations

import shutil

import pytest

import animevault


def test_animevault_package_imports():
    import animevault.database
    import animevault.migration

    assert animevault.__version__


def test_backend_modules_import():
    from backend import main, database, schemas
    from backend import services

    assert main.create_app
    assert database.get_db
    assert services.library.list_anime


def test_node_toolchain_available():
    """Node is required for the Electron renderer build."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; frontend build cannot run")
    npm = shutil.which("npm")
    assert npm is not None
