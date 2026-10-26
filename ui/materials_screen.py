"""
ui/materials_screen.py

Raw materials (wood, ply, hardware): what is in stock, change it with a reason,
see the stock history, and add, edit or delete a material. Owner and manager.
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.enums import UserRole
from services.session import Session
from services.stock_service import StockService
from ui.errors import handle_permissions
from ui.stock_dialogs import AdjustStockDialog, MovementsDialog
from ui.theme import Colors, Fonts, Theme


class MaterialDialog(QDialog):
    def __init__(self, parent, material: dict | None = None):
        super().__init__(parent)
        self._editing = material is not None
        self.setWindowTitle("Edit material" if material else "Add material")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        m = material or {}
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        self.name = QLineEdit(m.get("name") or "")
        self.name.setPlaceholderText("e.g. Teak plank")
        self.unit = QLineEdit(m.get("unit") or "")
        self.unit.setPlaceholderText("e.g. cft, kg, sheet, pcs")
        self.price = QDoubleSpinBox()
        self.price.setRange(0, 10_000_000)
        self.price.setPrefix("₹")
        self.price.setValue(float(m.get("current_price") or 0))
        self.stock = QDoubleSpinBox()
        self.stock.setRange(0, 10_000_000)
        self.stock.setDecimals(2)
        self.stock.setValue(float(m.get("stock") or 0))
        for w in (self.name, self.unit, self.price, self.stock):
            w.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Name *", styleSheet=Theme.label()), self.name)
        form.addRow(QLabel("Unit *", styleSheet=Theme.label()), self.unit)
        form.addRow(QLabel("Price per unit", styleSheet=Theme.label()), self.price)
        if self._editing:
            self.stock.setEnabled(False)
            self.stock.setToolTip("Use ± Stock to change it, so it is recorded")
            form.addRow(QLabel("In stock", styleSheet=Theme.label()), self.stock)
        else:
            form.addRow(QLabel("Opening stock", styleSheet=Theme.label()), self.stock)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Save")
        ok.setStyleSheet(Theme.btn_primary())
        ok.clicked.connect(self._check)
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow(row)

    def _check(self):
        if not self.name.text().strip() or not self.unit.text().strip():
            QMessageBox.warning(self, "Required", "Name and unit are required.")
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "name": self.name.text().strip(),
            "unit": self.unit.text().strip(),
            "current_price": self.price.value(),
        }
        if not self._editing:
            data["stock"] = self.stock.value()
        return data


class MaterialsScreen(QWidget):
    COL_NAME, COL_UNIT, COL_PRICE, COL_STOCK, COL_ACTIONS = range(5)

    def __init__(self):
        super().__init__()
        self._svc = StockService()
        self._rows: list[dict] = []
        self._is_owner = Session.is_authorized([UserRole.OWNER])
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("🌳  Materials")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        self.add_btn = QPushButton("➕  Add material")
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add)
        head.addWidget(self.add_btn)
        layout.addLayout(head)

        hint = QLabel(
            "Raw stock goes up when you confirm a purchase, and down when production uses it."
            " Use ± Stock for a count correction or a write-off."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Material", "Unit", "Price / unit (₹)", "In stock", ""])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(self.COL_ACTIONS, 270)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

    @handle_permissions
    def refresh_data(self):
        self._rows = self._svc.materials()
        self.table.setRowCount(len(self._rows))
        for r, m in enumerate(self._rows):
            for c, text in enumerate(
                [
                    m["name"],
                    m.get("unit") or "",
                    f"{float(m.get('current_price') or 0):,.2f}",
                    f"{float(m.get('stock') or 0):g}",
                ]
            ):
                cell = QTableWidgetItem(text)
                if c >= self.COL_PRICE:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, cell)
            self.table.setCellWidget(r, self.COL_ACTIONS, self._actions(m))
            self.table.setRowHeight(r, 52)

    def _actions(self, m: dict) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        buttons = [("± Stock", self._adjust), ("🕘", self._history), ("✏️ Edit", self._edit)]
        if self._is_owner:
            buttons.append(("🗑️", self._delete))
        for text, slot in buttons:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setStyleSheet(Theme.btn_table_action())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if text in ("🕘", "🗑️"):
                b.setFixedWidth(40)
            b.clicked.connect(lambda _=False, mm=m, s=slot: s(mm))
            h.addWidget(b)
        return box

    @handle_permissions
    def _add(self, _checked=False):
        d = MaterialDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.create_material(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _edit(self, m: dict):
        d = MaterialDialog(self, m)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.update_material(m["id"], d.get_data())
            self.refresh_data()

    @handle_permissions
    def _adjust(self, m: dict):
        d = AdjustStockDialog(self, m["name"], m.get("unit") or "", f"{float(m.get('stock') or 0):g}", 2)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.adjust_material(m["id"], d.change(), d.notes())
            self.refresh_data()

    @handle_permissions
    def _history(self, m: dict):
        MovementsDialog(
            self, f"Stock history: {m['name']}", self._svc.movements(raw_material_id=m["id"])
        ).exec()

    @handle_permissions
    def _delete(self, m: dict):
        ask = QMessageBox.question(
            self, "Confirm Delete", f"Delete {m['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes and self._svc.delete_material(m["id"]):
            self.refresh_data()
