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
    monkeypatch.setattr(StaffService, "reset_password", lambda self, uid, pw: calls.append(("reset", uid, pw)))
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
    assert buttons(s, 1) == ["✏️ Edit", "🔑 Password"]  # row 1 is you
    assert buttons(s, 0) == ["✏️ Edit", "🔑 Password", "Switch off"]
    assert buttons(s, 2)[-1] == "Switch on"


def test_switch_off_asks_first_then_sends_only_the_flag(qapp, fake, monkeypatch):
    s = StaffScreen()
    s.refresh_data()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[2].click()
    assert fake == []  # said no
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[2].click()
    assert fake == [("update", "u1", {"is_active": False})]


def test_add_staff_collects_login_details_and_wage(qapp):
    d = StaffDialog(None)
    d.username.setText("kavya")
    d.full_name.setText("Kavya R")
    d.email.setText("k@x.com")
    d.role.setCurrentIndex(d.role.findData("sales"))
    d.wage.setValue(700)
    d.password.setText("Strong1234")
    d.repeat.setText("Strong1234")
    data = d.get_data()
    assert data == {
        "username": "kavya", "password": "Strong1234", "full_name": "Kavya R", "email": "k@x.com",
        "phone": None, "base_daily_wage": 700.0, "role": "sales",
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
