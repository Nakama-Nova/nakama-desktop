"""
services/orders_service.py

Customer orders: list, details, move through the stages, take payments, edit. The rules
(allowed stage changes, no overpaying, no edits after delivery) live on the server.
"""

from services.api_client import APIClient
from services.session import Session

STATUSES = [
    ("New", "draft"),
    ("Confirmed", "confirmed"),
    ("In production", "in_production"),
    ("Ready", "ready"),
    ("Delivered", "delivered"),
    ("Cancelled", "cancelled"),
]
STATUS_WORDS = {value: label for label, value in STATUSES}
OPEN = ("draft", "confirmed", "in_production", "ready")
# the one forward step from each stage: (next status, button label)
NEXT_STEP = {
    "draft": ("confirmed", "✅  Confirm order"),
    "confirmed": ("in_production", "🛠  Start work"),
    "in_production": ("ready", "📦  Mark ready"),
    "ready": ("delivered", "🚚  Mark delivered"),
}
SOURCE_WORDS = {"pos": "Shop", "web": "Website"}
TYPE_WORDS = {"standard": "Standard", "custom": "Custom"}


def amount_of(order: dict) -> float:
    """What the order is worth: the final amount once set, else the estimate."""
    final = float(order.get("final_amount") or 0)
    return final if final > 0 else float(order.get("estimated_amount") or 0)


def items_summary(order: dict) -> str:
    items = order.get("items") or []
    if not items:
        return ""
    first = items[0].get("item_name") or "Catalogue item"
    first = f"{items[0]['quantity']} × {first}" if items[0].get("quantity", 1) > 1 else first
    return first + (f"  +{len(items) - 1} more" if len(items) > 1 else "")


class OrdersService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def orders(self, status=None, source=None, search=None, limit=100) -> list:
        params = {"status": status, "source": source, "search": search or None, "limit": limit}
        return self._api._get("/orders/", self._t(), params=params) or []

    def create(self, data: dict) -> dict:
        return self._api._post("/orders/", self._t(), json=data)

    def set_status(self, order_id: str, status: str, notes: str | None = None) -> dict:
        body = {"status": status}
        if notes:
            body["notes"] = notes
        return self._api._patch(f"/orders/{order_id}/status", self._t(), json=body)

    def add_payment(self, order_id: str, data: dict) -> dict:
        return self._api._post(f"/orders/{order_id}/payments", self._t(), json=data)

    def update(self, order_id: str, data: dict) -> dict:
        return self._api._patch(f"/orders/{order_id}", self._t(), json=data)
