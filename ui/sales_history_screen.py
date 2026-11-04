"""
ui/sales_history_screen.py

Bill History: every bill, its payment, and what you can do with it. View it, print it again, correct
its payment (owner and manager), or delete it (owner): the stock it took comes back, the bill stays
here marked Cancelled with the reason, and the books reverse it. No customer ids are shown.
"""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
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

from services.enums import UserRole
from services.event_bus import SALE_CREATED, EventBus
from services.sales_service import BillPdfError, SalesService
from services.session import Session
from ui.components.interactive import ChipBar
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async

PAYMENT_WORDS = {"paid": "Paid", "partial": "Part paid", "pending": "Not paid yet"}
PAYMENT_COLOURS = {"paid": Colors.SUCCESS, "partial": Colors.ORANGE, "pending": Colors.TEXT_SECONDARY}
METHODS = [("Cash", "cash"), ("UPI", "upi"), ("Card", "card"), ("Bank transfer", "bank"), ("Cheque", "cheque")]


def is_cancelled(sale: dict) -> bool:
    return (sale.get("order_status") or "") == "cancelled"


def bill_text(sale: dict, items: list[dict]) -> str:
    """A bill the way billing worked it out: each line before GST, its GST, then the totals."""
    msg = f"Bill: {sale.get('invoice_number', 'N/A')}\n\n"
    before_gst = 0.0
    for item in items:
        qty = item.get("quantity", 0)
        price = float(item.get("price_at_sale", 0))
        gst = float(item.get("cgst_amount") or 0) + float(item.get("sgst_amount") or 0)
        line = f"  • {item.get('item_name', 'Item')}:  {qty} × ₹{price:,.2f}"
        if gst:
            line += f"  + GST {float(item.get('gst_percent') or 0):g}% ₹{gst:,.2f}"
        msg += f"{line}  =  ₹{float(item.get('total_price', 0)):,.2f}\n"
        before_gst += price * qty
    tax = float(sale.get("tax_total") or 0)
    discount = float(sale.get("discount") or 0)
    msg += f"\nSubtotal (before GST): ₹{before_gst:,.2f}"
    if tax:
        msg += f"\nGST: ₹{tax:,.2f}  (CGST ₹{tax / 2:,.2f} + SGST ₹{tax / 2:,.2f})"
    if discount:
        msg += f"\nDiscount: -₹{discount:,.2f}"
    return msg + f"\nTotal: ₹{float(sale.get('total_amount', 0)):,.2f}"


class DeleteBillDialog(QDialog):
    """Says plainly what deleting a bill does, and asks why (the reason is kept with the bill)."""

    def __init__(self, parent, sale: dict):
        super().__init__(parent)
        self.setWindowTitle("Delete bill")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(QLabel(f"Delete bill {sale.get('invoice_number', '')}?", styleSheet=Theme.subheading()))
        amount = float(sale.get("total_amount") or 0)
        note = QLabel(
            f"Amount ₹{amount:,.2f}.\n\n"
            "• Every piece on it goes back to the shelf, in the place it was sold from.\n"
            "• The bill stays in Bill History, marked Cancelled, with your reason.\n"
            "• Sales, profit and the books stop counting it.\n"
            "• A bill made from an order lets that order be billed again.\n\n"
            "This cannot be undone. To change what was sold, delete this bill and make a new one."
        )
        note.setWordWrap(True)
        note.setStyleSheet(Theme.alert("warning"))
        v.addWidget(note)
        form = QFormLayout()
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Why? e.g. wrong item, billed twice")
        self.reason.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Reason *", styleSheet=Theme.label()), self.reason)
        v.addLayout(form)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Keep the bill")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        self.delete_btn = QPushButton("Delete bill")
        self.delete_btn.setStyleSheet(Theme.btn_danger())
        self.delete_btn.clicked.connect(self._check)
        row.addWidget(cancel)
        row.addWidget(self.delete_btn)
        v.addLayout(row)

    def _check(self):
        if len(self.reason.text().strip()) < 3:
            QMessageBox.warning(self, "Reason", "Please say why, in a few words, so the history makes sense.")
        else:
            self.accept()

    def reason_text(self) -> str:
        return self.reason.text().strip()


class PaymentDialog(QDialog):
    """Correct how a bill was paid. What was sold and its price stay as they are."""

    def __init__(self, parent, sale: dict):
        super().__init__(parent)
        self._sale = sale
        self.setWindowTitle(f"Payment: {sale.get('invoice_number', '')}")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        form.addRow(QLabel(f"Bill {sale.get('invoice_number', '')}  ·  ₹{float(sale.get('total_amount') or 0):,.2f}", styleSheet=Theme.subheading()))
        self.status = QComboBox()
        for value, label in (("pending", "Not paid yet"), ("partial", "Part paid"), ("paid", "Paid")):
            self.status.addItem(label, value)
        self.status.setCurrentIndex(max(0, self.status.findData(sale.get("payment_status") or "pending")))
        self.status.setStyleSheet(Theme.input_style())
        self.method = QComboBox()
        self.method.addItem("(not said)", None)
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.method.setCurrentIndex(max(0, self.method.findData(sale.get("payment_method"))))
        self.method.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Payment", styleSheet=Theme.label()), self.status)
        form.addRow(QLabel("Paid by", styleSheet=Theme.label()), self.method)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setStyleSheet(Theme.btn_primary())
        save.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(save)
        form.addRow(row)

    def changes(self) -> dict:
        """Only what was changed, as the server takes it."""
        out = {}
        if self.status.currentData() != (self._sale.get("payment_status") or "pending"):
            out["payment_status"] = self.status.currentData()
        if self.method.currentData() != self._sale.get("payment_method") and self.method.currentData():
            out["payment_method"] = self.method.currentData()
        return out


class SalesHistoryScreen(QWidget):
    COL_BILL, COL_AMOUNT, COL_DATE, COL_PAYMENT, COL_ACTIONS = range(5)

    def __init__(self):
        super().__init__()
        self._sales_service = SalesService()
        self._can_edit = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        self._can_delete = Session.is_authorized([UserRole.OWNER])
        self._sales: list[dict] = []
        self._shown: list[dict] = []
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

        EventBus.subscribe(SALE_CREATED, self.refresh_async)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header = QLabel("📜  Bill History")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()
        refresh_btn = QPushButton("🔄  Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(Theme.btn_secondary())
        refresh_btn.clicked.connect(self.refresh_async)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        self.chips = ChipBar()
        self.chips.changed.connect(lambda _k: self._show())
        layout.addWidget(self.chips)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Search by bill number...")
        self.search.setStyleSheet(Theme.input_style())
        self.search.textChanged.connect(lambda _t: self._show())
        filter_row.addWidget(self.search, 1)
        date_lbl = QLabel("Date:")
        date_lbl.setStyleSheet(Theme.label())
        filter_row.addWidget(date_lbl)
        self.date_filter = QDateEdit()
        self.date_filter.setCalendarPopup(True)
        self.date_filter.setDate(QDate.currentDate())
        self.date_filter.setStyleSheet(Theme.input_style())
        self.date_filter.setFixedWidth(160)
        filter_row.addWidget(self.date_filter)
        apply_btn = QPushButton("🔍  Filter")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(Theme.btn_secondary())
        apply_btn.clicked.connect(self._apply_filter)
        filter_row.addWidget(apply_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(Theme.btn_secondary())
        clear_btn.clicked.connect(self.refresh_async)
        filter_row.addWidget(clear_btn)
        layout.addLayout(filter_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Bill No.", "Amount (₹)", "Date", "Payment", "Actions"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_ACTIONS, 300 if self._can_delete else 240 if self._can_edit else 180)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Theme.table_style())
        self.table.cellDoubleClicked.connect(self._open_row)
        layout.addWidget(self.table)

    # ------------------------------------------------------------------ data
    def refresh_data(self):
        """EventBus-safe: no args. Loads all sales."""
        self._populate_table(self._sales_service.get_sales() or [])

    def refresh_async(self, _checked=False):
        """Same as refresh_data, but the bills are fetched in the background."""
        load_async(self, self._sales_service.get_sales, lambda sales: self._populate_table(sales or []))

    def _load_sales(self, customer_id=None, date=None):
        """Load sales with optional filters."""
        self._populate_table(self._sales_service.get_sales(customer_id=customer_id, date=date) or [])

    def _populate_table(self, sales: list[dict]):
        self._sales = sales
        counts = {
            "all": len(sales),
            "pending": sum(1 for s in sales if not is_cancelled(s) and (s.get("payment_status") or "pending") != "paid"),
            "paid": sum(1 for s in sales if not is_cancelled(s) and s.get("payment_status") == "paid"),
            "cancelled": sum(1 for s in sales if is_cancelled(s)),
        }
        self.chips.set_chips(
            [("all", "All", counts["all"]), ("pending", "Not fully paid", counts["pending"]), ("paid", "Paid", counts["paid"]), ("cancelled", "Cancelled", counts["cancelled"])]
        )
        self._show()

    def _visible(self) -> list[dict]:
        key, q = self.chips.current(), self.search.text().strip().lower()
        rows = []
        for s in self._sales:
            cancelled = is_cancelled(s)
            if key == "pending" and (cancelled or s.get("payment_status") == "paid"):
                continue
            if key == "paid" and (cancelled or s.get("payment_status") != "paid"):
                continue
            if key == "cancelled" and not cancelled:
                continue
            if q and q not in (s.get("invoice_number") or "").lower():
                continue
            rows.append(s)
        return rows

    def _show(self):
        self._shown = self._visible()
        self.table.setRowCount(0)
        for row, sale in enumerate(self._shown):
            self.table.insertRow(row)
            self.table.setRowHeight(row, 46)
            cancelled = is_cancelled(sale)
            created = str(sale.get("created_at") or "")
            created = created.split("T")[0] if "T" in created else created
            cells = [sale.get("invoice_number", "N/A"), f"₹{float(sale.get('total_amount', 0)):,.2f}", created]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == self.COL_AMOUNT:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if cancelled:
                    item.setForeground(QColor(Colors.TEXT_MUTED))
                    f = item.font()
                    f.setStrikeOut(True)
                    item.setFont(f)
                self.table.setItem(row, col, item)
            status = sale.get("payment_status") or "pending"
            word, colour = ("Cancelled", Colors.DANGER) if cancelled else (PAYMENT_WORDS.get(status, status), PAYMENT_COLOURS.get(status, Colors.TEXT_PRIMARY))
            pay = QTableWidgetItem(word)
            pay.setForeground(QColor(colour))
            f = pay.font()
            f.setBold(True)
            pay.setFont(f)
            self.table.setItem(row, self.COL_PAYMENT, pay)
            self.table.setCellWidget(row, self.COL_ACTIONS, self._actions(sale, cancelled))

    def _actions(self, sale: dict, cancelled: bool) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        buttons = [("👁️ View", self._view_details, "See what was sold"), ("🖨️ Print", self._reprint_invoice, "Open the bill PDF")]
        if self._can_edit and not cancelled:
            buttons.append(("✏️ Payment", self._edit_payment, "Correct how it was paid"))
        if self._can_delete and not cancelled:
            buttons.append(("🗑️ Delete", self._delete_bill, "Cancel this bill; the stock comes back"))
        for text, slot, tip in buttons:
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(28)
            b.setToolTip(tip)
            b.setStyleSheet(Theme.btn_table_action())
            b.clicked.connect(lambda _=False, s=sale, f=slot: f(s))
            h.addWidget(b)
        return box

    def _apply_filter(self):
        self._load_sales(date=self.date_filter.date().toString("yyyy-MM-dd"))

    # ------------------------------------------------------------------ actions
    def _open_row(self, row: int, _col: int):
        if 0 <= row < len(self._shown):
            self._view_details(self._shown[row])

    def _view_details(self, sale):
        sale_id = str(sale["id"])
        items = self._sales_service.get_sale_items(sale_id)
        if not items:
            QMessageBox.information(self, "No Items", "No items found for this bill.")
            return
        QMessageBox.information(self, "📋 Bill Details", bill_text(sale, items) + ("\n\nThis bill was deleted (cancelled)." if is_cancelled(sale) else ""))

    def _reprint_invoice(self, sale):
        inv_num = sale.get("invoice_number")
        if not inv_num:
            return

        try:
            self._sales_service.open_pdf(self._sales_service.fetch_and_save_pdf(inv_num))
        except BillPdfError as exc:
            QMessageBox.critical(self, "Bill PDF", f"Could not open the PDF for {inv_num}.\n\n{exc}")

    @handle_permissions
    def _edit_payment(self, sale):
        d = PaymentDialog(self, sale)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        changes = d.changes()
        if not changes:
            return
        self._sales_service.edit_sale(str(sale["id"]), changes)
        self.refresh_async()

    @handle_permissions
    def _delete_bill(self, sale):
        d = DeleteBillDialog(self, sale)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        self._sales_service.cancel_sale(str(sale["id"]), d.reason_text())
        QMessageBox.information(
            self,
            "Bill deleted",
            f"Bill {sale.get('invoice_number', '')} was deleted. Its stock is back on the shelf, and it stays in the history as Cancelled.",
        )
        self.refresh_async()
