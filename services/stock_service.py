"""
services/stock_service.py

Everything the stock screens need beyond plain items: categories and brands,
suppliers, raw materials, purchases, manual stock changes, the stock ledger and
product photos. Thin wrappers over the backend, owner/manager only (the server
enforces it).
"""

import os
from pathlib import Path

import requests

from services import api_client
from services.api_client import APIClient, APIError
from services.session import Session

MB = 1024 * 1024
PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
MODEL_TYPES = {".glb": "model/gltf-binary"}
PHOTO_MAX, MODEL_MAX = 10 * MB, 25 * MB  # what the website accepts for a published file


class AssetUploadError(Exception):
    """A photo or model could not be uploaded. The message says why, in plain words."""


def check_asset_file(path: str) -> str | None:
    """Why this file cannot be a product photo or model, or None if it can."""
    ext = Path(path).suffix.lower()
    name = Path(path).name
    if ext not in PHOTO_TYPES and ext not in MODEL_TYPES:
        return f"{name}: only JPG, PNG, WebP photos and .glb models can be added."
    try:
        size = os.path.getsize(path)
    except OSError:
        return f"{name}: the file could not be read."
    if size == 0:
        return f"{name}: the file is empty."
    limit = PHOTO_MAX if ext in PHOTO_TYPES else MODEL_MAX
    if size > limit:
        return f"{name} is {size / MB:.1f} MB; the limit is {limit // MB} MB. Make the photo smaller and try again."
    return None


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
        """Add a photo or model to the website. The file goes straight to the storage bucket
        (the server's own upload limit is 4.5 MB, smaller than many phone photos); it
        falls back to the server upload only where no bucket is set up (development)."""
        problem = check_asset_file(file_path)
        if problem:
            raise AssetUploadError(problem)
        path, ext, t = Path(file_path), Path(file_path).suffix.lower(), self._t()
        kind = "image" if ext in PHOTO_TYPES else "glb"
        content_type = {**PHOTO_TYPES, **MODEL_TYPES}[ext]
        try:
            signed = self._api._post(
                "/uploads/presign",
                t,
                json={"item_id": item_id, "kind": kind, "filename": path.name, "content_type": content_type, "size": os.path.getsize(path)},
                quiet=True,
            )
        except APIError as exc:
            if exc.status_code == 503:  # no bucket on this server: the plain upload still works
                return self._api._upload(f"/items/{item_id}/assets", t, file_path, alt)
            raise AssetUploadError(f"{path.name}: {exc}") from exc
        try:
            with open(path, "rb") as f:
                r = api_client._send(
                    signed["method"].lower(), signed["url"], fast_fail=False, data=f, headers=signed["headers"], timeout=api_client.UPLOAD_TIMEOUT
                )
        except requests.RequestException as exc:
            raise AssetUploadError(f"{path.name}: the connection dropped while sending it. Try again.") from exc
        if r.status_code not in (200, 201, 204):
            raise AssetUploadError(f"{path.name}: the storage service refused it ({r.status_code}). Try again.")
        try:
            return self._api._post(
                f"/items/{item_id}/assets/register",
                t,
                json={"key": signed["key"], "kind": kind, "visibility": "public", "content_type": content_type, "alt": alt or None},
                quiet=True,
            )
        except APIError as exc:
            raise AssetUploadError(f"{path.name}: {exc}") from exc

    def delete_asset(self, item_id: str, asset_id: str) -> bool:
        return self._api._delete(f"/items/{item_id}/assets/{asset_id}", self._t())
