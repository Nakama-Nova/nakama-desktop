"""
services/inventory_service.py

Inventory domain service — fetches items from the backend.
Used by InventoryWindow and SalesScreen.
"""

from services.api_client import APIClient
from services.session import Session


class InventoryService:
    """Inventory item operations."""

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def get_items(self) -> list | None:
        """Return all inventory items, or None on failure."""
        return self._api.get_items(Session.get_token())

    def create(self, **data) -> dict | None:
        """Create a new item."""
        return self._api._post("/items", Session.get_token(), json=data)

    def update(self, item_id: str, **data) -> dict | None:
        """Update an existing item."""
        return self._api._put(f"/items/{item_id}", Session.get_token(), json=data)

    def delete(self, item_id: str) -> bool:
        """Delete an item."""
        return self._api._delete(f"/items/{item_id}", Session.get_token())
