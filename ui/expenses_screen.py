"""
ui/expenses_screen.py

Money going out that is not timber or wages: rent, electricity, transport, tools,
repairs. Owner and manager add and fix entries; only the owner can cancel one
(it stays on record with the reason, so the books keep their history).
"""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
from services.money_service import PERIODS, MoneyService, period_range, rupees
from services.session import Session
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme

CATEGORIES = [
    "Shop rent",
    "Electricity",
    "Transport",
    "Tools",
    "Repairs",
    "Packing",
    "Tea and food",
    "Advertising",
    "Other",
]
METHODS = [("Cash", "cash"), ("UPI", "upi"), ("Bank", "bank"), ("Cheque", "cheque"), ("Other", "other")]


def date_edit(iso: str | None = None) -> QDateEdit:
    d = QDateEdit(QDate.fromString(iso, Qt.DateFormat.ISODate) if iso else QDate.currentDate())
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd MMM yyyy")
    d.setStyleSheet(Theme.input_style())
    return d


def iso(d: QDateEdit) -> str:
    return d.date().toString(Qt.DateFormat.ISODate)


def money_spin(maximum: float = 10_000_000) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, maximum)
    s.setDecimals(2)
    s.setPrefix("₹")
    s.setGroupSeparatorShown(True)
    s.setStyleSheet(Theme.input_style())
    return s


def dialog_buttons(dialog, ok_text="Save"):
    row = QHBoxLayout()
    row.addStretch()
    cancel = QPushButton("Cancel")
    cancel.setStyleSheet(Theme.btn_secondary())
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setStyleSheet(Theme.btn_primary())
    ok.clicked.connect(dialog._check)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row


class ExpenseDialog(QDialog):
    def __init__(self, parent, expense: dict | None = None, extra_categories=()):
        super().__init__(parent)
        e = expense or {}
        self.setWindowTitle("Edit expense" if expense else "Add expense")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)

        self.spent_on = date_edit(e.get("spent_on"))
        self.category = QComboBox()
        self.category.setEditable(True)  # type a new heading when none fits
        self.category.addItems(dict.fromkeys([*CATEGORIES, *extra_categories]))
        self.category.setCurrentText(e.get("category") or CATEGORIES[0])
        self.category.setStyleSheet(Theme.input_style())
        self.amount = money_spin()
        self.amount.setValue(float(e.get("amount") or 0))
        self.payee = QLineEdit(e.get("payee") or "")
        self.payee.setPlaceholderText("who was paid (optional)")
        self.payee.setStyleSheet(Theme.input_style())
        self.method = QComboBox()
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.method.setCurrentIndex(max(0, self.method.findData(e.get("method") or "cash")))
        self.method.setStyleSheet(Theme.input_style())
        self.notes = QLineEdit(e.get("notes") or "")
        self.notes.setPlaceholderText("optional")
        self.notes.setStyleSheet(Theme.input_style())

        for label, w in [
            ("Date", self.spent_on),
            ("Heading *", self.category),
            ("Amount *", self.amount),
            ("Paid to", self.payee),
            ("How paid", self.method),
            ("Note", self.notes),
        ]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(dialog_buttons(self))

    def _check(self):
        if not self.category.currentText().strip():
            QMessageBox.warning(self, "Check the form", "Pick or type a heading, such as Shop rent.")
        elif self.amount.value() <= 0:
            QMessageBox.warning(self, "Check the form", "Enter the amount spent.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "spent_on": iso(self.spent_on),
            "category": self.category.currentText().strip(),
            "amount": round(self.amount.value(), 2),
            "payee": self.payee.text().strip() or None,
            "method": self.method.currentData(),
            "notes": self.notes.text().strip() or None,
        }


class ExpensesScreen(QWidget):
    COL_DATE, COL_CAT, COL_PAYEE, COL_METHOD, COL_AMOUNT, COL_NOTES, COL_ACTIONS = range(7)

    def __init__(self):
        super().__init__()
        self._svc = MoneyService()
        self._rows: list[dict] = []
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("💸  Expenses")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.period = QComboBox()
        for label, key in PERIODS:
            self.period.addItem(label, key)
        self.period.setStyleSheet(Theme.input_style())
        self.period.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.period)
        self.add_btn = QPushButton("➕  Add expense")
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add)
        head.addWidget(self.add_btn)
        layout.addLayout(head)

        hint = QLabel(
            "Rent, electricity, transport, tools, repairs. Timber you buy goes under "
            "Purchases and staff pay under Wages, so leave those out here."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: 600;")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Date", "Heading", "Paid to", "How", "Amount", "Note", ""])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self.COL_NOTES, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_ACTIONS, 200)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

    @handle_permissions
    def refresh_data(self, _checked=False):
        start, end = period_range(self.period.currentData())
        self._rows = self._svc.expenses(start, end)
        summary = self._svc.expense_summary(start, end)
        parts = [f"{c['category']} {rupees(c['total'])}" for c in summary["by_category"]]
        self.summary.setText(
            f"Total spent {rupees(summary['total'])}" + ("   ·   " + "   ·   ".join(parts) if parts else "")
        )
        can_void = Session.is_authorized([UserRole.OWNER])
        self.table.setRowCount(len(self._rows))
        for r, e in enumerate(self._rows):
            values = [
                e["spent_on"],
                e["category"],
                e.get("payee") or "",
                e["method"].upper() if e["method"] == "upi" else e["method"].title(),
                rupees(e["amount"]),
                e.get("notes") or "",
            ]
            for c, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if c == self.COL_AMOUNT:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, cell)
            self.table.setCellWidget(r, self.COL_ACTIONS, self._actions(e, can_void))
            self.table.setRowHeight(r, 48)

    def _actions(self, e: dict, can_void: bool) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        buttons = [("✏️ Edit", self._edit)]
        if can_void:
            buttons.append(("Cancel entry", self._void))
        for text, slot in buttons:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setStyleSheet(Theme.btn_table_action())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, ee=e, s=slot: s(ee))
            h.addWidget(b)
        return box

    def _headings(self):
        return [e["category"] for e in self._rows]

    @handle_permissions
    def _add(self, _checked=False):
        d = ExpenseDialog(self, extra_categories=self._headings())
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.add_expense(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _edit(self, e: dict):
        d = ExpenseDialog(self, e, self._headings())
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.edit_expense(e["id"], d.get_data())
            self.refresh_data()

    @handle_permissions
    def _void(self, e: dict):
        reason, ok = QInputDialog.getText(
            self,
            "Cancel this entry",
            f"{e['category']} {rupees(e['amount'])} on {e['spent_on']}.\n"
            "It stays on record, marked cancelled. Why is it wrong?",
        )
        if not ok:
            return
        if len(reason.strip()) < 3:
            QMessageBox.warning(self, "Cancel entry", "Please give a short reason.")
            return
        self._svc.void_expense(e["id"], reason.strip())
        self.refresh_data()
