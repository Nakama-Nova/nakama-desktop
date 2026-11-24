"""Shifts, holidays and the staff record (docs/HR_CONTRACT.md H5, H6) against a fake server."""

from PyQt6.QtWidgets import QMessageBox

from services import hr_service
from services.session import Session
from ui.hr_setup import HolidaysDialog, ProfileDialog, ShiftsDialog

USER = {"id": "u1", "username": "ravi", "full_name": "Ravi", "address": "12 Temple Road", "id_proof_type": "aadhaar", "id_proof_last4": "1234", "shift_id": "s1"}


class FakeHr:
    def __init__(self):
        self.calls = []
        self._shifts = [{"id": "s1", "name": "Day", "start_time": "09:00:00", "end_time": "18:00:00", "grace_minutes": 10, "weekly_off": [6]}]
        self._holidays = [{"id": "h1", "date": "2026-11-01", "name": "Rajyotsava", "paid": True}]

    def shifts(self):
        return self._shifts

    def save_shift(self, sid, data):
        self.calls.append(("save_shift", sid, data))

    def delete_shift(self, sid):
        self.calls.append(("delete_shift", sid))

    def set_shift(self, uid, sid):
        self.calls.append(("set_shift", uid, sid))

    def holidays(self, year):
        self.calls.append(("holidays", year))
        return self._holidays

    def add_holiday(self, day, name, paid=True):
        self.calls.append(("add_holiday", day, name, paid))

    def delete_holiday(self, hid):
        self.calls.append(("delete_holiday", hid))

    def documents(self, uid):
        return [{"id": "d1", "kind": "id_proof", "filename": "aadhaar.pdf", "uploaded_at": "2026-11-20T10:00:00", "url": "https://signed"}]

    def upload_document(self, uid, kind, path):
        self.calls.append(("upload", uid, kind, path))

    def offboard(self, uid, day, note=None):
        self.calls.append(("offboard", uid, day))
        return {"last_working_date": day, "deactivates_on": day, "gross": "5000", "advance_balance": "1000", "net_to_pay": "4000"}


class FakeStaff:
    def __init__(self):
        self.updated = []

    def update(self, uid, data):
        self.updated.append((uid, data))


def test_shifts_list_and_add_with_weekly_off(qapp):
    hr = FakeHr()
    d = ShiftsDialog(None, hr)
    assert d.table.rowCount() == 1 and d.table.item(0, 1).text() == "09:00" and d.table.item(0, 4).text() == "Sun"
    d.name.setText("Late shift")
    d.off[5].setChecked(True)  # Saturday off too (Sunday is ticked by default)
    d._add()
    _kind, sid, data = hr.calls[-1]
    assert sid is None and data["name"] == "Late shift" and data["weekly_off"] == [5, 6] and data["grace_minutes"] == 10
    d.table.selectRow(0)
    d._delete()
    assert hr.calls[-1] == ("delete_shift", "s1")


def test_holidays_by_year(qapp):
    hr = FakeHr()
    d = HolidaysDialog(None, hr)
    assert d.table.item(0, 1).text() == "Rajyotsava" and d.table.item(0, 2).text() == "Yes"
    d._move(1)
    assert hr.calls[-1] == ("holidays", d._year) and d._year > 2025
    d.name.setText("Diwali")
    d.paid.setChecked(False)
    d._add()
    assert ("add_holiday", d.day.date().toString("yyyy-MM-dd"), "Diwali", False) in hr.calls


def test_profile_saves_details_and_the_shift_but_only_the_last_four_of_an_id(qapp, monkeypatch):
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    hr, staff = FakeHr(), FakeStaff()
    d = ProfileDialog(None, USER, hr, staff)
    assert d.address.text() == "12 Temple Road" and d.proof.currentData() == "aadhaar" and d.last4.text() == "1234" and d.shift.currentData() == "s1"
    d.last4.setText("12345678")
    assert d.last4.text() == "1234"  # the box refuses more than four: the whole number is never typed in
    d.em_name.setText("Meena")
    d.upi.setText("ravi@bank")
    d.shift.setCurrentIndex(0)
    d._save()
    uid, data = staff.updated[0]
    assert uid == "u1" and data["emergency_contact_name"] == "Meena" and data["pay_upi"] == "ravi@bank" and data["id_proof_last4"] == "1234"
    assert "joining_date" not in data and hr.calls[-1] == ("set_shift", "u1", None)
    assert d.docs.rowCount() == 1 and d.docs.item(0, 0).text() == "ID proof"


def test_offboarding_shows_what_is_still_owed(qapp, monkeypatch):
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr("ui.hr_setup.QInputDialog.getText", lambda *a, **k: ("2026-12-31", True))
    hr = FakeHr()
    ProfileDialog(None, USER, hr, FakeStaff())._offboard()
    assert hr.calls[-1] == ("offboard", "u1", "2026-12-31") and "₹4,000.00" in shown[-1]


def test_document_files_are_checked_before_anything_is_sent(tmp_path):
    big = tmp_path / "scan.pdf"
    big.write_bytes(b"x" * (hr_service.MAX_DOC_BYTES + 1))
    exe = tmp_path / "run.exe"
    exe.write_bytes(b"x")
    ok = tmp_path / "id.jpg"
    ok.write_bytes(b"x")
    assert "10 MB" in hr_service.check_document(str(big)) and "PDF" in hr_service.check_document(str(exe)) and hr_service.check_document(str(ok)) is None


def test_the_upload_goes_to_storage_then_is_confirmed(monkeypatch, tmp_path):
    from services import api_client
    from services.api_client import APIClient

    f = tmp_path / "id.jpg"
    f.write_bytes(b"abc")
    seen = []
    monkeypatch.setattr(APIClient, "_post", lambda self, path, token, json=None, **k: seen.append((path, json)) or ({"document_id": "d9", "upload_url": "https://bucket/x", "headers": {"Content-Type": "image/jpeg"}} if path.endswith("upload-url") else {"id": "d9"}))

    class R:
        status_code = 200

    monkeypatch.setattr(api_client, "_send", lambda method, url, **kw: seen.append((method, url, kw["headers"])) or R())
    out = hr_service.HrService().upload_document("u1", "id_proof", str(f))
    assert out == {"id": "d9"} and seen[0][1] == {"kind": "id_proof", "filename": "id.jpg", "content_type": "image/jpeg", "size": 3}
    assert seen[1] == ("put", "https://bucket/x", {"Content-Type": "image/jpeg"}) and seen[2][0] == "/people/users/u1/documents/d9/confirm"
