# Packaging for Windows

Builds a standalone `AnimeVault.exe` and an `AnimeVault-Setup.exe`
installer that registers a proper Windows uninstaller.

## Prerequisites

Two tools, neither of which is bundled with Python:

```powershell
pip install pyinstaller
winget install JRSoftware.InnoSetup
```

- **PyInstaller** freezes the app and everything it imports (PySide6,
  QtMultimedia and the background video) into one folder.
- **Inno Setup** turns that folder into `AnimeVault-Setup.exe` and writes
  the uninstaller Windows records under *Apps & features*.

## Build

```powershell
.\packaging\build_windows.ps1
```

Output lands in `dist/`:

| File | What it is |
|---|---|
| `AnimeVault-Setup.exe` | Installer — run this to install |
| `AnimeVault\AnimeVault.exe` | The frozen app, runnable without installing |

To build only the portable copy and skip the installer:

```powershell
.\packaging\build_windows.ps1 -SkipInstaller
```

## What the installer does

- Installs to `%LOCALAPPDATA%\Programs\AnimeVault` for the current user
  (no administrator rights needed; you can opt into all-users)
- Adds Start-menu and optional Desktop shortcuts
- Registers **AnimeVault Uninstall** in Windows *Apps & features*
- Deletes the cached poster and cache folders on uninstall

## Uninstalling

**Normal way:** Windows → *Apps & features* → **AnimeVault Uninstall**.

**From this repo:**

```powershell
# Remove the app, keep your library
.\packaging\uninstall.ps1

# Remove the app and delete the library database, posters and settings
.\packaging\uninstall.ps1 -PurgeData
```

The script prefers the registered uninstaller when it finds one and
falls back to deleting the install folder directly.

## Where your data lives

The library is **not** inside the install folder, so uninstalling does not
silently destroy it:

```
%APPDATA%\AnimeVault\animevault.db   library
%APPDATA%\AnimeVault\posters\       cover images
%APPDATA%\AnimeVault\cache\         provider cache
```

Deleting that folder resets the application completely.

## Notes

- The first build takes a few minutes — `--collect-all PySide6` is large.
- `QtMultimedia` and the background video are explicitly listed as
  hidden imports and added data, because neither is detected
  automatically.
- Build on Windows; PyInstaller does not cross-compile.