"""
services/places_service.py

Places (the plant units and the shop) and the stock held at each: what is where, what has
not been placed yet, and moving stock from one place to another. Owner and manager move
stock; sales staff can look. The server enforces it.
"""

from services.api_client import APIClient
from services.session import Session

NOT_PLACED = "Not placed yet"


class PlacesService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    # ----- the places themselves
    def places(self) -> list:
        return self._api._get("/plant-units/", self._t()) or []

    def save_place(self, data: dict, place_id: str | None = None) -> dict:
        if place_id:
            return self._api._put(f"/plant-units/{place_id}", self._t(), json=data)
        return self._api._post("/plant-units/", self._t(), json=data)

    # ----- stock at each place
    def levels(self) -> list:
        """Stock at places, then the stock with no place yet, as one list.
        Each row: location_id (None = not placed), location_name, item_id or raw_material_id,
        name, quantity."""
        t = self._t()
        placed = self._api._get("/stock/levels", t, params={"limit": 500}) or []
        unplaced = self._api._get("/stock/unassigned", t, params={"limit": 500}) or []
        return placed + unplaced

    def transfers(self, limit: int = 50) -> list:
        return self._api._get("/stock/transfers", self._t(), params={"limit": limit}) or []

    def move(
        self,
        *,
        item_id: str | None,
        raw_material_id: str | None,
        from_location_id: str | None,
        to_location_id: str | None,
        quantity: float,
        notes: str = "",
    ) -> dict:
        body = {
            "item_id": item_id,
            "raw_material_id": raw_material_id,
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "quantity": str(quantity),
            "notes": notes or None,
        }
        return self._api._post("/stock/transfers", self._t(), json=body)


def thing_key(row: dict) -> tuple[str, str]:
    """('item'|'material', id): what a stock row is about."""
    if row.get("item_id"):
        return "item", str(row["item_id"])
    return "material", str(row["raw_material_id"])


def place_name(places: list, location_id: str | None) -> str:
    if not location_id:
        return NOT_PLACED
    for p in places:
        if str(p["id"]) == str(location_id):
            return p["name"]
    return "Unknown place"
