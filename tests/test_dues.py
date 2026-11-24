from datetime import date

from services import dues


def sale(cid, total, status="pending", day="2026-11-01", **kw):
    return {"customer_id": cid, "total_amount": total, "payment_status": status, "created_at": day + "T10:00:00", "invoice_number": f"B-{total}", **kw}


def test_dues_add_up_per_buyer_and_ignore_paid_and_cancelled():
    sales = [
        sale("a", 1000, day="2026-10-20"), sale("a", 500, "partial", balance_due=200), sale("a", 700, "paid"),
        sale("a", 300, order_status="cancelled"), sale("b", 400, "partial"), sale("", 50),
    ]
    d = dues.dues_by_customer(sales, today=date(2026, 11, 24))
    assert d["a"]["owed"] == 1200 and d["a"]["days"] == 35 and len(d["a"]["bills"]) == 2  # 1000 + 200 still to pay
    assert d["b"]["owed"] == 400  # an older server: a part-paid bill counts in full
    assert set(d) == {"a", "b"}


def test_reminder_and_whatsapp_link():
    text = dues.reminder_text("Meena", "₹1,200.00", ["B-1", "B-2"])
    assert "Meena" in text and "₹1,200.00" in text and "B-1, B-2" in text
    link = dues.whatsapp_link("98765 43210", text)
    assert link.startswith("https://wa.me/919876543210?text=") and " " not in link
    assert dues.whatsapp_link("12", text) is None


def test_buyers_screen_shows_what_each_owes(qapp):
    from ui.customers_screen import CustomersScreen, DuesDialog

    s = CustomersScreen()
    s._show_customers(([{"id": "a", "name": "Meena", "phone": "9876543210"}, {"id": "b", "name": "Ravi"}], [sale("a", 1000)]))
    assert s.table.item(0, 3).text() == "₹1,000.00" and s.table.item(1, 3).text() == ""
    d = DuesDialog(None, {"name": "Meena", "phone": "9876543210"}, s._dues["a"])
    assert d.link().startswith("https://wa.me/919876543210")
