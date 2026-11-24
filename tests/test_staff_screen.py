"""Staff screen: list, add, edit, switch off, passwords, and who sees it."""

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton

from services.enums import UserRole
from services.session import Session
from services.staff_service import StaffService
from ui.main_window import MainWindow
from ui.staff_screen import PasswordDialog, StaffDialog, StaffScreen, password_problem

ME = {"id": "u0", "username": "owner", "full_name": "Shop Owner", "email": "o@x.com", "role": "owner", "is_active": True, "base_daily_wage": "0"}
ASHA = {"id": "u1", "username": "asha", "full_name": "Asha K", "email": "a@x.com", "phone": "98765", "role": "achari", "is_active": True, "base_daily_wage": "800"}
OLD = {"id": "u2", "username": "ravi", "full_name": None, "email": "r@x.com", "role": "worker", "is_active": False, "base_daily_wage": "500"}


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setattr(StaffService, "me", lambda self: ME)
    monkeypatch.setattr(StaffService, "users", lambda self: [OLD, ASHA, ME])
    monkeypatch.setattr(StaffService, "update", lambda self, uid, data: calls.append(("update", uid, data)))
    monkeypatch.setattr(StaffService, "create", lambda self, data: calls.append(("create", data)))
    monkeypatch.setattr(StaffService, "send_invite", lambda self, uid: calls.append(("invite", uid)))
    return calls


def buttons(screen, row):
    return [b.text() for b in screen.table.cellWidget(row, screen.COL_ACTIONS).findChildren(QPushButton)]


def test_lists_active_people_first_and_marks_you(qapp, fake):
    s = StaffScreen()
    s.refresh_data()
    names = [s.table.item(r, s.COL_USER).text() for r in range(3)]
    assert names == ["asha", "owner", "ravi"]  # active first, then switched off
    assert "(you)" in s.table.item(1, s.COL_NAME).text()
    assert s.table.item(0, s.COL_ROLE).text() == "Achari (carpenter)"
    assert s.table.item(0, s.COL_WAGE).text() == "₹800"
    assert s.table.item(2, s.COL_STATUS).text() == "Switched off"


def test_you_cannot_switch_yourself_off(qapp, fake):
    s = StaffScreen()
    s.refresh_data()
    assert buttons(s, 1) == ["Edit", "Email code", "Record"]  # row 1 is you
    assert buttons(s, 0) == ["Edit", "Email code", "Extra roles", "Switch off", "Record"]
    assert buttons(s, 2)[-2] == "Switch on"


def test_switch_off_asks_first_then_sends_only_the_flag(qapp, fake, monkeypatch):
    s = StaffScreen()
    s.refresh_data()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[3].click()
    assert fake == []  # said no
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[3].click()
    assert fake == [("update", "u1", {"is_active": False})]


def test_add_staff_collects_login_details_and_wage(qapp):
    d = StaffDialog(None)
    d.username.setText("kavya")
    d.full_name.setText("Kavya R")
    d.email.setText("k@x.com")
    d.role.setCurrentIndex(d.role.findData("sales"))
    d.wage.setValue(700)
    assert not hasattr(d, "password")  # the owner never types a password: the person is emailed a code
    data = d.get_data()
    assert data == {
        "username": "kavya", "full_name": "Kavya R", "email": "k@x.com",
        "phone": None, "base_daily_wage": 700.0, "overtime_rate_per_hour": None, "role": "sales",
    }


def test_editing_yourself_never_sends_a_role(qapp):
    d = StaffDialog(None, ME, is_me=True)
    assert not d.role.isEnabled() and not d.username.isEnabled()
    assert "role" not in d.get_data() and "password" not in d.get_data()
    other = StaffDialog(None, ASHA)
    assert other.get_data()["role"] == "achari"


def test_password_rules():
    assert password_problem("short", "short") is not None
    assert "match" in password_problem("LongEnough1", "Different12")
    assert password_problem("LongEnough1", "LongEnough1") is None


def test_password_dialog_refuses_a_mismatch(qapp, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[2])))
    d = PasswordDialog(None, "New password", ask_current=True)
    d.new.setText("LongEnough1")
    d.repeat.setText("nope")
    d._check()
    assert warned and "match" in warned[0] and d.result() == 0


@pytest.mark.parametrize(
    "role,sees",
    [(UserRole.OWNER, True), (UserRole.MANAGER, False), (UserRole.SALES, False), (UserRole.ACHARI, False), (UserRole.WORKER, False)],
)
def test_only_the_owner_sees_staff_in_the_menu(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert ("Staff" in [label for _, label, _ in w._get_allowed_nav_items()]) is sees


def test_emailing_a_code_asks_the_server_and_tells_the_owner(qapp, fake, dialogs):
    s = StaffScreen()
    s.refresh_data()
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[1].click()
    assert fake == [("invite", "u1")]
    assert dialogs and dialogs[0][1] == "Code sent"


def test_a_person_added_while_email_is_down_is_kept_and_the_owner_is_told(qapp, monkeypatch, dialogs):
    from services.api_client import APIError

    def refuse(self, data):
        raise APIError(503, '{"detail": "Email is not set up yet"}')

    monkeypatch.setattr(StaffService, "me", lambda self: ME)
    monkeypatch.setattr(StaffService, "users", lambda self: [ME])
    monkeypatch.setattr(StaffService, "create", refuse)
    monkeypatch.setattr(StaffDialog, "exec", lambda self: 1)
    monkeypatch.setattr(StaffDialog, "get_data", lambda self: {"username": "kavya", "full_name": "Kavya", "email": "k@x.com"})
    s = StaffScreen()
    s._add()
    assert dialogs and "Added, but the email did not go" in dialogs[0][1]
    assert "Email is not set up yet" in dialogs[0][2]


# ---------------------------------------------------------------- pay types (docs/HR_CONTRACT.md, H2)
def test_an_older_server_keeps_the_daily_wage_form(qapp):
    d = StaffDialog(None, ASHA)
    assert "pay_type" not in d.get_data() and "base_daily_wage" in d.get_data()
    assert d.pay_type.parent() is None or not d.pay_type.isVisibleTo(d)  # not on the form


def test_a_server_with_pay_types_gets_the_type_and_the_rate(qapp):
    d = StaffDialog(None, {**ASHA, "pay_type": "monthly", "pay_amount": "18000", "employment": "part_time"}, pay_types=True)
    assert d.pay_type.currentData() == "monthly" and d.employment.currentData() == "part_time" and d.wage.value() == 18000
    assert d.wage.suffix() == " / month"
    data = d.get_data()
    assert (data["pay_type"], data["pay_amount"], data["employment"]) == ("monthly", 18000, "part_time")
    assert "base_daily_wage" not in data  # the server works the daily figure out
    d.pay_type.setCurrentIndex(d.pay_type.findData("daily"))
    assert d.get_data()["base_daily_wage"] == 18000 and d.wage.suffix() == " / day"


def test_salary_history_lists_rates_and_saves_a_new_one(qapp):
    from ui.staff_screen import WageHistoryDialog

    class Svc:
        added = []

        def wages(self, uid):
            return [{"effective_from": "2026-04-01", "pay_type": "daily", "amount": "600", "note": "start"}]

        def add_wage(self, uid, data):
            self.added.append((uid, data))

    svc = Svc()
    d = WageHistoryDialog(None, ASHA, svc)
    assert d.table.rowCount() == 1 and d.table.item(0, 1).text() == "Daily wage" and d.table.item(0, 2).text() == "₹600.00"
    d.pay_type.setCurrentIndex(d.pay_type.findData("monthly"))
    d.amount.setValue(18000)
    d._add()
    uid, data = svc.added[0]
    assert uid == ASHA["id"] and data["pay_type"] == "monthly" and data["amount"] == 18000 and "effective_from" in data


def test_a_person_whose_pay_the_server_hid_is_not_given_pay_fields_to_overwrite(qapp):
    d = StaffDialog(None, {**ASHA, "pay_type": None, "pay_amount": None}, pay_types=True)  # null: this user may not read pay
    data = d.get_data()
    assert "pay_type" not in data and "pay_amount" not in data
