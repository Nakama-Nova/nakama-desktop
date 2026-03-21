"""
services/auth_service.py

Handles authentication. Delegates HTTP to APIClient, manages Session state.
"""

from services.api_client import APIClient
from services.session import Session


class AuthService:
    """Login / logout operations."""

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def login(self, username: str, password: str) -> dict | None:
        """Authenticate and store the token + role in Session. Returns the response dict or None."""
        result = self._api.login(username, password)
        if result:
            Session.set_token(result["access_token"])
            Session.set_role(result.get("role"))
        return result

    def logout(self) -> None:
        """Clear session state."""
        Session.clear_token()

    @staticmethod
    def is_authenticated() -> bool:
        return Session.is_authenticated()
