"""
ui/bill_payments.py

Two windows opened from Bill History: the payments on a bill (several, by different
methods; add one, or take a wrong one off with a reason) and a return (pick the goods that
came back; the server works out the refund and makes the credit note).
See docs/BILLING_B3_B4_CONTRACT.md.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.billing import METHODS, refund_estimate
from services.money import inr
from services.sales_service import SalesService
from ui.errors import handle_permissions
from ui.theme import Colors, Theme

REFUND_METHODS = METHODS + [("Store credit", "store_credit")]
METHOD_WORDS = {value: label for label, value in METHODS} | {"split": "Split"}


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    Theme.style_table(t)
    return t


def _num(v) -> float:
    return float(v or 0)


class PaymentsDialog(QDialog):
    """What has been paid on a bill, and a place to take more money or void a wrong entry."""

    def __init__(self, parent, sale: dict, svc: SalesService | None = None, can_add=True, can_void=True):
        super().__init__(parent)
        self._svc, self._sale = svc or SalesService(), sale
        self._can_add, self._can_void = can_add, can_void
        self.setWindowTitle(f"Payments: {sale.get('invoice_number', '')}")
        self.setMinimumSize(620, 420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        self.summary = QLabel(styleSheet=Theme.subheading())
        root.addWidget(self.summary)
        self.table = _table(["Date", "Paid by", "Amount", "Reference", ""])
        root.addWidget(self.table, 1)

        self.add_box = QHBoxLayout()
        self.method = QComboBox()
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 10_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("₹")
        self.reference = QLineEdit(placeholderText="UPI or cheque number (optional)")
        for w in (self.method, self.amount, self.reference):
            w.setStyleSheet(Theme.input_style())
        self.add_btn = QPushButton("Add payment")
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add)
        self.add_box.addWidget(self.method)
        self.add_box.addWidget(self.amount, 1)
        self.add_box.addWidget(self.reference, 2)
        self.add_box.addWidget(self.add_btn)
        for w in (self.method, self.amount, self.reference, self.add_btn):
            w.setVisible(can_add)
        root.addLayout(self.add_box)

        row = QHBoxLayout()
        self.void_btn = QPushButton("Take selected payment off…")
        self.void_btn.setStyleSheet(Theme.btn_secondary())
        self.void_btn.setVisible(can_void)
        self.void_btn.clicked.connect(self._void)
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.accept)
        row.addWidget(self.void_btn)
        row.addStretch()
        row.addWidget(close)
        root.addLayout(row)
        self._show()

    def sale(self) -> dict:
        return self._sale

    def _show(self):
        s = self._sale
        paid, due = _num(s.get("amount_paid")), _num(s.get("balance_due"))
        self.summary.setText(f"Bill {inr(_num(s.get('total_amount')))}  ·  paid {inr(paid)}  ·  still to pay {inr(due)}")
        pays = s.get("payments") or []
        self.table.setRowCount(len(pays))
        for r, p in enumerate(pays):
            void = bool(p.get("voided_at"))
            cells = [
                str(p.get("paid_on") or p.get("created_at") or "")[:10],
                METHOD_WORDS.get(p.get("method"), p.get("method") or ""),
                inr(_num(p.get("amount"))),
                p.get("reference") or "",
                f"Taken off: {p.get('void_reason') or ''}" if void else "",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, p.get("id"))
                if c == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if void:
                    f = item.font()
                    f.setStrikeOut(c < 4)
                    item.setFont(f)
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(r, c, item)
        self.amount.setValue(due)
        self.add_btn.setEnabled(due > 0 and self._sale.get("order_status") != "cancelled")

    @handle_permissions
    def _add(self):
        amount = self.amount.value()
        if amount <= 0:
            QMessageBox.warning(self, "Payment", "Enter the amount received.")
            return
        data = {"amount": round(amount, 2), "method": self.method.currentData()}
        if self.reference.text().strip():
            data["reference"] = self.reference.text().strip()
        self._sale = self._svc.add_payment(str(self._sale["id"]), data) or self._sale
        self.reference.clear()
        self._show()

    @handle_permissions
    def _void(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Payment", "Select the payment to take off.")
            return
        item = self.table.item(row, 0)
        if (self._sale.get("payments") or [])[row].get("voided_at"):
            QMessageBox.information(self, "Payment", "That payment is already taken off.")
            return
        reason, ok = QInputDialog.getText(self, "Take payment off", "Why? (kept on record)")
        if not ok or not reason.strip():
            return
        self._sale = self._svc.void_payment(str(self._sale["id"]), item.data(Qt.ItemDataRole.UserRole), reason.strip()) or self._sale
        self._show()


class ReturnDialog(QDialog):
    """Goods coming back from a bill: choose how many of each line, the reason and how to refund."""

    def __init__(self, parent, sale: dict, items: list[dict]):
        super().__init__(parent)
        self._sale, self._items = sale, items
        self._done = sale.get("returned_quantities") or {}
        self.setWindowTitle(f"Return: {sale.get('invoice_number', '')}")
        self.setMinimumSize(640, 460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        root.addWidget(QLabel("How many of each came back?", styleSheet=Theme.subheading()))
        self.table = _table(["Item", "Sold", "Already returned", "Return now"])
        self.table.setRowCount(len(items))
        self.spins: list[QSpinBox] = []
        for r, it in enumerate(items):
            left = max(0, int(it.get("quantity") or 0) - int(self._done.get(str(it.get("id")), 0)))
            for c, text in enumerate([it.get("item_name") or "Item", str(it.get("quantity")), str(int(self._done.get(str(it.get("id")), 0)))]):
                self.table.setItem(r, c, QTableWidgetItem(text))
            spin = QSpinBox()
            spin.setRange(0, left)
            spin.setEnabled(left > 0)
            spin.valueChanged.connect(self._recount)
            self.table.setCellWidget(r, 3, spin)
            self.spins.append(spin)
        root.addWidget(self.table, 1)

        self.method = QComboBox()
        for label, value in REFUND_METHODS:
            self.method.addItem(label, value)
        self.reason = QLineEdit(placeholderText="Why is it coming back? (required)")
        self.restock = QCheckBox("Put the goods back in stock (untick if damaged)")
        self.restock.setChecked(True)
        for w in (self.method, self.reason):
            w.setStyleSheet(Theme.input_style())
        self.estimate = QLabel(styleSheet=f"font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        for w in (QLabel("Refund by"), self.method, self.reason, self.restock, self.estimate):
            root.addWidget(w)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        self.ok_btn = QPushButton("Make credit note")
        self.ok_btn.setStyleSheet(Theme.btn_primary())
        self.ok_btn.clicked.connect(self._check)
        row.addWidget(cancel)
        row.addWidget(self.ok_btn)
        root.addLayout(row)
        self._recount()

    def lines(self) -> list[dict]:
        return [
            {"sale_item_id": str(it["id"]), "quantity": s.value()}
            for it, s in zip(self._items, self.spins)
            if s.value() > 0
        ]

    def refund(self) -> float:
        """The estimate; the server's figure on the credit note is the real one."""
        return refund_estimate(
            [(it.get("total_price"), int(it.get("quantity") or 0), s.value()) for it, s in zip(self._items, self.spins)],
            self._sale.get("discount"),
        )

    def _recount(self, _v=0):
        n = sum(s.value() for s in self.spins)
        self.estimate.setText(f"About {inr(self.refund())} back to the customer" if n else "")
        self.ok_btn.setEnabled(n > 0)

    def _check(self):
        if not self.reason.text().strip():
            QMessageBox.warning(self, "Return", "Say why it is coming back.")
            return
        self.accept()

    def reason_text(self) -> str:
        return self.reason.text().strip()
