"""
services/sales_service.py

Sales domain service — sale creation, invoice handling, history.
IDs are UUIDs (strings), not integers.
"""

import os
import uuid
from pathlib import Path

from database.outbox_repository import OutboxRepository
from services.api_client import APIClient
from services.session import Session


class SalesService:
    """Sale + invoice operations."""

    INVOICE_DIR = Path("invoices")

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _token(self) -> str:
        return Session.get_token()

    # ------------------------------------------------------------------
    # Sale creation
    # ------------------------------------------------------------------
    def create_sale(
        self, items: list[dict], customer_id: str | None = None
    ) -> dict | None:
        """POST /sales and return the SaleResponse dict."""
        return self._api.create_sale(self._token(), items, customer_id)

    def is_online(self) -> bool:
        return self._api.health_check()

    def queue_offline_sale(
        self, lines: list[dict], customer_name: str, customer_phone: str
    ) -> str:
        """
        Save a counter sale in the local outbox; the background sync pushes it
        when the backend is reachable. The server assigns the official,
        consecutive bill number then.

        lines: [{"item_id": str, "quantity": int, "price": float}, ...]
        Returns a short reference to show the user while the sale is queued.
        """
        sale_id = str(uuid.uuid4())
        payload = {
            "id": sale_id,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "items": [
                {
                    "product_id": ln["item_id"],
                    "quantity": ln["quantity"],
                    "price": ln["price"],
                }
                for ln in lines
            ],
            # The server recalculates from its own prices; this is informational.
            "total_amount": sum(ln["price"] * ln["quantity"] for ln in lines),
            "payment_method": "cash",
        }
        OutboxRepository().add_entry("sale", "create", payload)
        return sale_id[:8].upper()

    # ------------------------------------------------------------------
    # Invoice PDF
    # ------------------------------------------------------------------
    def fetch_and_save_pdf(self, invoice_number: str) -> Path | None:
        """Download invoice PDF from backend, persist locally, return path."""
        pdf_bytes = self._api.get_invoice_pdf(self._token(), invoice_number)
        if pdf_bytes is None:
            return None

        self.INVOICE_DIR.mkdir(exist_ok=True)
        filepath = self.INVOICE_DIR / f"{invoice_number}.pdf"
        filepath.write_bytes(pdf_bytes)
        return filepath

    @staticmethod
    def open_pdf(filepath: Path) -> None:
        """Open a local PDF with the OS default application."""
        os.startfile(str(filepath))

    # ------------------------------------------------------------------
    # Sales history
    # ------------------------------------------------------------------
    def get_sales(self, customer_id: str = None, date: str = None) -> list:
        return self._api.get_sales(self._token(), customer_id, date) or []

    def get_sale_items(self, sale_id: str) -> list:
        return self._api.get_sale_items(self._token(), sale_id) or []

    def get_sale_details(self, sale_id: str) -> dict | None:
        return self._api.get_sale_details(self._token(), sale_id)
