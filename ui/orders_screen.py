"""
ui/orders_screen.py

Customer orders, from the shop counter and from the website: see every order and its
details, move it through its stages (New, Confirmed, In production, Ready, Delivered),
take the advance and the balance, edit the amount or delivery date, or cancel it.
Everyone who sells can look at orders, create them and take money; only the owner and
manager change stages or edit.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
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
from services.money_service import rupees
from services.orders_service import (
    NEXT_STEP,
    OPEN,
    SOURCE_WORDS,
    STATUS_WORDS,
    STATUSES,
    TYPE_WORDS,
    OrdersService,
    amount_of,
    items_summary,
)
from services.session import Session
from ui.errors import handle_permissions
from ui.expenses_screen import METHODS, date_edit, dialog_buttons, iso, money_spin
from ui.letters_screen import issue_letter, show_letter
from ui.theme import Colors, Fonts, Theme

STATUS_COLORS = {
    "draft": Colors.ORANGE,
    "confirmed": Colors.BLUE,
    "in_production": Colors.PURPLE,
    "ready": Colors.GREEN,
    "delivered": Colors.TEXT_MUTED,
    "cancelled": Colors.RED,
}


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


def _cell(text, right=False) -> QTableWidgetItem:
    c = QTableWidgetItem(text)
    if right:
        c.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return c


def _line(text="", placeholder="") -> QLineEdit:
    e = QLineEdit(text or "")
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(Theme.input_style())
    return e


class PaymentDialog(QDialog):
    """Money received against an order. The amount starts at the balance due."""

    def __init__(self, parent, order: dict):
        super().__init__(parent)
        due = float(order.get("balance_due") or 0)
        self.setWindowTitle(f"Payment for {order['order_number']}")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        facts = QLabel(f"Order {rupees(amount_of(order))}  ·  paid {rupees(order.get('advance_paid'))}  ·  due {rupees(due)}")
        facts.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        form.addRow(facts)
        self.amount = money_spin(due if due > 0 else 10_000_000)  # never more than is due
        self.amount.setValue(due)
        self.method = QComboBox()
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.method.setStyleSheet(Theme.input_style())
        self.reference = _line(placeholder="UPI or cheque number (optional)")
        self.note = _line(placeholder="e.g. advance, second instalment")
        self.paid_on = date_edit()
        for label, w in [("Amount *", self.amount), ("How paid", self.method), ("Reference", self.reference), ("Note", self.note), ("Date", self.paid_on)]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(dialog_buttons(self, "Record payment"))

    def _check(self):
        if self.amount.value() <= 0:
            QMessageBox.warning(self, "Check the form", "Enter the amount received.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "amount": round(self.amount.value(), 2),
            "method": self.method.currentData(),
            "reference": self.reference.text().strip() or None,
            "note": self.note.text().strip() or None,
            "paid_on": iso(self.paid_on),
        }


class EditOrderDialog(QDialog):
    """Amounts, delivery date and notes of an open order. Only what changed is sent."""

    def __init__(self, parent, order: dict):
        super().__init__(parent)
        self._o = order
        self.setWindowTitle(f"Edit {order['order_number']}")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        self.estimate = money_spin()
        self.estimate.setValue(float(order.get("estimated_amount") or 0))
        self.final = money_spin()
        self.final.setValue(float(order.get("final_amount") or 0))
        self.final.setSpecialValueText("not set")
        self.final.setToolTip("The agreed price once the work is finished. Leave on 'not set' to use the estimate.")
        self.has_date = QCheckBox("Promised delivery date")
        self.has_date.setChecked(bool(order.get("expected_delivery")))
        self.date = date_edit(order.get("expected_delivery"))
        self.date.setEnabled(self.has_date.isChecked())
        self.has_date.toggled.connect(self.date.setEnabled)
        self.notes = QPlainTextEdit(order.get("notes") or "")
        self.notes.setFixedHeight(90)
        self.notes.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Estimate", styleSheet=Theme.label()), self.estimate)
        form.addRow(QLabel("Final amount", styleSheet=Theme.label()), self.final)
        form.addRow(self.has_date, self.date)
        form.addRow(QLabel("Notes", styleSheet=Theme.label()), self.notes)
        form.addRow(dialog_buttons(self))

    def _check(self):
        paid = float(self._o.get("advance_paid") or 0)
        if 0 < self.final.value() < paid:
            QMessageBox.warning(self, "Check the form", f"The final amount is less than the {rupees(paid)} already paid.")
        else:
            self.accept()

    def get_data(self) -> dict:
        o, out = self._o, {}
        if round(self.estimate.value(), 2) != round(float(o.get("estimated_amount") or 0), 2):
            out["estimated_amount"] = round(self.estimate.value(), 2)
        if round(self.final.value(), 2) != round(float(o.get("final_amount") or 0), 2):
            out["final_amount"] = round(self.final.value(), 2)
        date = iso(self.date) if self.has_date.isChecked() else None
        if date != o.get("expected_delivery"):
            out["expected_delivery"] = date
        notes = self.notes.toPlainText().strip()
        if notes != (o.get("notes") or ""):
            out["notes"] = notes
        return out


class NewOrderDialog(QDialog):
    """A new order: who it is for, what they want (catalogue pieces or a custom piece), the price and the advance."""

    CUSTOM = "__custom__"

    def __init__(self, parent, items: list[dict]):
        super().__init__(parent)
        self._items = {i["id"]: i for i in items}
        self._estimate_by_hand = False
        self.setWindowTitle("New order")
        self.setMinimumWidth(720)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        who = QFormLayout()
        self.name = _line(placeholder="customer name")
        self.phone = _line(placeholder="phone (finds them if they have ordered before)")
        self.kind = QComboBox()
        self.kind.addItem("Custom piece (made to order)", "custom")
        self.kind.addItem("Standard catalogue pieces", "standard")
        self.kind.setStyleSheet(Theme.input_style())
        who.addRow(QLabel("Customer", styleSheet=Theme.label()), self.name)
        who.addRow(QLabel("Phone", styleSheet=Theme.label()), self.phone)
        who.addRow(QLabel("Order type", styleSheet=Theme.label()), self.kind)
        root.addLayout(who)

        root.addWidget(QLabel("What they want", styleSheet=Theme.subheading()))
        self.lines = _table(["Piece", "Description (for a custom piece)", "Qty", "Price each"], 1)
        self.lines.setMaximumHeight(190)
        root.addWidget(self.lines)
        row = QHBoxLayout()
        add = QPushButton("➕  Add a piece")
        add.setStyleSheet(Theme.btn_secondary())
        add.clicked.connect(lambda _c=False: self._add_line())
        drop = QPushButton("Remove last")
        drop.setStyleSheet(Theme.btn_secondary())
        drop.clicked.connect(self._remove_last)
        row.addWidget(add)
        row.addWidget(drop)
        row.addStretch()
        root.addLayout(row)

        money = QFormLayout()
        self.estimate = money_spin()
        self.estimate.valueChanged.connect(self._estimate_edited)
        self.advance = money_spin()
        self.method = QComboBox()
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.method.setStyleSheet(Theme.input_style())
        self.has_date = QCheckBox("Promised delivery date")
        self.date = date_edit()
        self.date.setEnabled(False)
        self.has_date.toggled.connect(self.date.setEnabled)
        self.notes = _line(placeholder="wood, size, motif, anything the carver should know")
        money.addRow(QLabel("Estimate", styleSheet=Theme.label()), self.estimate)
        money.addRow(QLabel("Advance received", styleSheet=Theme.label()), self.advance)
        money.addRow(QLabel("Advance paid by", styleSheet=Theme.label()), self.method)
        money.addRow(self.has_date, self.date)
        money.addRow(QLabel("Notes", styleSheet=Theme.label()), self.notes)
        root.addLayout(money)
        root.addLayout(dialog_buttons(self, "Create order"))
        self._add_line()

    # -- the piece lines -----------------------------------------------
    def _add_line(self):
        r = self.lines.rowCount()
        self.lines.insertRow(r)
        pick = QComboBox()
        pick.addItem("Custom piece…", self.CUSTOM)
        for i in self._items.values():
            pick.addItem(f"{i['name']}  ({i.get('sku', '')})", i["id"])
        pick.setStyleSheet(Theme.input_style())
        text = _line(placeholder="e.g. Door with Ganesha, 6 ft")
        qty = QSpinBox()
        qty.setRange(1, 999)
        qty.setStyleSheet(Theme.input_style())
        price = money_spin(10_000_000)
        for widget, col in ((pick, 0), (text, 1), (qty, 2), (price, 3)):
            self.lines.setCellWidget(r, col, widget)
        self.lines.setRowHeight(r, 44)
        pick.currentIndexChanged.connect(lambda _i, p=pick, t=text, pr=price: self._picked(p, t, pr))
        qty.valueChanged.connect(lambda _v: self._recount())
        price.valueChanged.connect(lambda _v: self._recount())
        self._recount()

    def _remove_last(self):
        if self.lines.rowCount() > 1:
            self.lines.removeRow(self.lines.rowCount() - 1)
            self._recount()

    def _picked(self, pick, text, price):
        item = self._items.get(pick.currentData())
        text.setEnabled(item is None)
        if item:
            text.setText("")
            price.setValue(float(item.get("selling_price") or 0))
        self._recount()

    def _recount(self):
        if self._estimate_by_hand:
            return
        total = sum(self.lines.cellWidget(r, 2).value() * self.lines.cellWidget(r, 3).value() for r in range(self.lines.rowCount()))
        self.estimate.blockSignals(True)
        self.estimate.setValue(total)
        self.estimate.blockSignals(False)

    def _estimate_edited(self, _v):
        self._estimate_by_hand = True  # the owner typed a price: stop overwriting it

    # -- result -----------------------------------------------------------
    def _lines(self) -> list[dict]:
        out = []
        for r in range(self.lines.rowCount()):
            pick, text = self.lines.cellWidget(r, 0), self.lines.cellWidget(r, 1)
            line = {"quantity": self.lines.cellWidget(r, 2).value(), "unit_price": round(self.lines.cellWidget(r, 3).value(), 2)}
            if pick.currentData() == self.CUSTOM:
                line["item_name"] = text.text().strip()
            else:
                line["item_id"] = pick.currentData()
            out.append(line)
        return out

    def _check(self):
        lines = self._lines()
        if any("item_id" not in ln and not ln["item_name"] for ln in lines):
            QMessageBox.warning(self, "Check the form", "Describe each custom piece, or pick one from the catalogue.")
        elif self.advance.value() > 0 and self.estimate.value() > 0 and self.advance.value() > self.estimate.value():
            QMessageBox.warning(self, "Check the form", "The advance is more than the estimate.")
        elif self.phone.text().strip() and not self.name.text().strip():
            QMessageBox.warning(self, "Check the form", "Enter the customer's name too.")
        else:
            self.accept()

    def get_data(self) -> dict:
        order = {
            "order_type": self.kind.currentData(),
            "items": self._lines(),
            "estimated_amount": round(self.estimate.value(), 2),
            "advance_paid": 0,  # the advance is recorded as a payment, so it has a date and a method
            "notes": self.notes.text().strip() or None,
        }
        if self.has_date.isChecked():
            order["expected_delivery"] = iso(self.date)
        return {
            "name": self.name.text().strip(),
            "phone": self.phone.text().strip(),
            "order": order,
            "advance": round(self.advance.value(), 2),
            "method": self.method.currentData(),
        }


class OrdersScreen(QWidget):
    COL_NO, COL_DATE, COL_CUSTOMER, COL_ITEMS, COL_AMOUNT, COL_PAID, COL_DUE, COL_STATUS, COL_DELIVERY = range(9)

    def __init__(self):
        super().__init__()
        self._svc = OrdersService()
        self._rows: list[dict] = []
        self._current: dict | None = None
        self.can_manage = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        self.setStyleSheet(Theme.content_bg())
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self.refresh_data)
        self._build_ui()

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("📋  Orders")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search order, name or phone")
        self.search.setStyleSheet(Theme.input_style())
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        head.addWidget(self.search)
        self.status = QComboBox()
        self.status.addItem("Open orders", "open")
        self.status.addItem("All orders", "all")
        for label, value in STATUSES:
            self.status.addItem(label, value)
        self.status.setStyleSheet(Theme.input_style())
        self.status.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.status)
        self.source = QComboBox()
        self.source.addItem("Shop and website", None)
        self.source.addItem("Shop only", "pos")
        self.source.addItem("Website only", "web")
        self.source.setStyleSheet(Theme.input_style())
        self.source.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.source)
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        self.new_btn = QPushButton("➕  New order")
        self.new_btn.setStyleSheet(Theme.btn_primary())
        self.new_btn.clicked.connect(self._new)
        head.addWidget(self.new_btn)
        root.addLayout(head)

        self.table = _table(["Order", "Date", "Customer", "Items", "Amount", "Paid", "Due", "Status", "Delivery"], self.COL_ITEMS)
        self.table.setMaximumHeight(250)
        self.table.itemSelectionChanged.connect(self._selected)
        root.addWidget(self.table)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        root.addWidget(self.count)

        self.detail = QWidget()
        d = QVBoxLayout(self.detail)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(8)
        self.heading = QLabel("")
        self.heading.setStyleSheet(Theme.subheading())
        self.who = QLabel("")
        self.who.setWordWrap(True)
        self.who.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        self.extra = QLabel("")
        self.extra.setWordWrap(True)
        self.extra.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        for w in (self.heading, self.who, self.extra):
            d.addWidget(w)
        actions = QHBoxLayout()
        self.next_btn = QPushButton("")
        self.next_btn.setStyleSheet(Theme.btn_primary())
        self.next_btn.clicked.connect(lambda _c=False: self._advance())
        self.pay_btn = QPushButton("💵  Record payment")
        self.edit_btn = QPushButton("✏️  Edit")
        self.cancel_btn = QPushButton("Cancel order")
        self.letter_btn = QPushButton("✉️  Confirmation letter")
        for b, slot in ((self.pay_btn, self._pay), (self.letter_btn, self._letter), (self.edit_btn, self._edit), (self.cancel_btn, self._cancel)):
            b.setStyleSheet(Theme.btn_secondary())
            b.clicked.connect(lambda _c=False, s=slot: s())
        for b in (self.next_btn, self.pay_btn, self.letter_btn, self.edit_btn, self.cancel_btn):
            actions.addWidget(b)
        actions.addStretch()
        d.addLayout(actions)
        both = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Pieces ordered", styleSheet=Theme.subheading()))
        self.lines = _table(["Piece", "Qty", "Price", "Note"], 0)
        left.addWidget(self.lines)
        right.addWidget(QLabel("Payments", styleSheet=Theme.subheading()))
        self.payments = _table(["Date", "Amount", "How", "Reference"], 3)
        right.addWidget(self.payments)
        both.addLayout(left, 3)
        both.addLayout(right, 2)
        d.addLayout(both)
        self.detail.setVisible(False)
        root.addWidget(self.detail)

    # ------------------------------------------------------------- data
    @handle_permissions
    def refresh_data(self, _checked=False):
        keep = self._current["id"] if self._current else None
        status = self.status.currentData()
        asked = None if status in ("open", "all") else status
        rows = self._svc.orders(asked, self.source.currentData(), self.search.text().strip())
        if status == "open":
            rows = [o for o in rows if o["status"] in OPEN]
        self._rows = rows
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for r, o in enumerate(rows):
            customer = o.get("customer_name") or "Walk-in"
            if o.get("customer_phone"):
                customer += f"  ·  {o['customer_phone']}"
            values = [
                o["order_number"] + ("  🌐" if o.get("source") == "web" else ""),
                str(o["order_date"])[:10],
                customer,
                items_summary(o),
                rupees(amount_of(o)),
                rupees(o["advance_paid"]),
                rupees(o["balance_due"]),
                STATUS_WORDS.get(o["status"], o["status"]),
                o.get("expected_delivery") or "",
            ]
            for c, text in enumerate(values):
                cell = _cell(text, right=c in (self.COL_AMOUNT, self.COL_PAID, self.COL_DUE))
                if c == self.COL_STATUS:
                    cell.setForeground(QColor(STATUS_COLORS.get(o["status"], Colors.TEXT_PRIMARY)))
                self.table.setItem(r, c, cell)
            self.table.setRowHeight(r, 42)
            if o["id"] == keep:
                self.table.selectRow(r)
        self.table.blockSignals(False)
        self.count.setText(f"{len(rows)} order{'s' if len(rows) != 1 else ''}" + ("  (the newest 100)" if len(rows) >= 100 else ""))
        match = next((o for o in rows if o["id"] == keep), None)
        if match:
            self._show(match)
        else:
            self._current = None
            self.detail.setVisible(False)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._show(self._rows[rows[0].row()])

    def _show(self, o: dict):
        self._current = o
        self.detail.setVisible(True)
        kind = f"{SOURCE_WORDS.get(o.get('source'), 'Shop')} {TYPE_WORDS.get(o['order_type'], o['order_type']).lower()} order"
        self.heading.setText(f"{o['order_number']}  ·  {STATUS_WORDS.get(o['status'], o['status'])}  ·  {kind}")
        who = o.get("customer_name") or "Walk-in customer"
        if o.get("customer_phone"):
            who += f"  ·  {o['customer_phone']}"
        address = o.get("delivery_address") or {}
        if address:
            who += "\nDeliver to: " + ", ".join(str(v) for v in address.values() if v)
        self.who.setText(who)
        bits = [f"Amount {rupees(amount_of(o))}", f"Paid {rupees(o['advance_paid'])}", f"Due {rupees(o['balance_due'])}"]
        if o.get("expected_delivery"):
            bits.append(f"Promised {o['expected_delivery']}")
        extra = ["   ·   ".join(bits)]
        specs = o.get("custom_specs") or {}
        if specs:
            extra.append("Specs: " + ", ".join(f"{k}: {v}" for k, v in specs.items()))
        if o.get("notes"):
            extra.append("Notes: " + o["notes"])
        self.extra.setText("\n".join(extra))

        step = NEXT_STEP.get(o["status"])
        self.next_btn.setVisible(bool(step) and self.can_manage)
        self.next_btn.setText(step[1] if step else "")
        self.edit_btn.setVisible(o["status"] in OPEN and self.can_manage)
        self.cancel_btn.setVisible(o["status"] in OPEN and self.can_manage)
        self.pay_btn.setVisible(o["status"] != "cancelled")
        self.letter_btn.setVisible(o["status"] != "cancelled")
        self.pay_btn.setEnabled(not (float(o["balance_due"]) <= 0 < amount_of(o)))  # nothing left to collect

        self.lines.setRowCount(len(o.get("items") or []))
        for r, ln in enumerate(o.get("items") or []):
            for c, text in enumerate([ln.get("item_name") or "Catalogue piece", str(ln["quantity"]), rupees(ln["unit_price"]), ln.get("notes") or ""]):
                self.lines.setItem(r, c, _cell(text, right=c in (1, 2)))
        pays = o.get("payments") or []
        self.payments.setRowCount(len(pays))
        for r, p in enumerate(pays):
            how = "UPI" if p["method"] == "upi" else p["method"].title()
            for c, text in enumerate([p["paid_on"], rupees(p["amount"]), how, " · ".join(x for x in (p.get("reference"), p.get("note")) if x)]):
                self.payments.setItem(r, c, _cell(text, right=c == 1))

    # ---------------------------------------------------------- actions
    @handle_permissions
    def _advance(self):
        o = self._current
        step = NEXT_STEP.get(o["status"]) if o else None
        if not step:
            return
        if step[0] == "delivered" and float(o["balance_due"]) > 0:
            ask = QMessageBox.question(
                self,
                "Balance still due",
                f"{rupees(o['balance_due'])} is still due on {o['order_number']}. Mark it delivered anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ask != QMessageBox.StandardButton.Yes:
                return
        self._svc.set_status(o["id"], step[0])
        self.refresh_data()

    @handle_permissions
    def _cancel(self):
        o = self._current
        if not o:
            return
        reason, ok = QInputDialog.getText(self, "Cancel order", f"Why is {o['order_number']} cancelled?")
        if not ok:
            return
        if len(reason.strip()) < 3:
            QMessageBox.warning(self, "Cancel order", "Please give a short reason.")
            return
        notes = ((o.get("notes") or "") + f"\nCancelled: {reason.strip()}").strip()
        self._svc.set_status(o["id"], "cancelled", notes)
        self.refresh_data()

    @handle_permissions
    def _pay(self):
        o = self._current
        if not o:
            return
        d = PaymentDialog(self, o)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.add_payment(o["id"], d.get_data())
            self.refresh_data()

    @handle_permissions
    def _letter(self):
        o = self._current
        letter = issue_letter(self, "order_confirmation", order=o) if o else None
        if letter:
            show_letter(letter)

    @handle_permissions
    def _edit(self):
        o = self._current
        if not o:
            return
        d = EditOrderDialog(self, o)
        if d.exec() == QDialog.DialogCode.Accepted:
            changes = d.get_data()
            if changes:
                self._svc.update(o["id"], changes)
                self.refresh_data()

    @handle_permissions
    def _new(self, _checked=False):
        items = InventoryService().get_items(allow_cached=True) or []
        d = NewOrderDialog(self, items)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        data = d.get_data()
        order = data["order"]
        if data["phone"]:
            order["customer_id"] = CustomerService().ensure_customer(data["name"], data["phone"])
        created = self._svc.create(order)
        if data["advance"] > 0:
            created = self._svc.add_payment(created["id"], {"amount": data["advance"], "method": data["method"], "note": "Advance"})
        self._current = created
        self.status.blockSignals(True)
        self.status.setCurrentIndex(self.status.findData("all"))  # show every order so the new one is certainly listed
        self.status.blockSignals(False)
        self.refresh_data()
