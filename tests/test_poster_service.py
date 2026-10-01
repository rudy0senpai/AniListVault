"""Tests for poster downloading, caching, validation, and cleanup."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch
import urllib.error

import pytest

from animevault.models.anime import Anime
from animevault.services.poster import (
    download_poster,
    get_poster_path_for_url,
    is_valid_image,
    set_posters_dir,
)


class DummyResponse:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestPosterService:
    def setup_method(self):
        self._tmp_posters = Path("scratch/test_posters")
        set_posters_dir(self._tmp_posters)

    def teardown_method(self):
        if self._tmp_posters.exists():
            for f in self._tmp_posters.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass

    def test_image_validation(self):
        # Valid JPEG magic bytes
        assert is_valid_image(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        # Valid PNG magic bytes
        assert is_valid_image(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        # Valid WebP magic bytes
        assert is_valid_image(b"RIFF\x24\x00\x00\x00WEBPVP8 ")
        # Invalid / plain text or HTML error page
        assert not is_valid_image(b"<html>404 Not Found</html>")
        assert not is_valid_image(b"")

    def test_download_poster_success(self):
        # Fake 1KB JPEG data
        fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 1024
        with patch("urllib.request.urlopen", return_value=DummyResponse(fake_jpeg)):
            path_str = download_poster("https://example.com/poster.jpg")
            assert path_str is not None
            path = Path(path_str)
            assert path.exists()
            assert path.stat().st_size > 1000

    def test_poster_failure_returns_none_and_does_not_crash(self):
        http_err = urllib.error.HTTPError(
            url="https://example.com/bad_poster.jpg",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b"Not Found"),
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            # Must return None, never raise
            result = download_poster("https://example.com/bad_poster.jpg")
            assert result is None

    def test_corrupt_partial_download_discarded(self):
        # Returns HTML instead of image
        corrupt_data = b"<html>500 Internal Server Error</html>"
        with patch("urllib.request.urlopen", return_value=DummyResponse(corrupt_data)):
            result = download_poster("https://example.com/corrupt.png")
            assert result is None
            # No corrupted file left in posters dir
            assert len(list(self._tmp_posters.glob("*.png"))) == 0

    def test_poster_failure_does_not_prevent_anime_save(self, isolated_database):
        # Simulating search result with broken poster URL
        with patch("animevault.services.poster.download_poster", return_value=None):
            anime = Anime.create(
                title="Naruto",
                poster_url="https://example.com/broken.jpg",
            )
            assert anime.id is not None
            assert anime.poster_url == "https://example.com/broken.jpg"
            assert anime.poster_path == ""

    def test_delete_anime_cleans_up_poster_file(self, isolated_database):
        self._tmp_posters.mkdir(parents=True, exist_ok=True)
        poster_file = self._tmp_posters / "naruto_poster.jpg"
        poster_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 600)

        anime = Anime.create(
            title="Naruto",
            poster_path=str(poster_file),
        )
        assert poster_file.exists()

        # Delete anime
        anime.delete()

        # File must be cleaned up
        assert not poster_file.exists()
