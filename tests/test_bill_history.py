"""Bill History: payment words, filters, and deleting a bill or correcting its payment."""

import pytest
from PyQt6.QtWidgets import QDialog, QPushButton

import services.api_client as api_client
from services.enums import UserRole
from services.sales_service import SalesService
from services.session import Session
from ui.sales_history_screen import DeleteBillDialog, PaymentDialog, SalesHistoryScreen, is_cancelled

SALES = [
    {"id": "s1", "invoice_number": "NTD-0001", "total_amount": "18500.00", "created_at": "2026-11-02T10:00:00", "payment_status": "paid", "payment_method": "cash", "order_status": "completed"},
    {"id": "s2", "invoice_number": "NTD-0002", "total_amount": "9000.00", "created_at": "2026-11-02T11:00:00", "payment_status": "pending", "order_status": "completed"},
    {"id": "s3", "invoice_number": "NTD-0003", "total_amount": "500.00", "created_at": "2026-11-01T09:00:00", "payment_status": "paid", "order_status": "cancelled"},
]


@pytest.fixture
def history(monkeypatch):
    calls = []
    monkeypatch.setattr(SalesService, "get_sales", lambda self, customer_id=None, date=None: SALES)
    monkeypatch.setattr(SalesService, "cancel_sale", lambda self, sid, reason: calls.append(("cancel", sid, reason)))
    monkeypatch.setattr(SalesService, "edit_sale", lambda self, sid, changes: calls.append(("edit", sid, changes)))
    return calls


def buttons(screen, row):
    return [b.text() for b in screen.table.cellWidget(row, screen.COL_ACTIONS).findChildren(QPushButton)]


def test_each_bill_says_how_it_was_paid_and_cancelled_ones_are_marked(qapp, history):
    s = SalesHistoryScreen()
    s.refresh_data()
    words = [s.table.item(r, s.COL_PAYMENT).text() for r in range(s.table.rowCount())]
    assert words == ["Paid", "Not paid yet", "Cancelled"]
    assert s.table.item(2, 0).font().strikeOut()  # a deleted bill reads as struck through
    assert is_cancelled(SALES[2]) and not is_cancelled(SALES[0])


def test_the_chips_count_and_filter_the_bills(qapp, history):
    s = SalesHistoryScreen()
    s.refresh_data()
    assert s.table.rowCount() == 3
    s.chips.choose("pending")
    assert [s.table.item(r, 0).text() for r in range(s.table.rowCount())] == ["NTD-0002"]
    s.chips.choose("paid")
    assert [s.table.item(r, 0).text() for r in range(s.table.rowCount())] == ["NTD-0001"]  # a cancelled bill is not "paid"
    s.chips.choose("cancelled")
    assert [s.table.item(r, 0).text() for r in range(s.table.rowCount())] == ["NTD-0003"]
    s.chips.choose("all")
    s.search.setText("0002")
    assert s.table.rowCount() == 1


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.OWNER, ["👁️ View", "🖨️ Print", "✏️ Payment", "🗑️ Delete"]),
        (UserRole.MANAGER, ["👁️ View", "🖨️ Print", "✏️ Payment"]),  # may correct payment, never delete
        (UserRole.SALES, ["👁️ View", "🖨️ Print"]),
    ],
)
def test_who_gets_which_buttons(qapp, history, monkeypatch, role, expected):
    monkeypatch.setattr(Session, "_role", role)
    s = SalesHistoryScreen()
    s.refresh_data()
    assert buttons(s, 0) == expected
    assert buttons(s, 2) == ["👁️ View", "🖨️ Print"]  # nothing more to do to a deleted bill


def test_deleting_a_bill_asks_why_and_sends_the_reason(qapp, history, monkeypatch, dialogs):
    s = SalesHistoryScreen()
    s.refresh_data()
    monkeypatch.setattr(DeleteBillDialog, "exec", lambda self: (self.reason.setText("billed twice"), QDialog.DialogCode.Accepted)[1])
    s._delete_bill(SALES[1])
    assert history == [("cancel", "s2", "billed twice")]
    assert dialogs and "Bill NTD-0002 was deleted" in dialogs[-1][2]


def test_a_bill_is_not_deleted_without_a_reason(qapp, history, dialogs):
    d = DeleteBillDialog(None, SALES[0])
    d.reason.setText("x")
    d._check()
    assert dialogs and "why" in dialogs[-1][2].lower() and d.result() == 0
    d.reason.setText("wrong item")
    d._check()
    assert d.result() == 1 and d.reason_text() == "wrong item"


def test_correcting_a_payment_sends_only_what_changed(qapp, history, monkeypatch):
    s = SalesHistoryScreen()
    s.refresh_data()
    d = PaymentDialog(None, SALES[1])
    assert d.changes() == {}  # nothing touched, nothing to send
    d.status.setCurrentIndex(d.status.findData("paid"))
    d.method.setCurrentIndex(d.method.findData("upi"))
    assert d.changes() == {"payment_status": "paid", "payment_method": "upi"}
    monkeypatch.setattr(PaymentDialog, "exec", lambda self: (self.status.setCurrentIndex(self.status.findData("partial")), QDialog.DialogCode.Accepted)[1])
    s._edit_payment(SALES[1])
    assert history == [("edit", "s2", {"payment_status": "partial"})]


def test_the_client_deletes_with_the_reason_in_the_query(monkeypatch):
    seen = []

    class Resp:
        status_code, text, content = 200, "{}", b"{}"

        def json(self):
            return {"order_status": "cancelled"}

    monkeypatch.setattr(api_client._http, "delete", lambda url, **kw: seen.append((url, kw.get("params"))) or Resp())
    out = SalesService(api_client.APIClient("http://x")).cancel_sale("s9", "billed twice")
    assert seen == [("http://x/sales/s9", {"reason": "billed twice"})] and out["order_status"] == "cancelled"


def test_a_refused_delete_raises_the_servers_reason(monkeypatch):
    class Resp:
        status_code, text, content = 409, '{"detail": "This bill is already cancelled"}', b""

        def json(self):
            return {}

    monkeypatch.setattr(api_client._http, "delete", lambda url, **kw: Resp())
    with pytest.raises(api_client.APIError) as e:
        SalesService(api_client.APIClient("http://x")).cancel_sale("s9", "again")
    assert "already cancelled" in str(e.value)
