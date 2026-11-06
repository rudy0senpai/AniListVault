# AniListVault — Application Size Optimization & Distribution Audit Report

## Executive Summary

The project directory occupies **8.11 GB** across **38,259 files**. The largest single
contributor is **build outputs and distribution artifacts** at **7.4 GB** (91% of the total),
followed by virtual environments and development dependencies.

## Category Breakdown

| Category | Files | Size |
|---|---|---|
| Essential application source code | 2,337 | 41.0 MB |
| Build outputs and distribution artifacts | 28,868 | 7,577.9 MB |
| Python virtual environments | 6,537 | 658.4 MB |
| Development dependencies | 517 | 29.0 MB |
| **Total** | **38,259** | **8.11 GB** |

## Largest Files / Directories

| Path | Size |
|---|---|
| `dist/release-v0.3.1-20261010-180529/AnimeVault-Setup.exe` | 275.5 MB |
| `dist/release-v0.3.1-20261010-180956/AnimeVault-Setup.exe` | 275.4 MB |
| `dist/AnimeVault.exe` | 258.2 MB |
| `dist/AnimeVault-Setup.exe` | 258.2 MB |
| `build/release-v0.3.1-20261010-230414-600/AnimeVault/AnimeVault.pkg` | 257.8 MB |
| `dist/release-v0.3.1-20261010-201713/AnimeVault/_internal/PySide6/Qt6WebEngineCore.dll` | 194.1 MB |
| `dist/release-v0.3.1-20261010-201233/AnimeVault/_internal/PySide6/Qt6WebEngineCore.dll` | 194.1 MB |
| `dist/release-v0.3.1-20261010-180956/AnimeVault/_internal/Qt6WebEngineCore.dll` | 194.1 MB |
| `dist/release-v0.3.1-20261010-180529/AnimeVault/_internal/PySide6/Qt6WebEngineCore.dll` | 194.1 MB |
| `dist/release-v0.3.1-20261010-170456/AnimeVault/_internal/PySide6/Qt6WebEngineCore.dll` | 194.1 MB |
| `dist/release-v0.3.1-20261010-170122/AnimeVault/_internal/PySide6/Qt6WebEngineCore.dll` | 194.1 MB |

## Key Findings

1. **8 stale PyInstaller release builds** occupy ~6.9 GB in `dist/release-v0.3.1-20261010-*`
2. **Qt WebEngine Core** (194 MB × 7) is the largest single component in each release
3. **Built installers** (8 × ~258 MB) total ~2 GB of duplicate installers
4. The virtual environment (`.venv`) occupies 658 MB
5. **Source code is only 41 MB** — the app itself is tiny; the bloat is entirely in build artifacts

## Optimization Plan

1. Remove all stale build artifacts in `dist/` and `build/`
2. Remove the virtual environment (`.venv`) from the repository root
3. Optimize the PyInstaller packaging configuration to reduce installer size
4. Create a clean, reproducible release build
