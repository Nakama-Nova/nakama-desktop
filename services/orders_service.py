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
# an order can be billed from the moment it is confirmed with the customer
BILLABLE = ("confirmed", "in_production", "ready", "delivered")
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

    def orders(self, status=None, source=None, search=None, limit=1000) -> list:
        """The newest `limit` orders matching the filters, fetched a page at a time (the server
        returns at most 100 a call)."""
        params = {k: v for k, v in {"status": status, "source": source, "search": search or None}.items() if v}
        return self._api._get_all("/orders/", self._t(), params, max_rows=limit)

    def create(self, data: dict) -> dict:
        return self._api._post("/orders/", self._t(), json=data)

    def set_status(self, order_id: str, status: str, notes: str | None = None) -> dict:
        body = {"status": status}
        if notes:
            body["notes"] = notes
        return self._api._patch(f"/orders/{order_id}/status", self._t(), json=body)

    def add_payment(self, order_id: str, data: dict) -> dict:
        return self._api._post(f"/orders/{order_id}/payments", self._t(), json=data)

    def update_payment(self, order_id: str, payment_id: str, changes: dict) -> dict:
        """Correct a payment (owner): amount, method, reference, note or date. Only what is sent changes."""
        return self._api._patch(f"/orders/{order_id}/payments/{payment_id}", self._t(), json=changes)

    def void_payment(self, order_id: str, payment_id: str, reason: str) -> dict:
        """Take a wrong payment off the order (owner). It stays on record with the reason."""
        return self._api._post(f"/orders/{order_id}/payments/{payment_id}/void", self._t(), json={"reason": reason})

    def delete_order(self, order_id: str) -> bool:
        """Delete an order that never went anywhere (owner, manager). One with a bill, payments, jobs
        or letters is refused (409): cancel it instead."""
        return bool(self._api._delete_json(f"/orders/{order_id}", self._t()))

    def invoice(self, order_id: str, allow_negative_stock: bool = False) -> dict:
        """Make the bill for an order (or get the one it already has). Raises APIError with
        the server's reason, which the screen shows; nothing is popped up from here."""
        return self._api._post(
            f"/orders/{order_id}/invoice",
            self._t(),
            json={"allow_negative_stock": allow_negative_stock},
            quiet=True,
        )

    def update(self, order_id: str, data: dict) -> dict:
        return self._api._patch(f"/orders/{order_id}", self._t(), json=data)
