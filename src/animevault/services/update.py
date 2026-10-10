"""Safe GitHub Releases updater using HTTPS and verified installer digests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LATEST_RELEASE_API = "https://api.github.com/repos/rudy0senpai/AniListVault/releases/latest"
_INSTALLER_NAME = "AnimeVault-Setup.exe"
_MAX_INSTALLER_BYTES = 512 * 1024 * 1024
_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+){1,3})$", re.IGNORECASE)


class UpdateError(RuntimeError):
    """A release or installer could not be safely checked or downloaded."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    name: str
    notes: str
    page_url: str
    installer_url: str | None
    sha256: str | None


def _version_tuple(value: str) -> tuple[int, ...]:
    match = _VERSION_RE.fullmatch(value.strip())
    if not match:
        raise UpdateError(f"Invalid version string: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def _version_is_newer(candidate: str, current: str) -> bool:
    latest, installed = _version_tuple(candidate), _version_tuple(current)
    size = max(len(latest), len(installed))
    return latest + (0,) * (size - len(latest)) > installed + (0,) * (size - len(installed))


def parse_release_payload(payload: dict, current_version: str) -> UpdateInfo | None:
    """Return newer stable release metadata; never trusts non-HTTPS assets."""
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        return None
    tag = payload.get("tag_name", "")
    version_match = _VERSION_RE.fullmatch(tag.strip()) if isinstance(tag, str) else None
    if not version_match:
        raise UpdateError("The latest release has an invalid version tag.")
    version = version_match.group(1)
    if not _version_is_newer(version, current_version):
        return None

    page_url = payload.get("html_url", "")
    if not _is_https(page_url):
        raise UpdateError("The release page URL is not HTTPS.")

    asset_url = None
    digest = None
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict) or asset.get("name") != _INSTALLER_NAME:
            continue
        candidate_url = asset.get("browser_download_url", "")
        if _is_https(candidate_url):
            asset_url = candidate_url
            raw_digest = asset.get("digest", "")
            if isinstance(raw_digest, str) and raw_digest.startswith("sha256:"):
                candidate_digest = raw_digest.partition(":")[2].lower()
                if re.fullmatch(r"[0-9a-f]{64}", candidate_digest):
                    digest = candidate_digest
        break

    return UpdateInfo(
        version=version,
        name=str(payload.get("name") or f"AnimeVault {version}"),
        notes=str(payload.get("body") or ""),
        page_url=page_url,
        installer_url=asset_url,
        sha256=digest,
    )


def _is_https(url: object) -> bool:
    return isinstance(url, str) and urlparse(url).scheme == "https" and bool(urlparse(url).hostname)


def check_for_updates(current_version: str, *, timeout: float = 12.0) -> UpdateInfo | None:
    """Query the public latest stable release; returns None when current."""
    request = Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AnimeVault-Update-Checker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None  # No published GitHub Release yet.
        raise UpdateError(f"GitHub update check failed (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateError(f"Could not check for updates: {exc}") from exc
    return parse_release_payload(payload, current_version)


def download_installer(info: UpdateInfo, destination: str | Path) -> Path:
    """Download a release setup executable and atomically verify SHA-256."""
    if not info.installer_url or not info.sha256:
        raise UpdateError("This release has no HTTPS installer with a SHA-256 digest.")
    if not _is_https(info.installer_url):
        raise UpdateError("Refusing to download an installer over a non-HTTPS URL.")

    directory = Path(destination)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / _INSTALLER_NAME
    fd, temp_name = tempfile.mkstemp(prefix=".AnimeVault-Setup-", suffix=".download", dir=directory)
    digest = hashlib.sha256()
    total = 0
    try:
        request = Request(info.installer_url, headers={"User-Agent": "AnimeVault-Update-Checker"})
        with os.fdopen(fd, "wb") as output, urlopen(request, timeout=30) as response:
            if not _is_https(response.geturl()):
                raise UpdateError("The download redirected to a non-HTTPS URL.")
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_INSTALLER_BYTES:
                    raise UpdateError("The installer exceeds the 512 MiB download limit.")
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != info.sha256:
            raise UpdateError("Installer SHA-256 verification failed; the file was discarded.")
        os.replace(temp_name, target)
        return target
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def launch_installer(path: str | Path, expected_sha256: str) -> None:
    """Verify the setup again immediately before launching it, without a shell."""
    installer = Path(path).resolve(strict=True)
    if installer.name != _INSTALLER_NAME or installer.stat().st_size == 0:
        raise UpdateError("Refusing to launch an unexpected or empty installer file.")
    digest = hashlib.sha256()
    with installer.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise UpdateError("Installer SHA-256 verification failed before launch.")
    subprocess.Popen([str(installer)], close_fds=True)
