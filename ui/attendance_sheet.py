"""
ui/attendance_sheet.py

The month sheet: everyone's attendance for a month on one grid (P present, ½ half-day,
A absent, L leave, • holiday), with the days worked, and a CSV for the accountant.
"""

import calendar
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services import attendance_sheet as sheet_logic
from ui.theme import Colors, Theme

TINT = {"P": "#DDEFD9", "½": "#FFF1CC", "A": "#F7D6D2", "L": "#DCE6F7", "•": "#E8E0F0"}


class MonthSheetDialog(QDialog):
    def __init__(self, parent, service, users: list[dict]):
        super().__init__(parent)
        self._svc, self._users = service, users
        today = date.today()
        self._year, self._month = today.year, today.month
        self._sheet: dict = {"days": 0, "rows": []}
        self.setWindowTitle("Attendance month sheet")
        self.setMinimumSize(900, 520)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        bar = QHBoxLayout()
        self.prev_btn, self.next_btn = QPushButton("◀"), QPushButton("▶")
        for b in (self.prev_btn, self.next_btn):
            b.setStyleSheet(Theme.btn_secondary())
            b.setFixedWidth(44)
        self.prev_btn.clicked.connect(lambda: self._move(-1))
        self.next_btn.clicked.connect(lambda: self._move(1))
        self.title = QLabel(styleSheet=Theme.subheading())
        self.csv_btn = QPushButton("Save CSV…")
        self.csv_btn.setStyleSheet(Theme.btn_secondary())
        self.csv_btn.clicked.connect(self._save_csv)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.title)
        bar.addWidget(self.next_btn)
        bar.addStretch()
        bar.addWidget(self.csv_btn)
        root.addLayout(bar)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        Theme.style_table(self.table)
        root.addWidget(self.table, 1)
        root.addWidget(QLabel("P present   ½ half-day   A absent   L leave   • holiday", styleSheet=f"color: {Colors.TEXT_SECONDARY};"))
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.accept)
        root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self.load()

    def _move(self, delta: int):
        m = self._month - 1 + delta
        self._year, self._month = self._year + m // 12, m % 12 + 1
        self.load()

    def load(self):
        last = calendar.monthrange(self._year, self._month)[1]
        records = self._svc.get_all_attendance(None, f"{self._year:04d}-{self._month:02d}-01", f"{self._year:04d}-{self._month:02d}-{last:02d}")
        self.show_records(records)

    def show_records(self, records: list[dict]):
        self._sheet = sheet_logic.build_sheet(self._users, records, self._year, self._month)
        self.title.setText(f"{calendar.month_name[self._month]} {self._year}")
        days, rows = self._sheet["days"], self._sheet["rows"]
        self.table.setColumnCount(days + 2)
        self.table.setHorizontalHeaderLabels([str(d) for d in range(1, days + 1)] + ["Days", "Absent"])
        self.table.setRowCount(len(rows))
        self.table.setVerticalHeaderLabels([r["name"] for r in rows])
        self.table.verticalHeader().setVisible(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        for i, r in enumerate(rows):
            for d in range(1, days + 1):
                code = r["cells"].get(d, "")
                item = QTableWidgetItem(code)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if code:
                    item.setBackground(QColor(TINT[code]))
                    item.setForeground(QColor("#222222"))
                self.table.setItem(i, d - 1, item)
            for c, text in ((days, f"{r['worked']:g}"), (days + 1, str(r["absent"]))):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, c, item)

    def _save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save attendance", f"attendance-{self._year}-{self._month:02d}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(sheet_logic.to_csv(self._sheet, self._year, self._month))
        except OSError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
