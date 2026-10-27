"""Expenses, Wages and Profit screens: what they show, what they send, who sees them."""

from datetime import date

import pytest
from PyQt6.QtWidgets import QInputDialog, QPushButton

from services.enums import UserRole
from services.money_service import MoneyService, period_range, rupees
from services.session import Session
from ui.expenses_screen import ExpenseDialog, ExpensesScreen
from ui.main_window import MainWindow
from ui.payroll_screen import AdvanceDialog, PayDialog, PayrollScreen, WorkEntryDialog
from ui.profit_screen import ProfitScreen

EXPENSES = [
    {"id": "e1", "spent_on": "2026-10-05", "category": "Shop Rent", "amount": "6000.00", "payee": "Landlord", "method": "upi", "notes": None},
    {"id": "e2", "spent_on": "2026-10-09", "category": "Electricity", "amount": "900.50", "payee": None, "method": "cash", "notes": "Sept bill"},
]
ASHA = {"user_id": "u1", "username": "asha", "full_name": "Asha K", "role": "achari", "pending_daily": "1200.00", "pending_extras": "3750.00", "owed_gross": "4950.00", "advance_balance": "1000.00", "overtime_rate": "100"}
RAVI = {"user_id": "u2", "username": "ravi", "full_name": None, "role": "worker", "pending_daily": "0.00", "pending_extras": "0.00", "owed_gross": "0.00", "advance_balance": "0.00"}
PAYMENT = {"id": "p1", "user_id": "u1", "paid_on": "2026-10-01", "gross_daily": "800.00", "gross_extras": "200.00", "deductions": "100.00", "net_paid": "900.00", "method": "upi"}
PROFIT = {
    "sales": "15000.00", "purchases": "3000.00", "wages": "1500.00", "expenses": "2000.00", "profit": "8500.00",
    "margin_pct": "56.67", "unpaid_wages": "4950.00", "advances_outstanding": "1000.00", "raw_material_stock_value": "22000.00",
    "expenses_by_category": [{"category": "Rent", "total": "2000.00"}],
    "months": [{"month": "2026-09", "sales": "5000.00", "purchases": "3000.00", "wages": "0.00", "expenses": "0.00", "profit": "2000.00"},
               {"month": "2026-10", "sales": "10000.00", "purchases": "0.00", "wages": "1500.00", "expenses": "2000.00", "profit": "6500.00"}],
}


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setattr(MoneyService, "expenses", lambda self, s=None, e=None: EXPENSES)
    monkeypatch.setattr(MoneyService, "expense_summary", lambda self, s=None, e=None: {"total": "6900.50", "by_category": [{"category": "Shop Rent", "total": "6000.00"}, {"category": "Electricity", "total": "900.50"}]})
    monkeypatch.setattr(MoneyService, "void_expense", lambda self, i, r: calls.append(("void", i, r)))
    monkeypatch.setattr(MoneyService, "owed", lambda self: [ASHA, RAVI])
    monkeypatch.setattr(MoneyService, "payments", lambda self, uid=None: [PAYMENT])
    monkeypatch.setattr(MoneyService, "pay", lambda self, d: calls.append(("pay", d)) or {"net_paid": "4850.00", "deductions": "100.00"})
    monkeypatch.setattr(MoneyService, "profit", lambda self, s=None, e=None: PROFIT)
    return calls


def buttons(table, row, col):
    return [b.text() for b in table.cellWidget(row, col).findChildren(QPushButton)]


def test_period_ranges():
    today = date(2026, 3, 15)
    assert period_range("month", today) == ("2026-03-01", "2026-03-15")
    assert period_range("last_month", today) == ("2026-02-01", "2026-02-28")
    assert period_range("year", today) == ("2026-01-01", "2026-03-15")
    assert period_range("all", today) == (None, None)
    assert period_range("last_month", date(2026, 1, 5)) == ("2025-12-01", "2025-12-31")
    assert rupees("1234.5") == "₹1,234.50" and rupees(None) == "₹0.00"


def test_expenses_list_total_and_owner_only_cancel(qapp, fake, monkeypatch):
    s = ExpensesScreen()
    s.refresh_data()
    assert s.table.rowCount() == 2
    assert s.table.item(0, s.COL_AMOUNT).text() == "₹6,000.00"
    assert s.table.item(0, s.COL_METHOD).text() == "UPI"
    assert "Total spent ₹6,900.50" in s.summary.text() and "Electricity ₹900.50" in s.summary.text()
    assert buttons(s.table, 0, s.COL_ACTIONS) == ["✏️ Edit", "Cancel entry"]
    monkeypatch.setattr(Session, "_role", UserRole.MANAGER)
    s.refresh_data()
    assert buttons(s.table, 0, s.COL_ACTIONS) == ["✏️ Edit"]  # only the owner cancels


def test_cancel_needs_a_reason(qapp, fake, monkeypatch, dialogs):
    s = ExpensesScreen()
    s.refresh_data()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("x", True)))
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[1].click()
    assert fake == [] and dialogs[-1][0] == "warning"  # too short, nothing sent
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("entered twice", True)))
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[1].click()
    assert fake == [("void", "e1", "entered twice")]


def test_expense_dialog_payload_and_validation(qapp, dialogs):
    d = ExpenseDialog(None)
    d._check()
    assert d.result() == 0 and dialogs[-1][0] == "warning"  # no amount yet
    d.category.setCurrentText("Transport")
    d.amount.setValue(450.5)
    d.payee.setText("Raju")
    d.method.setCurrentIndex(d.method.findData("upi"))
    data = d.get_data()
    assert data["category"] == "Transport" and data["amount"] == 450.5
    assert data["payee"] == "Raju" and data["method"] == "upi" and data["notes"] is None
    editing = ExpenseDialog(None, EXPENSES[1])
    assert editing.get_data()["amount"] == 900.5 and editing.get_data()["notes"] == "Sept bill"


def test_wages_screen_for_the_owner_lists_everyone_and_pays(qapp, fake, dialogs, monkeypatch):
    s = PayrollScreen()
    s.refresh_data()
    assert s.table.rowCount() == 2
    assert s.table.item(0, s.COL_TOTAL).text() == "₹4,950.00"
    assert s.table.item(0, s.COL_ADVANCE).text() == "₹1,000.00"
    assert "Owed to staff now ₹4,950.00" in s.summary.text()
    assert s.payments.rowCount() == 1 and s.payments.item(0, 4).text() == "₹900.00"
    # nobody owed anything: Pay is greyed out, the others stay usable
    pay_btn, work_btn, adv_btn = s.table.cellWidget(1, s.COL_ACTIONS).findChildren(QPushButton)
    assert not pay_btn.isEnabled() and work_btn.isEnabled() and adv_btn.isEnabled()

    monkeypatch.setattr(PayDialog, "exec", lambda self: 1)  # accepted
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[0].click()
    assert fake[0][0] == "pay" and fake[0][1]["user_id"] == "u1" and fake[0][1]["deduction"] == 0
    assert "₹4,850.00" in dialogs[-1][2] and "taken back" in dialogs[-1][2]


def test_pay_dialog_caps_the_advance_taken_back(qapp):
    d = PayDialog(None, ASHA)  # owes 1000, due 4950
    assert d.deduction.isEnabled() and d.deduction.maximum() == 1000
    d.deduction.setValue(400)
    assert d.net.text() == "₹4,550.00"
    assert d.get_data()["deduction"] == 400 and d.get_data()["method"] == "cash"
    small = PayDialog(None, {**ASHA, "owed_gross": "300.00", "advance_balance": "1000.00"})
    assert small.deduction.maximum() == 300  # never more than the pay itself
    none_owed = PayDialog(None, RAVI)
    assert not none_owed.deduction.isEnabled()


def test_work_dialog_piece_overtime_and_bonus(qapp, dialogs):
    d = WorkEntryDialog(None, [ASHA, RAVI], "u1")
    d.kind.setCurrentIndex(d.kind.findData("piece"))
    d.description.setText("Carved Ganesha panel")
    d.quantity.setValue(2)
    d.rate.setValue(1500)
    assert d.total.text() == "₹3,000.00"
    data = d.get_data()
    assert (data["user_id"], data["kind"], data["quantity"], data["rate"]) == ("u1", "piece", 2, 1500)

    d.kind.setCurrentIndex(d.kind.findData("overtime"))
    d.rate.setValue(0)  # blank: the server uses their usual hourly rate
    assert d.get_data()["rate"] is None
    d._check()
    assert d.result() == 1  # overtime may leave the rate out

    d.kind.setCurrentIndex(d.kind.findData("bonus"))
    d.quantity.setValue(9)  # ignored for a bonus
    assert d.get_data()["quantity"] == 1
    d._check()
    assert dialogs[-1][0] == "warning"  # a bonus needs an amount


def test_advance_dialog(qapp, dialogs):
    d = AdvanceDialog(None, [ASHA, RAVI], "u2")
    assert d.person.currentData() == "u2"
    d._check()
    assert d.result() == 0 and dialogs[-1][0] == "warning"
    d.amount.setValue(500)
    d.kind.setCurrentIndex(d.kind.findData("recovery"))
    data = d.get_data()
    assert data["amount"] == 500 and data["kind"] == "recovery" and data["notes"] is None


def test_a_worker_sees_only_their_own_pay(qapp, monkeypatch):
    mine = {**ASHA, "pending_entries": [{"work_date": "2026-10-02", "kind": "piece", "description": "Panel", "amount": "3000.00"}], "recent_payments": [PAYMENT]}
    monkeypatch.setattr(Session, "_role", UserRole.WORKER)
    monkeypatch.setattr(MoneyService, "my_payroll", lambda self: mine)
    s = PayrollScreen()
    assert not s.can_manage and not hasattr(s, "table")
    s.refresh_data()
    assert s.card_daily.value_lbl.text() == "₹1,200.00"
    assert s.card_advance.value_lbl.text() == "₹1,000.00"
    assert s.entries.item(0, 1).text() == "Piece work" and s.entries.item(0, 3).text() == "₹3,000.00"
    assert s.my_payments.rowCount() == 1


def test_profit_screen_numbers_and_loss_colour(qapp, fake, monkeypatch):
    s = ProfitScreen()
    s.refresh_data()
    assert s.cards["sales"].value_lbl.text() == "₹15,000.00"
    assert s.cards["profit"].value_lbl.text() == "₹8,500.00"
    assert s.cards["margin"].value_lbl.text() == "56.7%"
    assert "Owed to staff now ₹4,950.00" in s.owed.text() and "₹22,000.00" in s.owed.text()
    assert s.table.rowCount() == 2 and s.table.item(1, 5).text() == "₹6,500.00"
    assert "#2F7D4F" in s.cards["profit"].value_lbl.styleSheet()
    monkeypatch.setattr(MoneyService, "profit", lambda self, s=None, e=None: {**PROFIT, "profit": "-250.00", "margin_pct": "-5.00"})
    s.refresh_data()
    assert "#B3261E" in s.cards["profit"].value_lbl.styleSheet()


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER, {"Wages", "Expenses", "Profit"}),
        (UserRole.MANAGER, {"Wages", "Expenses", "Profit"}),
        (UserRole.SALES, set()),
        (UserRole.ACHARI, {"Wages"}),
        (UserRole.WORKER, {"Wages"}),
    ],
)
def test_who_sees_the_money_screens(qapp, monkeypatch, role, expected):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    labels = {label for _, label, _ in w._get_allowed_nav_items()}
    assert labels & {"Wages", "Expenses", "Profit"} == expected
