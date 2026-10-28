"""
services/designs_service.py

Designs (DES-0001): reusable patterns, optionally taken from a restoration, that build
sculpture products. Owner and artisans only; the server enforces it.
"""

from services.api_client import APIClient
from services.session import Session

DESIGN_STATUSES = [("Draft", "draft"), ("Ready", "ready"), ("Retired", "retired")]
DESIGN_STATUS_WORDS = {value: label for label, value in DESIGN_STATUSES}
TYPE_WORDS = {"furniture": "Furniture", "sculpture": "Sculpture"}


class DesignsService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def designs(self, status=None, search=None, item_id=None) -> list:
        params = {"status": status, "search": search or None, "item_id": item_id}
        return self._api._get("/designs", self._t(), params=params) or []

    def design(self, design_id: str) -> dict:
        return self._api._get(f"/designs/{design_id}", self._t())

    def create(self, data: dict) -> dict:
        return self._api._post("/designs", self._t(), json=data)

    def update(self, design_id: str, data: dict) -> dict:
        return self._api._patch(f"/designs/{design_id}", self._t(), json=data)

    def link(self, design_id: str, item_id: str) -> list:
        return self._api._post(f"/designs/{design_id}/products", self._t(), json={"item_id": item_id})

    def unlink(self, design_id: str, item_id: str) -> bool:
        return self._api._delete(f"/designs/{design_id}/products/{item_id}", self._t())

    def create_product(self, design_id: str, data: dict) -> dict:
        return self._api._post(f"/designs/{design_id}/create-product", self._t(), json=data)
