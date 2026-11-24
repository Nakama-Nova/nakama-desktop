"""
services/app_settings.py

This computer's own preferences, kept in data/settings.json next to the local database (the
installed program keeps that folder in %LOCALAPPDATA%\\VrikshaStudios). Nothing here goes to the
server: they are about how this desk behaves, not about the shop's data.

    get("default_payment")        # "cash" | "none"
    set_value("open_bill_pdf", False)

A missing, unreadable or hand-edited file never breaks the program: it falls back to the
defaults, and values of the wrong kind are ignored.

The server address is not in that file: the program reads it from `.env` when it starts, so it
is read and written there (read_server_address, write_server_address).
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULTS = {
    "default_payment": "cash",  # how a new bill starts on New Bill: "cash" or "none" (not paid yet)
    "open_bill_pdf": True,  # open the bill's PDF as soon as it is created
    "auto_updates": True,  # check for a newer version in the background (installed program only)
    "theme": "light",  # "light" or "dark"; read when the program starts
    "recent_items": [],  # ids of the last products put on a bill here, newest first (quick-add chips)
}
_CHOICES = {"default_payment": ("cash", "none"), "theme": ("light", "dark")}


def settings_path() -> Path:
    return Path("data") / "settings.json"


def _valid(key: str, value) -> bool:
    if key not in DEFAULTS:
        return False
    if key in _CHOICES:
        return value in _CHOICES[key]
    if key == "recent_items":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(DEFAULTS[key]))


def load() -> dict:
    """Every setting, with the default for any that is missing or invalid."""
    values = dict(DEFAULTS)
    try:
        saved = json.loads(settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return values
    except (OSError, ValueError):
        logger.warning("settings.json could not be read; using the defaults")
        return values
    if isinstance(saved, dict):
        values.update({k: v for k, v in saved.items() if _valid(k, v)})
    return values


def get(key: str):
    return load()[key]


def save(values: dict) -> None:
    """Keep these settings (unknown or invalid ones are dropped). Raises OSError if the file
    cannot be written, so the screen can say so."""
    merged = load()
    merged.update({k: v for k, v in values.items() if _valid(k, v)})
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def set_value(key: str, value) -> None:
    save({key: value})


# ---------------------------------------------------------------- server address (.env)
ENV_KEY = "API_BASE_URL"
_URL = re.compile(r"^https?://[^\s/:]+(:\d{1,5})?(/[^\s]*)?$", re.IGNORECASE)


def env_path() -> Path:
    return Path(".env")


def clean_server_address(text: str) -> str | None:
    """The address as the program will use it (no trailing slash), or None when it is not an
    http:// or https:// address."""
    text = (text or "").strip().rstrip("/")
    return text if _URL.match(text) else None


def read_server_address(default: str = "") -> str:
    try:
        for line in env_path().read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith(ENV_KEY + "="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return default


def write_server_address(address: str) -> None:
    """Set API_BASE_URL in .env, leaving its other lines alone. Raises ValueError for a bad
    address and OSError if the file cannot be written."""
    clean = clean_server_address(address)
    if clean is None:
        raise ValueError("The address must start with http:// or https://, for example https://api.example.com")
    path = env_path()
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for line in lines:
        if line.strip().startswith(ENV_KEY + "="):
            if not done:
                out.append(f"{ENV_KEY}={clean}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{ENV_KEY}={clean}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def is_unencrypted_remote(address: str) -> bool:
    """http:// to a machine that is not this one: passwords and bills would cross the network in the open."""
    clean = clean_server_address(address) or ""
    host = re.sub(r"^https?://", "", clean, flags=re.IGNORECASE).split("/")[0].split(":")[0].lower()
    return clean.lower().startswith("http://") and host not in ("localhost", "127.0.0.1", "::1")
