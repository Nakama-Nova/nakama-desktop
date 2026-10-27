"""
services/update_service.py

Find out whether a newer installer was published on GitHub, download it, check
it, and hand it to the installer. Nothing is installed without the user pressing
"Update now".

Safety: only the project's own GitHub release address is accepted, the download
is checked against the SHA-256 published next to it, and the installer asks for
nothing beyond what the first install did (per-user, no administrator).
The installer is not code-signed, so this protects against a damaged or swapped
download, not against a compromised GitHub account.
"""

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable

import requests

from services.version import APP_VERSION, parse_version

REPO = "Nakama-Nova/nakama-desktop"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
INSTALLER_NAME = re.compile(r"^VrikshaStudiosDesk-Setup-[0-9A-Za-z.\-]+\.exe$")
TIMEOUT = 15


class UpdateError(Exception):
    """Something went wrong; the message is safe to show to the user."""


@dataclass
class UpdateInfo:
    version: str
    notes: str
    installer_url: str
    installer_name: str
    sha256_url: str
    size: int


def check_for_update(current: str = APP_VERSION, get=requests.get) -> UpdateInfo | None:
    """The newest published release if it is newer than `current`, else None.

    Raises UpdateError when the check itself fails (offline, rate limited).
    """
    mine = parse_version(current)
    if mine is None:
        return None  # a development build: never prompt
    try:
        resp = get(LATEST_URL, timeout=TIMEOUT, headers={"Accept": "application/vnd.github+json"})
    except requests.RequestException:
        raise UpdateError("Could not reach GitHub to check for updates.") from None
    if resp.status_code == 404:
        return None  # nothing published yet
    if resp.status_code != 200:
        raise UpdateError(f"The update check failed (GitHub said {resp.status_code}).")
    release = resp.json()
    latest = parse_version(release.get("tag_name"))
    if latest is None or latest <= mine:
        return None
    assets = {a["name"]: a for a in release.get("assets", [])}
    installer = next((a for n, a in assets.items() if INSTALLER_NAME.match(n)), None)
    checksum = assets.get(f"{installer['name']}.sha256") if installer else None
    if not installer or not checksum:
        return None  # a release without the installer files is not an update for us
    for a in (installer, checksum):
        if not a["browser_download_url"].startswith(DOWNLOAD_PREFIX):
            raise UpdateError("The update points somewhere unexpected, so it was ignored.")
    return UpdateInfo(
        version=".".join(str(x) for x in latest),
        notes=(release.get("body") or "").strip(),
        installer_url=installer["browser_download_url"],
        installer_name=installer["name"],
        sha256_url=checksum["browser_download_url"],
        size=int(installer.get("size") or 0),
    )


def download_installer(
    info: UpdateInfo,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    get=requests.get,
    folder: str | None = None,
) -> str:
    """Download the installer, verify its SHA-256, return the file path."""
    try:
        text = get(info.sha256_url, timeout=TIMEOUT).text
        expected = text.split()[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError
    except (requests.RequestException, ValueError, IndexError):
        raise UpdateError("Could not read the update's checksum, so nothing was installed.") from None

    folder = folder or tempfile.mkdtemp(prefix="vriksha-update-")
    path = os.path.join(folder, info.installer_name)
    digest = hashlib.sha256()
    done = 0
    try:
        with get(info.installer_url, stream=True, timeout=TIMEOUT) as resp:
            if resp.status_code != 200:
                raise UpdateError(f"The download failed (GitHub said {resp.status_code}).")
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
    if digest.hexdigest() != expected:
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
