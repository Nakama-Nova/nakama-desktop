"""
ui/stock_dialogs.py

Small dialogs used by the stock screens: change stock with a reason, the stock
ledger, a generic "manage a short list" dialog (categories, brands, suppliers)
and product photos.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.theme import Colors, Theme

MOVEMENT_WORDS = {
    "adjustment": "Manual change",
    "raw_in": "Received",
    "raw_consumed": "Used in production",
    "finished_in": "Made",
    "finished_out": "Sold",
}


def _button(text: str, style: str) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(style)
    return b


class AdjustStockDialog(QDialog):
    """Receive or remove stock. The reason is required: it goes in the ledger."""

    def __init__(self, parent, name: str, unit: str, current, decimals: int = 0):
        super().__init__(parent)
        self.setWindowTitle(f"Adjust stock: {name}")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)

        form.addRow(QLabel(f"In stock now: {current} {unit}", styleSheet=Theme.subheading()))
        row = QHBoxLayout()
        self.add_radio = QRadioButton("Receive (add)")
        self.add_radio.setChecked(True)
        self.remove_radio = QRadioButton("Remove")
        row.addWidget(self.add_radio)
        row.addWidget(self.remove_radio)
        form.addRow(row)

        self.qty = QDoubleSpinBox()
        self.qty.setDecimals(decimals)
        self.qty.setRange(0, 1_000_000)
        self.qty.setSuffix(f" {unit}")
        self.qty.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("How much", styleSheet=Theme.label()), self.qty)

        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Why? e.g. opening count, damaged, found in godown")
        self.reason.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Reason *", styleSheet=Theme.label()), self.reason)

        row = QHBoxLayout()
        row.addStretch()
        cancel = _button("Cancel", Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        ok = _button("Save", Theme.btn_primary())
        ok.clicked.connect(self._check)
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow(row)

    def _check(self):
        if self.qty.value() <= 0:
            QMessageBox.warning(self, "Quantity", "Enter how much to add or remove.")
        elif not self.reason.text().strip():
            QMessageBox.warning(self, "Reason", "Please say why, so the history makes sense.")
        else:
            self.accept()

    def change(self) -> float:
        v = self.qty.value()
        return v if self.add_radio.isChecked() else -v

    def notes(self) -> str:
        return self.reason.text().strip()


class MovementsDialog(QDialog):
    """The stock ledger for one product or material, newest first."""

    def __init__(self, parent, title: str, rows: list):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        lay = QVBoxLayout(self)
        self.table = QTableWidget(len(rows), 5)
        self.table.setHorizontalHeaderLabels(["When", "What happened", "Change", "By", "Note"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(Theme.table_style())
        for i, r in enumerate(rows):
            qty = float(r.get("quantity") or 0)
            values = [
                str(r.get("created_at", ""))[:16].replace("T", " "),
                MOVEMENT_WORDS.get(r.get("movement_type"), r.get("movement_type", "")),
                f"{qty:+g}",
                r.get("by") or "",
                r.get("notes") or "",
            ]
            for c, v in enumerate(values):
                cell = QTableWidgetItem(v)
                if c == 2:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell.setForeground(
                        Qt.GlobalColor.darkGreen if qty > 0 else Qt.GlobalColor.darkRed
                    )
                self.table.setItem(i, c, cell)
        lay.addWidget(self.table)
        if not rows:
            lay.addWidget(QLabel("Nothing recorded yet.", styleSheet=Theme.label()))
        close = _button("Close", Theme.btn_secondary())
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


class _RowDialog(QDialog):
    """Add or rename one row: a handful of text fields."""

    def __init__(self, parent, title: str, fields: list, row: dict | None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        self.edits: dict[str, QLineEdit] = {}
        for key, label in fields:
            e = QLineEdit((row or {}).get(key) or "")
            e.setStyleSheet(Theme.input_style())
            self.edits[key] = e
            form.addRow(QLabel(label, styleSheet=Theme.label()), e)
        row_l = QHBoxLayout()
        row_l.addStretch()
        cancel = _button("Cancel", Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        ok = _button("Save", Theme.btn_primary())
        ok.clicked.connect(self.accept)
        row_l.addWidget(cancel)
        row_l.addWidget(ok)
        form.addRow(row_l)

    def data(self) -> dict:
        return {k: (e.text().strip() or None) for k, e in self.edits.items()}


class ManageRowsDialog(QDialog):
    """List with Add / Edit / Delete for categories, brands or suppliers."""

    def __init__(self, parent, service, kind: str, title: str, fields: list):
        super().__init__(parent)
        self._svc, self._kind, self._fields = service, kind, fields
        self._rows: list = []
        self.setWindowTitle(title)
        self.resize(640, 420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(title, styleSheet=Theme.subheading()))
        top.addStretch()
        add = _button("➕ Add", Theme.btn_primary())
        add.clicked.connect(self._add)
        top.addWidget(add)
        lay.addLayout(top)
        self.table = QTableWidget(0, len(fields))
        self.table.setHorizontalHeaderLabels([f[1] for f in fields])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        lay.addWidget(self.table)
        row = QHBoxLayout()
        edit = _button("✏️ Edit", Theme.btn_secondary())
        edit.clicked.connect(self._edit)
        delete = _button("🗑️ Delete", Theme.btn_secondary())
        delete.clicked.connect(self._delete)
        close = _button("Close", Theme.btn_secondary())
        close.clicked.connect(self.accept)
        row.addWidget(edit)
        row.addWidget(delete)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    def reload(self):
        self._rows = self._svc.rows(self._kind)
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            for c, (key, _) in enumerate(self._fields):
                self.table.setItem(i, c, QTableWidgetItem(str(r.get(key) or "")))

    def _selected(self):
        i = self.table.currentRow()
        return self._rows[i] if 0 <= i < len(self._rows) else None

    def _add(self):
        d = _RowDialog(self, "Add", self._fields, None)
        if d.exec() == QDialog.DialogCode.Accepted and d.data().get("name"):
            self._svc.save_row(self._kind, d.data())
            self.reload()

    def _edit(self):
        row = self._selected()
        if not row:
            return
        d = _RowDialog(self, "Edit", self._fields, row)
        if d.exec() == QDialog.DialogCode.Accepted and d.data().get("name"):
            self._svc.save_row(self._kind, d.data(), row["id"])
            self.reload()

    def _delete(self):
        row = self._selected()
        if not row:
            return
        ask = QMessageBox.question(
            self, "Delete", f"Delete {row['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes:
            self._svc.delete_row(self._kind, row["id"])
            self.reload()


CATEGORY_FIELDS = [("name", "Name"), ("description", "Note")]
SUPPLIER_FIELDS = [
    ("name", "Name"),
    ("contact_person", "Contact person"),
    ("phone", "Phone"),
    ("address", "Address"),
    ("gstin", "GSTIN"),
]


class PhotosDialog(QDialog):
    """A product's photos and 3D model: what the website shows."""

    def __init__(self, parent, service, item: dict):
        super().__init__(parent)
        self._svc, self._item = service, item
        self._rows: list = []
        self.setWindowTitle(f"Photos: {item['name']}")
        self.resize(560, 380)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "JPG, PNG or WebP photos up to 10 MB, or one finished .glb model up to 25 MB. "
                "Photos here are public once the product is shown on the website.",
                wordWrap=True,
                styleSheet=f"color: {Colors.TEXT_SECONDARY};",
            )
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Kind", "Size", "Visible on website"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        lay.addWidget(self.table)
        row = QHBoxLayout()
        add = _button("➕ Add files", Theme.btn_primary())
        add.clicked.connect(self._add)
        delete = _button("🗑️ Delete selected", Theme.btn_secondary())
        delete.clicked.connect(self._delete)
        close = _button("Close", Theme.btn_secondary())
        close.clicked.connect(self.accept)
        row.addWidget(add)
        row.addWidget(delete)
        row.addStretch()
        row.addWidget(close)
        lay.addLayout(row)
        self.reload()

    def reload(self):
        self._rows = self._svc.assets(self._item["id"])
        self.table.setRowCount(len(self._rows))
        for i, a in enumerate(self._rows):
            kb = (a.get("bytes") or 0) / 1024
            vals = [
                "3D model" if a.get("kind") == "glb" else "Photo",
                f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB",
                "Yes" if a.get("visibility", "public") == "public" else "No (staff only)",
            ]
            for c, v in enumerate(vals):
                self.table.setItem(i, c, QTableWidgetItem(v))

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose photos or a model", "",
            "Photos and models (*.jpg *.jpeg *.png *.webp *.glb)",
        )
        for path in paths:
            self._svc.upload_asset(self._item["id"], path)
        if paths:
            self.reload()

    def _delete(self):
        i = self.table.currentRow()
        if 0 <= i < len(self._rows):
            self._svc.delete_asset(self._item["id"], self._rows[i]["id"])
            self.reload()
