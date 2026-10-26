"""
services/staff_service.py

Staff accounts: list, add, edit (including role and daily wage), switch on/off,
reset a password, and change your own. Adding, editing and resetting are
owner-only on the server.
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

    def reset_password(self, user_id: str, new_password: str) -> dict:
        return self._api._post(
            f"/auth/users/{user_id}/reset-password",
            self._t(),
            json={"new_password": new_password},
        )

    def change_my_password(self, current: str, new: str) -> dict:
        return self._api._post(
            "/auth/me/password",
            self._t(),
            json={"current_password": current, "new_password": new},
        )
