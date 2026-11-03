"""
ui/finance_screen.py

Accounts: the finance ledger, to read. Profit and loss, balance sheet, trial balance, the journal
entries and the chart of accounts, for a period you pick. Owner and manager look; the accountant
(the CA) looks at everything including the balance sheet; the balance sheet is for the owner and
the accountant. Nothing here changes the books: posting and corrections stay with the owner on
the server.
"""

from datetime import date, timedelta

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.api_client import APIError, ForbiddenError
from services.enums import UserRole
from services.finance_service import FinanceService
from services.session import Session
from ui.components.interactive import STATE_COLOURS, ChipBar, UsageBar
from ui.errors import handle_permissions
from ui.machines_screen import _coloured, money, parse_date
from ui.places_screen import _right, _table
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async

PAGE = 50  # entries fetched at a time
KIND_WORDS = {"manual": "Typed in", "posting": "Posted by the app", "reversal": "Reversal"}
SOURCE_WORDS = {
    "sale": "Sale",
    "order_payment": "Order payment",
    "purchase": "Purchase",
    "expense": "Expense",
    "wage": "Wages",
    "advance": "Staff advance",
    "machine": "Machine",
}
PERIOD_CHIPS = [("month", "This month"), ("last", "Last month"), ("year", "This financial year"), ("all", "All time"), ("custom", "Pick dates")]


def financial_year_start(today: date) -> date:
    """The financial year runs April to March."""
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


def period_for(key: str, today: date | None = None) -> tuple[date | None, date | None]:
    """(from, to) for a preset; (None, None) is all time."""
    today = today or date.today()
    if key == "month":
        return today.replace(day=1), today
    if key == "last":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if key == "year":
        return financial_year_start(today), today
    return None, None


def when(d) -> str:
    parsed = parse_date(d)
    return parsed.strftime("%d %b %Y") if parsed else ""


def source_words(entry: dict) -> str:
    s = entry.get("source_type")
    return SOURCE_WORDS.get(s, (s or "").replace("_", " ").capitalize()) if s else KIND_WORDS.get(entry.get("kind"), "")


def _amount_cell(text: str) -> QTableWidgetItem:
    return _right(text)


class EntryDialog(QDialog):
    """One journal entry: what happened and every line of it."""

    def __init__(self, parent, entry: dict):
        super().__init__(parent)
        self.setWindowTitle("Journal entry")
        self.setMinimumWidth(640)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        v.addWidget(QLabel(entry.get("memo") or "", wordWrap=True, styleSheet=Theme.subheading()))
        facts = [when(entry.get("entry_date")), KIND_WORDS.get(entry.get("kind"), entry.get("kind") or ""), source_words(entry)]
        v.addWidget(QLabel("  ·  ".join(f for f in facts if f), styleSheet=f"color: {Colors.TEXT_SECONDARY};"))
        if entry.get("reversed_by"):
            v.addWidget(QLabel("This entry was reversed: a later entry cancels it.", styleSheet=Theme.alert("warning"), wordWrap=True))
        if entry.get("reverses_id"):
            v.addWidget(QLabel("This entry reverses an earlier one.", styleSheet=Theme.alert("warning"), wordWrap=True))
        self.table = _table(["Account", "Debit", "Credit", "Note"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lines = entry.get("lines") or []
        self.table.setRowCount(len(lines))
        for i, ln in enumerate(lines):
            self.table.setItem(i, 0, QTableWidgetItem(f"{ln.get('account', '')}  {ln.get('account_name', '')}"))
            debit, credit = float(ln.get("debit") or 0), float(ln.get("credit") or 0)
            self.table.setItem(i, 1, _amount_cell(money(debit) if debit else ""))
            self.table.setItem(i, 2, _amount_cell(money(credit) if credit else ""))
            self.table.setItem(i, 3, QTableWidgetItem(ln.get("note") or ""))
            self.table.setRowHeight(i, 40)
        self.table.setMinimumHeight(min(60 + 40 * len(lines), 360))
        v.addWidget(self.table)
        v.addWidget(QLabel(f"Amount moved: {money(entry.get('total')) or '₹0.00'}", styleSheet=f"font-weight: 700; color: {Colors.TEXT_PRIMARY};"))
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_primary())
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        v.addLayout(row)


class LedgerDialog(QDialog):
    """One account with a running balance, for the period on the screen."""

    def __init__(self, parent, ledger: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Ledger: {ledger.get('name', '')}")
        self.setMinimumWidth(720)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        v.addWidget(QLabel(f"{ledger.get('code', '')}  {ledger.get('name', '')}", styleSheet=Theme.subheading()))
        span = f"{when(ledger.get('date_from')) or 'the beginning'} to {when(ledger.get('date_to')) or 'today'}"
        v.addWidget(QLabel(f"{span}  ·  opening balance {money(ledger.get('opening_balance')) or '₹0.00'}", styleSheet=f"color: {Colors.TEXT_SECONDARY};"))
        self.table = _table(["Date", "What happened", "Debit", "Credit", "Balance"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lines = ledger.get("lines") or []
        self.table.setRowCount(len(lines))
        for i, ln in enumerate(lines):
            self.table.setItem(i, 0, QTableWidgetItem(when(ln.get("entry_date"))))
            self.table.setItem(i, 1, QTableWidgetItem(ln.get("memo") or ""))
            debit, credit = float(ln.get("debit") or 0), float(ln.get("credit") or 0)
            self.table.setItem(i, 2, _amount_cell(money(debit) if debit else ""))
            self.table.setItem(i, 3, _amount_cell(money(credit) if credit else ""))
            self.table.setItem(i, 4, _amount_cell(money(ln.get("balance")) or ""))
            self.table.setRowHeight(i, 40)
        self.table.setMinimumHeight(260)
        v.addWidget(self.table, 1)
        v.addWidget(QLabel(f"Closing balance: {money(ledger.get('closing_balance')) or '₹0.00'}", styleSheet=f"font-weight: 700; color: {Colors.TEXT_PRIMARY};"))
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_primary())
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        v.addLayout(row)


def _report_table(rows: list, headers=("Code", "Account", "Amount")) -> object:
    t = _table(list(headers))
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    t.setRowCount(len(rows))
    for i, r in enumerate(rows):
        t.setItem(i, 0, QTableWidgetItem(r.get("code", "")))
        t.setItem(i, 1, QTableWidgetItem(r.get("name", "")))
        t.setItem(i, 2, _amount_cell(money(r.get("amount")) or "₹0.00"))
        t.setRowHeight(i, 40)
    return t


def _fill_report(table, rows: list) -> None:
    table.setRowCount(len(rows))
    for i, r in enumerate(rows):
        table.setItem(i, 0, QTableWidgetItem(r.get("code", "")))
        table.setItem(i, 1, QTableWidgetItem(r.get("name", "")))
        table.setItem(i, 2, _amount_cell(money(r.get("amount")) or "₹0.00"))
        table.setRowHeight(i, 40)


class FinanceScreen(QWidget):
    def __init__(self):
        super().__init__()
        self._svc = FinanceService()
        self._can_balance = Session.is_authorized([UserRole.OWNER, UserRole.ACCOUNTANT])
        self._range: tuple = period_for("month")
        self._kind: str | None = None
        self._entries: list = []
        self._more = False
        self._accounts: list = []
        self._balances: dict = {}
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("📒  Accounts")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.from_edit, self.to_edit = self._date_box(), self._date_box()
        for w in (QLabel("From", styleSheet=Theme.label()), self.from_edit, QLabel("to", styleSheet=Theme.label()), self.to_edit):
            head.addWidget(w)
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_async)
        head.addWidget(refresh)
        layout.addLayout(head)

        hint = QLabel("The books, to read. Pick a period; double-click an entry or an account to see it in full.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        layout.addWidget(self.status)

        # the period: presets here, exact dates beside the title
        self.chips = ChipBar()
        self.chips.set_chips([(k, label, 0) for k, label in PERIOD_CHIPS])
        self._strip_counts()
        self.chips.changed.connect(self._period_chosen)
        layout.addWidget(self.chips)
        self._set_dates(*self._range)
        self.from_edit.dateChanged.connect(self._dates_edited)
        self.to_edit.dateChanged.connect(self._dates_edited)
        self.chips.choose("month")

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_pnl()
        if self._can_balance:
            self._build_balance()
        self._build_trial()
        self._build_entries()
        self._build_accounts()

    def _strip_counts(self) -> None:
        """The period chips have no counts: show just their names."""
        for key, label in PERIOD_CHIPS:
            self.chips._buttons[key].setText(label)

    @staticmethod
    def _date_box() -> QDateEdit:
        e = QDateEdit()
        e.setCalendarPopup(True)
        e.setDisplayFormat("dd MMM yyyy")
        e.setStyleSheet(Theme.input_style())
        return e

    def _set_dates(self, frm, to) -> None:
        for edit, d in ((self.from_edit, frm), (self.to_edit, to)):
            edit.blockSignals(True)
            d = d or date.today()
            edit.setDate(QDate(d.year, d.month, d.day))
            edit.blockSignals(False)
        everything = frm is None and to is None
        self.from_edit.setEnabled(not everything)
        self.to_edit.setEnabled(not everything)

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QLabel]:
        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ background-color: {Colors.CARD_BG}; border: 1px solid {Colors.CARD_BORDER}; border-radius: 10px; }}"
            "QLabel { border: none; background: transparent; }"
        )
        v = QVBoxLayout(box)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)
        v.addWidget(QLabel(title, styleSheet=f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.CAPTION}px; font-weight: 600;"))
        value = QLabel("—")
        value.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")
        v.addWidget(value)
        return box, value

    def _build_pnl(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(12)
        cards = QHBoxLayout()
        cards.setSpacing(12)
        box1, self.income_lbl = self._card("Income")
        box2, self.expense_lbl = self._card("Expenses")
        box3, self.profit_lbl = self._card("Net profit")
        self.profit_caption = box3.layout().itemAt(0).widget()
        for b in (box1, box2, box3):
            cards.addWidget(b, 1)
        v.addLayout(cards)
        self.spend_bar = UsageBar()
        self.spend_words = QLabel("")
        v.addWidget(self.spend_bar)
        v.addWidget(self.spend_words)
        both = QHBoxLayout()
        both.setSpacing(16)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.addWidget(QLabel("Income", styleSheet=Theme.subheading()))
        self.income_table = _report_table([])
        left.addWidget(self.income_table)
        right.addWidget(QLabel("Expenses", styleSheet=Theme.subheading()))
        self.expense_table = _report_table([])
        right.addWidget(self.expense_table)
        both.addLayout(left, 1)
        both.addLayout(right, 1)
        v.addLayout(both, 1)
        self.tabs.addTab(page, "Profit and loss")

    def _build_balance(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        self.balance_note = QLabel("")
        self.balance_note.setWordWrap(True)
        v.addWidget(self.balance_note)
        cols = QHBoxLayout()
        cols.setSpacing(16)
        self.assets_table, self.liab_table, self.equity_table = _report_table([]), _report_table([]), _report_table([])
        self.assets_total, self.liab_total, self.equity_total = QLabel(""), QLabel(""), QLabel("")
        for title, table, total in (
            ("What the business has", self.assets_table, self.assets_total),
            ("What it owes", self.liab_table, self.liab_total),
            ("What it is worth", self.equity_table, self.equity_total),
        ):
            col = QVBoxLayout()
            col.addWidget(QLabel(title, styleSheet=Theme.subheading()))
            col.addWidget(table, 1)
            total.setStyleSheet(f"font-weight: 700; color: {Colors.TEXT_PRIMARY};")
            col.addWidget(total)
            cols.addLayout(col, 1)
        v.addLayout(cols, 1)
        self.tabs.addTab(page, "Balance sheet")

    def _build_trial(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        self.trial_table = _table(["Code", "Account", "Type", "Debit", "Credit"])
        self.trial_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.trial_table, 1)
        self.trial_note = QLabel("")
        v.addWidget(self.trial_note)
        self.tabs.addTab(page, "Trial balance")

    def _build_entries(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        self.kind_chips = ChipBar()
        self.kind_chips.set_chips([("all", "All", 0), ("manual", "Typed in", 0), ("posting", "Posted by the app", 0), ("reversal", "Reversals", 0)])
        for key, label in (("all", "All"), ("manual", "Typed in"), ("posting", "Posted by the app"), ("reversal", "Reversals")):
            self.kind_chips._buttons[key].setText(label)
        self.kind_chips.changed.connect(self._kind_chosen)
        v.addWidget(self.kind_chips)
        self.entry_search = QLineEdit()
        self.entry_search.setPlaceholderText("🔍  Search what happened...")
        self.entry_search.setStyleSheet(Theme.input_style())
        self.entry_search.textChanged.connect(lambda _t: self._show_entries())
        v.addWidget(self.entry_search)
        self.entries_table = _table(["Date", "What happened", "From", "Amount", ""])
        self.entries_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.entries_table.cellDoubleClicked.connect(self._open_entry)
        v.addWidget(self.entries_table, 1)
        self.more_btn = QPushButton("Show more entries")
        self.more_btn.setStyleSheet(Theme.btn_secondary())
        self.more_btn.clicked.connect(self._load_more)
        self.more_btn.setVisible(False)
        v.addWidget(self.more_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.tabs.addTab(page, "Entries")

    def _build_accounts(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        self.account_search = QLineEdit()
        self.account_search.setPlaceholderText("🔍  Search by code or name...")
        self.account_search.setStyleSheet(Theme.input_style())
        self.account_search.textChanged.connect(lambda _t: self._show_accounts())
        v.addWidget(self.account_search)
        self.accounts_table = _table(["Code", "Account", "Type", "Balance"])
        self.accounts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.accounts_table.cellDoubleClicked.connect(self._open_ledger)
        v.addWidget(self.accounts_table, 1)
        self.tabs.addTab(page, "Accounts")

    # ------------------------------------------------------------------ period
    def _period_chosen(self, key: str) -> None:
        if key != "custom":
            self._range = period_for(key)
            self._set_dates(*self._range)
        else:
            self._range = (self.from_edit.date().toPyDate(), self.to_edit.date().toPyDate())
            self.from_edit.setEnabled(True)
            self.to_edit.setEnabled(True)
        self.refresh_async()

    def _dates_edited(self, _d=None) -> None:
        self.chips.blockSignals(True)
        self.chips.choose("custom")
        self.chips.blockSignals(False)
        self._range = (self.from_edit.date().toPyDate(), self.to_edit.date().toPyDate())
        self.refresh_async()

    # ------------------------------------------------------------------ data
    def _fetch(self):
        frm, to = self._range
        svc = self._svc

        def safe(fn, *args):
            try:
                return fn(*args)
            except ForbiddenError:
                return None

        return {
            "pnl": svc.profit_and_loss(frm, to),
            "trial": svc.trial_balance(to),
            "balance": safe(svc.balance_sheet, to) if self._can_balance else None,
            "entries": svc.entries(frm, to, self._kind, PAGE, 0),
            "accounts": svc.accounts(),
            "recon": safe(svc.reconciliation, frm, to),
            "closing": safe(svc.closing),
        }

    @handle_permissions
    def refresh_data(self):
        self._show(self._fetch())

    def refresh_async(self, _checked=False):
        load_async(self, self._fetch, self._show)

    def _show(self, data: dict) -> None:
        self._show_status(data.get("recon"), data.get("closing"))
        self._show_pnl(data.get("pnl") or {})
        if self._can_balance:
            self._show_balance(data.get("balance"))
        self._show_trial(data.get("trial") or {})
        self._entries = data.get("entries") or []
        self._more = len(self._entries) == PAGE
        self._show_entries()
        self._accounts = data.get("accounts") or []
        self._balances = {r["code"]: r for r in (data.get("trial") or {}).get("rows", [])}
        self._show_accounts()

    def _show_status(self, recon, closing) -> None:
        parts, role = [], "success"
        if recon:
            if recon.get("agrees"):
                parts.append("✅ The ledger agrees with the profit report.")
            else:
                role = "warning"
                waiting, changed = int(recon.get("to_post") or 0), int(recon.get("to_reverse") or 0)
                bits = []
                if waiting:
                    bits.append(f"{waiting} record{'s' if waiting != 1 else ''} not in the ledger yet")
                if changed:
                    bits.append(f"{changed} changed since posting")
                parts.append("⚠️ The ledger and the profit report differ" + (f" ({', '.join(bits)})" if bits else "") + ". The owner can post the records.")
        through = (closing or {}).get("closed_through")
        if through:
            parts.append(f"Books are closed through {when(through)}.")
        self.status.setVisible(bool(parts))
        if parts:
            self.status.setStyleSheet(Theme.alert(role))
            self.status.setText("  ".join(parts))

    def _show_pnl(self, p: dict) -> None:
        income, expenses, net = float(p.get("total_income") or 0), float(p.get("total_expenses") or 0), float(p.get("net_profit") or 0)
        self.income_lbl.setText(money(income) or "₹0.00")
        self.expense_lbl.setText(money(expenses) or "₹0.00")
        loss = net < 0
        self.profit_caption.setText("Loss" if loss else "Net profit")
        self.profit_lbl.setText(money(net) or "₹0.00")
        self.profit_lbl.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {Colors.DANGER if loss else Colors.SUCCESS};")
        pct = expenses / income * 100 if income > 0 else (100.0 if expenses > 0 else 0.0)
        state = "over" if pct >= 100 else "warning" if pct >= 80 else "ok"
        self.spend_bar.set_usage(pct, state)
        self.spend_words.setText(f"Expenses are {pct:.0f}% of income" if income > 0 else ("No income in this period" if not expenses else "Expenses and no income in this period"))
        self.spend_words.setStyleSheet(f"color: {STATE_COLOURS[state]}; font-weight: 600;")
        _fill_report(self.income_table, p.get("income") or [])
        _fill_report(self.expense_table, p.get("expenses") or [])

    def _show_balance(self, b) -> None:
        if not b:
            self.balance_note.setText("The balance sheet could not be read.")
            for t in (self.assets_table, self.liab_table, self.equity_table):
                t.setRowCount(0)
            return
        _fill_report(self.assets_table, b.get("assets") or [])
        _fill_report(self.liab_table, b.get("liabilities") or [])
        equity = list(b.get("equity") or [])
        equity.append({"code": "", "name": "Profit so far (not yet in equity)", "amount": b.get("profit_so_far")})
        _fill_report(self.equity_table, equity)
        self.assets_total.setText(f"Total: {money(b.get('total_assets')) or '₹0.00'}")
        self.liab_total.setText(f"Total: {money(b.get('total_liabilities')) or '₹0.00'}")
        self.equity_total.setText(f"Total: {money(b.get('total_equity')) or '₹0.00'}")
        ok = bool(b.get("balanced"))
        self.balance_note.setStyleSheet(Theme.alert("success" if ok else "danger"))
        self.balance_note.setText(
            f"As of {when(b.get('as_of'))}. " + ("✅ Assets equal liabilities plus worth." if ok else "⚠️ The sheet does not balance: assets differ from liabilities plus worth.")
        )

    def _show_trial(self, t: dict) -> None:
        rows = t.get("rows") or []
        table = self.trial_table
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(r.get("code", "")))
            table.setItem(i, 1, QTableWidgetItem(r.get("name", "")))
            table.setItem(i, 2, QTableWidgetItem((r.get("type") or "").capitalize()))
            debit, credit = float(r.get("debit_balance") or 0), float(r.get("credit_balance") or 0)
            table.setItem(i, 3, _amount_cell(money(debit) if debit else ""))
            table.setItem(i, 4, _amount_cell(money(credit) if credit else ""))
            table.setRowHeight(i, 40)
        if t:
            ok = bool(t.get("balanced"))
            self.trial_note.setStyleSheet(f"color: {Colors.SUCCESS if ok else Colors.DANGER}; font-weight: 600;")
            self.trial_note.setText(
                f"As of {when(t.get('as_of'))}:  debits {money(t.get('debit_balance_total')) or '₹0.00'}  ·  credits "
                f"{money(t.get('credit_balance_total')) or '₹0.00'}  ·  " + ("balanced ✅" if ok else "NOT balanced ⚠️")
            )
        else:
            self.trial_note.setText("")

    # ------------------------------------------------------------------ entries
    def _kind_chosen(self, key: str) -> None:
        self._kind = None if key == "all" else key
        frm, to = self._range

        def fetch():
            return self._svc.entries(frm, to, self._kind, PAGE, 0)

        def render(rows):
            self._entries = rows or []
            self._more = len(self._entries) == PAGE
            self._show_entries()

        load_async(self, fetch, render)

    def _visible_entries(self) -> list:
        q = self.entry_search.text().strip().lower()
        if not q:
            return self._entries
        return [e for e in self._entries if q in (e.get("memo") or "").lower() or q in source_words(e).lower()]

    def _show_entries(self) -> None:
        rows = self._visible_entries()
        self._shown_entries = rows
        t = self.entries_table
        t.setRowCount(len(rows))
        for i, e in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(when(e.get("entry_date"))))
            t.setItem(i, 1, QTableWidgetItem(e.get("memo") or ""))
            t.setItem(i, 2, QTableWidgetItem(source_words(e)))
            t.setItem(i, 3, _amount_cell(money(e.get("total")) or "₹0.00"))
            flag = "Reversed" if e.get("reversed_by") else "Reversal" if e.get("reverses_id") else ""
            t.setItem(i, 4, _coloured(flag, Colors.ORANGE) if flag else QTableWidgetItem(""))
            t.setRowHeight(i, 44)
        self.more_btn.setVisible(self._more)

    def _load_more(self) -> None:
        frm, to, kind, offset = *self._range, self._kind, len(self._entries)

        def fetch():
            return self._svc.entries(frm, to, kind, PAGE, offset)

        def render(rows):
            rows = rows or []
            self._entries += rows
            self._more = len(rows) == PAGE
            self._show_entries()

        load_async(self, fetch, render)

    def _open_entry(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._shown_entries):
            EntryDialog(self, self._shown_entries[row]).exec()

    # ------------------------------------------------------------------ accounts
    def _show_accounts(self) -> None:
        q = self.account_search.text().strip().lower()
        rows = [a for a in self._accounts if not q or q in a["code"] or q in a["name"].lower()]
        self._shown_accounts = rows
        t = self.accounts_table
        t.setRowCount(len(rows))
        for i, a in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(a["code"]))
            name = QTableWidgetItem(a["name"] + ("" if a.get("is_active", True) else "  (switched off)"))
            t.setItem(i, 1, name)
            t.setItem(i, 2, QTableWidgetItem((a.get("type") or "").capitalize()))
            bal = self._balances.get(a["code"])
            t.setItem(i, 3, _amount_cell(money(bal.get("balance")) if bal else ""))
            t.setRowHeight(i, 40)

    @handle_permissions
    def _open_ledger(self, row: int, _col: int) -> None:
        if not 0 <= row < len(self._shown_accounts):
            return
        frm, to = self._range
        try:
            ledger = self._svc.ledger(self._shown_accounts[row]["code"], frm, to)
        except APIError as e:
            QMessageBox.warning(self, "Ledger", f"The ledger could not be read: {e}")
            return
        LedgerDialog(self, ledger).exec()
