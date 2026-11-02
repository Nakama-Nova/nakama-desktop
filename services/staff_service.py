"""
services/staff_service.py

Staff accounts: list, add, edit (including role and daily wage), switch on/off,
email someone a code to set their own password, and change your own. Adding, editing
and emailing a code are owner-only on the server.
"""

from services.api_client import APIClient
from services.session import Session


class StaffService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def me(self) -> dict:
        return self._api._get("/auth/me", self._t())

    def users(self) -> list:
        return self._api._get("/auth/", self._t()) or []

    def create(self, data: dict) -> dict:
        return self._api._post("/auth/register", self._t(), json=data)

    def update(self, user_id: str, data: dict) -> dict:
        return self._api._patch(f"/auth/users/{user_id}", self._t(), json=data)

    def send_invite(self, user_id: str) -> dict:
        """Email this person a code to set their own password (nobody else types or sees it)."""
        return self._api._post(f"/auth/users/{user_id}/send-invite", self._t())

    def change_my_password(self, current: str, new: str) -> dict:
        """The server ends every older sign-in when a password changes, and hands back a fresh
        one: keep it, or the next call would sign this user out."""
        result = self._api._post(
            "/auth/me/password",
            self._t(),
            json={"current_password": current, "new_password": new},
        )
        if result and result.get("access_token"):
            Session.set_token(result["access_token"])
        return result
