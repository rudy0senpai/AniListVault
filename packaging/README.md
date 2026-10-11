# Windows packaging

The canonical version is `src/animevault/_version.py`. Build on Windows with the project dependencies and PyInstaller installed in the selected Python environment. The standard installer also requires **Inno Setup 6** (`ISCC.exe`).

## Canonical clean build

```powershell
# In the Python environment used to build the app:
python -m pip install -e .
python -m pip install pyinstaller
winget install JRSoftware.InnoSetup

# Optional when the build Python is not the first `python` on PATH:
$env:ANIMEVAULT_PYTHON = (Get-Command python).Source
.\packaging\build_windows.ps1
```

`build_windows.ps1` reads the version and builds `src/animevault/cli.py` directly with PyInstaller `--clean --onefile --windowed`, using `src/` as an explicit import path and a unique `build/release-v.../` work directory. It stages the app in `dist/release-v<version>-<timestamp>/app/AnimeVault.exe`, then invokes Inno Setup with that exact staging directory as its source. The installer output is staged beside it as `AnimeVault-Setup.exe`.

Only after both build stages succeed does the script publish these stable paths:

- `dist/AnimeVault.exe` — the fresh one-file app.
- `dist/AnimeVault-Setup.exe` — the installer built from that app.
- `dist/AnimeVault-build.json` — version, source revision/worktree state, build mode, paths, sizes, and SHA-256 checksums.

The script verifies the new files are present, nontrivial, newer than the build start, and that the stable copies have the same checksums as the staged outputs. Previous flat outputs that could be mistaken for the current build are moved to `dist/legacy-stale-<timestamp>/` before building. Other versioned release outputs, source files, databases, and user data are not cleaned. `dist/` and `build/` remain ignored by Git.

The build fails if PyInstaller fails, the executable is missing/stale, Inno Setup is unavailable, or the installer is missing/stale. To intentionally build only the executable, run:

```powershell
.\packaging\build_windows.ps1 -SkipInstaller
```

That option does not leave an older installer at `dist/AnimeVault-Setup.exe`.

## Alternative portable installer

`build_installer.py` is an optional self-extracting alternative that does not need Inno Setup. It first invokes the same clean source build with `-SkipInstaller`, then creates `dist/AnimeVault-Portable-Setup.exe` from the fresh executable and a freshly built uninstaller. It never packages the old `dist/AnimeVault/` onedir folder and does not overwrite the standard `AnimeVault-Setup.exe`.

```powershell
python .\packaging\build_installer.py
```

`AnimeVault-Setup.spec` is intentionally disabled: it previously bundled a prebuilt `build/installer_stub/payload.zip` from an absolute machine-specific path and could reproduce an old app. Do not invoke it with PyInstaller; use `packaging/build_windows.ps1`.

## Verify and publish

Before distribution, run the tests and launch `dist/AnimeVault.exe`. For the standard installer, verify `dist/AnimeVault-Setup.exe` and the matching hashes in `dist/AnimeVault-build.json`. The versioned staging folder retains the exact app and installer used for that build.

1. Open the project's [GitHub Releases page](https://github.com/rudy0senpai/AniListVault/releases) and inspect the release matching the application version.
2. Upload `dist/AnimeVault-Setup.exe` (or the exact versioned installer) as a release asset. Do not commit generated executables into the source repository.
3. Verify the uploaded asset name, size, and download from the release page. Do not create a release or replace an existing asset without authorization.

## Installer behavior and user data

The Inno Setup package installs the app under `{autopf}\\AnimeVault`, creates a Start-menu shortcut, offers an optional Desktop shortcut, and registers an uninstaller. The self-extracting alternative installs under `%LOCALAPPDATA%\\Programs\\AnimeVault` and creates shortcuts through its launcher.

The library lives separately from the install folder:

```text
%APPDATA%\\AnimeVault\\animevault.db   library
%APPDATA%\\AnimeVault\\posters\\       cover images
%APPDATA%\\AnimeVault\\cache\\         provider cache
```

Normal uninstall keeps user data. The repository script's `-PurgeData` option explicitly removes it:

```powershell
.\\packaging\\uninstall.ps1
.\\packaging\\uninstall.ps1 -PurgeData
```

Older installations affected by the historical uninstaller issue can be repaired with `packaging/repair_uninstall.ps1`.

## Files

| File | Purpose |
|---|---|
| `build_windows.ps1` | Cleanly builds the app from current source and compiles the Inno Setup installer |
| `build_installer.py` | Rebuilds current source, then creates the separate portable installer |
| `AnimeVault.iss` | Inno Setup definition; requires explicit fresh source/output paths from the build script |
| `AnimeVault-Setup.spec` | Disabled legacy spec; fails closed to prevent stale payload builds |
| `uninstaller.py` | Source for the portable installer's `uninstall.exe` |
| `repair_uninstall.ps1` | Repairs older Windows uninstall registrations |
| `uninstall.ps1` | Removes the app; `-PurgeData` also deletes the library |
