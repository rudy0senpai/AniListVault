"""Safety tests for the standalone Windows uninstaller."""

import importlib.util
import sys
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "packaging" / "uninstaller.py"
_spec = importlib.util.spec_from_file_location("animevault_uninstaller", SOURCE)
uninstaller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uninstaller)


def test_cancelled_uninstall_does_not_close_app_or_remove_files(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["uninstall.exe"])
    monkeypatch.setattr(uninstaller, "_install_dir", lambda: str(tmp_path / "install"))
    monkeypatch.setattr(uninstaller, "_data_dir", lambda: str(tmp_path / "user-data"))
    monkeypatch.setattr(uninstaller, "_confirm", lambda _text: False)
    monkeypatch.setattr(uninstaller.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    assert uninstaller.main() == 1
    assert calls == []


def test_shutdown_request_is_not_forced(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(uninstaller.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(uninstaller, "_app_is_running", lambda: False)
    monkeypatch.setattr(uninstaller.time, "sleep", lambda _seconds: None)

    assert uninstaller._request_app_close() is True
    assert calls[0][0][0] == ["taskkill", "/IM", "AnimeVault.exe"]
    assert "/F" not in calls[0][0][0]


def test_self_delete_helper_uses_cmd_not_frozen_python(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(uninstaller.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(uninstaller.subprocess, "Popen", lambda *a, **k: launched.append((a, k)))

    install_dir = tmp_path / "AnimeVault Install"
    install_dir.mkdir()
    uninstaller._start_self_delete(str(install_dir))

    helper = next(tmp_path.glob("av_uninstall_cleanup_*.cmd"))
    script = helper.read_text(encoding="utf-8")
    assert "rmdir /s /q" in script
    assert "AnimeVault Install" in script
    assert launched
    assert sys.executable not in launched[0][0][0]
