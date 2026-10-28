"""Letters screen: list and filter, issue the four kinds, open and save the PDF, void, letterhead, who sees it."""

import pytest
from PyQt6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from services.customer_service import CustomerService
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.letters_service import LettersService
from services.orders_service import OrdersService
from services.restoration_service import RestorationService
from services.session import Session
from services.stock_service import StockService
from ui.letters_screen import (
    CertificateDialog,
    LetterheadDialog,
    LettersScreen,
    OrderConfirmationDialog,
    PurchaseReceiptDialog,
    QuotationDialog,
    issue_letter,
)
from ui.main_window import MainWindow
from ui.orders_screen import OrdersScreen
from ui.restoration_screen import RestorationScreen

L1 = {"id": "l1", "number": "QTN-2026-27-0001", "kind": "quotation", "kind_label": "Quotation", "status": "issued", "issued_on": "2026-10-28", "subject": "Quotation for temple door", "party_name": "Sri Rama Temple Trust", "amount": "57501.00", "void_reason": None}
L2 = {**L1, "id": "l2", "number": "PRC-2026-27-0001", "kind": "purchase_receipt", "party_name": "Mohan", "amount": "7500.00", "subject": "Purchase of Ganesha"}
L3 = {**L1, "id": "l3", "number": "QTN-2026-27-0002", "status": "void", "void_reason": "Wrong customer", "party_name": "Venkat"}
CUSTOMERS = [{"id": "c1", "name": "Lakshmi Devi", "phone": "9000011111", "address": "Main Street"}]
ORDER = {"id": "o1", "order_number": "ORD-2026-0007", "customer_name": "Venkat Rao", "status": "confirmed", "estimated_amount": "20000", "final_amount": "0", "advance_paid": "5000"}
NO_CUSTOMER = {**ORDER, "id": "o2", "order_number": "ORD-2026-0008", "customer_name": None}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    calls = []

    def listing(self, kind=None, status=None, search=None, limit=200):
        calls.append(("list", kind, status, search))
        rows = [L1, L2, L3]
        return [r for r in rows if (not kind or r["kind"] == kind) and (not status or r["status"] == status) and (not search or search.lower() in (r["number"] + r["party_name"]).lower())]

    monkeypatch.setattr(LettersService, "letters", listing)
    monkeypatch.setattr(LettersService, "issue", lambda self, kind, data: calls.append(("issue", kind, data)) or {**L1, "id": "new", "number": "QTN-2026-27-0003"})
    monkeypatch.setattr(LettersService, "void", lambda self, i, reason: calls.append(("void", i, reason)))
    monkeypatch.setattr(LettersService, "profile", lambda self: {"name": "Vriksha Studios", "phone": "9876543210", "gstin": None})
    monkeypatch.setattr(LettersService, "save_profile", lambda self, d: calls.append(("profile", d)) or d)
    monkeypatch.setattr(LettersService, "save_pdf", lambda self, letter, folder=None: calls.append(("pdf", letter["number"])) or tmp_path / f"{letter['number']}.pdf")
    monkeypatch.setattr(CustomerService, "get_all", lambda self: CUSTOMERS)
    monkeypatch.setattr(OrdersService, "orders", lambda self, status=None, source=None, search=None, limit=100: [ORDER, {**ORDER, "id": "o3", "status": "cancelled"}, NO_CUSTOMER])
    monkeypatch.setattr(StockService, "rows", lambda self, kind: [{"id": "s1", "name": "Mohan the carver", "phone": "9000022222", "address": "Channapatna"}])
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: [{"id": "i1", "sku": "SCU-0001", "name": "Ganesha", "item_type": "sculpture"}])
    monkeypatch.setattr(RestorationService, "projects", lambda self, status=None: [{"id": "r1", "title": "Door panel", "temple_name": "Sri Veerabhadra", "kind": "temple", "status": "restored"}, {"id": "r2", "title": "Finish it", "kind": "finishing", "status": "restored"}])
    return calls


@pytest.fixture
def screen(qapp, fake):
    s = LettersScreen()
    s.opened = []
    s.opener = s.opened.append
    s.refresh_data()
    return s


def pick(s, row):
    s.table.selectRow(row)
    s._selected()


def accept(cls, edit=lambda d: None):
    """Make a dialog class fill itself in and accept instead of waiting for a click."""
    return lambda self: (edit(self), QDialog.DialogCode.Accepted)[-1]


# ----------------------------------------------------------------- the screen
def test_lists_issued_letters_first_with_their_numbers(qapp, fake):
    s = LettersScreen()
    s.refresh_data()
    assert [s.table.item(r, s.COL_NUMBER).text() for r in range(s.table.rowCount())] == ["QTN-2026-27-0001", "PRC-2026-27-0001"]
    assert s.table.item(0, s.COL_AMOUNT).text() == "₹57,501.00" and s.table.item(1, s.COL_TYPE).text() == "Purchase receipt"
    s.status_filter.setCurrentIndex(s.status_filter.findData("void"))
    assert fake[-1] == ("list", None, "void", "") and s.table.rowCount() == 1


def test_filters_and_search_reach_the_server(qapp, fake):
    s = LettersScreen()
    s.kind_filter.setCurrentIndex(s.kind_filter.findData("purchase_receipt"))
    assert fake[-1] == ("list", "purchase_receipt", "issued", "")
    s.kind_filter.setCurrentIndex(0)
    s.search.setText("mohan")
    s._search_timer.stop()
    s.refresh_data()
    assert fake[-1] == ("list", None, "issued", "mohan") and s.table.rowCount() == 1


def test_selecting_a_letter_enables_its_buttons_and_shows_a_void_reason(screen):
    assert not screen.open_btn.isEnabled() and not screen.void_btn.isEnabled()
    pick(screen, 0)
    assert screen.open_btn.isEnabled() and screen.save_btn.isEnabled() and screen.void_btn.isEnabled()
    assert "Quotation for temple door" in screen.detail.text()
    screen.status_filter.setCurrentIndex(screen.status_filter.findData(None))
    pick(screen, 2)
    assert "Wrong customer" in screen.detail.text() and not screen.void_btn.isEnabled()  # a void letter cannot be voided again


def test_open_pdf_fetches_the_letter_and_opens_it(screen, fake):
    pick(screen, 1)
    screen.open_btn.click()
    assert ("pdf", "PRC-2026-27-0001") in fake and screen.opened and screen.opened[0].endswith("PRC-2026-27-0001.pdf")


def test_save_pdf_copies_it_where_asked(screen, tmp_path, monkeypatch, dialogs):
    pick(screen, 0)
    (tmp_path / "QTN-2026-27-0001.pdf").write_bytes(b"%PDF-1.4 sample")
    dest = tmp_path / "chosen.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(dest), "")))
    screen.save_btn.click()
    assert dest.read_bytes() == b"%PDF-1.4 sample" and dialogs[-1][0] == "information"


def test_voiding_asks_for_a_reason_first(screen, fake, dialogs, monkeypatch):
    pick(screen, 0)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("x", True)))
    screen.void_btn.click()
    assert not [c for c in fake if c[0] == "void"] and dialogs[-1][0] == "warning"
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Wrong customer", False)))
    screen.void_btn.click()
    assert not [c for c in fake if c[0] == "void"]
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("  Wrong customer ", True)))
    screen.void_btn.click()
    assert next(c for c in fake if c[0] == "void") == ("void", "l1", "Wrong customer")


# -------------------------------------------------------------------- issuing
def test_a_new_quotation_is_issued_then_opened(screen, fake, monkeypatch):
    def fill(d):
        d.name.setText("Sri Rama Temple Trust")
        d.lines.cellWidget(0, 0).setText("Teak door")
        d.lines.cellWidget(0, 2).setValue(45000)

    monkeypatch.setattr(QuotationDialog, "exec", accept(QuotationDialog, fill))
    screen.new_actions["quotation"].trigger()
    kind, data = next((c[1], c[2]) for c in fake if c[0] == "issue")
    assert kind == "quotation" and data["party_name"] == "Sri Rama Temple Trust" and data["valid_days"] == 15
    assert data["lines"] == [{"description": "Teak door", "quantity": 1, "unit_price": 45000.0}]
    assert screen.opened and screen.opened[0].endswith("QTN-2026-27-0003.pdf")


def test_the_quotation_form_fills_from_a_customer_and_needs_a_line(qapp, dialogs):
    d = QuotationDialog(None, CUSTOMERS)
    d.customer.setCurrentIndex(d.customer.findData("c1"))
    assert (d.name.text(), d.phone.text(), d.address.text()) == ("Lakshmi Devi", "9000011111", "Main Street")
    d._check()
    assert d.result() == 0 and "at least one line" in dialogs[-1][2]
    d.lines.cellWidget(0, 0).setText("Stool")
    d._add_line()
    d.lines.cellWidget(1, 0).setText("Bench")
    d.lines.cellWidget(1, 1).setValue(2)
    assert [x["description"] for x in d.get_data()["lines"]] == ["Stool", "Bench"] and d.get_data()["customer_id"] == "c1"
    d._remove_last()
    d._remove_last()  # the last remaining line stays
    assert d.lines.rowCount() == 1
    d.name.setText("")
    d._check()
    assert "who the quotation is for" in dialogs[-1][2]


def test_order_confirmation_lists_live_orders_and_needs_a_customer(qapp, fake, dialogs, monkeypatch):
    seen = []

    def look(self):
        seen.append([self.order.itemData(i) for i in range(self.order.count())])
        self.order.setCurrentIndex(0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(OrderConfirmationDialog, "exec", look)
    letter = issue_letter(None, "order_confirmation")
    assert seen == [["o1", "o2"]]  # the cancelled order is left out
    assert letter["number"] == "QTN-2026-27-0003" and next(c for c in fake if c[0] == "issue")[2] == {"order_id": "o1", "notes": None}
    d = OrderConfirmationDialog(None, [NO_CUSTOMER])
    d._check()
    assert d.result() == 0 and "no customer" in dialogs[-1][2]


def test_a_confirmation_from_an_order_is_fixed_to_that_order(qapp, fake, monkeypatch):
    seen = []
    monkeypatch.setattr(OrderConfirmationDialog, "exec", lambda self: (seen.append(self.order.count()), QDialog.DialogCode.Accepted)[-1])
    issue_letter(None, "order_confirmation", order=ORDER)
    assert seen == [1] and next(c for c in fake if c[0] == "issue")[2]["order_id"] == "o1"


def test_purchase_receipt_takes_the_supplier_and_needs_an_amount(qapp, fake, dialogs):
    d = PurchaseReceiptDialog(None, StockService().rows("suppliers"), InventoryService().get_items())
    d.supplier.setCurrentIndex(d.supplier.findData("s1"))
    assert d.name.text() == "Mohan the carver" and d.phone.text() == "9000022222"
    d.description.setText("Carved Ganesha, 2 ft")
    d._check()
    assert d.result() == 0 and "amount paid" in dialogs[-1][2]
    d.amount.setValue(7500)
    d.method.setCurrentIndex(d.method.findData("upi"))
    d.reference.setText("TXN987")
    data = d.get_data()
    assert data["supplier_id"] == "s1" and data["amount"] == 7500.0 and data["method"] == "upi" and data["reference"] == "TXN987"
    assert data["item_id"] is None and data["quantity"] == 1 and len(data["paid_on"]) == 10


def test_the_certificate_offers_only_restored_temple_projects(qapp, fake, monkeypatch):
    seen = []

    def fill(self):
        seen.append([self.project.itemData(i) for i in range(self.project.count())])
        self.work.setPlainText("Nose recarved in teak")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CertificateDialog, "exec", fill)
    issue_letter(None, "completion_certificate")
    assert seen == [["r1"]]  # the finishing project is not offered
    sent = next(c for c in fake if c[0] == "issue")
    assert sent[1] == "completion_certificate" and sent[2]["restoration_id"] == "r1" and sent[2]["work_done"] == "Nose recarved in teak"


def test_the_certificate_needs_a_project_and_the_work_done(qapp, dialogs):
    empty = CertificateDialog(None, [])
    empty._check()
    assert empty.result() == 0 and "marked Restored" in dialogs[-1][2]
    d = CertificateDialog(None, [{"id": "r1", "title": "Door", "temple_name": "T"}])
    d._check()
    assert d.result() == 0 and "what work was done" in dialogs[-1][2]


def test_cancelling_a_dialog_issues_nothing(screen, fake, monkeypatch):
    monkeypatch.setattr(QuotationDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    screen.new_actions["quotation"].trigger()
    assert not [c for c in fake if c[0] in ("issue", "pdf")] and not screen.opened


# ----------------------------------------------------------------- letterhead
def test_the_owner_edits_the_letterhead(screen, fake, dialogs, monkeypatch):
    d = LetterheadDialog(None, {"name": "Vriksha Studios", "phone": "9876543210"})
    assert d.fields["phone"].text() == "9876543210" and d.fields["gstin"].text() == ""
    d.fields["name"].setText("")
    d._check()
    assert d.result() == 0 and dialogs[-1][0] == "warning"
    monkeypatch.setattr(LetterheadDialog, "exec", accept(LetterheadDialog, lambda self: self.fields["address"].setText("12 Temple Road")))
    assert screen.head_btn.isHidden() is False
    screen.head_btn.click()
    saved = next(c for c in fake if c[0] == "profile")[1]
    assert saved["address"] == "12 Temple Road" and saved["name"] == "Vriksha Studios" and saved["gstin"] == ""


# -------------------------------------------------------------- who sees what
@pytest.mark.parametrize(
    "role,sees,kinds,void,letterhead",
    [
        (UserRole.OWNER, True, {"quotation", "order_confirmation", "purchase_receipt", "completion_certificate"}, True, True),
        (UserRole.MANAGER, True, {"quotation", "order_confirmation", "purchase_receipt"}, False, False),
        (UserRole.SALES, True, {"quotation", "order_confirmation"}, False, False),
        (UserRole.ARTISAN, False, set(), False, False),
        (UserRole.ACHARI, False, set(), False, False),
        (UserRole.WORKER, False, set(), False, False),
    ],
)
def test_each_role_gets_only_its_letters(qapp, fake, monkeypatch, role, sees, kinds, void, letterhead):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert ("Letters" in [label for _, label, _ in w._get_allowed_nav_items()]) is sees
    if sees:
        s = w.letters_view
        assert set(s.new_actions) == kinds
        assert s.void_btn.isHidden() is not void and s.head_btn.isHidden() is not letterhead


# ------------------------------------------------------- buttons on other screens
def test_an_order_has_a_confirmation_letter_button(qapp, fake, monkeypatch):
    shown = []
    monkeypatch.setattr("ui.orders_screen.show_letter", lambda letter: shown.append(letter["number"]))
    monkeypatch.setattr(OrdersService, "orders", lambda self, status=None, source=None, search=None, limit=100: [{**ORDER, "order_type": "custom", "items": [], "payments": [], "balance_due": "15000", "source": "pos", "order_date": "2026-10-28T10:00:00"}])
    monkeypatch.setattr(OrderConfirmationDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    s = OrdersScreen()
    s.refresh_data()
    s.table.selectRow(0)
    s._selected()
    assert not s.letter_btn.isHidden()
    s.letter_btn.click()
    assert shown == ["QTN-2026-27-0003"] and next(c for c in fake if c[0] == "issue")[2]["order_id"] == "o1"


def test_a_restored_temple_project_has_a_certificate_button_for_the_owner(qapp, fake, monkeypatch):
    shown = []
    monkeypatch.setattr("ui.letters_screen.show_letter", lambda letter, *a, **k: shown.append(letter["number"]))
    project = {"id": "r1", "title": "Door panel", "kind": "temple", "temple_name": "Sri Veerabhadra", "location": "Lepakshi", "status": "restored", "scans": [], "files": [], "designs": [], "condition_notes": None}
    monkeypatch.setattr(RestorationService, "projects", lambda self, status=None: [project])
    monkeypatch.setattr(RestorationService, "project", lambda self, i: project)
    monkeypatch.setattr(CertificateDialog, "exec", accept(CertificateDialog, lambda self: self.work.setPlainText("Recarved")))
    s = RestorationScreen()
    s._load_detail("r1")
    assert not s.certificate_btn.isHidden()
    s._certificate()
    sent = next(c for c in fake if c[0] == "issue")
    assert sent[1] == "completion_certificate" and sent[2]["restoration_id"] == "r1"
    s._current = {**project, "status": "review"}
    monkeypatch.setattr(RestorationService, "project", lambda self, i: {**project, "status": "review"})
    s._load_detail("r1")
    assert s.certificate_btn.isHidden()  # not restored yet
    monkeypatch.setattr(Session, "_role", UserRole.ARTISAN)
    monkeypatch.setattr(RestorationService, "project", lambda self, i: project)
    s._load_detail("r1")
    assert s.certificate_btn.isHidden()  # the owner issues certificates
