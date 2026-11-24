"""
services/leave_service.py

Leave: the kinds of leave, your balances, asking for leave, and (for the people who approve)
approving or rejecting. The rules (overlaps, balances, who may decide) live on the server.
See docs/HR_CONTRACT.md, H4.
"""

from services.api_client import APIClient
from services.session import Session

STATUS_WORDS = {"pending": "Waiting", "approved": "Approved", "rejected": "Not approved", "cancelled": "Cancelled"}


class LeaveService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def types(self) -> list:
        return self._api._get("/leave/types", self._t()) or []

    def my_balances(self) -> list:
        return self._api._get("/leave/balances/me", self._t()) or []

    def requests(self, status: str | None = None) -> list:
        """Yours; everyone's for the people who may read them (the server decides)."""
        params = {"status": status} if status else None
        return self._api._get("/leave/requests", self._t(), params=params) or []

    def ask(self, data: dict) -> dict:
        """{"leave_type_id", "from_date", "to_date", "half_day"?, "reason"?}"""
        return self._api._post("/leave/requests", self._t(), json=data, quiet=True)

    def decide(self, request_id: str, approve: bool, note: str | None = None) -> dict:
        return self._api._post(f"/leave/requests/{request_id}/{'approve' if approve else 'reject'}", self._t(), json={"note": note} if note else {})

    def cancel(self, request_id: str) -> dict:
        return self._api._post(f"/leave/requests/{request_id}/cancel", self._t())
