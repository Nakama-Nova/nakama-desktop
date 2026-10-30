"""
services/sales_service.py

Sales domain service — sale creation, invoice handling, history.
IDs are UUIDs (strings), not integers.
"""

import os
import uuid
import webbrowser
from pathlib import Path

import requests

from database.outbox_repository import OutboxRepository
from services.api_client import APIClient, APIError
from services.session import Session


class BillPdfError(Exception):
    """A bill's PDF could not be fetched, saved or opened. The message says why, in plain words."""


class SalesService:
    """Sale + invoice operations."""

    # In the user's own folder (always writable), not relative to wherever the program was started
    INVOICE_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "VrikshaStudios" / "invoices"

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _token(self) -> str:
        return Session.get_token()

    # ------------------------------------------------------------------
    # Sale creation
    # ------------------------------------------------------------------
    def create_sale(
        self,
        items: list[dict],
        customer_id: str | None = None,
        client_id: str | None = None,
    ) -> dict | None:
        """POST /sales and return the SaleResponse dict."""
        return self._api.create_sale(self._token(), items, customer_id, client_id)

    def is_online(self) -> bool:
        return self._api.health_check()

    def queue_offline_sale(
        self,
        lines: list[dict],
        customer_name: str,
        customer_phone: str,
        client_id: str | None = None,
    ) -> str:
        """
        Save a counter sale in the local outbox; the background sync pushes it
        when the backend is reachable. The server assigns the official,
        consecutive bill number then.

        lines: [{"item_id": str, "quantity": int, "price": float}, ...]
        client_id: the id already sent with an online attempt of this same bill,
        if there was one. It becomes the outbox id, which the server uses to
        spot a bill it already recorded.
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
        OutboxRepository().add_entry(
            "sale", "create", payload, entry_id=client_id, user_id=Session.get_user_id()
        )
        return sale_id[:8].upper()

    # ------------------------------------------------------------------
    # Invoice PDF
    # ------------------------------------------------------------------
    def fetch_and_save_pdf(self, invoice_number: str) -> Path:
        """Download a bill's PDF, keep a copy on this PC and return its path.
        Raises BillPdfError, with the reason, when it cannot."""
        try:
            pdf = self._api._get_file(f"/invoices/{invoice_number}/pdf", self._token())
        except APIError as exc:
            raise BillPdfError(f"The server could not make the PDF: {exc}") from exc
        except requests.RequestException as exc:
            raise BillPdfError("The server could not be reached, so the PDF could not be downloaded.") from exc
        if not pdf.startswith(b"%PDF"):
            raise BillPdfError("The server sent something that is not a PDF.")
        try:
            self.INVOICE_DIR.mkdir(parents=True, exist_ok=True)
            filepath = self.INVOICE_DIR / f"{invoice_number}.pdf"
            filepath.write_bytes(pdf)
        except OSError as exc:
            raise BillPdfError(f"The PDF could not be saved in {self.INVOICE_DIR}: {exc.strerror or exc}") from exc
        return filepath

    @staticmethod
    def open_pdf(filepath: Path) -> None:
        """Open a local PDF with the PC's PDF program, or the browser if none is set up.
        Raises BillPdfError when neither works."""
        try:
            os.startfile(str(filepath))  # noqa: S606 - the bill we just saved
            return
        except (AttributeError, OSError):
            pass  # not Windows, or no program is registered for .pdf
        if not webbrowser.open(Path(filepath).resolve().as_uri()):
            raise BillPdfError(f"No program on this PC could open the PDF. It is saved at {filepath}")

    # ------------------------------------------------------------------
    # Sales history
    # ------------------------------------------------------------------
    def get_sales(self, customer_id: str = None, date: str = None) -> list:
        return self._api.get_sales(self._token(), customer_id, date) or []

    def get_sale_items(self, sale_id: str) -> list:
        return self._api.get_sale_items(self._token(), sale_id) or []

    def get_sale_details(self, sale_id: str) -> dict | None:
        return self._api.get_sale_details(self._token(), sale_id)
