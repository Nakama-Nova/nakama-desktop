"""
services/stock_service.py

Everything the stock screens need beyond plain items: categories and brands,
suppliers, raw materials, purchases, manual stock changes, the stock ledger and
product photos. Thin wrappers over the backend, owner/manager only (the server
enforces it).
"""

from services.api_client import APIClient
from services.session import Session


class StockService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    # ----- categories, brands, suppliers (same shape: list / save / delete)
    def rows(self, kind: str) -> list:
        """kind: 'categories' | 'brands' | 'suppliers'"""
        return self._api._get(f"/{kind}/", self._t()) or []

    def save_row(self, kind: str, data: dict, row_id: str | None = None) -> dict:
        if row_id:
            return self._api._put(f"/{kind}/{row_id}", self._t(), json=data)
        return self._api._post(f"/{kind}/", self._t(), json=data)

    def delete_row(self, kind: str, row_id: str) -> bool:
        return self._api._delete(f"/{kind}/{row_id}", self._t())

    # ----- manual stock change and the ledger
    def adjust_item(self, item_id: str, quantity: int, notes: str) -> dict:
        return self._api._patch(
            f"/items/{item_id}/stock",
            self._t(),
            json={"quantity": quantity, "notes": notes},
        )

    def movements(
        self,
        item_id: str | None = None,
        raw_material_id: str | None = None,
        limit: int = 100,
    ) -> list:
        params = {"limit": limit}
        if item_id:
            params["item_id"] = item_id
        if raw_material_id:
            params["raw_material_id"] = raw_material_id
        return self._api._get("/inventory/movements", self._t(), params=params) or []

    # ----- raw materials
    def materials(self) -> list:
        return self._api._get("/raw-materials/", self._t(), params={"limit": 100}) or []

    def create_material(self, data: dict) -> dict:
        return self._api._post("/raw-materials/", self._t(), json=data)

    def update_material(self, material_id: str, data: dict) -> dict:
        return self._api._patch(f"/raw-materials/{material_id}", self._t(), json=data)

    def delete_material(self, material_id: str) -> bool:
        return self._api._delete(f"/raw-materials/{material_id}", self._t())

    def adjust_material(self, material_id: str, change: float, notes: str) -> dict:
        return self._api._post(
            f"/raw-materials/{material_id}/adjust",
            self._t(),
            json={"quantity_change": change, "notes": notes},
        )

    # ----- purchases
    def purchases(self) -> list:
        return self._api._get("/purchases/", self._t(), params={"limit": 100}) or []

    def purchase(self, purchase_id: str) -> dict:
        return self._api._get(f"/purchases/{purchase_id}", self._t())

    def create_purchase(self, data: dict) -> dict:
        return self._api._post("/purchases/", self._t(), json=data)

    def confirm_purchase(self, purchase_id: str) -> dict:
        return self._api._patch(f"/purchases/{purchase_id}/confirm", self._t())

    # ----- product photos and models (what the website shows)
    def assets(self, item_id: str) -> list:
        return self._api._get(f"/items/{item_id}/assets", self._t()) or []

    def upload_asset(self, item_id: str, file_path: str, alt: str = "") -> dict:
        return self._api._upload(f"/items/{item_id}/assets", self._t(), file_path, alt)

    def delete_asset(self, item_id: str, asset_id: str) -> bool:
        return self._api._delete(f"/items/{item_id}/assets/{asset_id}", self._t())
