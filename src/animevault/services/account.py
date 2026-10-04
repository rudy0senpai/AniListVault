"""Optional Google account connection for cloud sync.

Design notes
------------
* **Login is optional.** The application is fully usable with no account;
  every function here is a no-op until the user explicitly connects one.
* **Login is not sync.** Connecting a Google account only proves
  identity and grants access to a Drive folder.  The library itself is
  synchronised as a file in that folder (see :mod:`sync_service`), which
  keeps the app free of a hosted backend.
* **No password ever touches this app.**  Sign-in happens in the user's
  browser via Google's OAuth consent screen.
* **Private entries never leave the machine** unless the user opts in.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

#: Google OAuth client id for a *desktop* app.  Replace with your own from
#: https://console.cloud.google.com/apis/credentials (Desktop app).
DEFAULT_CLIENT_ID = os.environ.get("ANIMEVAULT_GOOGLE_CLIENT_ID", "")

#: Drive API endpoint.  Overridable for testing.
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_API = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

#: Only these scopes are requested: sign-in, then Drive file access.
SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/drive.file",
)

#: Where tokens are cached.  Kept inside the app's data directory.
TOKEN_FILENAME = "google_token.json"

# Drive API scope used to create the app's folder, granted only when the
# user agrees to use a dedicated app folder.
SCOPE_APP_FOLDER = "https://www.googleapis.com/auth/drive.appDataFolder"


def app_data_dir() -> Path:
    """The per-user application data directory."""
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / "AnimeVault"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_path() -> Path:
    return app_data_dir() / TOKEN_FILENAME


# ── Token storage ──────────────────────────────────────────────────

@dataclass
class Account:
    """A connected Google account.

    ``connected`` is the only thing the UI needs to branch on; the app is
    fully functional when this is ``False``.
    """

    email: str = ""
    connected: bool = False
    drive_folder_id: str = ""
    last_sync: str = ""
    auto_sync: bool = True

    def as_dict(self) -> dict:
        return {
            "email": self.email,
            "connected": self.connected,
            "drive_folder_id": self.drive_folder_id,
            "last_sync": self.last_sync,
            "auto_sync": self.auto_sync,
        }


def _restrict(path: Path) -> None:
    """Best-effort protection of the token file on POSIX systems."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows ACLs already restrict the user's profile.


def save_tokens(tokens: dict) -> None:
    """Persist OAuth tokens with a restricted file mode."""
    path = token_path()
    path.write_text(json.dumps(tokens), encoding="utf-8")
    _restrict(path)


def load_tokens() -> Optional[dict]:
    """Return stored tokens, or ``None`` when not connected."""
    path = token_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Stored Google token is unreadable: %s", exc)
        return None
    return data if data.get("access_token") else None


def disconnect() -> None:
    """Remove the stored token and forget the account.

    The local library is untouched — signing out never deletes data.
    """
    token_path().unlink(missing_ok=True)
    settings = app_data_dir() / "account.json"
    settings.unlink(missing_ok=True)


def load_account() -> Account:
    """Read the account record, if one exists."""
    path = app_data_dir() / "account.json"
    if not path.exists():
        return Account()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Account()
    return Account(
        email=data.get("email", ""),
        connected=bool(data.get("connected")),
        drive_folder_id=data.get("drive_folder_id", ""),
        last_sync=data.get("last_sync", ""),
        auto_sync=bool(data.get("auto_sync", True)),
    )


def save_account(account: Account) -> None:
    (app_data_dir() / "account.json").write_text(
        json.dumps(account.as_dict(), indent=2), encoding="utf-8"
    )


def mark_synced(folder_id: str = "") -> None:
    """Record that a sync just completed."""
    account = load_account()
    account.last_sync = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if folder_id:
        account.drive_folder_id = folder_id
    save_account(account)


def is_configured() -> bool:
    """Whether a Google client id has been supplied.

    Without it the UI offers import/export only, rather than presenting a
    sign-in button that cannot work.
    """
    return bool(DEFAULT_CLIENT_ID.strip())


def requires_client_id() -> str:
    """Human-readable explanation shown when no client id is configured."""
    return (
        "Cloud sync needs a Google OAuth client id.\n\n"
        "1. Open https://console.cloud.google.com/apis/credentials\n"
        "2. Create an OAuth client ID → Application → Desktop app\n"
        "3. Set the environment variable ANIMEVAULT_GOOGLE_CLIENT_ID\n\n"
        "Until then, AnimeVault works fully offline and you can still use\n"
        "Export and Import to move your library manually."
    )