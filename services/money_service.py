"""
services/money_service.py

Expenses, staff pay (daily wage, piece work, overtime, advances) and the real
profit report. Thin calls to the server; the maths all happens there.
"""

from datetime import date, timedelta

from services.api_client import APIClient
from services.session import Session

PERIODS = [
    ("This month", "month"),
    ("Last month", "last_month"),
    ("This year", "year"),
    ("All time", "all"),
]


def period_range(key: str, today: date | None = None):
    """(start, end) as ISO dates for a PERIODS key; (None, None) means everything."""
    today = today or date.today()
    first = today.replace(day=1)
    if key == "month":
        return first.isoformat(), today.isoformat()
    if key == "last_month":
        end = first - timedelta(days=1)
        return end.replace(day=1).isoformat(), end.isoformat()
    if key == "year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat()
    return None, None


def rupees(value) -> str:
    return f"₹{float(value or 0):,.2f}"


class MoneyService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    # -- expenses ------------------------------------------------------
    def expenses(self, start=None, end=None) -> list:
        params = {"start_date": start, "end_date": end}
        return self._api._get("/expenses/", self._t(), params=params) or []

    def expense_summary(self, start=None, end=None) -> dict:
        params = {"start_date": start, "end_date": end}
        return self._api._get("/expenses/summary", self._t(), params=params)

    def add_expense(self, data: dict) -> dict:
        return self._api._post("/expenses/", self._t(), json=data)

    def edit_expense(self, expense_id: str, data: dict) -> dict:
        return self._api._patch(f"/expenses/{expense_id}", self._t(), json=data)

    def void_expense(self, expense_id: str, reason: str) -> dict:
        return self._api._post(
            f"/expenses/{expense_id}/void", self._t(), json={"reason": reason}
        )

    # -- pay -----------------------------------------------------------
    def owed(self) -> list:
        return self._api._get("/payroll/summary", self._t()) or []

    def my_payroll(self) -> dict:
        return self._api._get("/payroll/me", self._t())

    def payments(self, user_id: str | None = None) -> list:
        params = {"user_id": user_id}
        return self._api._get("/payroll/payments", self._t(), params=params) or []

    def add_work_entry(self, data: dict) -> dict:
        return self._api._post("/payroll/work-entries", self._t(), json=data)

    def add_advance(self, data: dict) -> dict:
        return self._api._post("/payroll/advances", self._t(), json=data)

    def pay(self, data: dict) -> dict:
        return self._api._post("/payroll/pay", self._t(), json=data)

    # -- profit --------------------------------------------------------
    def profit(self, start=None, end=None) -> dict:
        params = {"start_date": start, "end_date": end}
        return self._api._get("/reports/profit", self._t(), params=params)
