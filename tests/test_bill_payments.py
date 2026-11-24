"""B3 and B4 on the desktop: split payments at the till, the payments window, the return window.
The server side is described in docs/BILLING_B3_B4_CONTRACT.md; these tests use a fake one."""

from PyQt6.QtWidgets import QMessageBox

from services.sales_service import SalesService
from ui.bill_payments import PaymentsDialog, ReturnDialog
from ui.sales_screen import CartItem, SalesScreen

SALE = {
    "id": "s1", "invoice_number": "INV-1", "total_amount": 1000, "discount": 0,
    "amount_paid": 400, "balance_due": 600, "order_status": "completed",
    "payments": [{"id": "p1", "method": "cash", "amount": 400, "paid_on": "2026-11-24"}],
}


def test_split_payment_at_the_till_sends_each_payment(qapp, monkeypatch):
    s = SalesScreen()
    s._cart = [CartItem("i1", "Chair", 1000.0, 0.0, 1)]
    s._update_totals()
    s.received_in.setValue(400)  # 400 handed over as cash...
    s._add_split_row()  # ...and the rest on UPI: the new row starts at what is still owed
    method, amount, _row = s._split_rows[0]
    assert amount.value() == 600
    method.setCurrentIndex(method.findData("upi"))
    assert s._received() == 1000 and s.pay_note.text() == ""
    assert s._payment() == {
        "payments": [{"amount": 400, "method": "cash"}, {"amount": 600, "method": "upi"}],
        "payment_status": "paid",
    }

    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    sent = {}
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(SalesService, "is_online", lambda self: True)
    monkeypatch.setattr(s._customer_service, "ensure_customer", lambda n, p: "c1")
    monkeypatch.setattr(SalesService, "create_sale", lambda self, **kw: sent.update(kw) or {"invoice_number": "INV-9", "payment_status": "paid"})
    monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: "b.pdf")
    monkeypatch.setattr(SalesService, "open_pdf", staticmethod(lambda p: None))
    s._generate_invoice()
    assert sent["payments"] == [{"amount": 400, "method": "cash"}, {"amount": 600, "method": "upi"}]
    assert s._split_rows == []  # the next bill starts with one payment again


def test_a_split_payment_is_not_saved_offline(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    s = SalesScreen()
    s._cart = [CartItem("i1", "Chair", 1000.0, 0.0, 1)]
    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    s._update_totals()
    s.received_in.setValue(400)
    s._add_split_row()
    monkeypatch.setattr(SalesService, "is_online", lambda self: False)
    s._generate_invoice()
    assert "split payment" in shown[-1] and s._cart


class FakeSales:
    def __init__(self):
        self.calls = []

    def add_payment(self, sale_id, data):
        self.calls.append(("add", sale_id, data))
        pays = SALE["payments"] + [{"id": "p2", **data}]
        return {**SALE, "amount_paid": 1000, "balance_due": 0, "payments": pays}

    def void_payment(self, sale_id, pid, reason):
        self.calls.append(("void", sale_id, pid, reason))
        return {**SALE, "amount_paid": 0, "balance_due": 1000, "payments": [{**SALE["payments"][0], "voided_at": "x", "void_reason": reason}]}


def test_payments_window_adds_the_balance_by_default_and_voids_with_a_reason(qapp, monkeypatch):
    fake = FakeSales()
    d = PaymentsDialog(None, SALE, fake)
    assert "paid ₹400.00" in d.summary.text() and "still to pay ₹600.00" in d.summary.text()
    assert d.amount.value() == 600 and d.table.rowCount() == 1
    d.method.setCurrentIndex(d.method.findData("upi"))
    d.reference.setText("UPI123")
    d._add()
    assert fake.calls[-1] == ("add", "s1", {"amount": 600.0, "method": "upi", "reference": "UPI123"})
    assert d.table.rowCount() == 2 and not d.add_btn.isEnabled()  # nothing left to pay

    monkeypatch.setattr("ui.bill_payments.QInputDialog.getText", lambda *a, **k: ("entered twice", True))
    d.table.selectRow(0)
    d._void()
    assert fake.calls[-1] == ("void", "s1", "p1", "entered twice")
    assert "Taken off: entered twice" in d.table.item(0, 4).text()


def test_return_window_limits_to_what_is_left_and_estimates_the_refund(qapp):
    sale = {"id": "s1", "invoice_number": "INV-1", "discount": 150, "returned_quantities": {"l1": 1}}
    items = [
        {"id": "l1", "item_name": "Chair", "quantity": 2, "total_price": 1000},
        {"id": "l2", "item_name": "Lamp", "quantity": 1, "total_price": 500},
    ]
    d = ReturnDialog(None, sale, items)
    assert d.spins[0].maximum() == 1 and d.spins[1].maximum() == 1  # one chair already came back
    assert not d.ok_btn.isEnabled()
    d.spins[0].setValue(1)
    assert d.lines() == [{"sale_item_id": "l1", "quantity": 1}]
    assert d.refund() == 450  # 500 for the chair, less its share of the 150 discount
    assert d.ok_btn.isEnabled() and "450.00" in d.estimate.text()


def test_service_calls_the_contract_routes(monkeypatch, tmp_path):
    from services.api_client import APIClient

    seen = []
    monkeypatch.setattr(APIClient, "_post", lambda self, path, token, json=None, **k: seen.append((path, json)) or {})
    monkeypatch.setattr(APIClient, "_get_file", lambda self, path, token: seen.append((path, None)) or b"%PDF-1")
    monkeypatch.setattr(SalesService, "INVOICE_DIR", tmp_path)
    svc = SalesService()
    svc.add_payment("s1", {"amount": 5, "method": "cash"})
    svc.void_payment("s1", "p1", "typo")
    svc.create_return("s1", [{"sale_item_id": "l1", "quantity": 1}], "cracked", "cash", False)
    path = svc.fetch_and_save_credit_note("CN/26-27/0001")
    assert [p for p, _ in seen] == ["/sales/s1/payments", "/sales/s1/payments/p1/void", "/sales/s1/returns", "/returns/CN/26-27/0001/pdf"]
    assert seen[2][1] == {"items": [{"sale_item_id": "l1", "quantity": 1}], "reason": "cracked", "refund_method": "cash", "restock": False}
    assert path.name == "CN-26-27-0001.pdf"  # the slashes of the number cannot be in a file name
