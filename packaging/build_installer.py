"""Build a self-extracting installer for AnimeVault.

Produces a single ``AnimeVault-Setup.exe`` that needs no installer
toolchain (no Inno Setup / NSIS).  The launcher is itself a small
PyInstaller program, so it carries its own interpreter and the end user
needs nothing pre-installed.

Run after PyInstaller has produced ``dist/AnimeVault``:

    python packaging/build_installer.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "AnimeVault"
ICON = ROOT / "src" / "animevault" / "resources" / "media" / "app.ico"

APP_NAME = "AnimeVault"
APP_VERSION = "0.3.0"

# ── Launcher ──────────────────────────────────────────────────────
# Runs inside the stub's own bundled interpreter.

LAUNCHER = r'''
import os, sys, shutil, zipfile, subprocess, tempfile

APP_NAME = "AnimeVault"
APP_VERSION = "0.3.0"
# Stable GUID: repeat installs upgrade instead of duplicating.
APP_ID = r"{7B2C9E14-6A3D-4F58-9C21-5E8D4A6F1B93}"

def msg(text, title="AnimeVault Setup", flags=0x40):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:
        print(text)

def ask(text, title="AnimeVault Setup"):
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(
            None, text, title, 0x04 | 0x20 | 0x100) == 6   # Yes/No
    except Exception:
        return False

def install_root():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)

def data_root():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)

def payload_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "payload.zip")

def uninstall_cmd():
    return (
        'cmd.exe /c ""{pythonw}" "{cleanup}" --uninstall"'
    )

def register_uninstall(install_dir):
    """Register with Windows so it appears in Apps & features.

    Windows treats an entry as removable only when *both* UninstallString
    and QuietUninstallString are present; setting just the first leaves the
    entry greyed out with no working Uninstall button.
    """
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault"
    uninstaller = os.path.join(install_dir, "uninstall.exe")
    if not os.path.isfile(uninstaller):
        msg("Warning: uninstall.exe is missing, so Windows may not offer "
            "an Uninstall option.\n\nReinstall AnimeVault to restore it.")
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "AnimeVault")
            winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ,
                              os.path.join(install_dir, "AnimeVault.exe"))
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(k, "NoModify", 0, winreg.DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.DWORD, 1)
            winreg.SetValueEx(k, "SystemComponent", 0, winreg.DWORD, 0)
            winreg.SetValueEx(k, "InstallState", 0, winreg.DWORD, 1)
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                              '"' + uninstaller + '"')
            winreg.SetValueEx(k, "QuietUninstallString", 0, winreg.REG_SZ,
                              '"' + uninstaller + '" /S')
    except Exception as e:
        msg("Installed, but could not register the uninstaller:\n%s" % e)

def make_shortcuts(install_dir, desktop):
    exe = os.path.join(install_dir, "AnimeVault.exe")
    try:
        import winreg
        # Start menu
        start = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs")
        os.makedirs(start, exist_ok=True)
        _link(os.path.join(start, APP_NAME + ".lnk"), exe)
        _link(os.path.join(start, APP_NAME + " Uninstall.lnk"),
              os.path.join(install_dir, "uninstall.exe"))
        if desktop:
            _link(os.path.join(desktop, APP_NAME + ".lnk"), exe)
    except Exception as e:
        msg("Installed, but shortcuts could not be created:\n%s" % e)

def _link(link_path, target):
    if os.path.exists(link_path):
        os.remove(link_path)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
                    "$s.TargetPath='%s';$s.Save()" % (link_path, target)],
                   capture_output=True)

def main():
    install_dir = install_root()
    exe = os.path.join(install_dir, "AnimeVault.exe")

    if os.path.isfile(exe):
        if not ask("%s is already installed.\n\n"
                   "Choose Yes to repair it (reinstall over the current copy)."
                   % APP_NAME):
            return
    elif not ask("Install %s %s?\n\n"
                 "It will be placed in:\n%s\n\n"
                 "Your library is kept separately in:\n%s"
                 % (APP_NAME, APP_VERSION, install_dir, data_root())):
        return

    if os.path.isdir(install_dir):
        shutil.rmtree(install_dir, ignore_errors=True)
    os.makedirs(install_dir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="av_setup_")
    try:
        msg("Extracting files...", flags=0x40)
        with zipfile.ZipFile(payload_path()) as z:
            z.extractall(tmp)

        # payload contains a single top-level "app" directory.
        src = os.path.join(tmp, "app")
        for name in os.listdir(src):
            shutil.move(os.path.join(src, name), os.path.join(install_dir, name))
    except Exception as e:
        msg("Could not extract the application files:\n\n%s\n\n"
            "Nothing was installed." % e, flags=0x10)
        shutil.rmtree(tmp, ignore_errors=True)
        return

    shutil.rmtree(tmp, ignore_errors=True)

    # The pre-built uninstall.exe is already inside the payload zip
    # (it lives alongside AnimeVault.exe in dist/AnimeVault).
    # Nothing extra to copy — it was extracted with everything else.
    uninstaller = os.path.join(install_dir, "uninstall.exe")
    if not os.path.isfile(uninstaller):
        msg("Note: uninstall.exe was not found in the payload.\n"
            "You may need to reinstall to get a working uninstaller.")

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    make_shortcuts(install_dir, os.path.isdir(desktop))
    register_uninstall(install_dir)

    msg("%s installed.\n\nIt will start now." % APP_NAME)
    try:
        subprocess.Popen([exe], close_fds=True)
    except Exception as e:
        msg("Installed, but could not start automatically:\n%s" % e)
        msg("Run:\n%s" % exe)

if __name__ == "__main__":
    main()
'''




def build_uninstaller() -> Path:
    """Compile the standalone uninstaller and return its path.

    Built as a console app so it works when launched from the Windows
    Settings uninstall button with no console of its own.
    """
    source = ROOT / "packaging" / "uninstaller.py"
    if not source.exists():
        raise SystemExit(f"Uninstaller source missing: {source}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "uninstall",
        "--icon", str(ICON),
        "--exclude-module", "PySide6",
        "--exclude-module", "animevault",
        str(source),
    ]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    built = ROOT / "dist" / "uninstall.exe"
    if rc != 0 or not built.exists():
        raise SystemExit("Could not build the uninstaller.")
    return built


def _install_uninstaller(install_dir: str) -> None:
    """Copy the compiled uninstaller into the install folder."""
    source = build_uninstaller()
    target = os.path.join(install_dir, "uninstall.exe")
    try:
        shutil.copy(source, target)
        print(f"  uninstaller: {target} "
              f"({os.path.getsize(target) / 1024:.0f} KB)")
    except Exception as exc:
        raise SystemExit(f"Could not install the uninstaller: {exc}")


def build() -> int:
    if not DIST.is_dir():
        raise SystemExit(
            "dist/AnimeVault not found.\n"
            "Build the app first: see packaging/README.md"
        )
    if not ICON.exists():
        raise SystemExit(f"Icon missing: {ICON}")
    if not shutil.which("powershell"):
        raise SystemExit("PowerShell is required to create shortcuts.")

    # 0. Build the standalone uninstaller so it can be bundled.
    uninstaller = build_uninstaller()
    print(f"  uninstaller: {uninstaller} "
          f"({uninstaller.stat().st_size / 1024:.0f} KB)")

    # 1. Zip the frozen application + uninstaller.
    payload = ROOT / "dist" / "payload.zip"
    print("Zipping application files...")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for item in DIST.rglob("*"):
            if item.is_file():
                z.write(item, Path("app") / item.relative_to(DIST))
        # Include the uninstaller inside the payload so the launcher
        # doesn't need to compile anything at install time.
        z.write(uninstaller, Path("app") / "uninstall.exe")
    print(f"  payload: {payload.stat().st_size / 1024 / 1024:.1f} MB")

    # 2. Build the small self-extracting stub around it.
    stage = ROOT / "build" / "installer_stub"
    stage.mkdir(parents=True, exist_ok=True)
    launcher = stage / "setup_launcher.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    shutil.copy(payload, stage / "payload.zip")

    print("Building installer stub (this takes a minute)...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "AnimeVault-Setup",
        "--icon", str(ICON),
        "--add-data", f"{stage / 'payload.zip'}{os.pathsep}.",
        # The stub must stay small: it never imports the app's modules.
        "--exclude-module", "PySide6",
        "--exclude-module", "animevault",
        str(launcher),
    ]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        raise SystemExit("PyInstaller failed while building the installer stub.")

    out = ROOT / "dist" / "AnimeVault-Setup.exe"
    if not out.exists():
        raise SystemExit("Installer was not produced.")

    payload.unlink(missing_ok=True)
    size = out.stat().st_size / 1024 / 1024
    print(f"\nInstaller ready: {out}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())