"""
services/finance_service.py

The finance ledger, read-only: profit and loss, balance sheet, trial balance, the chart of
accounts, an account's ledger, the journal entries and whether the ledger agrees with the
profit report. Owner, manager and the accountant (the CA) read; the balance sheet is for the
owner and the accountant. Posting and changing the books stay on the server for now.

Every call is `quiet`: a screen shows its own message instead of a general error pop-up.
"""

from datetime import date

from services.api_client import APIClient
from services.session import Session


def _iso(d) -> str | None:
    return d.isoformat() if isinstance(d, date) else (d or None)


class FinanceService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _get(self, path: str, **params):
        params = {k: v for k, v in params.items() if v not in (None, "")}
        return self._api._get(path, Session.get_token(), params=params or None, quiet=True)

    def accounts(self) -> list:
        return self._get("/finance/accounts") or []

    def trial_balance(self, as_of=None) -> dict:
        return self._get("/finance/trial-balance", as_of=_iso(as_of)) or {}

    def profit_and_loss(self, date_from=None, date_to=None) -> dict:
        return self._get("/finance/profit-and-loss", **{"from": _iso(date_from), "to": _iso(date_to)}) or {}

    def balance_sheet(self, as_of=None) -> dict:
        return self._get("/finance/balance-sheet", as_of=_iso(as_of)) or {}

    def ledger(self, code: str, date_from=None, date_to=None) -> dict:
        return self._get(f"/finance/ledger/{code}", **{"from": _iso(date_from), "to": _iso(date_to)}) or {}

    def entries(self, date_from=None, date_to=None, kind=None, limit: int = 50, offset: int = 0) -> list:
        return (
            self._get(
                "/finance/entries",
                **{"from": _iso(date_from), "to": _iso(date_to)},
                kind=kind,
                limit=limit,
                offset=offset,
            )
            or []
        )

    def reconciliation(self, date_from=None, date_to=None) -> dict:
        return self._get("/finance/reconciliation", **{"from": _iso(date_from), "to": _iso(date_to)}) or {}

    def closing(self) -> dict:
        return self._get("/finance/closing") or {}
