"""Receipts on paper: the figures, the provisional wording, the roll that grows with the bill, the PDF."""

from ui import receipt_render as rr
from conftest import create_bill

SALE = {
    "invoice_number": "NTD-0007", "created_at": "2026-11-24T10:00:00", "sub_total": 1000, "tax_total": 180,
    "discount": 80, "total_amount": 1100, "amount_paid": 600, "balance_due": 500, "payment_method": "upi",
    "customer_name": "Meena", "customer_phone": "9876543210",
}
ITEM = {"item_name": "Teak stool", "quantity": 2, "price_at_sale": 500, "gst_percent": 18, "cgst_amount": 90, "sgst_amount": 90, "total_price": 1180}


def test_receipt_takes_its_figures_from_the_bill():
    r = rr.receipt_from_sale(SALE, [ITEM], {"name": "Vriksha Studios"})
    assert (r["sub"], r["cgst"], r["sgst"], r["discount"], r["total"]) == (1000, 90, 90, 80, 1100)
    assert (r["paid"], r["balance"], r["number"], r["date"]) == (600, 500, "NTD-0007", "2026-11-24")
    assert r["lines"][0]["amount"] == 1180 and not r["provisional"]


def test_an_offline_bill_has_no_server_totals_so_they_are_worked_out_and_it_says_provisional():
    cart = [{"item_name": "Lamp", "quantity": 1, "price_at_sale": 100, "gst_percent": 12}]
    r = rr.receipt_from_sale({"invoice_number": "AB12CD34", "payment_status": "paid", "total_amount": 112}, cart, {}, provisional=True)
    assert r["sub"] == 100 and r["cgst"] == 6 and r["sgst"] == 6 and r["paid"] == 112 and r["balance"] == 0
    assert r["provisional"]


def test_a_roll_is_as_long_as_the_bill_needs(qapp):
    short = rr.receipt_from_sale(SALE, [ITEM], {"name": "Vriksha Studios"})
    long = rr.receipt_from_sale(SALE, [ITEM] * 12, {"name": "Vriksha Studios"})
    fmt = rr.BY_KEY["thermal_80"]
    a, b = rr.receipt_image(fmt, short), rr.receipt_image(fmt, long)
    assert a.width() == b.width() and b.height() > a.height() + 100
    assert rr.receipt_image(rr.BY_KEY["a4"], short).height() > rr.receipt_image(rr.BY_KEY["a4"], short).width()  # a sheet keeps its size


def test_every_paper_saves_a_pdf_and_the_choice_is_remembered(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    from ui.receipt_dialog import ReceiptDialog

    r = rr.receipt_from_sale(SALE, [ITEM], {"name": "Vriksha Studios"})
    for key, *_ in rr.FORMATS:
        out = tmp_path / f"{key}.pdf"
        rr.save_pdf(str(out), rr.BY_KEY[key], r)
        assert out.read_bytes().startswith(b"%PDF")
    QSettings("VrikshaStudios", "Nakama").remove("receipt/paper")
    d = ReceiptDialog(None, r)
    d.paper.setCurrentIndex(d.paper.findData("a5"))
    assert ReceiptDialog(None, r).paper.currentData() == "a5"
    QSettings("VrikshaStudios", "Nakama").remove("receipt/paper")


def test_the_till_keeps_the_last_bill_for_a_receipt(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from services.sales_service import SalesService
    from ui.sales_screen import CartItem, SalesScreen

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    s = SalesScreen()
    assert not s.receipt_btn.isEnabled()
    s._cart = [CartItem("i1", "Chair", 100.0, 0.0, 1)]
    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    monkeypatch.setattr(SalesService, "is_online", lambda self: False)
    create_bill(s)  # saved offline
    sale, items, provisional = s._last_bill
    assert provisional and sale["customer_name"] == "Meena" and items[0]["item_name"] == "Chair" and s.receipt_btn.isEnabled()


def test_a_payslip_comes_from_one_payout(qapp, tmp_path):
    pay = {"paid_on": "2026-11-24", "gross_daily": "6000", "gross_extras": "1500", "deductions": "500", "net_paid": "7000", "method": "upi"}
    p = rr.payslip_from_payment(pay, "Ravi", "Achari", {"name": "Vriksha Studios"})
    assert (p["gross"], p["deductions"], p["net"], p["payslip"]) == (7500, 500, 7000, True)
    out = tmp_path / "slip.pdf"
    for key, *_ in rr.FORMATS:
        rr.save_pdf(str(out), rr.BY_KEY[key], p)
        assert out.read_bytes().startswith(b"%PDF")
    assert rr.receipt_image(rr.BY_KEY["a5"], p).height() > 100


def test_payroll_screen_prints_the_selected_payout(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from services.session import Session
    from ui import payroll_screen
    from ui.receipt_dialog import ReceiptDialog

    monkeypatch.setattr(Session, "can", classmethod(lambda cls, a, *x: True))
    s = payroll_screen.PayrollScreen()
    owed = [{"user_id": "u1", "full_name": "Ravi", "username": "ravi", "role": "achari", "pending_daily": "0", "pending_extras": "0", "owed_gross": "0", "advance_balance": "0"}]
    pays = [{"user_id": "u1", "paid_on": "2026-11-24", "gross_daily": "100", "gross_extras": "0", "deductions": "0", "net_paid": "100", "method": "cash"}]
    s._refresh_everyone(owed, pays)
    shown = []
    monkeypatch.setattr(ReceiptDialog, "exec", lambda self: shown.append(self._receipt))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append("hint"))
    s.payslip_btn.click()  # one pay-out in the list: no need to select it
    assert shown[-1]["payslip"] and shown[-1]["name"] == "Ravi" and shown[-1]["net"] == 100
