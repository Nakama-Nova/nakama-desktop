"""
services/workforce_service.py

Desktop side workforce service for attendance and wages.
"""

from services.api_client import APIClient
from services.session import Session


class AttendanceService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _token(self) -> str:
        return Session.get_token()

    def get_users(self) -> list:
        """Fetch all users (admin only)."""
        return self._api.get_users(self._token()) or []

    def check_in(self, user_id: str) -> dict | None:
        """Mark a user as checked in today."""
        return self._api.check_in(self._token(), user_id)

    def check_out(self, attendance_id: str) -> dict | None:
        """Mark a user as checked out."""
        return self._api.check_out(self._token(), attendance_id)

    def get_my_attendance(self) -> list:
        """Get attendance records for the logged-in user."""
        return self._api.get_my_attendance(self._token()) or []

    def get_all_attendance(
        self, user_id: str = None, start_date: str = None, end_date: str = None
    ) -> list:
        """Get all attendance records (admin only)."""
        return (
            self._api.get_all_attendance(self._token(), user_id, start_date, end_date)
            or []
        )
