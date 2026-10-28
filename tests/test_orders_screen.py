"""Orders screen: the list, the details, stage buttons, payments, edits and new orders."""

import pytest
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from services.customer_service import CustomerService
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.orders_service import OrdersService, amount_of, items_summary
from services.session import Session
from ui.main_window import MainWindow
from ui.orders_screen import EditOrderDialog, NewOrderDialog, OrdersScreen, PaymentDialog


def order(n, status="confirmed", **kw):
    base = {
        "id": f"o{n}", "order_number": f"ORD-2026-000{n}", "customer_id": "c1", "customer_name": "Lakshmi Devi", "customer_phone": "9876543210",
        "order_type": "custom", "status": status, "custom_specs": {"wood": "teak"}, "estimated_amount": "10000.00", "advance_paid": "3000.00",
        "final_amount": "0.00", "balance_due": "7000.00", "expected_delivery": "2026-12-01", "order_date": "2026-10-20T09:30:00", "source": "pos",
        "delivery_address": None, "notes": "Antique finish",
        "items": [{"item_name": "Carved temple door", "quantity": 1, "unit_price": "10000.00", "notes": None}, {"item_name": None, "quantity": 2, "unit_price": "500.00", "notes": "brass"}],
        "payments": [{"id": "p1", "amount": "3000.00", "method": "upi", "reference": "UPI-1", "note": "advance", "paid_on": "2026-10-20"}],
    }
    return {**base, **kw}


WEB = order(2, "draft", source="web", customer_name="Ravi K", delivery_address={"address": "12 Temple Rd", "town": "Hindupur", "pincode": "515201"}, order_type="standard")
SHOP = order(1, "confirmed")
DONE = order(3, "delivered", advance_paid="10000.00", balance_due="0.00")
ROWS = [WEB, SHOP, DONE]


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def listing(self, status=None, source=None, search=None, limit=100):
        calls.append(("list", status, source, search))
        rows = [o for o in ROWS if (status is None or o["status"] == status) and (source is None or o["source"] == source)]
        return [o for o in rows if not search or search.lower() in (o["order_number"] + (o["customer_name"] or "")).lower()]

    monkeypatch.setattr(OrdersService, "orders", listing)
    monkeypatch.setattr(OrdersService, "set_status", lambda self, oid, st, notes=None: calls.append(("status", oid, st, notes)))
    monkeypatch.setattr(OrdersService, "add_payment", lambda self, oid, d: calls.append(("pay", oid, d)) or {**SHOP, "id": oid})
    monkeypatch.setattr(OrdersService, "update", lambda self, oid, d: calls.append(("update", oid, d)))
    monkeypatch.setattr(OrdersService, "create", lambda self, d: calls.append(("create", d)) or {**SHOP, "id": "new1"})
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: [{"id": "i1", "name": "Teak Chair", "sku": "FUR-0001", "selling_price": "4500"}])
    monkeypatch.setattr(CustomerService, "ensure_customer", lambda self, name, phone: calls.append(("customer", name, phone)) or "c9")
    return calls


def select(screen, row):
    screen.table.selectRow(row)
    screen._selected()


def visible(widget):
    return widget.isVisibleTo(widget.window()) if widget.window() is not widget else not widget.isHidden()


def test_helpers():
    assert amount_of(order(1)) == 10000 and amount_of(order(1, final_amount="12000.00")) == 12000
    assert items_summary(order(1)) == "Carved temple door  +1 more"
    assert items_summary({"items": [{"item_name": None, "quantity": 3}]}) == "3 × Catalogue item"
    assert items_summary({}) == ""


def test_lists_open_orders_by_default_with_customer_and_money(qapp, fake):
    s = OrdersScreen()
    s.refresh_data()
    assert s.table.rowCount() == 2  # the delivered one is not "open"
    texts = {s.table.item(r, s.COL_NO).text(): r for r in range(2)}
    assert "ORD-2026-0002  🌐" in texts  # website orders are marked
    r = texts["ORD-2026-0001"]
    assert s.table.item(r, s.COL_CUSTOMER).text() == "Lakshmi Devi  ·  9876543210"
    assert s.table.item(r, s.COL_AMOUNT).text() == "₹10,000.00" and s.table.item(r, s.COL_DUE).text() == "₹7,000.00"
    assert s.table.item(r, s.COL_STATUS).text() == "Confirmed" and s.table.item(r, s.COL_DELIVERY).text() == "2026-12-01"
    assert "2 orders" in s.count.text()


def test_filters_and_search_reach_the_server(qapp, fake):
    s = OrdersScreen()
    s.status.setCurrentIndex(s.status.findData("delivered"))
    assert fake[-1] == ("list", "delivered", None, "")
    s.source.setCurrentIndex(s.source.findData("web"))
    assert fake[-1][2] == "web"
    s.status.setCurrentIndex(s.status.findData("all"))
    assert s.table.rowCount() == 0 or fake[-1][1] is None  # "all" asks for no status filter
    s.search.setText("ravi")
    s._search_timer.stop()
    s.refresh_data()
    assert fake[-1][3] == "ravi"


def test_details_show_customer_address_pieces_and_payments(qapp, fake):
    s = OrdersScreen()
    s.status.setCurrentIndex(s.status.findData("all"))
    s.source.setCurrentIndex(0)
    web_row = next(r for r in range(s.table.rowCount()) if s.table.item(r, 0).text().startswith("ORD-2026-0002"))
    select(s, web_row)
    assert "New" in s.heading.text() and "Website standard order" in s.heading.text()
    assert "Ravi K" in s.who.text() and "12 Temple Rd, Hindupur, 515201" in s.who.text()
    shop_row = next(r for r in range(s.table.rowCount()) if s.table.item(r, 0).text() == "ORD-2026-0001")
    select(s, shop_row)
    assert "Paid ₹3,000.00" in s.extra.text() and "Due ₹7,000.00" in s.extra.text() and "Promised 2026-12-01" in s.extra.text()
    assert "wood: teak" in s.extra.text() and "Antique finish" in s.extra.text()
    assert [s.lines.item(r, 0).text() for r in range(2)] == ["Carved temple door", "Catalogue piece"]
    assert s.payments.item(0, 1).text() == "₹3,000.00" and s.payments.item(0, 2).text() == "UPI" and s.payments.item(0, 3).text() == "UPI-1 · advance"


@pytest.mark.parametrize(
    "status,label",
    [("draft", "Confirm order"), ("confirmed", "Start work"), ("in_production", "Mark ready"), ("ready", "Mark delivered")],
)
def test_one_button_moves_the_order_to_its_next_stage(qapp, fake, monkeypatch, status, label):
    o = order(5, status)
    monkeypatch.setattr(OrdersService, "orders", lambda self, *a, **k: [o])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    s = OrdersScreen()
    s.refresh_data()
    select(s, 0)
    assert label in s.next_btn.text() and not s.next_btn.isHidden()
    s.next_btn.click()
    assert fake[-1][:3] == ("status", "o5", {"draft": "confirmed", "confirmed": "in_production", "in_production": "ready", "ready": "delivered"}[status])


def test_delivering_with_a_balance_asks_first(qapp, fake, monkeypatch):
    o = order(6, "ready")  # Rs 7,000 still due
    monkeypatch.setattr(OrdersService, "orders", lambda self, *a, **k: [o])
    s = OrdersScreen()
    s.refresh_data()
    select(s, 0)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    s.next_btn.click()
    assert not [c for c in fake if c[0] == "status"]  # said no
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    s.next_btn.click()
    assert fake[-1] == ("status", "o6", "delivered", None)
    paid_up = order(7, "ready", advance_paid="10000.00", balance_due="0.00")
    monkeypatch.setattr(OrdersService, "orders", lambda self, *a, **k: [paid_up])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("no question when nothing is due"))))
    s.refresh_data()
    select(s, 0)
    s.next_btn.click()
    assert fake[-1][:3] == ("status", "o7", "delivered")


def test_cancelling_needs_a_reason_and_keeps_the_old_notes(qapp, fake, monkeypatch, dialogs):
    s = OrdersScreen()
    s.refresh_data()
    select(s, next(r for r in range(s.table.rowCount()) if s.table.item(r, 0).text() == "ORD-2026-0001"))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("x", True)))
    s.cancel_btn.click()
    assert dialogs[-1][0] == "warning" and not [c for c in fake if c[0] == "status"]
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("customer changed mind", True)))
    s.cancel_btn.click()
    assert next(c for c in fake if c[0] == "status") == ("status", "o1", "cancelled", "Antique finish\nCancelled: customer changed mind")


@pytest.mark.parametrize("role,manage", [(UserRole.OWNER, True), (UserRole.MANAGER, True), (UserRole.SALES, False)])
def test_only_the_owner_and_manager_change_stages_or_edit(qapp, fake, monkeypatch, role, manage):
    monkeypatch.setattr(Session, "_role", role)
    s = OrdersScreen()
    s.refresh_data()
    select(s, next(r for r in range(s.table.rowCount()) if s.table.item(r, 0).text() == "ORD-2026-0001"))
    assert (not s.next_btn.isHidden()) is manage and (not s.edit_btn.isHidden()) is manage and (not s.cancel_btn.isHidden()) is manage
    assert not s.pay_btn.isHidden()  # everyone who sells can take money


def test_a_delivered_or_cancelled_order_offers_no_change(qapp, fake, monkeypatch):
    for status in ("delivered", "cancelled"):
        o = order(8, status, advance_paid="10000.00", balance_due="0.00")
        monkeypatch.setattr(OrdersService, "orders", lambda self, *a, _o=o, **k: [_o])
        s = OrdersScreen()
        s.status.setCurrentIndex(s.status.findData("all"))
        select(s, 0)
        assert s.next_btn.isHidden() and s.edit_btn.isHidden() and s.cancel_btn.isHidden()
        assert s.pay_btn.isHidden() is (status == "cancelled")


def test_payment_dialog_starts_at_the_balance_and_cannot_exceed_it(qapp, dialogs):
    d = PaymentDialog(None, SHOP)
    assert d.amount.value() == 7000 and d.amount.maximum() == 7000
    d.amount.setValue(2000)
    d.method.setCurrentIndex(d.method.findData("upi"))
    d.reference.setText("UPI-9")
    data = d.get_data()
    assert data["amount"] == 2000 and data["method"] == "upi" and data["reference"] == "UPI-9" and data["note"] is None and data["paid_on"]
    d.amount.setValue(0)
    d._check()
    assert d.result() == 0 and dialogs[-1][0] == "warning"
    unpriced = PaymentDialog(None, order(9, estimated_amount="0.00", balance_due="0.00", advance_paid="0.00"))
    assert unpriced.amount.maximum() > 1_000_000  # a deposit before the price is agreed


def test_recording_a_payment_sends_it_and_reloads(qapp, fake, monkeypatch):
    s = OrdersScreen()
    s.refresh_data()
    select(s, next(r for r in range(s.table.rowCount()) if s.table.item(r, 0).text() == "ORD-2026-0001"))
    monkeypatch.setattr(PaymentDialog, "exec", lambda self: 1)
    s.pay_btn.click()
    pay = next(c for c in fake if c[0] == "pay")
    assert pay[1] == "o1" and pay[2]["amount"] == 7000 and pay[2]["method"] == "cash"


def test_edit_dialog_sends_only_what_changed(qapp, dialogs):
    d = EditOrderDialog(None, SHOP)
    assert d.get_data() == {}
    d.final.setValue(11000)
    d.notes.setPlainText("Antique finish, brass hinges")
    assert d.get_data() == {"final_amount": 11000.0, "notes": "Antique finish, brass hinges"}
    d.has_date.setChecked(False)
    assert d.get_data()["expected_delivery"] is None  # clearing the promised date
    low = EditOrderDialog(None, SHOP)
    low.final.setValue(1000)  # less than the 3,000 already paid
    low._check()
    assert low.result() == 0 and "already paid" in dialogs[-1][2]


def test_new_order_dialog_builds_custom_and_catalogue_lines(qapp, dialogs):
    items = [{"id": "i1", "name": "Teak Chair", "sku": "FUR-0001", "selling_price": "4500"}]
    d = NewOrderDialog(None, items)
    d._check()
    assert d.result() == 0 and "Describe each custom piece" in dialogs[-1][2]  # the blank custom line
    d.lines.cellWidget(0, 1).setText("Door with Ganesha, 6 ft")
    d.lines.cellWidget(0, 3).setValue(25000)
    d._add_line()
    d.lines.cellWidget(1, 0).setCurrentIndex(d.lines.cellWidget(1, 0).findData("i1"))
    d.lines.cellWidget(1, 2).setValue(2)
    assert d.lines.cellWidget(1, 3).value() == 4500  # the catalogue price comes in by itself
    assert d.estimate.value() == 25000 + 2 * 4500  # and the estimate adds up
    d.name.setText("Lakshmi")
    d.phone.setText("9876543210")
    d.advance.setValue(10000)
    d.method.setCurrentIndex(d.method.findData("upi"))
    d.has_date.setChecked(True)
    data = d.get_data()
    assert data["name"] == "Lakshmi" and data["advance"] == 10000 and data["method"] == "upi"
    o = data["order"]
    assert o["advance_paid"] == 0 and o["estimated_amount"] == 34000 and o["expected_delivery"]
    assert o["items"] == [{"quantity": 1, "unit_price": 25000.0, "item_name": "Door with Ganesha, 6 ft"}, {"quantity": 2, "unit_price": 4500.0, "item_id": "i1"}]
    d.advance.setValue(40000)  # more than the estimate
    d._check()
    assert d.result() == 0 and "more than the estimate" in dialogs[-1][2]


def test_a_typed_estimate_is_not_overwritten_by_the_lines(qapp):
    d = NewOrderDialog(None, [])
    d.estimate.setValue(18000)  # agreed by hand
    d.lines.cellWidget(0, 3).setValue(5000)
    assert d.estimate.value() == 18000


def test_creating_an_order_finds_the_customer_then_records_the_advance_as_a_payment(qapp, fake, monkeypatch):
    s = OrdersScreen()
    s.refresh_data()
    monkeypatch.setattr(NewOrderDialog, "exec", lambda self: (self.lines.cellWidget(0, 1).setText("Mandap pillar"), self.lines.cellWidget(0, 3).setValue(12000), self.name.setText("Lakshmi"), self.phone.setText("9876543210"), self.advance.setValue(4000), 1)[-1])
    s.new_btn.click()
    kinds = [c[0] for c in fake]
    assert kinds.index("customer") < kinds.index("create") < kinds.index("pay")
    create = next(c for c in fake if c[0] == "create")[1]
    assert create["customer_id"] == "c9" and create["advance_paid"] == 0 and create["estimated_amount"] == 12000
    pay = next(c for c in fake if c[0] == "pay")
    assert pay[2]["amount"] == 4000 and pay[2]["note"] == "Advance"


def test_a_walk_in_order_needs_no_customer(qapp, fake, monkeypatch):
    s = OrdersScreen()
    monkeypatch.setattr(NewOrderDialog, "exec", lambda self: (self.lines.cellWidget(0, 1).setText("Small stool"), 1)[-1])
    s.new_btn.click()
    assert not [c for c in fake if c[0] in ("customer", "pay")] and "customer_id" not in next(c for c in fake if c[0] == "create")[1]


@pytest.mark.parametrize(
    "role,sees",
    [(UserRole.OWNER, True), (UserRole.MANAGER, True), (UserRole.SALES, True), (UserRole.ACHARI, False), (UserRole.WORKER, False), (UserRole.ARTISAN, False)],
)
def test_who_sees_orders_in_the_menu(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert ("Orders" in [label for _, label, _ in w._get_allowed_nav_items()]) is sees
