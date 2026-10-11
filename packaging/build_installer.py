"""Build a self-extracting installer for AnimeVault.

Produces a single ``AnimeVault-Setup.exe`` that needs no installer
toolchain (no Inno Setup / NSIS).  The launcher is itself a small
PyInstaller program, so it carries its own interpreter and the end user
needs nothing pre-installed.

Run on Windows. This alternative builder first invokes
``packaging/build_windows.ps1 -SkipInstaller`` to perform a clean build from
current source, then packages ``dist/AnimeVault.exe`` as
``dist/AnimeVault-Portable-Setup.exe``. It never consumes an old onedir folder.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from animevault._version import __version__ as APP_VERSION

APP_EXE = ROOT / "dist" / "AnimeVault.exe"
PORTABLE_SETUP = ROOT / "dist" / "AnimeVault-Portable-Setup.exe"
ICON = ROOT / "src" / "animevault" / "resources" / "media" / "app.ico"

APP_NAME = "AnimeVault"

# ── Launcher ──────────────────────────────────────────────────────
# Runs inside the stub's own bundled interpreter.

LAUNCHER = r'''
import os, sys, shutil, zipfile, subprocess, tempfile

APP_NAME = "AnimeVault"
APP_VERSION = "__APP_VERSION__"
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
LAUNCHER = LAUNCHER.replace("__APP_VERSION__", APP_VERSION)


def build_application() -> Path:
    """Run the canonical clean source build and return its fresh executable."""
    if os.name != "nt":
        raise SystemExit("The Windows application build must run on Windows.")
    script = ROOT / "packaging" / "build_windows.ps1"
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not script.is_file() or not powershell:
        raise SystemExit("PowerShell and packaging/build_windows.ps1 are required.")
    env = os.environ.copy()
    env["ANIMEVAULT_PYTHON"] = sys.executable
    started = time.time()
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-SkipInstaller"],
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Fresh application build failed with exit code {result.returncode}.")
    if not APP_EXE.is_file() or APP_EXE.stat().st_mtime < started - 2:
        raise SystemExit("The canonical build did not produce a fresh dist/AnimeVault.exe.")
    return APP_EXE


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
    if not ICON.exists():
        raise SystemExit(f"Icon missing: {ICON}")
    if not shutil.which("powershell.exe") and not shutil.which("pwsh.exe"):
        raise SystemExit("PowerShell is required to build the application.")

    # Always compile the current source first; never consume dist/AnimeVault/.
    app_exe = build_application()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    stage = ROOT / "build" / f"portable-setup-{stamp}"
    stage.mkdir(parents=True, exist_ok=False)

    uninstaller = build_uninstaller()
    print(f"  fresh app: {app_exe} ({app_exe.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  uninstaller: {uninstaller} ({uninstaller.stat().st_size / 1024:.0f} KB)")

    payload = stage / "payload.zip"
    print("Zipping freshly built application and uninstaller...")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(app_exe, Path("app") / "AnimeVault.exe")
        z.write(uninstaller, Path("app") / "uninstall.exe")
    print(f"  payload: {payload.stat().st_size / 1024 / 1024:.1f} MB")

    launcher = stage / "setup_launcher.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    stub_work = stage / "stub-work"
    stub_spec = stage / "stub-spec"
    stub_work.mkdir()
    stub_spec.mkdir()
    started = time.time()
    print("Building the separate portable setup executable...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "AnimeVault-Portable-Setup",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(stub_work),
        "--specpath", str(stub_spec),
        "--icon", str(ICON),
        "--add-data", f"{payload}{os.pathsep}.",
        "--exclude-module", "PySide6",
        "--exclude-module", "animevault",
        str(launcher),
    ]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        raise SystemExit("PyInstaller failed while building the portable setup stub.")

    if not PORTABLE_SETUP.is_file() or PORTABLE_SETUP.stat().st_size < 1_000_000:
        raise SystemExit(f"Portable installer was not regenerated: {PORTABLE_SETUP}")
    if PORTABLE_SETUP.stat().st_mtime < started - 2:
        raise SystemExit(f"Portable installer is older than this build: {PORTABLE_SETUP}")

    size = PORTABLE_SETUP.stat().st_size / 1024 / 1024
    print(f"\nPortable installer ready: {PORTABLE_SETUP} ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())