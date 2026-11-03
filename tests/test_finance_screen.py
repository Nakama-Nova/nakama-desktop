"""Accounts: the finance ledger to read (profit and loss, balance sheet, trial balance, entries,
accounts), who sees what, and the accountant role."""

from datetime import date

import pytest

from services.api_client import ForbiddenError
from services.enums import UserRole
from services.finance_service import FinanceService
from services.session import Session
from ui.finance_screen import EntryDialog, FinanceScreen, LedgerDialog, financial_year_start, period_for
from ui.main_window import MainWindow

from tests.conftest import settle


def row(code, name, amount):
    return {"code": code, "name": name, "amount": amount}


PNL = {
    "income": [row("4000", "Sales", "182000.00"), row("4100", "Order income", "64500.00")],
    "expenses": [row("5000", "Purchases", "98000.00"), row("5100", "Wages", "61000.00")],
    "total_income": "246500.00", "total_expenses": "159000.00", "net_profit": "87500.00",
}
BALANCE = {
    "as_of": "2026-11-03", "assets": [row("1000", "Cash", "52000.00")], "liabilities": [row("2000", "Suppliers", "41000.00")],
    "equity": [row("3000", "Capital", "245000.00")], "profit_so_far": "76000.00",
    "total_assets": "52000.00", "total_liabilities": "41000.00", "total_equity": "321000.00", "balanced": False,
}
TRIAL = {
    "as_of": "2026-11-03", "debit_balance_total": "52000.00", "credit_balance_total": "52000.00", "balanced": True,
    "rows": [
        {"code": "1000", "name": "Cash", "type": "asset", "debit_balance": "52000.00", "credit_balance": "0", "balance": "52000.00"},
        {"code": "4000", "name": "Sales", "type": "income", "debit_balance": "0", "credit_balance": "52000.00", "balance": "52000.00"},
    ],
}
ENTRIES = [
    {"id": "e1", "entry_date": "2026-11-02", "memo": "Bill NTD-0001", "kind": "posting", "source_type": "sale", "total": "18500.00",
     "lines": [{"account": "1000", "account_name": "Cash", "debit": "18500.00", "credit": "0"},
               {"account": "4000", "account_name": "Sales", "debit": "0", "credit": "18500.00", "note": "walk-in"}]},
    {"id": "e2", "entry_date": "2026-11-01", "memo": "Teak from Ravi", "kind": "posting", "source_type": "purchase", "total": "41000.00",
     "reversed_by": "e3", "lines": []},
]
ACCOUNTS = [
    {"id": "a1", "code": "1000", "name": "Cash", "type": "asset", "normal_side": "debit", "is_active": True},
    {"id": "a2", "code": "4000", "name": "Sales", "type": "income", "normal_side": "credit", "is_active": False},
]


@pytest.fixture
def books(monkeypatch):
    calls = []
    monkeypatch.setattr(FinanceService, "profit_and_loss", lambda self, a=None, b=None: PNL)
    monkeypatch.setattr(FinanceService, "balance_sheet", lambda self, a=None: BALANCE)
    monkeypatch.setattr(FinanceService, "trial_balance", lambda self, a=None: TRIAL)
    monkeypatch.setattr(FinanceService, "accounts", lambda self: ACCOUNTS)
    monkeypatch.setattr(FinanceService, "reconciliation", lambda self, a=None, b=None: {"agrees": True, "to_post": 0, "to_reverse": 0})
    monkeypatch.setattr(FinanceService, "closing", lambda self: {"closed_through": "2026-09-30"})

    def entries(self, frm=None, to=None, kind=None, limit=50, offset=0):
        calls.append((frm, to, kind, limit, offset))
        return ENTRIES

    monkeypatch.setattr(FinanceService, "entries", entries)
    return calls


def test_the_period_presets():
    today = date(2026, 11, 3)
    assert period_for("month", today) == (date(2026, 11, 1), today)
    assert period_for("last", today) == (date(2026, 10, 1), date(2026, 10, 31))
    assert period_for("last", date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 31))  # over a year end
    assert period_for("year", today) == (date(2026, 4, 1), today)
    assert financial_year_start(date(2026, 2, 10)) == date(2025, 4, 1)  # January to March belong to last April's year
    assert period_for("all", today) == (None, None)


def test_profit_and_loss_shows_the_totals_and_both_sides(qapp, books):
    s = FinanceScreen()
    s.refresh_data()
    assert (s.income_lbl.text(), s.expense_lbl.text(), s.profit_lbl.text()) == ("₹246,500.00", "₹159,000.00", "₹87,500.00")
    assert [s.income_table.item(r, 1).text() for r in range(s.income_table.rowCount())] == ["Sales", "Order income"]
    assert s.expense_table.item(1, 2).text() == "₹61,000.00"
    assert "65%" in s.spend_words.text()  # expenses as a share of income


def test_a_loss_is_called_a_loss(qapp, books, monkeypatch):
    monkeypatch.setattr(FinanceService, "profit_and_loss", lambda self, a=None, b=None: {**PNL, "net_profit": "-5000.00"})
    s = FinanceScreen()
    s.refresh_data()
    assert s.profit_caption.text() == "Loss" and s.profit_lbl.text() == "-₹5,000.00"


def test_the_balance_sheet_says_when_it_does_not_balance(qapp, books):
    s = FinanceScreen()
    s.refresh_data()
    assert s.assets_total.text() == "Total: ₹52,000.00"
    assert s.equity_table.item(s.equity_table.rowCount() - 1, 1).text().startswith("Profit so far")
    assert "does not balance" in s.balance_note.text()


def test_the_trial_balance_and_the_banner(qapp, books):
    s = FinanceScreen()
    s.refresh_data()
    assert s.trial_table.rowCount() == 2 and "balanced" in s.trial_note.text()
    assert not s.status.isHidden() and "agrees" in s.status.text() and "closed through 30 Sep 2026" in s.status.text()


def test_the_banner_warns_when_records_are_waiting_to_be_posted(qapp, books, monkeypatch):
    monkeypatch.setattr(FinanceService, "reconciliation", lambda self, a=None, b=None: {"agrees": False, "to_post": 3, "to_reverse": 1})
    s = FinanceScreen()
    s.refresh_data()
    assert "3 records not in the ledger yet" in s.status.text() and "1 changed since posting" in s.status.text()


def test_entries_search_marks_reversals_and_open_in_full(qapp, books, monkeypatch):
    s = FinanceScreen()
    s.refresh_data()
    assert s.entries_table.rowCount() == 2 and s.entries_table.item(1, 4).text() == "Reversed"
    s.entry_search.setText("teak")
    assert s.entries_table.rowCount() == 1 and s.entries_table.item(0, 2).text() == "Purchase"
    s.entry_search.setText("")
    opened = []
    monkeypatch.setattr(EntryDialog, "exec", lambda self: opened.append(self.table.rowCount()))
    s._open_entry(0, 0)
    assert opened == [2]  # the two lines of the first entry


def test_choosing_a_kind_asks_the_server_for_that_kind(qapp, books):
    s = FinanceScreen()
    s.refresh_data()
    s.kind_chips.choose("reversal")
    settle()
    assert books[-1][2] == "reversal"
    s.kind_chips.choose("all")
    settle()
    assert books[-1][2] is None


def test_picking_dates_or_a_preset_changes_the_period_asked_for(qapp, books):
    s = FinanceScreen()
    s.refresh_data()
    s.chips.choose("all")
    settle()
    assert books[-1][:2] == (None, None) and not s.from_edit.isEnabled()
    s.chips.choose("last")
    settle()
    assert s.from_edit.isEnabled() and books[-1][0].day == 1


def test_accounts_list_opens_a_ledger(qapp, books, monkeypatch):
    s = FinanceScreen()
    s.refresh_data()
    assert s.accounts_table.rowCount() == 2 and "switched off" in s.accounts_table.item(1, 1).text()
    assert s.accounts_table.item(0, 3).text() == "₹52,000.00"  # its balance from the trial balance
    monkeypatch.setattr(
        FinanceService, "ledger",
        lambda self, code, a=None, b=None: {"code": code, "name": "Cash", "opening_balance": "0", "closing_balance": "100.00",
                                            "lines": [{"entry_date": "2026-11-02", "memo": "x", "debit": "100.00", "credit": "0", "balance": "100.00"}]},
    )
    shown = []
    monkeypatch.setattr(LedgerDialog, "exec", lambda self: shown.append(self.table.rowCount()))
    s._open_ledger(0, 0)
    assert shown == [1]


def test_only_the_owner_and_the_accountant_get_the_balance_sheet(qapp, books, monkeypatch):
    def tabs(role):
        monkeypatch.setattr(Session, "_role", role)
        s = FinanceScreen()
        return [s.tabs.tabText(i) for i in range(s.tabs.count())]

    assert "Balance sheet" in tabs(UserRole.OWNER) and "Balance sheet" in tabs(UserRole.ACCOUNTANT)
    assert "Balance sheet" not in tabs(UserRole.MANAGER)


def test_a_refused_balance_sheet_is_a_note_not_a_crash(qapp, books, monkeypatch):
    def refuse(self, a=None):
        raise ForbiddenError(403, "no")

    monkeypatch.setattr(FinanceService, "balance_sheet", refuse)
    s = FinanceScreen()
    s.refresh_data()
    assert "could not be read" in s.balance_note.text()


@pytest.mark.parametrize(
    "role,sees",
    [(UserRole.OWNER, True), (UserRole.MANAGER, True), (UserRole.ACCOUNTANT, True), (UserRole.SALES, False), (UserRole.WORKER, False)],
)
def test_who_has_accounts_in_the_side_panel(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert ("Accounts" in [label for _, label, _ in w._get_allowed_nav_items()]) is sees


def test_the_accountant_has_only_accounts_and_starts_there(qapp, monkeypatch):
    assert UserRole("accountant") is UserRole.ACCOUNTANT  # signing in as the CA no longer fails
    monkeypatch.setattr(Session, "_role", UserRole.ACCOUNTANT)
    w = MainWindow()
    w._sync_timer.stop()
    assert [label for _, label, _ in w._get_allowed_nav_items()] == ["Accounts"]
    assert w.content_stack.currentIndex() == 21
