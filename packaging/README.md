# Packaging for Windows

Builds a single `AnimeVault-Setup.exe` that a non-technical user can
double-click. No installer toolchain is required — the setup program is
itself a small self-extracting PyInstaller build.

## Build

```powershell
pip install pyinstaller
.\packaging\build_windows.ps1
```

Output lands in `dist/`:

| File | What it is |
|---|---|
| `AnimeVault-Setup.exe` | **The installer.** ~75 MB, one file. |
| `AnimeVault\AnimeVault.exe` | The frozen app, runnable without installing |

To rebuild only the installer from an existing `dist/AnimeVault/`:

```powershell
.\packaging\build_installer.py
```

## What the installer does

When a user double-clicks `AnimeVault-Setup.exe`:

1. Asks for confirmation (or offers repair if already installed).
2. Extracts to `%LOCALAPPDATA%\Programs\AnimeVault` — **no admin rights needed**.
3. Creates Start-menu and Desktop shortcuts.
4. Registers **AnimeVault** in Windows *Apps & features*, with an
   uninstaller.
5. Launches the app.

## Uninstalling

**Normal way:** Windows → *Apps & features* → **AnimeVault** → Uninstall.

**From this repo:**

```powershell
# Remove the app, keep the library
.\packaging\uninstall.ps1

# Remove the app and delete the library database, posters and settings
.\packaging\uninstall.ps1 -PurgeData
```

## Where user data lives

The library sits **outside** the install folder, so uninstalling never
destroys it:

```
%APPDATA%\AnimeVault\animevault.db   library
%APPDATA%\AnimeVault\posters\       cover images
%APPDATA%\AnimeVault\cache\         provider cache
```

## Notes

- The app is large (~150 MB unpacked) because PySide6 and QtMultimedia
  are bundled, and the background video alone is 8.4 MB. The installer
  compresses that to ~75 MB.
- The first build takes several minutes; later rebuilds are quicker.
- Build on Windows — PyInstaller does not cross-compile.
- `packaging/AnimeVault.iss` is kept for anyone who prefers Inno Setup;
  it is not required.
