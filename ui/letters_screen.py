"""
ui/letters_screen.py

Official letters on the shop letterhead: quotation, order confirmation with advance
receipt, purchase receipt for a piece bought from another artisan, and the completion
certificate of a temple restoration. Each gets its number once (QTN-2026-27-0001) and
opens as a PDF; a wrong one is voided, never deleted. The owner edits the letterhead.
"""

import shutil
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.customer_service import CustomerService
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.letters_service import (
    KIND_SHORT,
    KIND_WORDS,
    KINDS,
    LETTERHEAD_FIELDS,
    LettersService,
    may_issue,
)
from services.money_service import rupees
from services.orders_service import OrdersService, amount_of
from services.restoration_service import RestorationService
from services.session import Session
from services.stock_service import StockService
from ui.errors import handle_permissions
from ui.expenses_screen import METHODS, date_edit, dialog_buttons, iso, money_spin
from ui.item_scan import open_file
from ui.theme import Colors, Fonts, Theme


def _table(headers, stretch=None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch is not None:
        h.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setStyleSheet(Theme.table_style())
    return t


def _line(text="", placeholder="") -> QLineEdit:
    e = QLineEdit(text or "")
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(Theme.input_style())
    return e


def _text(placeholder="", height=70) -> QPlainTextEdit:
    e = QPlainTextEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(height)
    e.setStyleSheet(Theme.input_style())
    return e


def _combo() -> QComboBox:
    c = QComboBox()
    c.setStyleSheet(Theme.input_style())
    return c


def _form_dialog(dialog: QDialog, title: str, width: int = 520) -> QFormLayout:
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(width)
    dialog.setStyleSheet(f"background-color: {Colors.BG};")
    form = QFormLayout(dialog)
    form.setContentsMargins(24, 20, 24, 20)
    form.setSpacing(10)
    return form


def _rows(form: QFormLayout, rows) -> None:
    for label, widget in rows:
        form.addRow(QLabel(label, styleSheet=Theme.label()), widget)


def _none(value: str) -> str | None:
    return value.strip() or None


# ------------------------------------------------------------------ dialogs
class QuotationDialog(QDialog):
    """Who the quotation is for, the lines with their prices, and how long it holds."""

    def __init__(self, parent, customers: list[dict]):
        super().__init__(parent)
        self._customers = {c["id"]: c for c in customers}
        form = _form_dialog(self, "New quotation", 640)
        self.customer = _combo()
        self.customer.addItem("Someone not in the customer list", None)
        for c in customers:
            self.customer.addItem(f"{c['name']}  {c.get('phone') or ''}".strip(), c["id"])
        self.customer.currentIndexChanged.connect(self._picked)
        self.name = _line(placeholder="name on the quotation")
        self.phone = _line()
        self.address = _line()
        self.subject = _line(placeholder="optional, e.g. Quotation for temple door")
        self.lines = _table(["What", "Qty", "Price each (with GST)"], 0)
        self.lines.setMaximumHeight(170)
        add = QPushButton("➕  Add a line")
        add.setStyleSheet(Theme.btn_secondary())
        add.clicked.connect(lambda _c=False: self._add_line())
        drop = QPushButton("Remove last")
        drop.setStyleSheet(Theme.btn_secondary())
        drop.clicked.connect(self._remove_last)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(drop)
        buttons.addStretch()
        self.days = QSpinBox()
        self.days.setRange(1, 365)
        self.days.setValue(15)
        self.days.setSuffix(" days")
        self.days.setStyleSheet(Theme.input_style())
        self.notes = _text("wood, finish, delivery, anything the customer should know")
        _rows(form, [("Customer", self.customer), ("Name *", self.name), ("Phone", self.phone), ("Address", self.address), ("Subject", self.subject)])
        form.addRow(QLabel("Lines", styleSheet=Theme.subheading()))
        form.addRow(self.lines)
        form.addRow(buttons)
        _rows(form, [("Valid for", self.days), ("Notes", self.notes)])
        form.addRow(dialog_buttons(self, "Issue quotation"))
        self._add_line()

    def _picked(self, _i=0):
        c = self._customers.get(self.customer.currentData())
        if c:
            self.name.setText(c["name"])
            self.phone.setText(c.get("phone") or "")
            self.address.setText(c.get("address") or "")

    def _add_line(self):
        r = self.lines.rowCount()
        self.lines.insertRow(r)
        qty = QSpinBox()
        qty.setRange(1, 10000)
        qty.setStyleSheet(Theme.input_style())
        for col, widget in enumerate((_line(placeholder="e.g. Teak door with Ganesha, 7 ft"), qty, money_spin())):
            self.lines.setCellWidget(r, col, widget)
        self.lines.setRowHeight(r, 44)

    def _remove_last(self):
        if self.lines.rowCount() > 1:
            self.lines.removeRow(self.lines.rowCount() - 1)

    def _lines(self) -> list[dict]:
        out = []
        for r in range(self.lines.rowCount()):
            text = self.lines.cellWidget(r, 0).text().strip()
            if text:
                out.append({"description": text, "quantity": self.lines.cellWidget(r, 1).value(), "unit_price": round(self.lines.cellWidget(r, 2).value(), 2)})
        return out

    def _check(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Check the form", "Say who the quotation is for.")
        elif not self._lines():
            QMessageBox.warning(self, "Check the form", "Add at least one line with a description.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "customer_id": self.customer.currentData(),
            "party_name": self.name.text().strip(),
            "party_phone": _none(self.phone.text()),
            "party_address": _none(self.address.text()),
            "subject": _none(self.subject.text()),
            "lines": self._lines(),
            "valid_days": self.days.value(),
            "notes": _none(self.notes.toPlainText()),
        }


class OrderConfirmationDialog(QDialog):
    """Pick the order; the letter carries its pieces, the advance received and the balance."""

    def __init__(self, parent, orders: list[dict]):
        super().__init__(parent)
        form = _form_dialog(self, "Order confirmation and advance receipt", 560)
        self.order = _combo()
        for o in orders:
            who = o.get("customer_name") or "no customer"
            self.order.addItem(f"{o['order_number']}  ·  {who}  ·  {rupees(amount_of(o))}, advance {rupees(o.get('advance_paid'))}", o["id"])
        self._orders = {o["id"]: o for o in orders}
        self.notes = _text("optional, printed on the letter")
        note = QLabel("The letter shows the order's pieces, every payment received so far, and the balance due. It cannot change after it is issued; issue a new one after the next payment.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow(note)
        _rows(form, [("Order *", self.order), ("Notes", self.notes)])
        form.addRow(dialog_buttons(self, "Issue letter"))

    def _check(self):
        o = self._orders.get(self.order.currentData())
        if not o:
            QMessageBox.warning(self, "Check the form", "There is no order to write about.")
        elif not o.get("customer_name"):
            QMessageBox.warning(self, "Check the form", "This order has no customer. Add the customer to the order first.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {"order_id": self.order.currentData(), "notes": _none(self.notes.toPlainText())}


class PurchaseReceiptDialog(QDialog):
    """A piece bought from another artisan: who sold it, what it is, what was paid."""

    def __init__(self, parent, suppliers: list[dict], items: list[dict]):
        super().__init__(parent)
        self._suppliers = {s["id"]: s for s in suppliers}
        form = _form_dialog(self, "Purchase receipt", 560)
        self.supplier = _combo()
        self.supplier.addItem("Someone not in the supplier list", None)
        for s in suppliers:
            self.supplier.addItem(f"{s['name']}  {s.get('phone') or ''}".strip(), s["id"])
        self.supplier.currentIndexChanged.connect(self._picked)
        self.name = _line(placeholder="name of the artisan who sold it")
        self.phone = _line()
        self.address = _line()
        self.item = _combo()
        self.item.addItem("Not linked to a product in Stock", None)
        for i in sorted(items, key=lambda i: (i.get("item_type") != "sculpture", i.get("sku") or "")):
            self.item.addItem(f"{i.get('sku', '')}  {i['name']}", i["id"])
        self.description = _line(placeholder="e.g. Carved Ganesha, 2 ft, unfinished")
        self.qty = QSpinBox()
        self.qty.setRange(1, 10000)
        self.qty.setStyleSheet(Theme.input_style())
        self.amount = money_spin()
        self.paid_on = date_edit()
        self.method = _combo()
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.reference = _line(placeholder="UPI id, cheque number (optional)")
        self.notes = _text("optional, printed on the receipt", 54)
        _rows(
            form,
            [
                ("Bought from", self.supplier), ("Name *", self.name), ("Phone", self.phone), ("Address", self.address),
                ("Piece in Stock", self.item), ("What *", self.description), ("Quantity", self.qty), ("Amount paid *", self.amount),
                ("Paid on", self.paid_on), ("Paid by", self.method), ("Reference", self.reference), ("Notes", self.notes),
            ],
        )  # fmt: skip
        form.addRow(dialog_buttons(self, "Issue receipt"))

    def _picked(self, _i=0):
        s = self._suppliers.get(self.supplier.currentData())
        if s:
            self.name.setText(s["name"])
            self.phone.setText(s.get("phone") or "")
            self.address.setText(s.get("address") or "")

    def _check(self):
        if not self.name.text().strip() or not self.description.text().strip():
            QMessageBox.warning(self, "Check the form", "Fill in who sold it and what it is.")
        elif self.amount.value() <= 0:
            QMessageBox.warning(self, "Check the form", "Enter the amount paid.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "supplier_id": self.supplier.currentData(),
            "seller_name": self.name.text().strip(),
            "seller_phone": _none(self.phone.text()),
            "seller_address": _none(self.address.text()),
            "item_id": self.item.currentData(),
            "description": self.description.text().strip(),
            "quantity": self.qty.value(),
            "amount": round(self.amount.value(), 2),
            "paid_on": iso(self.paid_on),
            "method": self.method.currentData(),
            "reference": _none(self.reference.text()),
            "notes": _none(self.notes.toPlainText()),
        }


class CertificateDialog(QDialog):
    """The certificate of a temple restoration that is marked Restored."""

    def __init__(self, parent, projects: list[dict]):
        super().__init__(parent)
        form = _form_dialog(self, "Certificate of completion", 560)
        self.project = _combo()
        for p in projects:
            self.project.addItem(f"{p['title']}  ·  {p.get('temple_name') or ''}", p["id"])
        self.work = _text("what was done: repairs, recarving, cleaning, finish", 100)
        self.done_on = date_edit()
        self.notes = _text("optional", 54)
        if not projects:
            note = QLabel("No temple restoration is marked Restored yet. Set its status to Restored in the Restoration screen first.")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {Colors.RED};")
            form.addRow(note)
        _rows(form, [("Restoration *", self.project), ("Work done *", self.work), ("Completed on", self.done_on), ("Notes", self.notes)])
        form.addRow(dialog_buttons(self, "Issue certificate"))

    def _check(self):
        if not self.project.currentData():
            QMessageBox.warning(self, "Check the form", "Choose a restoration that is marked Restored.")
        elif not self.work.toPlainText().strip():
            QMessageBox.warning(self, "Check the form", "Say what work was done.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "restoration_id": self.project.currentData(),
            "work_done": self.work.toPlainText().strip(),
            "completed_on": iso(self.done_on),
            "notes": _none(self.notes.toPlainText()),
        }


class LetterheadDialog(QDialog):
    """The name, address and signatory printed at the top of every letter (owner only)."""

    def __init__(self, parent, profile: dict):
        super().__init__(parent)
        form = _form_dialog(self, "Letterhead", 520)
        self.fields = {key: _line(profile.get(key) or "") for key, _label in LETTERHEAD_FIELDS}
        _rows(form, [(label, self.fields[key]) for key, label in LETTERHEAD_FIELDS])
        note = QLabel("Letters already issued keep the letterhead they were issued with.")
        note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow(note)
        form.addRow(dialog_buttons(self))

    def _check(self):
        if not self.fields["name"].text().strip():
            QMessageBox.warning(self, "Check the form", "The letterhead needs a name.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {key: e.text().strip() for key, e in self.fields.items()}


# ------------------------------------------------------------------- screen
def issue_letter(parent, kind: str, order: dict | None = None, restoration: dict | None = None, svc: LettersService | None = None):
    """Ask for the details and issue the letter; None if cancelled. `order` / `restoration` fix
    the dialog to that one order or project (the buttons on those screens)."""
    svc = svc or LettersService()
    if kind == "quotation":
        dialog = QuotationDialog(parent, CustomerService().get_all())
    elif kind == "order_confirmation":
        orders = [order] if order else [o for o in OrdersService().orders(limit=100) if o["status"] != "cancelled"]
        dialog = OrderConfirmationDialog(parent, orders)
    elif kind == "purchase_receipt":
        dialog = PurchaseReceiptDialog(parent, StockService().rows("suppliers"), InventoryService().get_items(allow_cached=True) or [])
    else:
        projects = [restoration] if restoration else [p for p in RestorationService().projects("restored") if p.get("kind", "temple") == "temple"]
        dialog = CertificateDialog(parent, projects)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return svc.issue(kind, dialog.get_data())


def show_letter(letter: dict, svc: LettersService | None = None, opener=None) -> None:
    """Fetch a letter's PDF and open it in the PC's PDF viewer."""
    (opener or open_file)(str((svc or LettersService()).save_pdf(letter)))


class LettersScreen(QWidget):
    COL_NUMBER, COL_TYPE, COL_DATE, COL_TO, COL_AMOUNT, COL_STATUS = range(6)

    def __init__(self):
        super().__init__()
        self._svc = LettersService()
        self._rows: list[dict] = []
        self.opener = open_file
        self.setStyleSheet(Theme.content_bg())
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self.refresh_data)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("✉️  Letters")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.search = _line(placeholder="Search number, name or subject")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        head.addWidget(self.search)
        self.kind_filter = _combo()
        self.kind_filter.addItem("All kinds", None)
        for label, value in KINDS:
            if may_issue(value):
                self.kind_filter.addItem(KIND_SHORT[value], value)
        self.kind_filter.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.kind_filter)
        self.status_filter = _combo()
        for label, value in (("Issued", "issued"), ("Voided", "void"), ("All", None)):
            self.status_filter.addItem(label, value)
        self.status_filter.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.status_filter)
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        self.head_btn = QPushButton("🏷️  Letterhead")
        self.head_btn.setStyleSheet(Theme.btn_secondary())
        self.head_btn.setVisible(Session.is_authorized([UserRole.OWNER]))
        self.head_btn.clicked.connect(lambda _c=False: self._letterhead())
        head.addWidget(self.head_btn)
        self.new_btn = QPushButton("➕  New letter")
        self.new_btn.setStyleSheet(Theme.btn_primary())
        self.new_menu = QMenu(self)
        self.new_actions = {}
        for label, value in KINDS:
            if may_issue(value):
                action = self.new_menu.addAction(label)
                action.triggered.connect(lambda _c=False, k=value: self._new(k))
                self.new_actions[value] = action
        self.new_btn.setMenu(self.new_menu)
        head.addWidget(self.new_btn)
        root.addLayout(head)

        hint = QLabel("Every letter gets its own number, once, and opens as a PDF on the shop letterhead. A letter cannot be changed after it is issued; if one is wrong, void it and issue a new one.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(hint)

        self.table = _table(["Number", "Letter", "Date", "To", "Amount", "Status"], self.COL_TO)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.doubleClicked.connect(lambda _i: self._open())
        root.addWidget(self.table)

        actions = QHBoxLayout()
        self.open_btn = QPushButton("📄  Open PDF")
        self.save_btn = QPushButton("💾  Save PDF…")
        self.void_btn = QPushButton("🚫  Void…")
        self.void_btn.setVisible(Session.is_authorized([UserRole.OWNER]))
        for b, slot in ((self.open_btn, self._open), (self.save_btn, self._save), (self.void_btn, self._void)):
            b.setStyleSheet(Theme.btn_secondary())
            b.setEnabled(False)
            b.clicked.connect(lambda _c=False, s=slot: s())
            actions.addWidget(b)
        actions.addStretch()
        root.addLayout(actions)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(self.detail)

    # ------------------------------------------------------------- data
    @handle_permissions
    def refresh_data(self, _checked=False):
        keep = self._current()["id"] if self._current() else None
        self._rows = self._svc.letters(self.kind_filter.currentData(), self.status_filter.currentData(), self.search.text().strip())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for r, x in enumerate(self._rows):
            values = [
                x["number"], KIND_SHORT.get(x["kind"], x["kind"]), x["issued_on"], x["party_name"],
                rupees(x["amount"]) if x.get("amount") is not None else "",
                "Void" if x["status"] == "void" else "Issued",
            ]  # fmt: skip
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
            self.table.setRowHeight(r, 40)
            if x["id"] == keep:
                self.table.selectRow(r)
        self.table.blockSignals(False)
        self._selected()

    def _current(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self._rows[rows[0].row()] if rows and rows[0].row() < len(self._rows) else None

    def _selected(self):
        x = self._current()
        for b in (self.open_btn, self.save_btn):
            b.setEnabled(bool(x))
        self.void_btn.setEnabled(bool(x) and x["status"] != "void")
        if not x:
            self.detail.setText("")
        elif x["status"] == "void":
            self.detail.setText(f"{x['number']} was voided: {x.get('void_reason') or 'no reason given'}")
        else:
            self.detail.setText(f"{x['number']}  ·  {x['subject']}")

    # ---------------------------------------------------------- actions
    def open_pdf(self, letter: dict) -> None:
        show_letter(letter, self._svc, self.opener)

    @handle_permissions
    def _new(self, kind: str):
        letter = issue_letter(self, kind, svc=self._svc)
        if letter:
            self.status_filter.blockSignals(True)
            self.status_filter.setCurrentIndex(self.status_filter.findData(None))
            self.status_filter.blockSignals(False)
            self.refresh_data()
            self.open_pdf(letter)

    @handle_permissions
    def _open(self):
        x = self._current()
        if x:
            self.open_pdf(x)

    @handle_permissions
    def _save(self):
        x = self._current()
        if not x:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save the letter", f"{x['number']}.pdf", "PDF (*.pdf)")
        if dest:
            shutil.copyfile(self._svc.save_pdf(x), Path(dest))
            QMessageBox.information(self, "Saved", f"Saved to {dest}")

    @handle_permissions
    def _void(self):
        x = self._current()
        if not x or x["status"] == "void":
            return
        reason, ok = QInputDialog.getText(self, "Void letter", f"Why is {x['number']} void? It stays on record with this reason, and its number is not used again.")
        if not ok:
            return
        if len(reason.strip()) < 3:
            QMessageBox.warning(self, "Void letter", "Please give a short reason.")
            return
        self._svc.void(x["id"], reason.strip())
        self.refresh_data()

    @handle_permissions
    def _letterhead(self):
        d = LetterheadDialog(self, self._svc.profile())
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.save_profile(d.get_data())
            QMessageBox.information(self, "Saved", "The letterhead is saved. New letters will use it.")
