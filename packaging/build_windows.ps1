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

$versionSource = Join-Path $root "src\animevault\_version.py"
$versionText = Get-Content -LiteralPath $versionSource -Raw
$versionMatch = [regex]::Match($versionText, '__version__\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Could not read the canonical application version from $versionSource"
}
$version = $versionMatch.Groups[1].Value
$releaseName = "release-v$version-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$releaseDir = Join-Path $root "dist\$releaseName"
$workDir = Join-Path $root "build\$releaseName"
$appDir = Join-Path $releaseDir "AnimeVault"
$exePath = Join-Path $appDir "AnimeVault.exe"
$iconPath = Join-Path $root "src\animevault\resources\media\app.ico"
$mediaPath = Join-Path $root "src\animevault\resources\media"
$entryPoint = Join-Path $root "src\animevault\cli.py"
New-Item -ItemType Directory -Path $releaseDir, $workDir -Force | Out-Null
$env:ANIMEVAULT_VERSION = $version
$buildPython = if ($env:ANIMEVAULT_PYTHON) { $env:ANIMEVAULT_PYTHON } else { "python" }

Write-Host "==> Building AnimeVault v$version in isolated paths; existing build/dist files will be preserved" -ForegroundColor Cyan
Write-Host "==> Freezing application with PyInstaller" -ForegroundColor Cyan
& $buildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "AnimeVault" `
    --distpath $releaseDir `
    --workpath $workDir `
    --specpath (Join-Path $workDir "spec") `
    --icon $iconPath `
    --add-data "$mediaPath;src/animevault/resources/media" `
    --collect-all PySide6 `
    --hidden-import "PySide6.QtMultimedia" `
    --hidden-import "PySide6.QtMultimediaWidgets" `
    $entryPoint
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $exePath)) {
    throw "PyInstaller did not produce $exePath"
}

Write-Host "==> Built: $exePath" -ForegroundColor Green

if ($SkipInstaller) {
    Write-Host "==> Skipping installer (Inno Setup not run)" -ForegroundColor Yellow
    exit 0
}

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "iscc"
) | Where-Object { $_ -and (Get-Command $_ -ErrorAction SilentlyContinue) } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "==> Inno Setup not found; skipping installer." -ForegroundColor Yellow
    Write-Host "    Install it with: winget install JRSoftware.InnoSetup" -ForegroundColor Yellow
    exit 0
}

Write-Host "==> Building installer with Inno Setup" -ForegroundColor Cyan
$sourceMacro = $appDir
$outputMacro = $releaseDir
& $iscc "/Qp" "/DSourceDir=$sourceMacro" "/DOutputDir=$outputMacro" "packaging\AnimeVault.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$setupPath = Join-Path $releaseDir "AnimeVault-Setup.exe"
if (Test-Path $setupPath) {
    Write-Host "==> Built: $setupPath" -ForegroundColor Green
} else {
    throw "Inno Setup did not produce $setupPath"
}