"""
ui/receipt_dialog.py

Print a bill as a receipt: choose the paper (80 mm or 58 mm thermal roll, A5, A4), see it, then
save a PDF or print. The choice is remembered. Works from the bill's own figures, so it also
prints a provisional receipt for a bill saved while offline.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout

from services.letters_service import LettersService
from services.sales_service import BillPdfError, SalesService
from ui import receipt_render as rr
from ui.theme import Colors, Theme

RECEIPT_DIR = SalesService.INVOICE_DIR.parent / "receipts"


def shop_details() -> dict:
    """The letterhead the shop already keeps (name, address, phone, GSTIN); the name alone when it cannot be had."""
    try:
        profile = LettersService().profile() or {}
    except Exception:  # offline, or not allowed to read it: print with the name only
        profile = {}
    return {"name": profile.get("name") or "Vriksha Studios", **{k: profile.get(k) for k in ("tagline", "address", "phone", "gstin")}}


class ReceiptDialog(QDialog):
    def __init__(self, parent, receipt: dict):
        super().__init__(parent)
        self._receipt = receipt
        self.setWindowTitle("Pay slip" if receipt.get("payslip") else "Receipt" + (" (provisional)" if receipt.get("provisional") else ""))
        self.setMinimumSize(520, 560)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)
        self.paper = QComboBox()
        for key, title, *_ in rr.FORMATS:
            self.paper.addItem(title, key)
        self.paper.setStyleSheet(Theme.input_style())
        saved = QSettings("VrikshaStudios", "Nakama").value("receipt/paper", "thermal_80")
        self.paper.setCurrentIndex(max(0, self.paper.findData(saved)))
        root.addWidget(QLabel("Paper"))
        root.addWidget(self.paper)
        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidget(self.preview)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.reject)
        self.print_btn = QPushButton("🖨  Print…")
        self.print_btn.setStyleSheet(Theme.btn_secondary())
        self.print_btn.clicked.connect(self._print)
        self.pdf_btn = QPushButton("📄  Save PDF and open")
        self.pdf_btn.setStyleSheet(Theme.btn_primary())
        self.pdf_btn.clicked.connect(self._pdf)
        for b in (close, self.print_btn, self.pdf_btn):
            row.addWidget(b)
        root.addLayout(row)
        self.paper.currentIndexChanged.connect(self._changed)
        self._changed()

    def fmt(self):
        return rr.BY_KEY[self.paper.currentData()]

    def _changed(self, *_):
        QSettings("VrikshaStudios", "Nakama").setValue("receipt/paper", self.paper.currentData())
        self.preview.setPixmap(QPixmap.fromImage(rr.receipt_image(self.fmt(), self._receipt, dpi=110)))

    def _pdf(self):
        try:
            RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
            number = (self._receipt.get("number") or "receipt").replace("/", "-")
            path = RECEIPT_DIR / f"{number}-{datetime.now():%H%M%S}.pdf"
            rr.save_pdf(str(path), self.fmt(), self._receipt)
            SalesService.open_pdf(Path(path))
        except (OSError, BillPdfError) as exc:
            QMessageBox.warning(self, "Could not make the PDF", str(exc))

    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec() == QDialog.DialogCode.Accepted:
            rr.render(printer, self.fmt(), self._receipt)
