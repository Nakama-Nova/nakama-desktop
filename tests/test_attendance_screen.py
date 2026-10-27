"""
Workforce screen vs the server's rules: check-in and check-out are owner/manager/
sales only (403 otherwise), and Check Out must close the record of the worker
chosen in the box, not whichever open record happens to be listed last.
"""

import pytest

from services.enums import UserRole
from services.session import Session
from ui.attendance_screen import AttendanceScreen

ASHA, BALU = "user-asha", "user-balu"
USERS = [
    {"id": ASHA, "full_name": "Asha", "username": "asha"},
    {"id": BALU, "full_name": "Balu", "username": "balu"},
]


def rec(rid, user_id, check_in="2026-10-27T09:00:00", check_out=None):
    return {
        "id": rid,
        "user_id": user_id,
        "date": "2026-10-27",
        "status": "present",
        "check_in": check_in,
        "check_out": check_out,
        "user": {"full_name": user_id},
    }


class FakeService:
    def __init__(self, records, users=USERS):
        self.records, self.users, self.checked_out = records, users, []

    def get_users(self):
        return self.users

    def get_all_attendance(self):
        return self.records

    def get_my_attendance(self):
        return self.records

    def check_out(self, attendance_id):
        self.checked_out.append(attendance_id)
        return {"total_hours": "8.00"}


def screen_as(role, records, monkeypatch, dialogs):
    monkeypatch.setattr(Session, "_role", role)
    s = AttendanceScreen()  # offline at start-up, like the real app
    s._service = FakeService(records)
    s.refresh_data()
    return s


@pytest.mark.parametrize("role", [UserRole.WORKER, UserRole.ACHARI])
def test_roles_the_server_refuses_get_no_check_in_or_check_out(
    qapp, role, monkeypatch, dialogs
):
    s = screen_as(role, [rec("a1", ASHA)], monkeypatch, dialogs)
    assert s.btn_check_out.isHidden()
    assert not hasattr(s, "btn_check_in") and not hasattr(s, "user_combo")
    assert s.table.rowCount() == 1  # they still see their own history


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES])
def test_roles_the_server_allows_see_the_controls(qapp, role, monkeypatch, dialogs):
    s = screen_as(role, [], monkeypatch, dialogs)
    assert not s.btn_check_out.isHidden() and hasattr(s, "btn_check_in")


def test_check_out_closes_the_selected_workers_record_not_the_last_one_listed(
    qapp, monkeypatch, dialogs
):
    records = [rec("asha-open", ASHA), rec("balu-open", BALU)]  # Balu's is listed last
    s = screen_as(UserRole.OWNER, records, monkeypatch, dialogs)

    s.user_combo.setCurrentIndex(s.user_combo.findData(ASHA))
    assert s.btn_check_out.isEnabled()
    s._handle_check_out()
    assert s._service.checked_out == ["asha-open"]

    s.user_combo.setCurrentIndex(s.user_combo.findData(BALU))
    s._handle_check_out()
    assert s._service.checked_out == ["asha-open", "balu-open"]


def test_check_out_is_disabled_for_someone_who_is_not_checked_in(
    qapp, monkeypatch, dialogs
):
    records = [rec("balu-open", BALU), rec("asha-done", ASHA, check_out="2026-10-27T17:00:00")]
    s = screen_as(UserRole.MANAGER, records, monkeypatch, dialogs)

    s.user_combo.setCurrentIndex(s.user_combo.findData(ASHA))
    assert not s.btn_check_out.isEnabled()
    s._handle_check_out()  # even if triggered anyway, it must not close Balu's day
    assert s._service.checked_out == []

    s.user_combo.setCurrentIndex(s.user_combo.findData(BALU))
    assert s.btn_check_out.isEnabled()


def test_refreshing_keeps_the_selected_worker(qapp, monkeypatch, dialogs):
    s = screen_as(UserRole.OWNER, [rec("balu-open", BALU)], monkeypatch, dialogs)
    s.user_combo.setCurrentIndex(s.user_combo.findData(BALU))
    s.refresh_data()
    assert s.user_combo.currentData() == BALU and s.btn_check_out.isEnabled()


def test_the_newest_open_record_of_a_worker_wins(qapp, monkeypatch, dialogs):
    records = [
        rec("old", ASHA, check_in="2026-10-26T09:00:00"),
        rec("new", ASHA, check_in="2026-10-27T09:00:00"),
    ]
    s = screen_as(UserRole.OWNER, records, monkeypatch, dialogs)
    s.user_combo.setCurrentIndex(s.user_combo.findData(ASHA))
    s._handle_check_out()
    assert s._service.checked_out == ["new"]
