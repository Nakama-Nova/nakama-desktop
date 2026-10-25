"""
services/inventory_service.py

Inventory domain service — fetches items from the backend.
Used by InventoryWindow and SalesScreen.
"""

import json
from pathlib import Path

import requests

from services.api_client import APIClient
from services.session import Session

# Last item list the backend returned. Lets the New Bill screen list items
# when the app starts without a connection (counter keeps selling offline).
ITEMS_CACHE = Path("data") / "items_cache.json"


class InventoryService:
    """Inventory item operations."""

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def get_items(self, allow_cached: bool = False) -> list | None:
        """
        Return all inventory items, or None on failure.

        With allow_cached, a connection failure falls back to the last list
        saved here (possibly stale); without it the error propagates as before.
        """
        try:
            items = self._api.get_items(Session.get_token())
        except requests.RequestException:
            if not allow_cached:
                raise
            return self._read_cache()
        if items is not None and allow_cached:
            self._write_cache(items)
        return items

    @staticmethod
    def _write_cache(items: list) -> None:
        try:
            ITEMS_CACHE.parent.mkdir(exist_ok=True)
            ITEMS_CACHE.write_text(json.dumps(items), encoding="utf-8")
        except OSError:
            pass  # the cache is a convenience; never break billing over it

    @staticmethod
    def _read_cache() -> list | None:
        try:
            return json.loads(ITEMS_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def create(self, **data) -> dict | None:
        """Create a new item."""
        return self._api._post("/items", Session.get_token(), json=data)

    def update(self, item_id: str, **data) -> dict | None:
        """Update an existing item."""
        return self._api._put(f"/items/{item_id}", Session.get_token(), json=data)

    def delete(self, item_id: str) -> bool:
        """Delete an item."""
        return self._api._delete(f"/items/{item_id}", Session.get_token())
