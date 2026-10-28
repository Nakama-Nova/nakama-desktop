"""
services/notifications_service.py

Asks the server "what happened since <time>?" (website orders, money received, stock
running low, finished 3D scans) and remembers what the user has already been told:
the time to ask from, the ids already shown, and the recent list for the bell.
The server decides who may hear what; this only keeps the bookkeeping.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from services.api_client import APIClient
from services.session import Session

KEEP_SEEN = 300  # ids remembered, so a repeat is never shown
KEEP_RECENT = 50  # what the bell lists
TOAST_AT_MOST = 3  # more than this at once is summed up in one pop-up

# what a notification opens: server screen name -> sidebar label
SCREEN_LABELS = {"orders": "Orders", "stock": "Stock", "restoration": "Restoration"}


def state_path() -> Path:
    """One file per signed-in user: what one person is told is not shown to the next person at this PC."""
    return Path("data") / f"notifications-{Session.get_user_id() or 'anyone'}.json"


def _empty_state() -> dict:
    return {"since": None, "seen": [], "recent": [], "unread": 0, "popups": True}


def load_state(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or state_path()).read_text(encoding="utf-8"))
        return {**_empty_state(), **data}
    except (OSError, ValueError):
        return _empty_state()


def save_state(state: dict, path: Path | None = None) -> None:
    target = path or state_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass  # losing the bookkeeping only means a repeat pop-up, never a failed screen


def absorb(state: dict, feed: dict) -> list[dict]:
    """Take a server answer into the state. Returns the items that are new to this PC."""
    new = [x for x in feed.get("items", []) if x["id"] not in set(state["seen"])]
    state["since"] = feed.get("server_time") or state["since"]
    state["seen"] = (state["seen"] + [x["id"] for x in new])[-KEEP_SEEN:]
    state["recent"] = (new[::-1] + state["recent"])[:KEEP_RECENT]  # newest first
    state["unread"] = min(state["unread"] + len(new), KEEP_RECENT)
    return new


def popup_text(new: list[dict]) -> tuple[str, str]:
    """The title and text of the pop-up for these new items."""
    if len(new) <= TOAST_AT_MOST:
        title = new[0]["title"] if len(new) == 1 else f"{len(new)} new notifications"
        body = new[0]["body"] if len(new) == 1 else "\n".join(x["title"] for x in new)
        return title, body
    return f"{len(new)} new notifications", "\n".join(x["title"] for x in new[:TOAST_AT_MOST]) + f"\nand {len(new) - TOAST_AT_MOST} more"


def local_time(iso: str) -> str:
    """A short local time for the list: 14:05 today, or 27 Oct 14:05."""
    try:
        at = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return ""
    now = datetime.now(timezone.utc).astimezone()
    return at.strftime("%H:%M") if at.date() == now.date() else at.strftime("%d %b %H:%M")


class NotificationsService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def fetch(self, since: str | None) -> dict:
        """One poll. Without `since` the server only says where to start."""
        params = {"since": since} if since else None
        return self._api._get("/notifications", Session.get_token(), params=params, quiet=True)
