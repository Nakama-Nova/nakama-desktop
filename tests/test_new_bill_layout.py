"""New Bill: lakh-grouped money, a summary panel that holds the total, a quiet Clear."""

import pytest

from services.money import inr
from ui.sales_screen import CartItem, SalesScreen


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "₹0.00"),
        (None, "₹0.00"),
        (999.5, "₹999.50"),
        (1000, "₹1,000.00"),
        (22400, "₹22,400.00"),
        (100000, "₹1,00,000.00"),
        (184600.5, "₹1,84,600.50"),
        (12345678.9, "₹1,23,45,678.90"),
        (-6000, "-₹6,000.00"),
    ],
)
def test_amounts_use_lakh_grouping(value, expected):
    assert inr(value) == expected


def test_no_decimals_when_asked():
    assert inr(1284600, 0) == "₹12,84,600"


def test_totals_sit_in_the_summary_panel_and_read_like_rupees(qapp):
    w = SalesScreen()
    w._cart = [CartItem("a", "Rosewood sofa set", 185000, 18, 1), CartItem("b", "Brass lamp", 4800, 12, 2)]
    w._refresh_table()
    assert w.subtotal_lbl.text() == "₹1,94,600.00"
    assert w.cgst_lbl.text() == w.sgst_lbl.text() == "₹17,226.00"  # half of 18% on the sofa and 12% on two lamps
    assert w.grandtotal_lbl.text() == "₹2,29,052.00"
    assert w.table.item(0, w.COL_TOTAL).text() == "₹2,18,300.00"
    # Money is right-aligned so digits line up
    assert w.table.item(0, w.COL_PRICE).textAlignment() & 0x2  # Qt.AlignRight


def test_create_is_the_loud_button_and_clear_is_quiet(qapp):
    w = SalesScreen()
    assert w.invoice_btn.text() == "Create bill"
    assert w.clear_btn.text() == "Clear bill"
    assert "background: transparent" in w.clear_btn.styleSheet()
    w._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    w._refresh_table()
    w.clear_btn.click()
    assert w._cart == [] and w.grandtotal_lbl.text() == "₹0.00"


# ---------------------------------------------------------------- Paid by
def test_paid_by_offers_the_methods_bill_history_knows_and_not_paid_yet(qapp):
    from ui.sales_history_screen import METHODS

    w = SalesScreen()
    labels = [w.pay_pick.itemText(i) for i in range(w.pay_pick.count())]
    assert labels[:-1] == [label for label, _ in METHODS] and labels[-1] == "Not paid yet"
    assert w.pay_pick.currentText() == "Cash"  # the usual counter sale


def test_a_method_means_paid_and_not_paid_yet_means_pending(qapp):
    w = SalesScreen()
    assert w._payment() == {"payment_method": "cash", "payment_status": "paid"}
    w.pay_pick.setCurrentIndex(w.pay_pick.findText("UPI"))
    assert w._payment() == {"payment_method": "upi", "payment_status": "paid"}
    w.pay_pick.setCurrentIndex(w.pay_pick.findText("Not paid yet"))
    assert w._payment() == {"payment_status": "pending"}


def test_clearing_the_bill_goes_back_to_cash(qapp):
    w = SalesScreen()
    w.pay_pick.setCurrentIndex(w.pay_pick.findText("Card"))
    w.clear_btn.click()
    assert w.pay_pick.currentText() == "Cash"


def test_the_online_bill_carries_how_it_was_paid(qapp, monkeypatch):
    from services.customer_service import CustomerService
    from services.sales_service import SalesService

    w = SalesScreen()
    w._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    w.phone_input.setText("9876543210")
    w.customer_input.setText("Meena")
    w.pay_pick.setCurrentIndex(w.pay_pick.findText("UPI"))
    seen = {}
    monkeypatch.setattr(SalesService, "is_online", lambda self: True)
    monkeypatch.setattr(CustomerService, "ensure_customer", lambda self, n, p: "cust-1")

    def create(self, items, customer_id=None, client_id=None, **kw):
        seen.update(kw)
        return None  # stop here: the point is what was sent

    monkeypatch.setattr(SalesService, "create_sale", create)
    monkeypatch.setattr("ui.sales_screen.QMessageBox.critical", lambda *a, **k: None)
    w._generate_invoice()
    assert seen == {"payment_method": "upi", "payment_status": "paid"}


def test_an_offline_bill_keeps_the_method_and_says_the_server_shows_it_unpaid(qapp, monkeypatch):
    import json

    from database.outbox_repository import OutboxRepository
    from services.sales_service import SalesService

    w = SalesScreen()
    w._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    w.phone_input.setText("9876543210")
    w.customer_input.setText("Meena")
    w.pay_pick.setCurrentIndex(w.pay_pick.findText("Card"))
    shown = []
    monkeypatch.setattr(SalesService, "is_online", lambda self: False)
    monkeypatch.setattr("ui.sales_screen.QMessageBox.information", lambda *a, **k: shown.append(a[2]))
    w._generate_invoice()
    (entry,) = OutboxRepository().get_pending()
    payload = json.loads(entry.payload)
    assert payload["payment_method"] == "card" and payload["payment_status"] == "paid"
    assert "correct it in Bill History" in shown[-1]


def test_a_bill_not_paid_yet_is_queued_without_a_method(qapp, monkeypatch):
    import json

    from database.outbox_repository import OutboxRepository
    from services.sales_service import SalesService

    w = SalesScreen()
    w._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    w.phone_input.setText("9876543210")
    w.customer_input.setText("Meena")
    w.pay_pick.setCurrentIndex(w.pay_pick.findText("Not paid yet"))
    shown = []
    monkeypatch.setattr(SalesService, "is_online", lambda self: False)
    monkeypatch.setattr("ui.sales_screen.QMessageBox.information", lambda *a, **k: shown.append(a[2]))
    w._generate_invoice()
    (entry,) = OutboxRepository().get_pending()
    payload = json.loads(entry.payload)
    assert payload["payment_method"] is None and payload["payment_status"] == "pending"
    assert "correct it" not in shown[-1]  # nothing to correct


def test_the_api_sends_payment_fields_only_when_chosen(monkeypatch):
    from services.api_client import APIClient

    api = APIClient()
    sent = []
    monkeypatch.setattr(api, "_post", lambda path, token, json=None: sent.append(json) or {"invoice_number": "X"})
    api.create_sale("t", [{"item_id": "a", "quantity": 1}])
    api.create_sale("t", [{"item_id": "a", "quantity": 1}], payment_method="upi", payment_status="paid")
    assert "payment_method" not in sent[0] and "payment_status" not in sent[0]  # server default: not paid
    assert sent[1]["payment_method"] == "upi" and sent[1]["payment_status"] == "paid"
