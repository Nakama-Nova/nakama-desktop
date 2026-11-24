"""Leave on the desktop (docs/HR_CONTRACT.md, H4), against a fake server."""

from PyQt6.QtWidgets import QMessageBox

from services.api_client import APIError
from services.session import Session
from ui.leave_screen import LeaveScreen

DATA = {
    "types": [{"id": "t1", "name": "Casual leave", "paid": True, "yearly_days": 12}, {"id": "t2", "name": "Unpaid leave", "paid": False}],
    "balances": [{"leave_type_id": "t1", "name": "Casual leave", "yearly_days": 12, "used": 2, "pending": 1, "left": 9}],
    "requests": [
        {"id": "r2", "user_name": "Anil", "leave_type_id": "t1", "from_date": "2026-12-01", "to_date": "2026-12-02", "days": 2, "status": "approved"},
        {"id": "r1", "user_name": "Ravi", "leave_type_id": "t2", "from_date": "2026-12-10", "to_date": "2026-12-10", "days": 1, "status": "pending"},
    ],
}


class Fake:
    def __init__(self, data=DATA, fail=None):
        self.data, self.fail, self.calls = data, fail, []

    def types(self):
        if self.fail:
            raise self.fail
        return self.data["types"]

    def my_balances(self):
        return self.data["balances"]

    def requests(self, status=None):
        return self.data["requests"]

    def ask(self, data):
        self.calls.append(("ask", data))
        if self.fail_ask:
            raise APIError(422, "Only 3 days of Casual leave left")

    fail_ask = False

    def decide(self, rid, approve, note=None):
        self.calls.append(("decide", rid, approve, note))

    def cancel(self, rid):
        self.calls.append(("cancel", rid))


def test_balances_requests_and_asking(qapp, monkeypatch):
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: a != "leave:request:approve"))
    fake = Fake()
    s = LeaveScreen(fake)
    s.refresh_data()
    assert "Casual leave: 9 left of 12" in s.balances.text() and s.kind.count() == 2
    assert s.table.rowCount() == 2 and s.table.item(0, 3).text() == "1"
    assert s.table.item(0, 4).text() == "Waiting"  # waiting requests first
    assert s.approve_btn.isHidden()  # asking only: a worker cannot decide
    s.half.setChecked(True)
    s.reason.setText("family function")
    s._ask()
    kind, data = fake.calls[-1]
    assert kind == "ask" and data["leave_type_id"] == "t1" and data["half_day"] is True and data["reason"] == "family function"


def test_the_server_refusing_a_request_is_shown_in_plain_words(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    fake = Fake()
    fake.fail_ask = True
    s = LeaveScreen(fake)
    s.refresh_data()
    s._ask()
    assert shown and "Only 3 days of Casual leave left" in shown[-1]


def test_a_manager_approves_or_declines_the_selected_waiting_request(qapp, monkeypatch):
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    monkeypatch.setattr("ui.leave_screen.QInputDialog.getText", lambda *a, **k: ("not this week", True))
    fake = Fake()
    s = LeaveScreen(fake)
    s.refresh_data()
    s.table.selectRow(0)  # Ravi, waiting
    s._decide(True)
    s._decide(False)
    assert fake.calls[0] == ("decide", "r1", True, None) and fake.calls[1] == ("decide", "r1", False, "not this week")
    s.table.selectRow(1)  # Anil's is already approved: nothing to decide
    n = len(fake.calls)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    s._decide(True)
    assert len(fake.calls) == n


def test_an_older_server_without_leave_says_so(qapp, monkeypatch):
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    s = LeaveScreen(Fake(fail=APIError(404, "Not Found")))
    s.refresh_data()
    assert "not switched on" in s.note.text() and s.form.isHidden() and s.table.rowCount() == 0


def test_a_leave_type_with_no_limit_does_not_break_the_balances(qapp, monkeypatch):
    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    data = {**DATA, "balances": [{"leave_type_id": "t2", "name": "Unpaid leave", "yearly_days": None, "used": 3, "pending": 0, "left": None}]}
    s = LeaveScreen(Fake(data))
    s.refresh_data()
    assert "Unpaid leave: no limit (3 taken)" in s.balances.text()
