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
