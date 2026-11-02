"""
services/registers_service.py

The machine and tool registers, and the monthly / yearly budgets for machines and raw
materials. Machines and budgets are owner and manager (only the owner sets a budget); tools
are also visible to the achari (head carpenter). The server enforces it.
"""

from services.api_client import APIClient
from services.session import Session


class RegistersService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    # ----- machines
    def machines(self) -> list:
        return self._api._get("/machines/", self._t(), params={"limit": 200}) or []

    def save_machine(self, data: dict, machine_id: str | None = None) -> dict:
        if machine_id:
            return self._api._put(f"/machines/{machine_id}", self._t(), json=data)
        return self._api._post("/machines/", self._t(), json=data)

    def add_maintenance(self, machine_id: str, data: dict) -> dict:
        return self._api._post(f"/machines/{machine_id}/maintenance", self._t(), json=data)

    def maintenance(self, machine_id: str) -> list:
        return self._api._get(f"/machines/{machine_id}/maintenance", self._t()) or []

    def start_downtime(self, machine_id: str, reason: str) -> dict:
        return self._api._post(
            f"/machines/{machine_id}/downtime", self._t(), json={"reason": reason or None}
        )

    def end_downtime(self, machine_id: str) -> dict:
        return self._api._post(f"/machines/{machine_id}/downtime/end", self._t())

    def downtime(self, machine_id: str) -> list:
        return self._api._get(f"/machines/{machine_id}/downtime", self._t()) or []

    # ----- tools
    def tools(self) -> list:
        return self._api._get("/tools/", self._t(), params={"limit": 200}) or []

    def save_tool(self, data: dict, tool_id: str | None = None) -> dict:
        if tool_id:
            return self._api._put(f"/tools/{tool_id}", self._t(), json=data)
        return self._api._post("/tools/", self._t(), json=data)

    def issue_tool(self, tool_id: str, user_id: str, notes: str = "") -> dict:
        return self._api._post(
            f"/tools/{tool_id}/issue", self._t(), json={"user_id": user_id, "notes": notes or None}
        )

    def return_tool(self, tool_id: str, outcome: str, notes: str = "") -> dict:
        return self._api._post(
            f"/tools/{tool_id}/return",
            self._t(),
            json={"outcome": outcome, "notes": notes or None},
        )

    def tool_history(self, tool_id: str) -> list:
        return self._api._get(f"/tools/{tool_id}/history", self._t()) or []

    def staff(self) -> list:
        """People a tool can be handed to."""
        return self._api._get("/auth/", self._t()) or []

    # ----- budgets
    def current_budgets(self) -> list:
        """This month and this financial year, for machines and for raw materials."""
        return self._api._get("/budgets/current", self._t()) or []

    def all_budgets(self) -> list:
        return self._api._get("/budgets/", self._t(), params={"limit": 200}) or []

    def set_budget(self, category: str, period: str, starts_on: str, amount: float, notes: str = "") -> dict:
        return self._api._put(
            "/budgets/",
            self._t(),
            json={
                "category": category,
                "period": period,
                "starts_on": starts_on,
                "amount": str(amount),
                "notes": notes or None,
            },
        )

    def delete_budget(self, budget_id: str) -> bool:
        return self._api._delete(f"/budgets/{budget_id}", self._t())
