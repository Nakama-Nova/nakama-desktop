"""One price rule on every screen: cost + profit % + GST; Stock, Bill History, Orders agree; the side panel is grouped."""

import pytest
from PyQt6.QtWidgets import QLabel

from services import pricing
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.session import Session
from ui.inventory_window import InventoryWindow
from ui.item_form import ItemDialog
from ui.main_window import MainWindow
from ui.orders_screen import NewOrderDialog
from ui.sales_history_screen import bill_text


# ------------------------------------------------------------------ the rule
def test_the_rule_matches_the_server():
    cost = pricing.cost_of(9000, 7000)
    assert cost == 16000.0
    net = pricing.price_from_cost(cost, 25)
    assert net == 20000.0 and pricing.with_gst(net, 12) == 22400.0
    assert pricing.net_from_gross(22400, 12) == 20000.0
    assert pricing.profit_percent_of(16000, 20000) == 25.0 and pricing.profit_percent_of(0, 5) is None
    assert pricing.price_from_cost("333.33", 10) == 366.66  # half up, to the paisa


def test_a_cached_item_without_the_server_figure_is_worked_out():
    assert pricing.price_with_gst({"selling_price": "1000", "gst_percent": "18"}) == 1180.0
    assert pricing.price_with_gst({"selling_price": "1000", "price_with_gst": "1234.50"}) == 1234.5
    assert pricing.price_with_gst({}) == 0.0


# ---------------------------------------------------------------- the form
def test_a_new_product_is_priced_from_cost_profit_and_gst(qapp):
    d = ItemDialog(None, None, [], [])
    assert d.by_profit.isChecked() and d.selling.isReadOnly()
    d.purchase.setValue(9000)
    d.production.setValue(7000)
    d.profit.setValue(25)
    assert d.cost_lbl.text() == "₹16,000.00" and d.selling.value() == 20000.0  # GST 0%: no tax on top
    d.gst.setCurrentIndex(d.gst.findData(12))
    assert d.selling.value() == 22400.0  # picking the GST shows the selling price
    assert "20,000.00" in d.net_lbl.text() and "2,400.00" in d.net_lbl.text()
    data = d.get_data()
    assert data["selling_price"] == 20000.0 and data["profit_percent"] == 25.0 and data["gst_percent"] == 12


def test_typing_the_selling_price_overrides_the_formula(qapp):
    d = ItemDialog(None, None, [], [])
    d.purchase.setValue(9000)
    d.production.setValue(7000)
    d.gst.setCurrentIndex(d.gst.findData(12))
    d.by_profit.setChecked(False)
    assert not d.selling.isReadOnly() and not d.profit.isEnabled()
    d.selling.setValue(11200)  # what the customer pays
    data = d.get_data()
    assert data["selling_price"] == 10000.0 and data["profit_percent"] is None  # stored before GST
    assert d.net_lbl.text().startswith("₹10,000.00")
    d.gst.setCurrentIndex(d.gst.findData(0))  # the same typed price, no GST: nothing to add
    assert d.get_data()["selling_price"] == 11200.0


def test_an_existing_hand_priced_product_keeps_its_stored_price(qapp):
    # 28% GST makes some prices drift by a paisa if they are worked back: untouched means unchanged
    item = {"name": "Stool", "sku": "S", "selling_price": "333.33", "gst_percent": "28", "purchase_price": "100", "production_cost": "50"}  # fmt: skip
    d = ItemDialog(None, item, [], [])
    assert not d.by_profit.isChecked()
    data = d.get_data()
    assert data["selling_price"] == 333.33 and data["profit_percent"] is None
    assert d.selling.value() == pricing.with_gst(333.33, 28)
    assert d.profit.value() == pricing.profit_percent_of(150, 333.33)  # the margin it leaves, for information


def test_an_existing_product_priced_by_profit_stays_on_the_formula(qapp):
    item = {"name": "Chair", "sku": "C", "selling_price": "1800", "profit_percent": "20", "purchase_price": "1000", "production_cost": "500", "gst_percent": "5"}  # fmt: skip
    d = ItemDialog(None, item, [], [])
    assert d.by_profit.isChecked() and d.profit.value() == 20
    d.production.setValue(1000)  # the making cost went up
    data = d.get_data()
    assert data["selling_price"] == 2400.0 and d.selling.value() == 2520.0


# --------------------------------------------------------------------- Stock
ITEMS = [
    {"id": "i1", "name": "Armchair", "sku": "FUR-0001", "selling_price": "20000", "gst_percent": "12", "price_with_gst": "22400.00", "current_stock": 2, "min_stock": 5, "unit": "pcs"},
    {"id": "i2", "name": "Stool", "sku": "FUR-0002", "selling_price": "900", "gst_percent": "0", "current_stock": 9, "min_stock": 5, "unit": "pcs"},
]  # fmt: skip


def test_stock_shows_the_price_with_gst_and_the_rate(qapp, monkeypatch):
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: ITEMS)
    w = InventoryWindow()
    w.refresh_data()
    assert w.table.horizontalHeaderItem(w.COL_PRICE).text() == "Price with GST"
    assert w.table.item(0, w.COL_PRICE).text() == "₹22,400.00" and w.table.item(0, w.COL_GST).text() == "12%"
    assert w.table.item(1, w.COL_PRICE).text() == "₹900.00" and w.table.item(1, w.COL_GST).text() == "-"


# --------------------------------------------------------------- Bill History
def test_a_bill_shows_the_gst_on_each_line_and_the_totals():
    sale = {"invoice_number": "INV-1", "tax_total": "2400.00", "discount": "100.00", "total_amount": "22300.00"}
    items = [{"item_name": "Armchair", "quantity": 1, "price_at_sale": "20000", "gst_percent": "12", "cgst_amount": "1200", "sgst_amount": "1200", "total_price": "22400"}]  # fmt: skip
    text = bill_text(sale, items)
    assert "1 × ₹20,000.00  + GST 12% ₹2,400.00  =  ₹22,400.00" in text
    assert "Subtotal (before GST): ₹20,000.00" in text and "CGST ₹1,200.00 + SGST ₹1,200.00" in text
    assert "Discount: -₹100.00" in text and text.endswith("Total: ₹22,300.00")


def test_a_bill_without_gst_has_no_tax_lines():
    sale = {"invoice_number": "INV-2", "tax_total": "0.00", "discount": "0.00", "total_amount": "900.00"}
    items = [{"item_name": "Stool", "quantity": 1, "price_at_sale": "900", "total_price": "900"}]
    text = bill_text(sale, items)
    assert "GST" not in text.replace("before GST", "") and text.endswith("Total: ₹900.00")


# -------------------------------------------------------------------- Orders
def test_an_order_takes_the_catalogue_price_with_gst(qapp):
    d = NewOrderDialog(None, ITEMS)
    d.lines.cellWidget(0, 0).setCurrentIndex(1)  # the armchair
    assert d.lines.cellWidget(0, 3).value() == 22400.0
    d.lines.cellWidget(0, 0).setCurrentIndex(2)  # an item cached without the server's figure
    assert d.lines.cellWidget(0, 3).value() == 900.0
    assert d.lines.horizontalHeaderItem(3).text() == "Price each (with GST)"


# ------------------------------------------------------------------ side panel
def headings(w):
    return [x.text() for x in w.nav_scroll.widget().findChildren(QLabel)]


def test_the_side_panel_is_grouped_under_headings(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    labels = [label for _, label, _ in w._get_allowed_nav_items()]
    assert labels == ["Home", "New Bill", "Bill History", "Orders", "Buyers", "Letters", "Stock", "Materials", "Purchases", "3D Lab", "Restoration", "Designs", "Attendance", "Wages", "Staff", "Expenses", "Profit", "Reports"]  # fmt: skip
    assert headings(w) == ["SELLING", "STOCK AND BUYING", "WORKSHOP", "PEOPLE AND PAY", "MONEY"]
    assert sorted(i for _, _, i in w.NAV_ITEMS) == list(range(18))  # every page is still reachable, once
    assert {label for names in w.NAV_SECTIONS.values() for label in names} == set(labels) - {"Home"}


@pytest.mark.parametrize(
    "role,expected",
    [
        (UserRole.SALES, ["SELLING", "STOCK AND BUYING", "PEOPLE AND PAY"]),  # no Materials/Purchases, still Stock
        (UserRole.WORKER, ["STOCK AND BUYING", "WORKSHOP", "PEOPLE AND PAY"]),
        (UserRole.ARTISAN, ["STOCK AND BUYING", "WORKSHOP", "PEOPLE AND PAY"]),
        (UserRole.MANAGER, ["SELLING", "STOCK AND BUYING", "WORKSHOP", "PEOPLE AND PAY", "MONEY"]),
    ],
)
def test_a_heading_shows_only_when_the_role_has_something_under_it(qapp, monkeypatch, role, expected):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert headings(w) == expected
