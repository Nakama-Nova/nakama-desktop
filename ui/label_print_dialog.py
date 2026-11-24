"""
ui/label_print_dialog.py

Print stickers (QR + bar code + name + price) for the products chosen in Stock: pick a
format (single labels, receipt roll, hang tag, A4 sticker sheets), how many of each, and
where to start on a part-used sheet. Preview first; then save a PDF or print.
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from services.label_layouts import FORMATS, BY_KEY
from services.sales_service import BillPdfError, SalesService
from ui import label_render
from ui.theme import Colors, Theme

LABEL_DIR = SalesService.INVOICE_DIR.parent / "labels"


def expand(items: list[dict], copies: int, per_unit_stock: bool) -> list[dict]:
    """One entry per label to print. Products without a code cannot be labelled and are left out."""
    out = []
    for item in items:
        if not item.get("sku"):
            continue
        units = max(1, int(item.get("current_stock") or 0)) if per_unit_stock else 1
        out += [item] * (units * copies)
    return out


class LabelPrintDialog(QDialog):
    def __init__(self, parent, items: list[dict]):
        super().__init__(parent)
        self._items = [i for i in items if i.get("sku")]
        self._skipped = len(items) - len(self._items)
        self.setWindowTitle("Print labels")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        note = f"{len(self._items)} product(s). Each label has a QR with the Vriksha mark and a bar code of the product code."
        if self._skipped:
            note += f" {self._skipped} without a code left out."
        info = QLabel(note)
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.format = QComboBox()
        for f in FORMATS:
            self.format.addItem(f.title, f.key)
        self.format.setStyleSheet(Theme.input_style())
        self.copies = QSpinBox()
        self.copies.setRange(1, 500)
        self.copies.setStyleSheet(Theme.input_style())
        self.per_stock = QCheckBox("One label for every unit in stock")
        self.start = QSpinBox()
        self.start.setRange(1, 65)
        self.start.setToolTip("Where to start on a sheet that is already part used (1 = the first place)")
        self.start.setStyleSheet(Theme.input_style())
        self.start_label = QLabel("Start at place")
        for text, w in (("Format", self.format), ("Copies of each", self.copies), ("", self.per_stock)):
            form.addRow(text, w)
        form.addRow(self.start_label, self.start)
        root.addLayout(form)

        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(200)
        root.addWidget(self.preview)
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(self.count)

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

        self.format.currentIndexChanged.connect(self._changed)
        self.copies.valueChanged.connect(self._changed)
        self.per_stock.toggled.connect(self._changed)
        self.start.valueChanged.connect(self._changed)
        self._changed()

    def fmt(self):
        return BY_KEY[self.format.currentData()]

    def labels(self) -> list[dict]:
        return expand(self._items, self.copies.value(), self.per_stock.isChecked())

    def _changed(self, *_):
        fmt = self.fmt()
        self.start.setMaximum(fmt.per_page)
        self.start.setVisible(fmt.is_sheet)
        self.start_label.setVisible(fmt.is_sheet)
        if self._items:
            img = label_render.label_image(fmt, self._items[0], dpi=200)
            self.preview.setPixmap(QPixmap.fromImage(img).scaledToHeight(min(220, img.height()), Qt.TransformationMode.SmoothTransformation))
        n = len(self.labels())
        pages = -(-(n + self.start.value() - 1) // fmt.per_page) if fmt.is_sheet else n
        self.count.setText(f"{n} label(s), {pages} {'sheet' if fmt.is_sheet else 'label page'}(s)")
        for b in (self.print_btn, self.pdf_btn):
            b.setEnabled(n > 0)

    def _start(self) -> int:
        return self.start.value() - 1 if self.fmt().is_sheet else 0

    def _pdf(self):
        try:
            LABEL_DIR.mkdir(parents=True, exist_ok=True)
            path = LABEL_DIR / f"labels-{datetime.now():%Y%m%d-%H%M%S}.pdf"
            label_render.save_pdf(str(path), self.fmt(), self.labels(), self._start())
            SalesService.open_pdf(path)
        except (OSError, BillPdfError) as exc:
            QMessageBox.warning(self, "Could not make the PDF", str(exc))

    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec() == QDialog.DialogCode.Accepted:
            label_render.render(printer, self.fmt(), self.labels(), self._start())
