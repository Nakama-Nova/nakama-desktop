"""
services/letters_service.py

Official letters (quotation, order confirmation with advance receipt, purchase receipt,
completion certificate): issue, list, void and fetch the PDF. The server numbers each
letter once and decides who may issue and see which kind; the roles here only decide
which buttons to show.
"""

import tempfile
from pathlib import Path

from services.api_client import APIClient
from services.enums import UserRole
from services.session import Session

KINDS = [
    ("Quotation", "quotation"),
    ("Order confirmation and advance receipt", "order_confirmation"),
    ("Purchase receipt (bought piece)", "purchase_receipt"),
    ("Certificate of completion", "completion_certificate"),
]
KIND_WORDS = {value: label for label, value in KINDS}
KIND_SHORT = {
    "quotation": "Quotation",
    "order_confirmation": "Order confirmation",
    "purchase_receipt": "Purchase receipt",
    "completion_certificate": "Certificate",
}
ISSUERS = {
    "quotation": [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES],
    "order_confirmation": [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES],
    "purchase_receipt": [UserRole.OWNER, UserRole.MANAGER],
    "completion_certificate": [UserRole.OWNER],
}
LETTER_ROLES = [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]
LETTERHEAD_FIELDS = [
    ("name", "Name"),
    ("tagline", "Tagline"),
    ("address", "Address"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("gstin", "GSTIN (leave empty until registered)"),
    ("signatory_name", "Signed by"),
    ("signatory_title", "Title"),
    ("footer_note", "Footer line"),
]


def may_issue(kind: str) -> bool:
    return Session.is_authorized(ISSUERS[kind])


class LettersService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def letters(self, kind=None, status=None, search=None, limit=200) -> list:
        params = {"kind": kind, "status": status, "search": search or None, "limit": limit}
        return self._api._get("/letters", self._t(), params=params) or []

    def issue(self, kind: str, data: dict) -> dict:
        return self._api._post(f"/letters/{kind.replace('_', '-')}", self._t(), json=data)

    def void(self, letter_id: str, reason: str) -> dict:
        return self._api._post(f"/letters/{letter_id}/void", self._t(), json={"reason": reason})

    def profile(self) -> dict:
        return self._api._get("/letters/profile", self._t()) or {}

    def save_profile(self, data: dict) -> dict:
        return self._api._put("/letters/profile", self._t(), json=data)

    def save_pdf(self, letter: dict, folder: Path | None = None) -> Path:
        """Fetch the letter's PDF into a folder (a temporary one by default) and return its path."""
        pdf = self._api._get_bytes(f"/letters/{letter['id']}/pdf", self._t())
        if pdf is None:
            raise RuntimeError("The letter could not be fetched. Try again.")
        folder = folder or Path(tempfile.gettempdir()) / "vriksha-letters"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{letter['number']}.pdf"
        path.write_bytes(pdf)
        return path
