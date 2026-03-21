"""
services/sales_service.py

Sales domain service — sale creation, invoice handling, history.
IDs are UUIDs (strings), not integers.
"""

import os
from pathlib import Path

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
    def create_sale(self, items: list[dict],
                    customer_id: str | None = None) -> dict | None:
        """POST /sales and return the SaleResponse dict."""
        return self._api.create_sale(self._token(), items, customer_id)

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
