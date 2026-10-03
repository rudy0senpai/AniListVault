<#
.SYNOPSIS
    Removes an installed AnimeVault, including its data.

.DESCRIPTION
    Prefers the registered uninstaller (which Windows records under
    "Apps & features"). Falls back to deleting the install folder and the
    user data folder directly.

.PARAMETER PurgeData
    Also delete the library database, cached posters and settings.
    Without this, your library is left untouched.

.EXAMPLE
    .\packaging\uninstall.ps1
    .\packaging\uninstall.ps1 -PurgeData
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$PurgeData
)

$ErrorActionPreference = "Stop"

# Ask Windows where it installed AnimeVault, if it did.
$installDir = $null
try {
    $keys = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($key in $keys) {
        $entry = Get-ItemProperty $key -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -eq "AnimeVault" } |
            Select-Object -First 1
        if ($entry) {
            if ($entry.UninstallString) { $installDir = $entry.InstallLocation }
            if (-not $installDir -and $entry.UninstallString) {
                if ($entry.UninstallString -match '"([^"]+)"') {
                    $installDir = Split-Path -Parent $Matches[1]
                }
            }
            break
        }
    }
} catch { }

if ($installDir -and (Test-Path $installDir)) {
    $uninstaller = Join-Path $installDir "unins000.exe"
    if (Test-Path $uninstaller) {
        if ($PSCmdlet.ShouldProcess($uninstaller, "Run AnimeVault uninstaller")) {
            Write-Host "==> Running registered uninstaller" -ForegroundColor Cyan
            # /VERYSILENT /SUPPRESSMSGBOXES so it can run unattended.
            $proc = Start-Process -FilePath $uninstaller `
                -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" `
                -Wait -PassThru
            Write-Host "    Uninstaller exited with code $($proc.ExitCode)" -ForegroundColor DarkGray
        }
    }
    elseif ($PSCmdlet.ShouldProcess($installDir, "Delete install folder")) {
        Write-Host "==> Removing $installDir" -ForegroundColor Cyan
        Remove-Item -Path $installDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
else {
    Write-Host "==> No installed copy found; nothing to uninstall." -ForegroundColor Yellow
}

# User data lives outside the install folder.
$dataDir = Join-Path $env:APPDATA "AnimeVault"
if ($PurgeData) {
    if (Test-Path $dataDir) {
        if ($PSCmdlet.ShouldProcess($dataDir, "Delete AnimeVault data")) {
            Write-Host "==> Purging data at $dataDir" -ForegroundColor Cyan
            Remove-Item -Path $dataDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
elseif (Test-Path $dataDir) {
    Write-Host "==> Library data kept at $dataDir" -ForegroundColor DarkGray
    Write-Host "    Re-run with -PurgeData to delete it." -ForegroundColor DarkGray
}

Write-Host "==> Done." -ForegroundColor Green