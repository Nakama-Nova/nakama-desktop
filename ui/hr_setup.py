"""
ui/hr_setup.py

The people-side set-up windows: work shifts, public holidays, and a person's staff record
(joining date, address, emergency contact, UPI, ID proof last four, shift, documents, and the
last working day). See docs/HR_CONTRACT.md, H5 and H6.
"""

import webbrowser
from datetime import date

from PyQt6.QtCore import QDate, QTime, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
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
    QTimeEdit,
    QVBoxLayout,
)

from services.hr_service import DOC_KINDS, ID_PROOFS, WEEKDAYS, DocumentError, HrService
from services.money import inr
from services.session import Session
from services.staff_service import StaffService
from ui.theme import Colors, Theme


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    Theme.style_table(t)
    return t


def _btn(text: str, primary=False) -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(Theme.btn_primary() if primary else Theme.btn_secondary())
    return b


class ShiftsDialog(QDialog):
    """Work shifts: a name, start and end, minutes of grace before someone counts as late, and the weekly off days."""

    def __init__(self, parent, svc: HrService | None = None):
        super().__init__(parent)
        self._svc, self._rows = svc or HrService(), []
        self.setWindowTitle("Work shifts")
        self.setMinimumSize(640, 460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        self.table = _table(["Shift", "Starts", "Ends", "Late after", "Weekly off"])
        v.addWidget(self.table, 1)
        v.addWidget(QLabel("Add a shift", styleSheet=Theme.subheading()))
        row = QHBoxLayout()
        self.name = QLineEdit(placeholderText="e.g. Day shift")
        self.start, self.end = QTimeEdit(QTime(9, 0)), QTimeEdit(QTime(18, 0))
        self.grace = QSpinBox()
        self.grace.setRange(0, 240)
        self.grace.setValue(10)
        self.grace.setSuffix(" min grace")
        for w in (self.name, self.start, self.end, self.grace):
            w.setStyleSheet(Theme.input_style())
            row.addWidget(w)
        v.addLayout(row)
        off = QHBoxLayout()
        off.addWidget(QLabel("Weekly off:"))
        self.off = [QCheckBox(d) for d in WEEKDAYS]
        self.off[6].setChecked(True)
        for c in self.off:
            off.addWidget(c)
        off.addStretch()
        v.addLayout(off)
        bar = QHBoxLayout()
        self.del_btn, self.add_btn = _btn("Delete selected"), _btn("Add shift", True)
        close = _btn("Close")
        self.del_btn.clicked.connect(self._delete)
        self.add_btn.clicked.connect(self._add)
        close.clicked.connect(self.accept)
        bar.addWidget(self.del_btn)
        bar.addStretch()
        bar.addWidget(close)
        bar.addWidget(self.add_btn)
        v.addLayout(bar)
        self._load()

    def _load(self):
        self._rows = self._svc.shifts()
        self.table.setRowCount(len(self._rows))
        for r, s in enumerate(self._rows):
            off = ", ".join(WEEKDAYS[d] for d in s.get("weekly_off") or [])
            for c, text in enumerate([s["name"], str(s["start_time"])[:5], str(s["end_time"])[:5], f"{s.get('grace_minutes', 0)} min", off]):
                self.table.setItem(r, c, QTableWidgetItem(text))

    def _add(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Shift", "Give the shift a name.")
            return
        self._svc.save_shift(None, {
            "name": self.name.text().strip(), "start_time": self.start.time().toString("HH:mm:ss"), "end_time": self.end.time().toString("HH:mm:ss"),
            "grace_minutes": self.grace.value(), "weekly_off": [i for i, c in enumerate(self.off) if c.isChecked()],
        })
        self.name.clear()
        self._load()

    def _delete(self):
        r = self.table.currentRow()
        if not 0 <= r < len(self._rows):
            return
        self._svc.delete_shift(self._rows[r]["id"])  # the server refuses (409) a shift people are on
        self._load()


class HolidaysDialog(QDialog):
    """Public holidays of a year; paid ones count as paid days for salaried staff."""

    def __init__(self, parent, svc: HrService | None = None):
        super().__init__(parent)
        self._svc, self._rows, self._year = svc or HrService(), [], date.today().year
        self.setWindowTitle("Holidays")
        self.setMinimumSize(520, 440)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        bar = QHBoxLayout()
        self.prev, self.next, self.title = _btn("◀"), _btn("▶"), QLabel(styleSheet=Theme.subheading())
        self.prev.clicked.connect(lambda: self._move(-1))
        self.next.clicked.connect(lambda: self._move(1))
        for w in (self.prev, self.title, self.next):
            bar.addWidget(w)
        bar.addStretch()
        v.addLayout(bar)
        self.table = _table(["Date", "Holiday", "Paid"])
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.day = QDateEdit(QDate.currentDate())
        self.day.setCalendarPopup(True)
        self.name = QLineEdit(placeholderText="e.g. Diwali")
        self.paid = QCheckBox("Paid")
        self.paid.setChecked(True)
        for w in (self.day, self.name):
            w.setStyleSheet(Theme.input_style())
        for w in (self.day, self.name, self.paid):
            row.addWidget(w)
        v.addLayout(row)
        b = QHBoxLayout()
        self.del_btn, self.add_btn, close = _btn("Delete selected"), _btn("Add holiday", True), _btn("Close")
        self.del_btn.clicked.connect(self._delete)
        self.add_btn.clicked.connect(self._add)
        close.clicked.connect(self.accept)
        b.addWidget(self.del_btn)
        b.addStretch()
        b.addWidget(close)
        b.addWidget(self.add_btn)
        v.addLayout(b)
        self._load()

    def _move(self, d: int):
        self._year += d
        self._load()

    def _load(self):
        self.title.setText(str(self._year))
        self._rows = self._svc.holidays(self._year)
        self.table.setRowCount(len(self._rows))
        for r, h in enumerate(self._rows):
            for c, text in enumerate([str(h["date"])[:10], h["name"], "Yes" if h.get("paid", True) else "No"]):
                self.table.setItem(r, c, QTableWidgetItem(text))

    def _add(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Holiday", "Give the holiday a name.")
            return
        self._svc.add_holiday(self.day.date().toString("yyyy-MM-dd"), self.name.text().strip(), self.paid.isChecked())
        self.name.clear()
        self._load()

    def _delete(self):
        r = self.table.currentRow()
        if 0 <= r < len(self._rows):
            self._svc.delete_holiday(self._rows[r]["id"])
            self._load()


NOT_SET = QDate(2000, 1, 1)


class ProfileDialog(QDialog):
    """A person's staff record: details, shift, documents, and the last working day."""

    def __init__(self, parent, user: dict, hr: HrService | None = None, staff: StaffService | None = None):
        super().__init__(parent)
        self._user, self._hr, self._staff = user, hr or HrService(), staff or StaffService()
        self._docs: list[dict] = []
        self.setWindowTitle(f"Staff record: {user.get('full_name') or user.get('username')}")
        self.setMinimumSize(620, 640)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(8)
        self.joined = QDateEdit(QDate.fromString(str(user.get("joining_date") or "")[:10], "yyyy-MM-dd") if user.get("joining_date") else NOT_SET)
        self.joined.setCalendarPopup(True)
        self.joined.setMinimumDate(NOT_SET)
        self.joined.setSpecialValueText("not set")
        self.address = QLineEdit(user.get("address") or "")
        self.em_name = QLineEdit(user.get("emergency_contact_name") or "")
        self.em_phone = QLineEdit(user.get("emergency_contact_phone") or "")
        self.upi = QLineEdit(user.get("pay_upi") or "", placeholderText="name@bank")
        self.proof = QComboBox()
        self.proof.addItem("(none)", None)
        for label, value in ID_PROOFS:
            self.proof.addItem(label, value)
        self.proof.setCurrentIndex(max(0, self.proof.findData(user.get("id_proof_type"))))
        self.last4 = QLineEdit(user.get("id_proof_last4") or "", placeholderText="last 4 only")
        self.last4.setMaxLength(4)
        self.last4.setToolTip("Only the last four letters or digits are kept, never the whole number")
        self.shift = QComboBox()
        self.shift.addItem("(no shift)", None)
        for s in self._safe(self._hr.shifts, []):
            self.shift.addItem(s["name"], s["id"])
        self.shift.setCurrentIndex(max(0, self.shift.findData(user.get("shift_id"))))
        self._shift_before = self.shift.currentData()
        for label, w in (("Joined", self.joined), ("Address", self.address), ("Emergency contact", self.em_name), ("Their phone", self.em_phone), ("Pays by UPI to", self.upi), ("ID proof", self.proof), ("ID last four", self.last4), ("Shift", self.shift)):
            row = QHBoxLayout()
            lab = QLabel(label, styleSheet=Theme.label())
            lab.setFixedWidth(130)
            w.setStyleSheet(Theme.input_style())
            row.addWidget(lab)
            row.addWidget(w, 1)
            v.addLayout(row)
        self.save_btn = _btn("Save details", True)
        self.save_btn.clicked.connect(self._save)
        v.addWidget(self.save_btn, 0, Qt.AlignmentFlag.AlignRight)

        can_docs = Session.can("people:user:read_documents")
        self.doc_title = QLabel("Documents", styleSheet=Theme.subheading())
        self.docs = _table(["Kind", "File", "Added"])
        self.docs.setMaximumHeight(130)
        self.kind = QComboBox()
        for label, value in DOC_KINDS:
            self.kind.addItem(label, value)
        self.upload_btn, self.open_btn, self.remove_btn = _btn("Add a file…"), _btn("Open"), _btn("Delete")
        self.upload_btn.clicked.connect(self._upload)
        self.open_btn.clicked.connect(self._open_doc)
        self.remove_btn.clicked.connect(self._remove_doc)
        drow = QHBoxLayout()
        for w in (self.kind, self.upload_btn, self.open_btn, self.remove_btn):
            drow.addWidget(w)
        for w in (self.doc_title, self.docs):
            v.addWidget(w)
            w.setVisible(can_docs)
        self.doc_row = drow
        v.addLayout(drow)
        for w in (self.kind, self.upload_btn, self.open_btn, self.remove_btn):
            w.setVisible(can_docs)
        self.upload_btn.setVisible(can_docs and Session.can("people:user:write_documents"))
        self.remove_btn.setVisible(can_docs and Session.can("people:user:write_documents"))
        if can_docs:
            self._load_docs()

        self.leave_btn = _btn("Last working day…")
        self.leave_btn.setVisible(Session.can("people:user:offboard"))
        self.leave_btn.clicked.connect(self._offboard)
        bottom = QHBoxLayout()
        close = _btn("Close")
        close.clicked.connect(self.accept)
        bottom.addWidget(self.leave_btn)
        bottom.addStretch()
        bottom.addWidget(close)
        v.addLayout(bottom)

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception:  # not allowed or not reachable: the part stays empty
            return default

    def details(self) -> dict:
        d = {
            "address": self.address.text().strip() or None, "emergency_contact_name": self.em_name.text().strip() or None,
            "emergency_contact_phone": self.em_phone.text().strip() or None, "pay_upi": self.upi.text().strip() or None,
            "id_proof_type": self.proof.currentData(), "id_proof_last4": self.last4.text().strip() or None,
        }
        if self.joined.date() != NOT_SET:
            d["joining_date"] = self.joined.date().toString("yyyy-MM-dd")
        return d

    def _save(self):
        self._staff.update(self._user["id"], self.details())
        if self.shift.currentData() != self._shift_before:
            self._hr.set_shift(self._user["id"], self.shift.currentData())
            self._shift_before = self.shift.currentData()
        QMessageBox.information(self, "Staff record", "Saved.")

    def _load_docs(self):
        self._docs = self._safe(lambda: self._hr.documents(self._user["id"]), [])
        words = {v: k for k, v in DOC_KINDS}
        self.docs.setRowCount(len(self._docs))
        for r, d in enumerate(self._docs):
            for c, text in enumerate([words.get(d.get("kind"), d.get("kind") or ""), d.get("filename") or "", str(d.get("uploaded_at") or "")[:10]]):
                self.docs.setItem(r, c, QTableWidgetItem(text))

    def _selected_doc(self) -> dict | None:
        r = self.docs.currentRow()
        return self._docs[r] if 0 <= r < len(self._docs) else None

    def _upload(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file", "", "Photos and PDF (*.jpg *.jpeg *.png *.webp *.pdf)")
        if not path:
            return
        try:
            self._hr.upload_document(self._user["id"], self.kind.currentData(), path)
        except DocumentError as exc:
            QMessageBox.warning(self, "File not kept", str(exc))
            return
        self._load_docs()

    def _open_doc(self):
        d = self._selected_doc()
        if d and d.get("url"):
            webbrowser.open(d["url"])  # a short-lived link: it stops working after a few minutes

    def _remove_doc(self):
        d = self._selected_doc()
        if d and QMessageBox.question(self, "Delete file", f"Delete {d.get('filename')}? It cannot be brought back.") == QMessageBox.StandardButton.Yes:
            self._hr.delete_document(self._user["id"], d["id"])
            self._load_docs()

    def _offboard(self):
        text, ok = QInputDialog.getText(self, "Last working day", "Last working day (YYYY-MM-DD):", text=date.today().isoformat())
        if not ok:
            return
        try:
            day = date.fromisoformat(text.strip())
        except ValueError:
            QMessageBox.warning(self, "Last working day", "Write the date like 2026-12-31.")
            return
        s = self._hr.offboard(self._user["id"], day.isoformat())
        QMessageBox.information(
            self, "Settlement",
            f"Last working day {s['last_working_date']}. The account is switched off from {s['deactivates_on']}.\n\n"
            f"Pay still owed {inr(float(s['gross']))}, advance to take back {inr(float(s['advance_balance']))}.\n"
            f"To pay them: {inr(float(s['net_to_pay']))} (use Pay in Wages).",
        )
