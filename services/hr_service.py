"""
services/hr_service.py

Shifts, holidays, and a person's staff record: profile details, documents (ID proof and
the like, kept private) and leaving the job. See docs/HR_CONTRACT.md, H5 and H6, and the
backend's docs/HR_BACKEND_NOTES.md for where it differs.
"""

import mimetypes
import os
from pathlib import Path

import requests

from services import api_client
from services.api_client import APIClient, APIError
from services.session import Session

DOC_KINDS = [("ID proof", "id_proof"), ("Contract", "contract"), ("Photo", "photo"), ("Other", "other")]
ID_PROOFS = [("Aadhaar", "aadhaar"), ("PAN", "pan"), ("Voter ID", "voter"), ("Driving licence", "driving"), ("Other", "other")]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DOC_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}
MAX_DOC_BYTES = 10 * 1024 * 1024


class DocumentError(Exception):
    """A document could not be sent; the message says why, in plain words."""


def check_document(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    if ext not in DOC_TYPES:
        return "Only photos (JPG, PNG, WebP) and PDF files can be kept."
    if os.path.getsize(path) > MAX_DOC_BYTES:
        return "Files can be 10 MB at most."
    return None


class HrService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    # ----- shifts and holidays
    def shifts(self) -> list:
        return self._api._get("/shifts", self._t()) or []

    def save_shift(self, shift_id: str | None, data: dict) -> dict:
        if shift_id:
            return self._api._put(f"/shifts/{shift_id}", self._t(), json=data)
        return self._api._post("/shifts", self._t(), json=data)

    def delete_shift(self, shift_id: str) -> bool:
        return self._api._delete(f"/shifts/{shift_id}", self._t())

    def set_shift(self, user_id: str, shift_id: str | None) -> dict:
        return self._api._put(f"/people/users/{user_id}/shift", self._t(), json={"shift_id": shift_id})

    def holidays(self, year: int) -> list:
        return self._api._get("/holidays", self._t(), params={"year": year}) or []

    def add_holiday(self, day: str, name: str, paid: bool = True) -> dict:
        return self._api._post("/holidays", self._t(), json={"date": day, "name": name, "paid": paid})

    def delete_holiday(self, holiday_id: str) -> bool:
        return self._api._delete(f"/holidays/{holiday_id}", self._t())

    # ----- profile, documents, leaving
    def documents(self, user_id: str) -> list:
        return self._api._get(f"/people/users/{user_id}/documents", self._t()) or []

    def upload_document(self, user_id: str, kind: str, file_path: str) -> dict:
        """Send a file straight to private storage, then tell the server it arrived."""
        problem = check_document(file_path)
        if problem:
            raise DocumentError(problem)
        path = Path(file_path)
        content_type = DOC_TYPES[path.suffix.lower()] or mimetypes.guess_type(path.name)[0]
        t = self._t()
        try:
            signed = self._api._post(
                f"/people/users/{user_id}/documents/upload-url", t,
                json={"kind": kind, "filename": path.name, "content_type": content_type, "size": os.path.getsize(path)}, quiet=True,
            )
        except APIError as exc:
            raise DocumentError(f"{path.name}: {exc}") from exc
        try:
            with open(path, "rb") as f:
                r = api_client._send("put", signed["upload_url"], fast_fail=False, data=f, headers=signed.get("headers") or {}, timeout=api_client.UPLOAD_TIMEOUT)
        except requests.RequestException as exc:
            raise DocumentError(f"{path.name}: the connection dropped while sending it. Try again.") from exc
        if r.status_code not in (200, 201, 204):
            raise DocumentError(f"{path.name}: the storage service refused it ({r.status_code}). Try again.")
        try:
            return self._api._post(f"/people/users/{user_id}/documents/{signed['document_id']}/confirm", t, quiet=True)
        except APIError as exc:
            raise DocumentError(f"{path.name}: {exc}") from exc

    def delete_document(self, user_id: str, document_id: str) -> bool:
        return self._api._delete(f"/people/users/{user_id}/documents/{document_id}", self._t())

    def offboard(self, user_id: str, last_working_date: str, note: str | None = None) -> dict:
        """Set the last working day; returns the settlement (what is still owed to them)."""
        body = {"last_working_date": last_working_date}
        if note:
            body["note"] = note
        return self._api._post(f"/people/users/{user_id}/offboard", self._t(), json=body)
