"""Poster image download and caching service."""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_POSTERS_DIR: Path = (
    Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault" / "posters"
)


def set_posters_dir(path: Path) -> None:
    """Override poster storage directory (for tests)."""
    global _POSTERS_DIR
    _POSTERS_DIR = path


def get_posters_dir() -> Path:
    return _POSTERS_DIR


def is_valid_image(data: bytes) -> bool:
    """Check magic bytes for common image formats (JPEG, PNG, WebP, GIF)."""
    if len(data) < 12:
        return False
    # JPEG: \xff\xd8\xff
    if data.startswith(b"\xff\xd8\xff"):
        return True
    # PNG: \x89PNG\r\n\x1a\n
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    # GIF: GIF87a or GIF89a
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return True
    # WebP: RIFF....WEBP
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    return False


def get_poster_path_for_url(url: str) -> Path:
    """Deterministically map a poster URL to a local cache filename."""
    h = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:24]
    ext = ".jpg"
    lower = url.lower()
    if ".png" in lower:
        ext = ".png"
    elif ".webp" in lower:
        ext = ".webp"
    return _POSTERS_DIR / f"poster_{h}{ext}"


def download_poster(url: str, timeout: int = 15) -> Optional[str]:
    """Download an image from *url* and save it to the poster cache.

    Returns the absolute string path to the cached image on success, or
    ``None`` if the download or image validation fails.
    """
    if not url or not url.strip().startswith("http"):
        return None

    url = url.strip()
    target_path = get_poster_path_for_url(url)

    # Return cached image if it already exists and is non-empty
    if target_path.exists() and target_path.stat().st_size > 512:
        return str(target_path)

    _POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(f".tmp_{os.getpid()}_{hashlib.md5(url.encode()).hexdigest()[:8]}")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AnimeVault/0.2 (ImageDownloader)",
            "Accept": "image/webp,image/png,image/jpeg,image/*;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()

        if not is_valid_image(data):
            logger.warning("Poster at %r is not a valid image format", url)
            return None

        tmp_path.write_bytes(data)
        os.replace(tmp_path, target_path)
        return str(target_path)
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP error %s downloading poster from %s", exc.code, url)
        return None
    except urllib.error.URLError as exc:
        logger.warning("Network error downloading poster from %s: %s", url, exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error downloading poster from %s: %s", url, exc)
        return None
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
