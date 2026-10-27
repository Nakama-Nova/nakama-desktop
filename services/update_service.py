"""
services/update_service.py

Find out whether a newer installer was published, download it, check it, and hand
it to the installer. Nothing is installed without the user pressing "Update now".

The installers live in a private GitHub repository, so the app does not talk to
GitHub: it asks the shop's own server (signed in as the staff member), which
reads the releases and sends the app to a short-lived signed download address.

Safety: the download is checked against the SHA-256 the server reports, and the
installer asks for nothing beyond what the first install did (per-user, no
administrator). The installer is not code-signed, so this protects against a
damaged or swapped download, not against a compromised server or GitHub account.
"""

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable

import requests

from services.api_client import APIClient, APIError, ForbiddenError
from services.session import Session
from services.version import APP_VERSION, parse_version

INSTALLER_NAME = re.compile(r"^VrikshaStudiosDesk-Setup-[0-9A-Za-z.\-]+\.exe$")
TIMEOUT = 15


class UpdateError(Exception):
    """Something went wrong; the message is safe to show to the user."""


@dataclass
class UpdateInfo:
    version: str
    notes: str
    installer_name: str
    sha256: str
    size: int


def check_for_update(current: str = APP_VERSION, api: APIClient | None = None) -> UpdateInfo | None:
    """The newest published version if it is newer than `current`, else None.

    Raises UpdateError when the check itself fails (offline, signed out, the
    server has no update source set up).
    """
    mine = parse_version(current)
    if mine is None:
        return None  # a development build: never prompt
    api = api or APIClient()
    try:
        data = api._get("/app/updates/latest", Session.get_token(), quiet=True)
    except ForbiddenError:
        raise UpdateError("You are not allowed to check for updates.") from None
    except APIError as e:
        if e.status_code == 404:
            return None  # nothing published yet
        if e.status_code == 401:
            raise UpdateError("Sign in again to check for updates.") from None
        raise UpdateError(str(e)) from None
    except requests.RequestException:
        raise UpdateError("Could not reach the server to check for updates.") from None

    latest = parse_version(data.get("version"))
    name = data.get("installer_name") or ""
    digest = (data.get("sha256") or "").lower()
    if latest is None or latest <= mine:
        return None
    if not INSTALLER_NAME.match(name) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateError("The server sent an update that does not look right, so it was ignored.")
    return UpdateInfo(
        version=".".join(str(x) for x in latest),
        notes=(data.get("notes") or "").strip(),
        installer_name=name,
        sha256=digest,
        size=int(data.get("size") or 0),
    )


def download_installer(
    info: UpdateInfo,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    get=requests.get,
    folder: str | None = None,
    base_url: str | None = None,
    token: str | None = None,
) -> str:
    """Download the installer, verify its SHA-256, return the file path."""
    base = (base_url or APIClient()._base_url).rstrip("/")
    headers = {"Authorization": f"Bearer {token or Session.get_token()}"}
    folder = folder or tempfile.mkdtemp(prefix="vriksha-update-")
    path = os.path.join(folder, info.installer_name)
    digest = hashlib.sha256()
    done = 0
    try:
        # The server answers with a redirect to a signed address; requests drops the
        # sign-in header when the redirect goes to another host.
        with get(f"{base}/app/updates/download/{info.version}", headers=headers, stream=True, timeout=TIMEOUT) as resp:
            if resp.status_code == 401:
                raise UpdateError("Sign in again to download the update.")
            if resp.status_code != 200:
                raise UpdateError(f"The download failed (the server said {resp.status_code}).")
            total = int(resp.headers.get("Content-Length") or info.size or 0)
            with open(path, "wb") as out:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if cancelled():
                        raise UpdateError("The update was cancelled.")
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException:
        _remove(path)
        raise UpdateError("The download was interrupted. Check the connection and try again.") from None
    except UpdateError:
        _remove(path)
        raise
    if digest.hexdigest() != info.sha256:
        _remove(path)
        raise UpdateError("The downloaded file is damaged (checksum mismatch), so it was not installed.")
    return path


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def launch_installer(path: str, popen=subprocess.Popen) -> None:
    """Start the installer; the caller then quits the app so its files can be replaced.

    /SILENT shows only a small progress window and the installer restarts the app
    when it finishes (see installer.iss).
    """
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    popen(
        [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=flags,
        close_fds=True,
    )
