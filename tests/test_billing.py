from services.billing import change_or_balance, discount_amount, payment_status
from conftest import create_bill


def test_discount_in_rupees_or_percent_never_more_than_the_bill():
    assert discount_amount(1180, "amount", 180) == 180
    assert discount_amount(1180, "percent", 10) == 118
    assert discount_amount(999.99, "percent", 12.5) == 125.0  # 124.99875 rounds to the paisa
    assert discount_amount(500, "amount", 900) == 500
    assert discount_amount(500, "percent", 150) == 500
    assert discount_amount(500, "amount", -5) == 0


def test_payment_status_and_change():
    assert payment_status(1000, 1000) == "paid" and payment_status(1000, 1500) == "paid"
    assert payment_status(1000, 400) == "partial" and payment_status(1000, 0) == "pending"
    assert change_or_balance(1000, 1500) == ("change", 500)
    assert change_or_balance(1000, 400) == ("balance", 600)


def test_till_sends_discount_and_payment_and_blocks_offline_discount(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from services.sales_service import SalesService
    from ui.sales_screen import CartItem, SalesScreen

    msgs = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: msgs.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: msgs.append(a[2]))
    s = SalesScreen()
    s._cart = [CartItem("i1", "Chair", 1000.0, 18.0, 1)]
    s._update_totals()
    assert s._total == 1180 and s.received_in.value() == 1180  # default: paid in full

    s.discount_kind.setCurrentIndex(1)
    s.discount_in.setValue(10)  # 10 % of 1180
    assert s._discount == 118 and s._total == 1062 and s.received_in.value() == 1062
    s.received_in.setValue(500)  # the cashier types an amount: part paid, then it stays put
    s.pay_pick.setCurrentIndex(1)
    assert s._payment() == {"payment_method": "upi", "payment_status": "partial"}
    assert "Balance" in s.pay_note.text()

    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    sent = {}
    monkeypatch.setattr(SalesService, "is_online", lambda self: True)
    monkeypatch.setattr(s._customer_service, "ensure_customer", lambda n, p: "c1")
    monkeypatch.setattr(SalesService, "create_sale", lambda self, **kw: sent.update(kw) or {"invoice_number": "INV-1", "discount": 118, "payment_status": "partial"})
    monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: "b.pdf")
    monkeypatch.setattr(SalesService, "open_pdf", staticmethod(lambda p: None))
    create_bill(s)
    assert sent["discount"] == 118 and sent["payment_method"] == "upi" and sent["payment_status"] == "partial"
    assert "Balance to collect" in msgs[-1] and "did not record" not in msgs[-1]

    # offline: a discount cannot travel through the sync, so the bill is not saved
    s._cart = [CartItem("i1", "Chair", 1000.0, 18.0, 1)]
    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    s.discount_in.setValue(10)
    monkeypatch.setattr(SalesService, "is_online", lambda self: False)
    create_bill(s)
    assert "cannot be saved offline" in msgs[-1] and s._cart


def test_refund_estimate_spreads_the_bill_discount_over_the_lines():
    from services.billing import received_total, refund_estimate

    lines = [(1000, 2, 1), (500, 1, 0)]  # return 1 of 2 chairs; the lamp stays
    assert refund_estimate(lines, 0) == 500
    assert refund_estimate(lines, 150) == 450  # the 10 % discount (150 of 1500) comes off the refund too
    assert refund_estimate([(1000, 2, 0)], 0) == 0
    assert received_total(300.10, 199.90) == 500
