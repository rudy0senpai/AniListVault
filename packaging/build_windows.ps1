<#
.SYNOPSIS
    Builds AnimeVault-Setup.exe (installer) and AnimeVault-Portable.exe.

.DESCRIPTION
    Uses PyInstaller to freeze the application into a standalone Windows
    executable, then Inno Setup (if installed) to wrap it in a
    Setup.exe with Start-menu and Desktop shortcuts.

    Both tools must be installed first:
        pip install pyinstaller
        winget install JRSoftware.InnoSetup

.PARAMETER SkipInstaller
    Build only the portable executable; skip Inno Setup entirely.

.EXAMPLE
    .\packaging\build_windows.ps1
    .\packaging\build_windows.ps1 -SkipInstaller
#>
[CmdletBinding()]
param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Cleaning previous builds" -ForegroundColor Cyan
Get-ChildItem -Path build, dist -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "==> Freezing application with PyInstaller" -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "AnimeVault" `
    --icon "src\animevault\resources\media\app.ico" `
    --add-data "src\animevault\resources\media;src\animevault\resources\media" `
    --collect-all PySide6 `
    --hidden-import "PySide6.QtMultimedia" `
    --hidden-import "PySide6.QtMultimediaWidgets" `
    "src\animevault\cli.py"

if (-not (Test-Path "dist\AnimeVault\AnimeVault.exe")) {
    throw "PyInstaller did not produce dist\AnimeVault\AnimeVault.exe"
}

Write-Host "==> Built: dist\AnimeVault\AnimeVault.exe" -ForegroundColor Green

if ($SkipInstaller) {
    Write-Host "==> Skipping installer (Inno Setup not run)" -ForegroundColor Yellow
    exit 0
}

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "iscc"
) | Where-Object { $_ -and (Get-Command $_ -ErrorAction SilentlyContinue) } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "==> Inno Setup not found; skipping installer." -ForegroundColor Yellow
    Write-Host "    Install it with: winget install JRSoftware.InnoSetup" -ForegroundColor Yellow
    exit 0
}

Write-Host "==> Building installer with Inno Setup" -ForegroundColor Cyan
& $iscc "packaging\AnimeVault.iss"

if (Test-Path "dist\AnimeVault-Setup.exe") {
    Write-Host "==> Built: dist\AnimeVault-Setup.exe" -ForegroundColor Green
} else {
    throw "Inno Setup did not produce dist\AnimeVault-Setup.exe"
}