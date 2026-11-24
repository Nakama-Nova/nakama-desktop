"""
ui/leave_screen.py

Leave. Everyone sees their balances and can ask for leave; the people who approve (owner,
manager) also see everyone's requests with Approve and Not approve. A server without leave
yet says so instead of failing. See docs/HR_CONTRACT.md, H4.
"""

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
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

from services.api_client import APIError
from services.leave_service import STATUS_WORDS, LeaveService
from services.session import Session
from ui.errors import handle_permissions
from ui.icons import IconButton
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async


class LeaveScreen(QWidget):
    def __init__(self, svc: LeaveService | None = None):
        super().__init__()
        self._svc = svc or LeaveService()
        self._can_decide = Session.can("leave:request:approve")
        self._rows: list[dict] = []
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("Leave")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = IconButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_async)
        head.addWidget(refresh)
        v.addLayout(head)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        v.addWidget(self.note)
        self.balances = QLabel("")
        self.balances.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: 600;")
        v.addWidget(self.balances)

        self.form = QWidget()
        f = QHBoxLayout(self.form)
        f.setContentsMargins(0, 0, 0, 0)
        self.kind = QComboBox()
        self.start, self.end = QDateEdit(QDate.currentDate()), QDateEdit(QDate.currentDate())
        for d in (self.start, self.end):
            d.setCalendarPopup(True)
        self.half = QCheckBox("Half day")
        self.reason = QLineEdit(placeholderText="Reason (optional)")
        self.send_btn = QPushButton("Ask for leave")
        self.send_btn.setStyleSheet(Theme.btn_primary())
        self.send_btn.clicked.connect(self._ask)
        for w in (self.kind, self.start, self.end, self.reason):
            w.setStyleSheet(Theme.input_style())
        for w in (self.kind, QLabel("from"), self.start, QLabel("to"), self.end, self.half, self.reason, self.send_btn):
            f.addWidget(w)
        v.addWidget(self.form)

        self.table = QTableWidget(0, 6 if self._can_decide else 5)
        headers = ["Who", "Kind", "From", "To", "Days", "Status"] if self._can_decide else ["Kind", "From", "To", "Days", "Status"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        Theme.style_table(self.table)
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addStretch()
        self.approve_btn = QPushButton("Approve selected")
        self.reject_btn = QPushButton("Not approve…")
        self.cancel_btn = QPushButton("Cancel my request")
        self.approve_btn.setStyleSheet(Theme.btn_primary())
        self.reject_btn.setStyleSheet(Theme.btn_secondary())
        self.cancel_btn.setStyleSheet(Theme.btn_secondary())
        self.approve_btn.clicked.connect(lambda _c=False: self._decide(True))
        self.reject_btn.clicked.connect(lambda _c=False: self._decide(False))
        self.cancel_btn.clicked.connect(self._cancel)
        for b in (self.approve_btn, self.reject_btn):
            b.setVisible(self._can_decide)
            row.addWidget(b)
        row.addWidget(self.cancel_btn)
        v.addLayout(row)

    # ------------------------------------------------------------ data
    def _fetch(self):
        try:
            return {"types": self._svc.types(), "balances": self._svc.my_balances(), "requests": self._svc.requests()}
        except APIError as exc:
            if exc.status_code == 404:  # an older server: no leave yet
                return None
            raise

    @handle_permissions
    def refresh_data(self, _checked=False):
        self._show(self._fetch())

    def refresh_async(self, _checked=False):
        load_async(self, self._fetch, self._show)

    def _show(self, data):
        self.form.setVisible(data is not None)
        if data is None:
            self.note.setText("Leave is not switched on at the server yet. It appears here once the server is updated.")
            self.balances.setText("")
            self.table.setRowCount(0)
            return
        self.note.setText("Ask for leave here; a manager approves it. Approved leave shows on the attendance sheet." if not self._can_decide else "Waiting requests are at the top. Select one to approve or not approve.")
        current = self.kind.currentData()
        self.kind.clear()
        for t in data["types"]:
            self.kind.addItem(t["name"] + ("" if t.get("paid", True) else " (unpaid)"), t["id"])
        if current is not None:
            self.kind.setCurrentIndex(max(0, self.kind.findData(current)))
        self.balances.setText("   ·   ".join(
            (f"{b['name']}: {b['left']:g} left" + (f" of {b['yearly_days']:g}" if b.get("yearly_days") else "")) if b.get("left") is not None else f"{b['name']}: no limit ({b.get('used') or 0:g} taken)"
            for b in data["balances"]
        ))
        self._rows = sorted(data["requests"], key=lambda r: (r.get("status") != "pending", str(r.get("from_date") or "")), reverse=False)
        kinds = {t["id"]: t["name"] for t in data["types"]}
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            cells = [kinds.get(r.get("leave_type_id"), ""), str(r.get("from_date") or "")[:10], str(r.get("to_date") or "")[:10], f"{float(r.get('days') or 0):g}", STATUS_WORDS.get(r.get("status"), r.get("status") or "")]
            if self._can_decide:
                cells.insert(0, r.get("user_name") or (r.get("user") or {}).get("full_name") or "")
            for c, text in enumerate(cells):
                self.table.setItem(i, c, QTableWidgetItem(text))

    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    # --------------------------------------------------------- actions
    @handle_permissions
    def _ask(self, _checked=False):
        if self.kind.currentData() is None:
            QMessageBox.information(self, "Leave", "There is no kind of leave to choose yet.")
            return
        a, b = self.start.date(), self.end.date()
        if b < a:
            QMessageBox.warning(self, "Leave", "The last day is before the first day.")
            return
        data = {"leave_type_id": self.kind.currentData(), "from_date": a.toString("yyyy-MM-dd"), "to_date": b.toString("yyyy-MM-dd")}
        if self.half.isChecked() and a == b:
            data["half_day"] = True
        if self.reason.text().strip():
            data["reason"] = self.reason.text().strip()
        try:
            self._svc.ask(data)
        except APIError as exc:  # overlap, balance used up: the server says it in plain words
            QMessageBox.warning(self, "Leave", APIError._plain(exc.detail))
            return
        self.reason.clear()
        self.refresh_data()

    @handle_permissions
    def _decide(self, approve: bool):
        r = self._selected()
        if not r or r.get("status") != "pending":
            QMessageBox.information(self, "Leave", "Select a request that is waiting.")
            return
        note = None
        if not approve:
            note, ok = QInputDialog.getText(self, "Not approve", "Tell them why:")
            if not ok or not note.strip():
                return
        self._svc.decide(r["id"], approve, note.strip() if note else None)
        self.refresh_data()

    @handle_permissions
    def _cancel(self, _checked=False):
        r = self._selected()
        if not r or r.get("status") not in ("pending", "approved"):
            QMessageBox.information(self, "Leave", "Select a request of yours to cancel.")
            return
        self._svc.cancel(r["id"])
        self.refresh_data()
