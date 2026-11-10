<#
.SYNOPSIS
    Rebuilds the current AnimeVault source as a Windows standalone executable
    using Nuitka (native compilation, no Python runtime dependencies).

.DESCRIPTION
    Uses Nuitka to compile src\animevault\cli.py into a single standalone
    Windows executable. Nuitka bundles the Python interpreter and all required
    dependencies directly into the executable, so no separate Python installation
    is needed.

    Output is placed in dist\AnimeVault\AnimeVault.exe.

.PARAMETER Skip
    Skip the build (for verification purposes).

.EXAMPLE
    .\packaging\build_nuitka.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Remove any old build artifacts
if (Test-Path -LiteralPath "dist") {
    Remove-Item -LiteralPath "dist" -Recurse -Force
}
if (Test-Path -LiteralPath "build") {
    Remove-Item -LiteralPath "build" -Recurse -Force
}
if (Test-Path -LiteralPath "*.spec") {
    Remove-Item -LiteralPath "*.spec" -Force
}

$versionSource = Join-Path $root "src\animevault\_version.py"
$versionLine = Get-Content -LiteralPath $versionSource -Raw |
    Select-String -Pattern '__version__' -SimpleMatch |
    Select-Object -First 1 -Expand Line
if ($null -eq $versionLine) {
    throw "Could not find __version__ in $versionSource"
}
$version = ($versionLine -split '=')[1].Trim().Trim('"').Trim("'")

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$releaseName = "release-v$version-$timestamp"
$distDir = Join-Path $root "dist"
$releaseDir = Join-Path $distDir $releaseName
$appDir = Join-Path $releaseDir "app"
New-Item -ItemType Directory -Path $appDir -Force | Out-Null

$buildPython = if ($env:ANIMEVAULT_PYTHON) { $env:ANIMEVAULT_PYTHON } else { ".venv\Scripts\python.exe" }

Write-Host "==> Application version: $version" -ForegroundColor Cyan
Write-Host "==> Building with Nuitka..." -ForegroundColor Cyan

# Run Nuitka compilation
& $buildPython -m nuitka `
    --standalone `
    --windows-disable-console `
    --windows-icon-from-ico="src\animevault\resources\media\app.ico" `
    --include-data-dir="src\animevault\resources\media=animevault/resources/media" `
    --output-dir="$appDir" `
    "--follow-imports" `
    "--python-flag=-OO" `
    "--include-package=animevault.resources.media" `
    "src\animevault\cli.py"

if ($LASTEXITCODE -ne 0) {
    throw "Nuitka compilation failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path $appDir "AnimeVault.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Nuitka did not produce the expected executable: $exePath"
}

$exeInfo = Get-Item -LiteralPath $exePath
Write-Host "==> Nuitka build complete:" -ForegroundColor Green
Write-Host "    Executable: $exePath" -ForegroundColor Green
Write-Host "    Size: $($exeInfo.Length) bytes" -ForegroundColor Green

# Calculate SHA-256
$sha256 = Get-FileHash -LiteralPath $exePath -Algorithm SHA256
Write-Host "    SHA-256: $($sha256.Hash)" -ForegroundColor Green
