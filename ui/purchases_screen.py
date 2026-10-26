"""
ui/purchases_screen.py

Buying stock: record a purchase from a supplier (materials and/or finished
products), and confirm it when the goods arrive, which adds them to stock.
Owner and manager.
"""

from datetime import datetime

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.inventory_service import InventoryService
from services.stock_service import StockService
from ui.errors import handle_permissions
from ui.item_form import GST_CHOICES
from ui.stock_dialogs import SUPPLIER_FIELDS, ManageRowsDialog
from ui.theme import Colors, Fonts, Theme

STATUS_WORDS = {"pending": "Waiting for goods", "confirmed": "Received"}
TYPE_CHOICES = [("Bill from the supplier", "tax_invoice"), ("Voucher (no bill)", "purchase_voucher")]
PAY_CHOICES = [("Not paid yet", "pending"), ("Paid", "paid")]


def _combo(choices) -> QComboBox:
    c = QComboBox()
    for label, value in choices:
        c.addItem(label, value)
    c.setStyleSheet(Theme.input_style())
    return c


class NewPurchaseDialog(QDialog):
    def __init__(self, parent, suppliers: list, materials: list, items: list):
        super().__init__(parent)
        self.setWindowTitle("New purchase")
        self.resize(720, 560)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        self._lines: list[dict] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)

        form = QFormLayout()
        self.supplier = _combo([("(not chosen)", None)] + [(s["name"], s["id"]) for s in suppliers])
        self.invoice = QLineEdit()
        self.invoice.setPlaceholderText("supplier's bill number, if any")
        self.invoice.setStyleSheet(Theme.input_style())
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setStyleSheet(Theme.input_style())
        self.kind = _combo(TYPE_CHOICES)
        self.paid = _combo(PAY_CHOICES)
        self.notes = QLineEdit()
        self.notes.setStyleSheet(Theme.input_style())
        for label, w in [
            ("Supplier", self.supplier),
            ("Bill number", self.invoice),
            ("Date", self.date),
            ("Document", self.kind),
            ("Payment", self.paid),
            ("Note", self.notes),
        ]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        root.addLayout(form)

        # one line: what, how much, price
        add_row = QHBoxLayout()
        self.what = QComboBox()
        for m in materials:
            self.what.addItem(f"Material: {m['name']} ({m.get('unit') or ''})", ("raw_material_id", m["id"]))
        for i in items:
            self.what.addItem(f"Product: {i['name']}", ("item_id", i["id"]))
        self.what.setStyleSheet(Theme.input_style())
        self.qty = QDoubleSpinBox()
        self.qty.setRange(0, 1_000_000)
        self.qty.setDecimals(2)
        self.qty.setPrefix("Qty ")
        self.price = QDoubleSpinBox()
        self.price.setRange(0, 10_000_000)
        self.price.setPrefix("₹")
        self.price.setSuffix(" each")
        self.gst = _combo([(f"GST {g}%", g) for g in GST_CHOICES])
        add = QPushButton("➕ Add line")
        add.setStyleSheet(Theme.btn_secondary())
        add.clicked.connect(self._add_line)
        for w in (self.what, self.qty, self.price, self.gst, add):
            if isinstance(w, QDoubleSpinBox):
                w.setStyleSheet(Theme.input_style())
            add_row.addWidget(w)
        add_row.setStretch(0, 3)
        root.addLayout(add_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["What", "Qty", "Price", "GST", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(Theme.table_style())
        root.addWidget(self.table)

        bottom = QHBoxLayout()
        self.total = QLabel("Total ₹0.00")
        self.total.setStyleSheet(Theme.subheading())
        bottom.addWidget(self.total)
        bottom.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        save = QPushButton("💾 Save purchase")
        save.setStyleSheet(Theme.btn_primary())
        save.clicked.connect(self._check)
        bottom.addWidget(cancel)
        bottom.addWidget(save)
        root.addLayout(bottom)

    def _add_line(self):
        if self.what.count() == 0 or self.qty.value() <= 0:
            QMessageBox.warning(self, "Line", "Choose what you bought and a quantity above zero.")
            return
        key, ident = self.what.currentData()
        self._lines.append(
            {
                "label": self.what.currentText(),
                key: ident,
                "quantity": self.qty.value(),
                "unit_price": self.price.value(),
                "gst_percent": self.gst.currentData(),
            }
        )
        self.qty.setValue(0)
        self._redraw()

    def _redraw(self):
        self.table.setRowCount(len(self._lines))
        total = 0.0
        for r, line in enumerate(self._lines):
            base = line["quantity"] * line["unit_price"]
            total += base * (1 + line["gst_percent"] / 100)
            for c, text in enumerate(
                [line["label"], f"{line['quantity']:g}", f"₹{line['unit_price']:,.2f}", f"{line['gst_percent']}%"]
            ):
                self.table.setItem(r, c, QTableWidgetItem(text))
            rm = QPushButton("✖")
            rm.setStyleSheet(Theme.btn_table_action())
            rm.clicked.connect(lambda _=False, i=r: self._remove(i))
            self.table.setCellWidget(r, 4, rm)
        self.total.setText(f"Total ₹{total:,.2f}")

    def _remove(self, index: int):
        if 0 <= index < len(self._lines):
            del self._lines[index]
            self._redraw()

    def _check(self):
        if not self._lines:
            QMessageBox.warning(self, "Purchase", "Add at least one line.")
            return
        self.accept()

    def get_data(self) -> dict:
        d = self.date.date()
        when = datetime(d.year(), d.month(), d.day(), 12, 0)
        return {
            "supplier_id": self.supplier.currentData(),
            "invoice_number": self.invoice.text().strip() or None,
            "purchase_date": when.isoformat(),
            "purchase_type": self.kind.currentData(),
            "payment_status": self.paid.currentData(),
            "notes": self.notes.text().strip() or None,
            "items": [
                {k: v for k, v in line.items() if k != "label"} for line in self._lines
            ],
        }


class PurchasesScreen(QWidget):
    def __init__(self):
        super().__init__()
        self._svc = StockService()
        self._inventory = InventoryService()
        self._rows: list[dict] = []
        self._suppliers: dict[str, str] = {}
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("🛒  Purchases")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        for text, style, slot in [
            ("🏭  Suppliers", Theme.btn_secondary(), self._suppliers_dialog),
            ("🔄  Refresh", Theme.btn_secondary(), self.refresh_data),
            ("➕  New purchase", Theme.btn_primary(), self._new),
        ]:
            b = QPushButton(text)
            b.setStyleSheet(style)
            b.clicked.connect(slot)
            head.addWidget(b)
        layout.addLayout(head)

        hint = QLabel(
            "Save a purchase when you order or get the bill. Press Confirm when the goods"
            " arrive: that adds them to stock."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Bill no.", "Supplier", "Total (₹)", "Status", "Payment", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 190)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

    @handle_permissions
    def refresh_data(self, _checked=False):
        self._suppliers = {s["id"]: s["name"] for s in self._svc.rows("suppliers")}
        self._rows = self._svc.purchases()
        self.table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            status = STATUS_WORDS.get(p.get("status"), p.get("status") or "")
            values = [
                str(p.get("purchase_date") or "")[:10],
                p.get("invoice_number") or "",
                self._suppliers.get(p.get("supplier_id"), ""),
                f"{float(p.get('total_amount') or 0):,.2f}",
                status,
                "Paid" if p.get("payment_status") == "paid" else "Not paid yet",
            ]
            for c, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if c == 3:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, cell)
            self.table.setCellWidget(r, 6, self._actions(p))
            self.table.setRowHeight(r, 46)

    def _actions(self, p: dict) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        view = QPushButton("👁 View")
        view.setStyleSheet(Theme.btn_table_action())
        view.setFixedHeight(30)
        view.clicked.connect(lambda _=False, pp=p: self._view(pp))
        h.addWidget(view)
        if p.get("status") == "pending":
            ok = QPushButton("✅ Confirm")
            ok.setStyleSheet(Theme.btn_table_action())
            ok.setFixedHeight(30)
            ok.clicked.connect(lambda _=False, pp=p: self._confirm(pp))
            h.addWidget(ok)
        return box

    @handle_permissions
    def _new(self, _checked=False):
        dialog = NewPurchaseDialog(
            self,
            self._svc.rows("suppliers"),
            self._svc.materials(),
            self._inventory.get_items() or [],
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._svc.create_purchase(dialog.get_data())
            self.refresh_data()

    @handle_permissions
    def _view(self, p: dict):
        full = self._svc.purchase(p["id"])
        lines = "\n".join(
            f"• {float(i['quantity']):g} × ₹{float(i['unit_price']):,.2f}"
            f"  (GST {float(i.get('gst_percent') or 0):g}%)  = ₹{float(i['line_total']):,.2f}"
            for i in full.get("items", [])
        )
        QMessageBox.information(
            self,
            f"Purchase {full.get('invoice_number') or ''}".strip(),
            f"{lines}\n\nTotal ₹{float(full.get('total_amount') or 0):,.2f}"
            f"\nTax ₹{float(full.get('tax_total') or 0):,.2f}",
        )

    @handle_permissions
    def _confirm(self, p: dict):
        ask = QMessageBox.question(
            self,
            "Goods received?",
            "Confirming adds these goods to stock. This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes:
            self._svc.confirm_purchase(p["id"])
            self.refresh_data()

    @handle_permissions
    def _suppliers_dialog(self, _checked=False):
        ManageRowsDialog(self, self._svc, "suppliers", "Suppliers", SUPPLIER_FIELDS).exec()
        self.refresh_data()
