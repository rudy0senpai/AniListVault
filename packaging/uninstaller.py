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


def _start_self_delete(install_dir: str) -> None:
    """Delete *install_dir* from a helper process.

    A running process holds its own directory open on Windows, so the
    deletion has to happen after this script exits.
    """
    helper = os.path.join(tempfile.gettempdir(), "av_uninstall_cleanup.py")
    with open(helper, "w", encoding="utf-8") as handle:
        handle.write(
            "import os, shutil, time\n"
            f"target = {install_dir!r}\n"
            "for _ in range(30):\n"
            "    if not os.path.isdir(target):\n"
            "        break\n"
            "    shutil.rmtree(target, ignore_errors=True)\n"
            "    time.sleep(0.5)\n"
        )
    try:
        subprocess.Popen([sys.executable, helper], close_fds=True)
    except Exception:
        # Without the helper the user can simply delete the folder.
        pass


def main() -> int:
    """Remove the application, keeping the user's library."""
    silent = any(arg.upper() == "/S" for arg in sys.argv[1:])
    install_dir = _install_dir()
    data = _data_dir()

    # A running app would keep its files locked.
    subprocess.run(
        ["taskkill", "/F", "/IM", f"{APP_NAME}.exe"], capture_output=True
    )
    time.sleep(1)

    if not silent and not _confirm(
        f"Uninstall {APP_NAME}?\n\n"
        f"Application files will be removed from:\n{install_dir}\n\n"
        f"Your library, covers and settings are kept in:\n{data}"
    ):
        return 1

    _remove_shortcuts()
    _remove_registry()
    _start_self_delete(install_dir)

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