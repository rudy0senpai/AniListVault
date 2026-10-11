<#
.SYNOPSIS
    Rebuilds the current AnimeVault source as a Windows executable and installer.

.DESCRIPTION
    Uses PyInstaller --clean --onefile against src/animevault/cli.py in unique,
    versioned staging directories. On success it publishes the freshly built
    executable and Inno Setup installer to dist\AnimeVault.exe and
    dist\AnimeVault-Setup.exe. Older flat outputs are moved aside first so a
    failed build cannot leave a stale artifact at the usual path.

    Requires a Python environment with project dependencies and PyInstaller,
    plus Inno Setup 6 unless -SkipInstaller is specified.

.PARAMETER SkipInstaller
    Build and publish only the fresh portable executable.

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

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$releaseName = "release-v$version-$timestamp"
$distDir = Join-Path $root "dist"
$releaseDir = Join-Path $distDir $releaseName
$appDir = Join-Path $releaseDir "app"
$workDir = Join-Path (Join-Path $root "build") $releaseName
$specDir = Join-Path $workDir "spec"
$entryPoint = Join-Path $root "src\animevault\cli.py"
$iconPath = Join-Path $root "src\animevault\resources\media\app.ico"
$mediaPath = Join-Path $root "src\animevault\resources\media"
$stagedExe = Join-Path $appDir "AnimeVault.exe"
$portableExe = Join-Path $distDir "AnimeVault.exe"
$stagedSetup = Join-Path $releaseDir "AnimeVault-Setup.exe"
$portableSetup = Join-Path $distDir "AnimeVault-Setup.exe"
$manifestPath = Join-Path $distDir "AnimeVault-build.json"

foreach ($requiredPath in @($entryPoint, $iconPath, $mediaPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required source/build input is missing: $requiredPath"
    }
}
if ((Test-Path -LiteralPath $releaseDir) -or (Test-Path -LiteralPath $workDir)) {
    throw "Refusing to reuse a build directory: $releaseName"
}
New-Item -ItemType Directory -Path $appDir, $specDir -Force | Out-Null

$sourceRevision = "unknown"
$sourceWorktree = "unknown"
$gitCandidates = @(
    (Join-Path $env:ProgramFiles "Git\cmd\git.exe"),
    (Join-Path $env:ProgramFiles "Git\bin\git.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
$gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $gitCandidates -and $gitCommand -and $gitCommand.Source -notlike "*\WindowsApps\*") {
    $gitCandidates += $gitCommand.Source
}
$gitPath = $gitCandidates | Select-Object -First 1
if ($gitPath) {
    try {
        $revisionOutput = & $gitPath -C $root rev-parse --short HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $revisionOutput) {
            $sourceRevision = ($revisionOutput | Select-Object -First 1).Trim()
            $statusOutput = & $gitPath -C $root status --porcelain --untracked-files=normal 2>$null
            if ($LASTEXITCODE -eq 0) {
                $sourceWorktree = if ($statusOutput) { "dirty" } else { "clean" }
            }
        }
    } catch {
        Write-Warning "Could not read Git metadata; continuing with source revision unknown."
    }
}

# Do not let inherited global paths contaminate PyInstaller's module discovery.
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
$env:PYTHONNOUSERSITE = "1"
$env:ANIMEVAULT_VERSION = $version

$buildPython = if ($env:ANIMEVAULT_PYTHON) { $env:ANIMEVAULT_PYTHON } else { "python" }
$pythonCheck = & $buildPython -c "import PyInstaller; print(PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python ($buildPython) cannot import PyInstaller. Install project dependencies and PyInstaller in that environment."
}
$pyInstallerVersion = ($pythonCheck | Select-Object -Last 1).Trim()

# Preserve only the known generated flat outputs that could otherwise be
# mistaken for the current build. Versioned releases and all source/user data
# are left untouched.
$legacyOutputs = @(
    @{ Path = $portableExe; Name = "AnimeVault.exe" },
    @{ Path = $portableSetup; Name = "AnimeVault-Setup.exe" },
    @{ Path = (Join-Path $distDir "AnimeVault"); Name = "AnimeVault-onedir" }
)
$existingLegacy = @($legacyOutputs | Where-Object { Test-Path -LiteralPath $_.Path })
if ($existingLegacy.Count -gt 0) {
    $legacyDir = Join-Path $distDir "legacy-stale-$timestamp"
    New-Item -ItemType Directory -Path $legacyDir -Force | Out-Null
    foreach ($oldOutput in $existingLegacy) {
        Move-Item -LiteralPath $oldOutput.Path -Destination (Join-Path $legacyDir $oldOutput.Name)
    }
    Write-Host "==> Moved previous flat outputs to $legacyDir" -ForegroundColor Yellow
}

$buildStarted = Get-Date
Write-Host "==> Source revision: $sourceRevision ($sourceWorktree working tree)" -ForegroundColor Cyan
Write-Host "==> Application version: $version" -ForegroundColor Cyan
Write-Host "==> Building current source entry point: src/animevault/cli.py" -ForegroundColor Cyan
Write-Host "==> PyInstaller $pyInstallerVersion; clean one-file build" -ForegroundColor Cyan

& $buildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "AnimeVault" `
    --distpath $appDir `
    --workpath $workDir `
    --specpath $specDir `
    --paths (Join-Path $root "src") `
    --icon $iconPath `
    --add-data "$mediaPath;src/animevault/resources/media" `
    --collect-all PySide6 `
    --hidden-import "PySide6.QtMultimedia" `
    --hidden-import "PySide6.QtMultimediaWidgets" `
    $entryPoint
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $stagedExe -PathType Leaf)) {
    throw "PyInstaller did not produce the expected fresh executable: $stagedExe"
}
$exeInfo = Get-Item -LiteralPath $stagedExe
if ($exeInfo.Length -lt 1000000 -or $exeInfo.LastWriteTimeUtc -lt $buildStarted.ToUniversalTime().AddSeconds(-2)) {
    throw "The generated executable is missing, unexpectedly small, or older than this build: $stagedExe"
}
$exeHash = (Get-FileHash -LiteralPath $stagedExe -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "==> Fresh application executable: $stagedExe ($($exeInfo.Length) bytes; SHA-256 $exeHash)" -ForegroundColor Green

$setupInfo = $null
if (-not $SkipInstaller) {
    $isccCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($isccCommand) { $isccCandidates += $isccCommand.Source }
    $iscc = $isccCandidates | Select-Object -First 1
    if (-not $iscc) {
        throw "Inno Setup 6 (ISCC.exe) was not found. Install it or explicitly use -SkipInstaller."
    }

    Write-Host "==> Building installer from the freshly built app directory: $appDir" -ForegroundColor Cyan
    & $iscc "/Qp" "/DSourceDir=$appDir" "/DOutputDir=$releaseDir" "packaging\AnimeVault.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath $stagedSetup -PathType Leaf)) {
        throw "Inno Setup did not produce the expected installer: $stagedSetup"
    }
    $setupInfo = Get-Item -LiteralPath $stagedSetup
    if ($setupInfo.Length -lt 1000000 -or $setupInfo.LastWriteTimeUtc -lt $buildStarted.ToUniversalTime().AddSeconds(-2)) {
        throw "The generated installer is missing, unexpectedly small, or older than this build: $stagedSetup"
    }
    $setupHash = (Get-FileHash -LiteralPath $stagedSetup -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "==> Fresh installer: $stagedSetup ($($setupInfo.Length) bytes; SHA-256 $setupHash)" -ForegroundColor Green
}

# Publish the stable paths only after every requested build stage succeeded.
Copy-Item -LiteralPath $stagedExe -Destination $portableExe -Force
$publishedExeHash = (Get-FileHash -LiteralPath $portableExe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($publishedExeHash -ne $exeHash) {
    throw "Published executable checksum does not match the fresh staged build."
}
if ($setupInfo) {
    Copy-Item -LiteralPath $stagedSetup -Destination $portableSetup -Force
    $publishedSetupHash = (Get-FileHash -LiteralPath $portableSetup -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($publishedSetupHash -ne $setupHash) {
        throw "Published installer checksum does not match the fresh staged installer."
    }
}

$installerManifest = $null
if ($setupInfo) {
    $installerManifest = [ordered]@{
        path = "dist/AnimeVault-Setup.exe"
        versioned_path = $stagedSetup.Substring($root.Length + 1).Replace("\", "/")
        bytes = $setupInfo.Length
        sha256 = $setupHash
    }
}
$manifest = [ordered]@{
    application_version = $version
    source_revision = $sourceRevision
    source_worktree = $sourceWorktree
    entry_point = "src/animevault/cli.py"
    build_mode = "PyInstaller --clean --onefile --windowed"
    pyinstaller_version = $pyInstallerVersion
    build_started_utc = $buildStarted.ToUniversalTime().ToString("o")
    completed_utc = (Get-Date).ToUniversalTime().ToString("o")
    executable = [ordered]@{
        path = "dist/AnimeVault.exe"
        versioned_path = $stagedExe.Substring($root.Length + 1).Replace("\", "/")
        bytes = $exeInfo.Length
        sha256 = $exeHash
    }
    installer = $installerManifest
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "==> Published executable: $portableExe" -ForegroundColor Green
if ($setupInfo) {
    Write-Host "==> Published installer: $portableSetup" -ForegroundColor Green
} else {
    Write-Host "==> Installer intentionally skipped; no stale installer remains at the stable output path." -ForegroundColor Yellow
}
Write-Host "==> Build manifest: $manifestPath" -ForegroundColor Green
Write-Host "==> Versioned staging directory: $releaseDir" -ForegroundColor Green
Write-Host "==> PyInstaller work directory: $workDir" -ForegroundColor Green
