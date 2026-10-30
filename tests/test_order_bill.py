"""Creating the bill from an order: the button, the question, the stock-shortage path, the PDF."""

import pytest
from PyQt6.QtWidgets import QMessageBox

import ui.orders_screen as orders_module
from services.api_client import APIError
from services.enums import UserRole
from services.orders_service import OrdersService
from services.sales_service import BillPdfError, SalesService
from services.session import Session
from ui.orders_screen import OrdersScreen
from tests.test_orders_screen import DONE, SHOP, WEB, order

BILLED = order(4, "ready", invoice_number="NTD-2026-00007", sale_id="s7")


@pytest.fixture
def screen_for(qapp, monkeypatch):
    calls = {"invoice": [], "pdf": [], "opened": []}
    rows = [WEB, SHOP, DONE, BILLED]
    monkeypatch.setattr(OrdersService, "orders", lambda self, status=None, source=None, search=None, limit=100: rows)

    def make(answer=None):
        def invoice(self, order_id, allow_negative_stock=False):
            calls["invoice"].append((order_id, allow_negative_stock))
            if isinstance(answer, Exception) and not allow_negative_stock:
                raise answer
            return {"invoice_number": "NTD-2026-00008", "total_amount": "10000.00"}

        monkeypatch.setattr(OrdersService, "invoice", invoice)
        monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: calls["pdf"].append(n) or f"{n}.pdf")
        monkeypatch.setattr(SalesService, "open_pdf", staticmethod(lambda path: calls["opened"].append(path)))
        s = OrdersScreen()
        s.status.setCurrentIndex(s.status.findData("all"))
        s.refresh_data()
        return s

    return make, calls


def select(s, number):
    row = next(r for r, o in enumerate(s._rows) if o["order_number"] == number)
    s.table.selectRow(row)
    s._selected()


def answer(monkeypatch, yes=True):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes if yes else QMessageBox.StandardButton.No))


def test_the_button_follows_the_stage_and_the_bill(screen_for):
    make, _ = screen_for
    s = make()
    select(s, WEB["order_number"])  # still a draft: confirm it with the customer first
    assert s.bill_btn.isHidden()
    select(s, SHOP["order_number"])
    assert not s.bill_btn.isHidden() and s.bill_btn.text() == "🧾  Create bill"
    select(s, DONE["order_number"])  # delivered orders can be billed too
    assert not s.bill_btn.isHidden() and s.bill_btn.text() == "🧾  Create bill"
    select(s, BILLED["order_number"])
    assert s.bill_btn.text() == "🧾  Open bill" and "Bill NTD-2026-00007" in s.heading.text()
    assert s.edit_btn.isHidden() and s.cancel_btn.isHidden()  # a billed order's amount is fixed


def test_creating_the_bill_asks_first_then_opens_the_pdf(screen_for, monkeypatch):
    make, calls = screen_for
    s = make()
    select(s, SHOP["order_number"])
    answer(monkeypatch, yes=False)
    s.bill_btn.click()
    assert calls["invoice"] == [] and calls["opened"] == []  # said no: nothing happened
    answer(monkeypatch, yes=True)
    s.bill_btn.click()
    assert calls["invoice"] == [("o1", False)] and calls["pdf"] == ["NTD-2026-00008"] and calls["opened"] == ["NTD-2026-00008.pdf"]


def test_the_question_says_what_will_happen(screen_for, monkeypatch):
    make, _ = screen_for
    s = make()
    select(s, SHOP["order_number"])
    seen = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda parent, title, text, *a, **k: seen.append(text) or QMessageBox.StandardButton.No))
    s.bill_btn.click()
    assert "ORD-2026-0001" in seen[0] and "₹10,000.00" in seen[0] and "₹3,000.00" in seen[0] and "Stock is taken off" in seen[0]


def test_an_existing_bill_is_just_opened(screen_for, monkeypatch):
    make, calls = screen_for
    s = make()
    select(s, BILLED["order_number"])
    answer(monkeypatch, yes=False)  # no question is asked for a bill that already exists
    s.bill_btn.click()
    assert calls["invoice"] == [] and calls["pdf"] == ["NTD-2026-00007"] and calls["opened"] == ["NTD-2026-00007.pdf"]


def test_short_stock_offers_to_bill_anyway(screen_for, monkeypatch):
    make, calls = screen_for
    s = make(APIError(400, '{"detail": "Insufficient stock for Teak stool"}'))
    select(s, SHOP["order_number"])
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda parent, title, text, *a, **k: asked.append(title) or QMessageBox.StandardButton.Yes))
    s.bill_btn.click()
    assert asked == ["Create the bill", "Not enough in stock"]
    assert calls["invoice"] == [("o1", False), ("o1", True)] and calls["opened"]
    # saying no to going ahead leaves it unbilled
    calls["invoice"].clear(); calls["opened"].clear()
    replies = iter([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: next(replies)))
    s.bill_btn.click()
    assert calls["invoice"] == [("o1", False)] and calls["opened"] == []


def test_any_other_refusal_is_shown_with_its_reason(screen_for, monkeypatch, dialogs):
    make, calls = screen_for
    s = make(APIError(409, '{"detail": "Set the order\'s amount before billing it"}'))
    select(s, SHOP["order_number"])
    answer(monkeypatch)
    s.bill_btn.click()
    kind, title, text = dialogs[-1]
    assert kind == "warning" and title == "The bill was not made" and "Set the order's amount" in text
    assert calls["opened"] == []


def test_a_pdf_that_will_not_open_still_says_the_bill_was_made(screen_for, monkeypatch, dialogs):
    make, calls = screen_for
    s = make()
    monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: (_ for _ in ()).throw(BillPdfError("no space left")))
    select(s, SHOP["order_number"])
    answer(monkeypatch)
    s.bill_btn.click()
    kind, title, text = dialogs[-1]
    assert title == "Bill made, PDF not shown" and "NTD-2026-00008" in text and "no space left" in text


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES])
def test_everyone_who_takes_orders_can_bill_them(screen_for, monkeypatch, role):
    make, _ = screen_for
    monkeypatch.setattr(Session, "_role", role)
    s = make()
    select(s, SHOP["order_number"])
    assert not s.bill_btn.isHidden()
