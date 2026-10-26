"""
services/lab_service.py

3D Lab: list the furniture pieces and open the Lab in the browser.

The Lab itself (viewer and editor) is a web page served by the backend. The
desktop only asks the backend for a short-lived link and opens it. The link is
not a login: it works for the Lab only.
"""

import webbrowser

from services.api_client import APIClient
from services.inventory_service import InventoryService
from services.session import Session


class LabService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _token(self) -> str:
        return Session.get_token()

    def list_furniture(self) -> list:
        """Furniture pieces set up in the Lab (id, name, sku, parts, sizes)."""
        return self._api.get_lab_items(self._token()) or []

    def all_items(self) -> list:
        """Every catalogue item (owner/manager choose one to set up as furniture)."""
        return InventoryService(self._api).get_items() or []

    def open(self, item_id: str, edit: bool = False) -> str | None:
        """Ask for a link and open it in the browser. Returns the URL, or None on failure."""
        link = self._api.create_lab_link(
            self._token(), item_id, "edit" if edit else "view"
        )
        if not link:
            return None
        webbrowser.open(link["url"])
        return link["url"]
