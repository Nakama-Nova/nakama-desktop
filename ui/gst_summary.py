"""
ui/gst_summary.py

The GST figures for a period (taxable value, CGST, SGST, IGST), shown on the Reports screen,
with a CSV to hand to the accountant. The figures come from the server's /reports/gst-summary.
"""

from datetime import date, timedelta

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services import gst
from services.money import inr
from ui.components.metric_card import MetricCard
from ui.theme import Colors, Theme
from ui.workers import load_async

PERIODS = [("This month", "month"), ("Last month", "last"), ("This year (April to now)", "fy"), ("Choose dates", "custom")]


def period_dates(key: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if key == "last":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if key == "fy":  # the Indian financial year starts on 1 April
        year = today.year if today.month >= 4 else today.year - 1
        return date(year, 4, 1), today
    return today.replace(day=1), today


class GstSummaryPanel(QFrame):
    def __init__(self, report_service):
        super().__init__()
        self._svc, self._data, self._asked = report_service, None, False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        head = QHBoxLayout()
        title = QLabel("GST for the accountant")
        title.setStyleSheet(Theme.subheading())
        head.addWidget(title)
        head.addStretch()
        self.period = QComboBox()
        for label, key in PERIODS:
            self.period.addItem(label, key)
        self.start, self.end = QDateEdit(), QDateEdit()
        for d in (self.start, self.end):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd MMM yyyy")
            d.setVisible(False)
        for w in (self.period, self.start, self.end):
            w.setStyleSheet(Theme.input_style())
            head.addWidget(w)
        self.csv_btn = QPushButton("Save CSV…")
        self.csv_btn.setStyleSheet(Theme.btn_secondary())
        self.csv_btn.setEnabled(False)
        self.csv_btn.clicked.connect(self._save_csv)
        head.addWidget(self.csv_btn)
        root.addLayout(head)
        cards = QHBoxLayout()
        self.cards = {
            "taxable_value": MetricCard("Taxable value", "₹0.00", Colors.BLUE, icon="🧾"),
            "cgst_total": MetricCard("CGST", "₹0.00", Colors.GREEN, icon="🏛️"),
            "sgst_total": MetricCard("SGST", "₹0.00", Colors.TEAL, icon="🏛️"),
            "igst_total": MetricCard("IGST", "₹0.00", Colors.ORANGE, icon="🏛️"),
            "total_tax": MetricCard("Total GST", "₹0.00", Colors.PURPLE, icon="📈"),
        }
        for c in self.cards.values():
            cards.addWidget(c)
        root.addLayout(cards)
        self.note = QLabel("")
        self.note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(self.note)
        self.period.currentIndexChanged.connect(self._period_changed)
        self.start.dateChanged.connect(self.refresh)
        self.end.dateChanged.connect(self.refresh)
        self._period_changed(refresh=False)  # nothing is asked of the server until the panel is on screen

    def showEvent(self, event):
        super().showEvent(event)
        if self._data is None and not self._asked:
            self.refresh()

    def dates(self) -> tuple[date, date]:
        if self.period.currentData() == "custom":
            return self.start.date().toPyDate(), self.end.date().toPyDate()
        return period_dates(self.period.currentData())

    def _period_changed(self, _i=0, refresh=True):
        custom = self.period.currentData() == "custom"
        a, b = period_dates("month") if custom else self.dates()
        for d, v in ((self.start, a), (self.end, b)):
            d.blockSignals(True)
            d.setDate(QDate(v.year, v.month, v.day))
            d.blockSignals(False)
            d.setVisible(custom)
        if refresh:
            self.refresh()

    def refresh(self, *_):
        self._asked = True
        a, b = self.dates()
        load_async(self, lambda: self._svc.get_gst_summary(a.isoformat(), b.isoformat()), self._show)

    def _show(self, data):
        self._data = data
        self.csv_btn.setEnabled(bool(data))
        for key, card in self.cards.items():
            card.set_value(inr(float((data or {}).get(key) or 0)))
        self.note.setText("" if data else "The GST figures could not be loaded.")

    def _save_csv(self):
        a, b = self.dates()
        path, _ = QFileDialog.getSaveFileName(self, "Save GST summary", f"gst-{a}-{b}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel reads the ₹-free text correctly
                f.write(gst.summary_csv(self._data or {}, a.isoformat(), b.isoformat()))
        except OSError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
