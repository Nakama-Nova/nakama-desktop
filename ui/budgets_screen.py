"""
ui/budgets_screen.py

Budgets for machines and raw materials: this month and this financial year (April to March),
what has been spent, what is left, and a bar that turns amber at 80% and red when it is all used.
Buying is never blocked. Owner and manager look; only the owner sets or removes a budget.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.enums import UserRole
from services.registers_service import RegistersService
from services.session import Session
from ui.components.bootstrap import Card, Grid12
from ui.components.interactive import STATE_COLOURS, UsageBar, action_buttons
from ui.errors import handle_permissions
from ui.machines_screen import _coloured, money, parse_date
from ui.places_screen import _button_row, _right, _table
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async

CATEGORY_WORDS = {"machines": "Machines", "raw_materials": "Raw materials"}
STATE_WORDS = {"ok": "On track", "warning": "Nearly used", "over": "Over budget", "no_budget": "No budget"}


def period_label(period: str, start) -> str:
    d = parse_date(start)
    if d is None:
        return ""
    if period == "financial_year":
        return f"Year {d.year}–{(d.year + 1) % 100:02d}"
    return d.strftime("%B %Y")


def usage_text(amount: float, spent: float) -> tuple[float, str, str]:
    """(percent used, state, words) for a budget of `amount` with `spent` used so far."""
    if amount <= 0:
        return 0.0, "no_budget", "No budget set"
    pct = spent / amount * 100
    state = "over" if spent >= amount else "warning" if pct >= 80 else "ok"
    left = amount - spent
    words = f"{pct:.0f}% used · " + (f"{money(left)} left" if left >= 0 else f"{money(-left)} over")
    return pct, state, words


class SetBudgetDialog(QDialog):
    """Set or change one budget. The bar and the words below show what it would look like
    against what has been spent, as the amount is typed."""

    def __init__(self, parent, status: dict):
        super().__init__(parent)
        self._spent = float(status.get("spent") or 0)
        self._status = status
        label = f"{CATEGORY_WORDS.get(status['category'], status['category'])} · {period_label(status['period'], status['period_start'])}"
        self.setWindowTitle(f"Budget: {label}")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        form.addRow(QLabel(label, styleSheet=Theme.subheading()))
        form.addRow(QLabel(f"Spent so far: {money(self._spent) or '₹0.00'}", styleSheet=f"color: {Colors.TEXT_SECONDARY};"))
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0, 100_000_000)
        self.amount.setPrefix("₹")
        self.amount.setSingleStep(1000)
        self.amount.setValue(float(status.get("amount") or 0))
        self.amount.setStyleSheet(Theme.input_style())
        self.notes = QLineEdit(status.get("notes") or "")
        self.notes.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Budget", styleSheet=Theme.label()), self.amount)
        form.addRow(QLabel("Note", styleSheet=Theme.label()), self.notes)
        self.bar = UsageBar()
        self.words = QLabel("")
        form.addRow(self.bar)
        form.addRow(self.words)
        row, ok = _button_row(self, "Save")
        ok.clicked.connect(self.accept)
        form.addRow(row)
        self.amount.valueChanged.connect(self._preview)
        self._preview()

    def _preview(self, *_):
        pct, state, words = usage_text(self.amount.value(), self._spent)
        self.bar.set_usage(pct, state)
        self.words.setText(words)
        self.words.setStyleSheet(f"color: {STATE_COLOURS[state]}; font-weight: 600;")

    def get_data(self) -> tuple[str, str, str, float, str]:
        s = self._status
        return s["category"], s["period"], s["period_start"], self.amount.value(), self.notes.text().strip()


class BudgetCard(Card):
    def __init__(self, status: dict, can_set: bool, on_set):
        super().__init__(f"{CATEGORY_WORDS.get(status['category'], status['category'])} · {period_label(status['period'], status['period_start'])}")
        amount = float(status["amount"]) if status.get("amount") is not None else 0.0
        spent = float(status.get("spent") or 0)
        pct, state, words = usage_text(amount, spent)
        state = status.get("state") or state
        colour = STATE_COLOURS.get(state, Colors.TEXT_MUTED)
        big = QLabel(f"{money(spent) or '₹0.00'}" + (f"  of  {money(amount)}" if amount else ""))
        big.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")
        self.body.addWidget(big)
        self.bar = UsageBar()
        self.bar.set_usage(float(status.get("percent_used") or pct), state)
        self.body.addWidget(self.bar)
        line = QLabel(words)
        line.setStyleSheet(f"color: {colour}; font-weight: 600;")
        self.body.addWidget(line)
        worth = QLabel(
            ("Machines are worth " if status["category"] == "machines" else "Stock is worth ")
            + f"{money(status.get('current_value')) or '₹0.00'} today"
        )
        worth.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self.body.addWidget(worth)
        self.set_btn = QPushButton("✏️  Change budget" if amount else "➕  Set a budget")
        self.set_btn.setStyleSheet(Theme.btn_table_action())
        self.set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_btn.setVisible(can_set)
        self.set_btn.clicked.connect(lambda: on_set(status))
        self.body.addWidget(self.set_btn, 0, Qt.AlignmentFlag.AlignLeft)


class BudgetsScreen(QWidget):
    COL_PERIOD, COL_CATEGORY, COL_AMOUNT, COL_SPENT, COL_LEFT, COL_STATE, COL_ACTIONS = range(7)

    def __init__(self):
        super().__init__()
        self._svc = RegistersService()
        self._is_owner = Session.is_authorized([UserRole.OWNER])
        self._all: list[dict] = []
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("🎯  Budgets")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_async)
        head.addWidget(refresh)
        layout.addLayout(head)

        hint = QLabel(
            "A budget is a guide: buying is never stopped when one is used up. The bar turns amber at 80%"
            + (" and red when it is all used. Click a card's button to set or change its budget." if self._is_owner else " and red when it is all used.")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.alert = QLabel("")
        self.alert.setWordWrap(True)
        self.alert.setVisible(False)
        layout.addWidget(self.alert)

        self.grid = Grid12()
        layout.addWidget(self.grid)

        layout.addWidget(QLabel("Every budget set", styleSheet=Theme.subheading()))
        self.table = _table(["Period", "For", "Budget", "Spent", "Left", "State", ""])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_ACTIONS, 70 if self._is_owner else 0)
        self.table.setColumnHidden(self.COL_ACTIONS, not self._is_owner)
        layout.addWidget(self.table, 1)

    # ------------------------------------------------------------------ data
    def _fetch(self):
        return self._svc.current_budgets(), self._svc.all_budgets()

    @handle_permissions
    def refresh_data(self):
        self._show(self._fetch())

    def refresh_async(self, _checked=False):
        load_async(self, self._fetch, self._show)

    def _show(self, data):
        current, self._all = data
        self.layout().removeWidget(self.grid)  # a fresh grid: its cards are rebuilt from the new figures
        self.grid.hide()
        self.grid.deleteLater()
        self.grid = Grid12()
        self.layout().insertWidget(self.layout().indexOf(self.alert) + 1, self.grid)
        for status in current:
            self.grid.add(BudgetCard(status, self._is_owner, self._set), lg=6, md=6, sm=12)

        hot = [s for s in current if s.get("state") in ("warning", "over")]
        self.alert.setVisible(bool(hot))
        if hot:
            over = any(s["state"] == "over" for s in hot)
            self.alert.setStyleSheet(Theme.alert("danger" if over else "warning"))
            self.alert.setText(
                "⚠️  "
                + "   ·   ".join(
                    f"{CATEGORY_WORDS.get(s['category'], s['category'])} ({period_label(s['period'], s['period_start']).lower()}): "
                    + STATE_WORDS[s["state"]].lower()
                    for s in hot
                )
            )
        self._fill_table()

    def _fill_table(self):
        t = self.table
        t.setRowCount(len(self._all))
        for i, s in enumerate(self._all):
            left = float(s["remaining"]) if s.get("remaining") is not None else None
            cells = [
                period_label(s["period"], s["period_start"]),
                CATEGORY_WORDS.get(s["category"], s["category"]),
                money(s.get("amount")) or "—",
                money(s.get("spent")) or "₹0.00",
                money(left) if left is not None else "—",
            ]
            for c, text in enumerate(cells):
                t.setItem(i, c, _right(text) if c >= self.COL_AMOUNT else QTableWidgetItem(text))
            t.setItem(i, self.COL_STATE, _coloured(STATE_WORDS.get(s["state"], s["state"]), STATE_COLOURS.get(s["state"], Colors.TEXT_MUTED)))
            if self._is_owner and s.get("id"):
                t.setCellWidget(i, self.COL_ACTIONS, action_buttons([("🗑️", lambda ss=s: self._delete(ss), "Remove this budget")]))
            t.setRowHeight(i, 48)

    # ------------------------------------------------------------------ actions
    @handle_permissions
    def _set(self, status: dict):
        d = SetBudgetDialog(self, status)
        if d.exec() == QDialog.DialogCode.Accepted:
            category, period, start, amount, notes = d.get_data()
            self._svc.set_budget(category, period, start, amount, notes)
            self.refresh_data()

    @handle_permissions
    def _delete(self, status: dict):
        ask = QMessageBox.question(
            self,
            "Remove budget",
            f"Remove the {CATEGORY_WORDS.get(status['category'], status['category']).lower()} budget for "
            f"{period_label(status['period'], status['period_start'])}? What was spent is not touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes and self._svc.delete_budget(status["id"]):
            self.refresh_data()
