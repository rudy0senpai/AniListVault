"""Release-check and verified-update download behavior."""

import hashlib

import pytest

from animevault.services.update import (
    UpdateError,
    check_for_updates,
    download_installer,
    parse_release_payload,
)


def release_payload(version="v0.4.0", url="https://github.com/sample-owner/sample-repo/releases/download/v0.4.0/AnimeVault-Setup.exe", digest=None):
    asset = {
        "name": "AnimeVault-Setup.exe",
        "browser_download_url": url,
    }
    if digest is not None:
        asset["digest"] = digest
    return {
        "tag_name": version,
        "name": "AnimeVault 0.4.0",
        "body": "Bug fixes and improvements",
        "html_url": "https://github.com/sample-owner/sample-repo/releases/tag/v0.4.0",
        "draft": False,
        "prerelease": False,
        "assets": [asset],
    }


def test_release_parser_extracts_verified_setup_asset():
    expected = "ab" * 32
    info = parse_release_payload(release_payload(digest=f"sha256:{expected}"), "0.3.0")
    assert info is not None
    assert info.version == "0.4.0"
    assert info.sha256 == expected
    assert info.installer_url.endswith("AnimeVault-Setup.exe")


def test_parser_ignores_same_or_older_release():
    assert parse_release_payload(release_payload("v0.3.0"), "0.3.0") is None
    assert parse_release_payload(release_payload("v0.2.9"), "0.3.0") is None


def test_parser_does_not_mark_non_https_asset_installable():
    info = parse_release_payload(release_payload(url="http://example.test/setup.exe"), "0.3.0")
    assert info is not None
    assert info.installer_url is None


def test_download_checks_digest_and_writes_installer(tmp_path, monkeypatch):
    payload = b"verified installer bytes"
    digest = hashlib.sha256(payload).hexdigest()
    info = parse_release_payload(release_payload(digest=f"sha256:{digest}"), "0.3.0")

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, size=-1):
            nonlocal payload
            chunk, payload = payload[:size], payload[size:]
            return chunk
        def geturl(self):
            return info.installer_url

    monkeypatch.setattr("animevault.services.update.urlopen", lambda *_a, **_k: Response())
    output = download_installer(info, tmp_path)
    assert output.name == "AnimeVault-Setup.exe"
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest


def test_download_rejects_digest_mismatch_and_removes_partial_file(tmp_path, monkeypatch):
    info = parse_release_payload(release_payload(digest=f"sha256:{'00' * 32}"), "0.3.0")

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def __init__(self):
            self.sent = False
        def read(self, _size=-1):
            if self.sent:
                return b""
            self.sent = True
            return b"tampered"
        def geturl(self):
            return info.installer_url

    monkeypatch.setattr("animevault.services.update.urlopen", lambda *_a, **_k: Response())
    with pytest.raises(UpdateError, match="SHA-256"):
        download_installer(info, tmp_path)
    assert not (tmp_path / "AnimeVault-Setup.exe").exists()


def test_unavailable_release_endpoint_is_not_reported_as_up_to_date(monkeypatch):
    from urllib.error import HTTPError

    def missing(*_args, **_kwargs):
        raise HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr("animevault.services.update.urlopen", missing)
    with pytest.raises(UpdateError, match="returned 404"):
        check_for_updates(
            "0.3.1",
            release_api="https://api.github.com/repos/sample-owner/sample-repo/releases/latest",
        )


def test_default_private_repo_check_uses_github_cli_auth(monkeypatch):
    import json
    import subprocess

    from animevault.services.update import DEFAULT_RELEASE_API

    monkeypatch.delenv("ANIMEVAULT_RELEASE_API", raising=False)
    calls = []

    def gh_auth(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout="fake-token-for-test-only\n", stderr=""
        )

    payload = json.dumps(release_payload("v0.3.1")).encode("utf-8")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size=-1):
            return payload

    requests = []

    def open_url(request, **_kwargs):
        requests.append(request)
        return Response()

    monkeypatch.setattr("animevault.services.update.subprocess.run", gh_auth)
    monkeypatch.setattr("animevault.services.update.urlopen", open_url)

    assert check_for_updates("0.3.1") is None
    assert requests[0].full_url == DEFAULT_RELEASE_API
    assert requests[0].get_header("Authorization") == "Bearer fake-token-for-test-only"
    assert calls[0][0][:3] == ["gh", "auth", "token"]
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["timeout"] <= 5


def test_private_repo_404_recommends_signing_in_with_github_cli(monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.delenv("ANIMEVAULT_RELEASE_API", raising=False)
    monkeypatch.setattr(
        "animevault.services.update.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(
        "animevault.services.update.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPError("url", 404, "Not Found", {}, None)
        ),
    )
    with pytest.raises(UpdateError, match="gh auth login"):
        check_for_updates("0.3.1")


def test_release_source_must_be_configured_and_official():
    with pytest.raises(UpdateError, match="Enter an official HTTPS"):
        check_for_updates("0.3.1", release_api="https://example.com/latest")


def test_launch_requires_digest_match(tmp_path, monkeypatch):
    from animevault.services.update import launch_installer

    installer = tmp_path / "AnimeVault-Setup.exe"
    installer.write_bytes(b"ready to install")
    launched = []
    monkeypatch.setattr("animevault.services.update.subprocess.Popen", lambda *a, **k: launched.append((a, k)))
    expected = hashlib.sha256(b"ready to install").hexdigest()

    launch_installer(installer, expected)
    assert launched and launched[0][0][0] == [str(installer.resolve())]
    with pytest.raises(UpdateError, match="SHA-256"):
        launch_installer(installer, "00" * 32)
