"""
ui/payroll_screen.py

Staff pay. Owner and manager see what everyone is owed and can pay them, add piece
work, overtime or a bonus, and give or take back an advance. Everyone else sees
only their own balance.

The daily wage comes from attendance; this screen adds what attendance cannot
know (a carving paid by the piece, extra hours) and settles it all in one pay-out.
"""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
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
from services.money_service import MoneyService, rupees
from services.session import Session
from ui.components.metric_card import MetricCard
from ui.errors import handle_permissions
from ui.expenses_screen import METHODS, date_edit, dialog_buttons, iso, money_spin
from ui.staff_screen import ROLE_WORDS
from ui.theme import Colors, Fonts, Theme

KINDS = [
    ("Piece or job work", "piece"),
    ("Overtime hours", "overtime"),
    ("Bonus", "bonus"),
]
KIND_WORDS = {"piece": "Piece work", "overtime": "Overtime", "bonus": "Bonus"}


def person_name(p: dict) -> str:
    return p.get("full_name") or p.get("username") or "?"


def _people_combo(people: list[dict], user_id: str | None) -> QComboBox:
    box = QComboBox()
    for p in people:
        box.addItem(person_name(p), p["user_id"])
    if user_id:
        box.setCurrentIndex(max(0, box.findData(user_id)))
    box.setStyleSheet(Theme.input_style())
    return box


class WorkEntryDialog(QDialog):
    """Pay by the piece, by the hour, or a bonus, on top of the daily wage."""

    def __init__(self, parent, people: list[dict], user_id: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add work or bonus")
        self.setMinimumWidth(430)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        self._people = {p["user_id"]: p for p in people}
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)

        self.person = _people_combo(people, user_id)
        self.kind = QComboBox()
        for label, value in KINDS:
            self.kind.addItem(label, value)
        self.kind.setStyleSheet(Theme.input_style())
        self.work_date = date_edit()
        self.description = QLineEdit()
        self.description.setStyleSheet(Theme.input_style())
        self.quantity = QDoubleSpinBox()
        self.quantity.setRange(0.01, 100000)
        self.quantity.setDecimals(2)
        self.quantity.setValue(1)
        self.quantity.setStyleSheet(Theme.input_style())
        self.rate = money_spin(1_000_000)
        self.total = QLabel("")
        self.total.setStyleSheet(f"font-weight: 700; color: {Colors.TEXT_PRIMARY};")

        self._qty_label = QLabel("", styleSheet=Theme.label())
        self._rate_label = QLabel("", styleSheet=Theme.label())
        form.addRow(QLabel("Who", styleSheet=Theme.label()), self.person)
        form.addRow(QLabel("What for", styleSheet=Theme.label()), self.kind)
        form.addRow(QLabel("Date", styleSheet=Theme.label()), self.work_date)
        form.addRow(QLabel("Details *", styleSheet=Theme.label()), self.description)
        form.addRow(self._qty_label, self.quantity)
        form.addRow(self._rate_label, self.rate)
        form.addRow(QLabel("Comes to", styleSheet=Theme.label()), self.total)
        form.addRow(dialog_buttons(self, "Add"))

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.person.currentIndexChanged.connect(self._kind_changed)
        self.quantity.valueChanged.connect(self._recount)
        self.rate.valueChanged.connect(self._recount)
        self._kind_changed()

    def _usual_overtime(self) -> float:
        return float(self._people.get(self.person.currentData(), {}).get("overtime_rate") or 0)

    def _kind_changed(self, _i=0):
        kind = self.kind.currentData()
        bonus = kind == "bonus"
        self._qty_label.setVisible(not bonus)
        self.quantity.setVisible(not bonus)
        self._qty_label.setText("Hours" if kind == "overtime" else "How many pieces")
        self._rate_label.setText(
            {"piece": "Rate per piece *", "overtime": "Rate per hour", "bonus": "Amount *"}[kind]
        )
        self.description.setPlaceholderText(
            {"piece": "e.g. Carved Ganesha panel", "overtime": "e.g. Rush order", "bonus": "e.g. Diwali bonus"}[kind]
        )
        self.rate.setSpecialValueText("their usual rate" if kind == "overtime" else "")
        self._recount()

    def _recount(self, _v=0):
        qty = 1 if self.kind.currentData() == "bonus" else self.quantity.value()
        rate = self.rate.value()
        if self.kind.currentData() == "overtime" and rate == 0:
            self.total.setText("their usual hourly rate × hours (worked out on save)")
        else:
            self.total.setText(rupees(qty * rate))

    def _check(self):
        kind = self.kind.currentData()
        if not self.description.text().strip():
            QMessageBox.warning(self, "Check the form", "Say what the work or bonus was for.")
        elif self.rate.value() <= 0 and kind != "overtime":
            QMessageBox.warning(self, "Check the form", "Enter the rate (or the bonus amount).")
        else:
            self.accept()

    def get_data(self) -> dict:
        kind = self.kind.currentData()
        rate = round(self.rate.value(), 2)
        return {
            "user_id": self.person.currentData(),
            "work_date": iso(self.work_date),
            "kind": kind,
            "description": self.description.text().strip(),
            "quantity": 1 if kind == "bonus" else round(self.quantity.value(), 2),
            "rate": rate or None,  # overtime at 0 = the person's usual rate, set on the server
        }


class AdvanceDialog(QDialog):
    """Lend money to a staff member, or note that they paid some back."""

    def __init__(self, parent, people: list[dict], user_id: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Advance")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        self.person = _people_combo(people, user_id)
        self.kind = QComboBox()
        self.kind.addItem("Give an advance", "advance")
        self.kind.addItem("They paid some back", "recovery")
        self.kind.setStyleSheet(Theme.input_style())
        self.given_on = date_edit()
        self.amount = money_spin(1_000_000)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("optional, e.g. for hospital")
        self.notes.setStyleSheet(Theme.input_style())
        for label, w in [
            ("Who", self.person),
            ("What", self.kind),
            ("Date", self.given_on),
            ("Amount *", self.amount),
            ("Note", self.notes),
        ]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(dialog_buttons(self))

    def _check(self):
        if self.amount.value() <= 0:
            QMessageBox.warning(self, "Check the form", "Enter the amount.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "user_id": self.person.currentData(),
            "given_on": iso(self.given_on),
            "amount": round(self.amount.value(), 2),
            "kind": self.kind.currentData(),
            "notes": self.notes.text().strip() or None,
        }


class PayDialog(QDialog):
    """Pay everything a person has earned up to a date; optionally take back advance."""

    def __init__(self, parent, row: dict):
        super().__init__(parent)
        self._row = row
        self.setWindowTitle(f"Pay {person_name(row)}")
        self.setMinimumWidth(430)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)

        due = float(row["owed_gross"])
        owes = float(row["advance_balance"])
        facts = QLabel(
            f"Daily wages {rupees(row['pending_daily'])}\n"
            f"Piece work, overtime, bonus {rupees(row['pending_extras'])}\n"
            f"Total due {rupees(due)}\n"
            f"Advance they still owe {rupees(owes)}"
        )
        facts.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        form.addRow(facts)

        self.through = date_edit()
        self.deduction = money_spin(max(owes, 0))
        self.deduction.setToolTip("Taken from this pay-out to clear part of their advance")
        self.deduction.setEnabled(owes > 0)
        self.deduction.setMaximum(min(owes, due))
        self.method = QComboBox()
        for label, value in METHODS:
            self.method.addItem(label, value)
        self.method.setStyleSheet(Theme.input_style())
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("UPI or cheque number (optional)")
        self.reference.setStyleSheet(Theme.input_style())
        self.net = QLabel("")
        self.net.setStyleSheet(f"font-size: {Fonts.BODY + 2}px; font-weight: 700; color: {Colors.GREEN_DARK};")
        for label, w in [
            ("Pay everything up to", self.through),
            ("Take back from advance", self.deduction),
            ("How paid", self.method),
            ("Reference", self.reference),
            ("They receive", self.net),
        ]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(dialog_buttons(self, "Pay now"))
        self.deduction.valueChanged.connect(self._recount)
        self._recount()

    def _recount(self, _v=0):
        self.net.setText(rupees(float(self._row["owed_gross"]) - self.deduction.value()))

    def _check(self):
        if float(self._row["owed_gross"]) <= 0:
            QMessageBox.information(self, "Pay", "Nothing is due to this person.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "user_id": self._row["user_id"],
            "through": iso(self.through),
            "deduction": round(self.deduction.value(), 2),
            "method": self.method.currentData(),
            "reference": self.reference.text().strip() or None,
        }


def _table(headers, stretch_col=None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_col is not None:
        h.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
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


class PayrollScreen(QWidget):
    COL_NAME, COL_ROLE, COL_DAILY, COL_EXTRAS, COL_TOTAL, COL_ADVANCE, COL_ACTIONS = range(7)

    def __init__(self):
        super().__init__()
        self._svc = MoneyService()
        self._owed: list[dict] = []
        self.can_manage = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    # ---------------------------------------------------------- layout
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("💰  Wages" if self.can_manage else "💰  My pay")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        if self.can_manage:
            self.work_btn = QPushButton("➕  Work or bonus")
            self.work_btn.setStyleSheet(Theme.btn_secondary())
            self.work_btn.clicked.connect(lambda _c=False: self._add_work(None))
            head.addWidget(self.work_btn)
            self.advance_btn = QPushButton("🤝  Advance")
            self.advance_btn.setStyleSheet(Theme.btn_secondary())
            self.advance_btn.clicked.connect(lambda _c=False: self._advance(None))
            head.addWidget(self.advance_btn)
        layout.addLayout(head)

        hint = QLabel(
            "Daily wages come from attendance. Add piece work, overtime or a bonus here, then "
            "Pay to settle everything up to a date. Paying is what counts wages in your profit."
            if self.can_manage
            else "What you have earned and not been paid yet, any advance you owe, and your last pay-outs."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: 600;")
        layout.addWidget(self.summary)

        if self.can_manage:
            self.table = _table(["Name", "Role", "Daily wages", "Piece/OT/bonus", "Total due", "Advance owed", ""], self.COL_NAME)
            self.table.horizontalHeader().setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(self.COL_ACTIONS, 330)
            layout.addWidget(self.table)
            layout.addWidget(QLabel("Recent pay-outs", styleSheet=Theme.subheading()))
            self.payments = _table(["Paid on", "Name", "Earned", "Taken back", "They received", "How"])
            self.payments.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.payments.setMaximumHeight(220)
            layout.addWidget(self.payments)
        else:
            cards = QGridLayout()
            cards.setSpacing(14)
            self.card_daily = MetricCard("Daily wages due", "₹0.00", Colors.GREEN, icon="📅")
            self.card_extras = MetricCard("Piece work, overtime, bonus", "₹0.00", Colors.BLUE, icon="🪵")
            self.card_advance = MetricCard("Advance I owe", "₹0.00", Colors.ORANGE, icon="🤝")
            for i, c in enumerate((self.card_daily, self.card_extras, self.card_advance)):
                cards.addWidget(c, 0, i)
            layout.addLayout(cards)
            layout.addWidget(QLabel("Work waiting to be paid", styleSheet=Theme.subheading()))
            self.entries = _table(["Date", "What", "Details", "Amount"], 2)
            layout.addWidget(self.entries)
            layout.addWidget(QLabel("My last pay-outs", styleSheet=Theme.subheading()))
            self.my_payments = _table(["Paid on", "Earned", "Taken back", "I received", "How"])
            layout.addWidget(self.my_payments)

    # ------------------------------------------------------------ data
    @handle_permissions
    def refresh_data(self, _checked=False):
        if self.can_manage:
            self._refresh_everyone()
        else:
            self._refresh_mine()

    def _refresh_everyone(self):
        self._owed = self._svc.owed()
        names = {p["user_id"]: person_name(p) for p in self._owed}
        due = sum(float(p["owed_gross"]) for p in self._owed)
        lent = sum(float(p["advance_balance"]) for p in self._owed)
        self.summary.setText(f"Owed to staff now {rupees(due)}   ·   Advances out {rupees(lent)}")
        self.table.setRowCount(len(self._owed))
        for r, p in enumerate(self._owed):
            values = [
                person_name(p),
                ROLE_WORDS.get(p.get("role"), p.get("role") or ""),
                rupees(p["pending_daily"]),
                rupees(p["pending_extras"]),
                rupees(p["owed_gross"]),
                rupees(p["advance_balance"]),
            ]
            for c, text in enumerate(values):
                self.table.setItem(r, c, _cell(text, right=c >= self.COL_DAILY))
            self.table.setCellWidget(r, self.COL_ACTIONS, self._actions(p))
            self.table.setRowHeight(r, 52)
        rows = self._svc.payments()[:20]
        self.payments.setRowCount(len(rows))
        for r, p in enumerate(rows):
            gross = float(p["gross_daily"]) + float(p["gross_extras"])
            values = [
                p["paid_on"],
                names.get(p["user_id"], "(former staff)"),
                rupees(gross),
                rupees(p["deductions"]),
                rupees(p["net_paid"]),
                p["method"].upper() if p["method"] == "upi" else p["method"].title(),
            ]
            for c, text in enumerate(values):
                self.payments.setItem(r, c, _cell(text, right=c in (2, 3, 4)))

    def _refresh_mine(self):
        me = self._svc.my_payroll()
        self.card_daily.set_value(rupees(me["pending_daily"]))
        self.card_extras.set_value(rupees(me["pending_extras"]))
        self.card_advance.set_value(rupees(me["advance_balance"]))
        self.summary.setText(f"Total waiting for you: {rupees(me['owed_gross'])}")
        entries = me["pending_entries"]
        self.entries.setRowCount(len(entries))
        for r, e in enumerate(entries):
            values = [e["work_date"], KIND_WORDS.get(e["kind"], e["kind"]), e["description"], rupees(e["amount"])]
            for c, text in enumerate(values):
                self.entries.setItem(r, c, _cell(text, right=c == 3))
        pays = me["recent_payments"]
        self.my_payments.setRowCount(len(pays))
        for r, p in enumerate(pays):
            gross = float(p["gross_daily"]) + float(p["gross_extras"])
            values = [p["paid_on"], rupees(gross), rupees(p["deductions"]), rupees(p["net_paid"]), p["method"].title()]
            for c, text in enumerate(values):
                self.my_payments.setItem(r, c, _cell(text, right=c in (1, 2, 3)))

    # --------------------------------------------------------- actions
    def _actions(self, p: dict) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        for text, slot, on in [
            ("💵 Pay", self._pay, float(p["owed_gross"]) > 0),
            ("➕ Work", self._add_work, True),
            ("🤝 Advance", self._advance, True),
        ]:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setEnabled(on)
            b.setStyleSheet(Theme.btn_table_action())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, pp=p, s=slot: s(pp))
            h.addWidget(b)
        return box

    @handle_permissions
    def _pay(self, p: dict):
        d = PayDialog(self, p)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        paid = self._svc.pay(d.get_data())
        QMessageBox.information(
            self,
            "Paid",
            f"{person_name(p)} was paid {rupees(paid['net_paid'])}"
            + (f" ({rupees(paid['deductions'])} taken back from their advance)." if float(paid["deductions"]) else "."),
        )
        self.refresh_data()

    @handle_permissions
    def _add_work(self, p: dict | None):
        d = WorkEntryDialog(self, self._owed_for_dialog(), p["user_id"] if p else None)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.add_work_entry(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _advance(self, p: dict | None):
        d = AdvanceDialog(self, self._owed_for_dialog(), p["user_id"] if p else None)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.add_advance(d.get_data())
            self.refresh_data()

    def _owed_for_dialog(self) -> list[dict]:
        return self._owed or self._svc.owed()
