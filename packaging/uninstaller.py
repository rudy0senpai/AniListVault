"""Standalone AnimeVault uninstaller.

Built into ``uninstall.exe`` by ``build_installer.py`` and copied into the
install folder, so Windows *Apps & features* → Uninstall actually removes
the application instead of re-installing it.

Kept as a real module (rather than a string inside the installer) so it can
be linted, tested and edited on its own.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

APP_NAME = "AnimeVault"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault"


def _msg(text: str, flags: int = 0x40) -> None:
    """Show a message box, falling back to stdout when there is no desktop."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, f"{APP_NAME} Uninstall", flags)
    except Exception:
        print(text)


def _confirm(text: str) -> bool:
    """Ask a Yes/No question.  Returns False when the user declines."""
    try:
        import ctypes

        # 0x04=Yes 0x20=NoTopMost 0x100=UserIcon
        return (
            ctypes.windll.user32.MessageBoxW(
                None, text, f"{APP_NAME} Uninstall", 0x04 | 0x20 | 0x100
            )
            == 6
        )
    except Exception:
        return False


def _data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def _install_dir() -> str:
    """The folder this executable lives in."""
    return os.path.dirname(os.path.abspath(sys.executable))


def _remove_shortcuts() -> None:
    """Delete the Start-menu and Desktop entries."""
    targets = []
    start = os.path.join(
        os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"
    )
    targets += [
        os.path.join(start, f"{APP_NAME}.lnk"),
        os.path.join(start, f"{APP_NAME} Uninstall.lnk"),
    ]
    targets.append(
        os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk")
    )
    for path in targets:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _remove_registry() -> None:
    """Remove the Apps & features entry."""
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
    except Exception:
        pass


def _app_is_running() -> bool:
    """Check for a still-running AnimeVault after requesting a graceful close."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_NAME}.exe", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return f'"{APP_NAME}.exe"' in (result.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return True


def _request_app_close() -> bool:
    """Ask Windows to close the app without force-killing unsaved work."""
    try:
        subprocess.run(
            ["taskkill", "/IM", f"{APP_NAME}.exe"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return not _app_is_running()
    time.sleep(1)
    return not _app_is_running()


def _start_self_delete(install_dir: str) -> None:
    """Remove the install directory after this frozen executable exits.

    A PyInstaller executable is not a Python interpreter. Use a temporary
    command script instead of trying to execute a Python helper with it.
    """
    if not os.path.isdir(install_dir):
        return
    helper = os.path.join(tempfile.gettempdir(), f"av_uninstall_cleanup_{os.getpid()}.cmd")
    target = os.path.normpath(install_dir).replace("%", "%%")
    with open(helper, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f'rmdir /s /q "{target}"\r\n'
            'del /f /q "%~f0" >nul 2>nul\r\n'
        )
    try:
        subprocess.Popen(
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", "start", "", "/b", helper],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        try:
            os.remove(helper)
        except OSError:
            pass
        raise


def main() -> int:
    """Remove the application, keeping the user's library."""
    silent = any(arg.upper() == "/S" for arg in sys.argv[1:])
    install_dir = _install_dir()
    data = _data_dir()

    if not silent and not _confirm(
        f"Uninstall {APP_NAME}?\n\n"
        f"Application files will be removed from:\n{install_dir}\n\n"
        f"Your library, covers and settings are kept in:\n{data}"
    ):
        return 1

    # Never force-kill the app; it could be writing the library database.
    if not _request_app_close():
        if not silent:
            _msg(
                f"{APP_NAME} is still running. Close it and run the uninstaller again.",
                flags=0x10,
            )
        return 2

    try:
        _start_self_delete(install_dir)
    except OSError as exc:
        if not silent:
            _msg(f"Could not schedule safe removal of the install folder:\n{exc}", flags=0x10)
        return 3
    _remove_shortcuts()
    _remove_registry()

    if not silent:
        kept = (
            f"\n\nYour library was kept in:\n{data}"
            if os.path.isdir(data)
            else ""
        )
        _msg(f"{APP_NAME} has been uninstalled.{kept}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())