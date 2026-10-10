# Repairs the uninstall registration for an already-installed AnimeVault.
#
# The original installer copied *itself* to uninstall.exe, so Uninstall
# re-installed the app instead of removing it, and left UninstallString
# empty so Windows showed no working Uninstall button.
#
# This script installs the real uninstaller and rewrites the registry entry.
# Safe to re-run.

$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:LOCALAPPDATA "Programs\AnimeVault"
$uninstaller = Join-Path $installDir "uninstall.exe"
$source = Join-Path $PSScriptRoot "..\dist\uninstall.exe"
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AnimeVault"

if (-not (Test-Path $installDir)) {
    Write-Host "AnimeVault is not installed at $installDir" -ForegroundColor Yellow
    exit 0
}

# 1. Replace the fake uninstaller (a copy of the installer) with the real one.
if (-not (Test-Path $source)) {
    Write-Host "Built uninstaller not found at $source" -ForegroundColor Red
    Write-Host "Build it first:  .\packaging\build_installer.py" -ForegroundColor Yellow
    exit 1
}

Copy-Item $source $uninstaller -Force
Write-Host "Installed real uninstaller: $uninstaller" -ForegroundColor Green

# 2. Remove the stale helper script from the old installer, if present.
$cleanup = Join-Path $installDir "cleanup.py"
if (Test-Path $cleanup) {
    Remove-Item $cleanup -Force -ErrorAction SilentlyContinue
}

# 3. Write the registry entry Windows needs for a working Uninstall button.
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name "DisplayName"     -Value "AnimeVault"
$versionSource = Join-Path $PSScriptRoot "..\src\animevault\_version.py"
$versionMatch = [regex]::Match((Get-Content -LiteralPath $versionSource -Raw), '__version__\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) { throw "Could not load canonical app version from $versionSource" }
$appVersion = $versionMatch.Groups[1].Value
Set-ItemProperty -Path $key -Name "DisplayVersion"  -Value $appVersion
Set-ItemProperty -Path $key -Name "Publisher"       -Value "AnimeVault"
Set-ItemProperty -Path $key -Name "DisplayIcon"     -Value (Join-Path $installDir "AnimeVault.exe")
Set-ItemProperty -Path $key -Name "InstallLocation" -Value $installDir
Set-ItemProperty -Path $key -Name "NoModify"        -Value 1 -Type DWord
Set-ItemProperty -Path $key -Name "NoRepair"        -Value 1 -Type DWord
Set-ItemProperty -Path $key -Name "SystemComponent" -Value 0 -Type DWord
Set-ItemProperty -Path $key -Name "InstallState"    -Value 1 -Type DWord
Set-ItemProperty -Path $key -Name "UninstallString"       -Value ('"' + $uninstaller + '"')
Set-ItemProperty -Path $key -Name "QuietUninstallString"  -Value ('"' + $uninstaller + '" /S')

Write-Host "Registered uninstall entry." -ForegroundColor Green
Write-Host ""
Write-Host "Uninstall now via:" -ForegroundColor Cyan
Write-Host "  Windows Settings > Apps > Installed apps > AnimeVault > Uninstall"
Write-Host "  or run: $uninstaller"
Write-Host ""
Write-Host "Your library is kept in $(Join-Path $env:APPDATA 'AnimeVault')" -ForegroundColor DarkGray