"""
ui/inventory_window.py

Stock screen — auto-loads, search filter, hides UUIDs,
shows stock status indicator (OK / Low).
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QDialog,
    QFormLayout,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui.theme import Theme, Colors, Fonts
from ui.errors import handle_permissions
from services.inventory_service import InventoryService
from services.session import Session
from services.enums import UserRole


class ItemDialog(QDialog):
    """Add/Edit item form dialog."""

    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.setWindowTitle("Add Item" if not item else "Edit Item")
        self.setFixedWidth(400)
        self.setStyleSheet(f"background-color: {Colors.BG};")

        layout = QFormLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Teak Wood Sofa")
        self.name_edit.setStyleSheet(Theme.input_style())

        self.sku_edit = QLineEdit()
        self.sku_edit.setPlaceholderText("e.g. WD-001")
        self.sku_edit.setStyleSheet(Theme.input_style())

        self.price_edit = QDoubleSpinBox()
        self.price_edit.setRange(0, 1000000)
        self.price_edit.setPrefix("₹")
        self.price_edit.setStyleSheet(Theme.input_style())

        self.stock_edit = QDoubleSpinBox()
        self.stock_edit.setRange(0, 10000)
        self.stock_edit.setStyleSheet(Theme.input_style())

        if item:
            self.name_edit.setText(item.get("name") or "")
            self.sku_edit.setText(item.get("sku") or "")
            self.price_edit.setValue(float(item.get("selling_price") or 0))
            self.stock_edit.setValue(float(item.get("current_stock") or 0))

        layout.addRow(QLabel("Name *", styleSheet=Theme.label()), self.name_edit)
        layout.addRow(QLabel("SKU *", styleSheet=Theme.label()), self.sku_edit)
        layout.addRow(
            QLabel("Selling Price", styleSheet=Theme.label()), self.price_edit
        )
        layout.addRow(
            QLabel("Initial Stock", styleSheet=Theme.label()), self.stock_edit
        )

        btns = QHBoxLayout()
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet(Theme.btn_primary())
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(Theme.btn_secondary())
        cancel_btn.clicked.connect(self.reject)

        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addRow(btns)

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "sku": self.sku_edit.text().strip(),
            "selling_price": self.price_edit.value(),
            "current_stock": int(self.stock_edit.value()),
        }


class InventoryWindow(QWidget):

    def __init__(self):
        super().__init__()
        self._inventory_service = InventoryService()
        self._all_items: list[dict] = []

        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("📦  Stock")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()

        refresh_btn = QPushButton("🔄  Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(Theme.btn_secondary())
        refresh_btn.clicked.connect(self.refresh_data)
        header_row.addWidget(refresh_btn)

        self.add_btn = QPushButton("➕  Add Item")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add_item)
        header_row.addWidget(self.add_btn)

        # RBAC: Hide add button for unauthorized
        self.can_edit = Session.is_authorized(
            [UserRole.OWNER, UserRole.MANAGER, UserRole.ACHARI]
        )
        self.add_btn.setVisible(self.can_edit)

        layout.addLayout(header_row)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search items by name...")
        self.search_input.setStyleSheet(Theme.input_style())
        self.search_input.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_input)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5 if self.can_edit else 4)
        cols = ["Item Name", "Price (₹)", "In Stock", "Status"]
        if self.can_edit:
            cols.append("Actions")
        self.table.setHorizontalHeaderLabels(cols)

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        if self.can_edit:
            self.table.horizontalHeader().setSectionResizeMode(
                4, QHeaderView.ResizeMode.Fixed
            )
            self.table.setColumnWidth(4, 160)

        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())

        layout.addWidget(self.table)

    @handle_permissions
    def refresh_data(self):
        """Auto-called on page switch or manual refresh."""
        items = self._inventory_service.get_items()
        if items is None:
            QMessageBox.warning(
                self, "Connection Issue", "Could not load stock from server."
            )
            return

        self._all_items = items
        self._populate_table(items)

    def _populate_table(self, items: list[dict]):
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            name_item = QTableWidgetItem(item["name"])
            price_item = QTableWidgetItem(
                f"₹{float(item.get('selling_price', 0)):,.2f}"
            )
            stock_val = int(item.get("current_stock", 0))
            min_stock = int(item.get("min_stock", 5))
            stock_item = QTableWidgetItem(str(stock_val))

            # Status indicator
            if stock_val <= min_stock:
                status_text = "⚠️ Low"
                status_color = QColor(Colors.LOW_STOCK_BG)
            else:
                status_text = "✅ OK"
                status_color = QColor(Colors.SUCCESS_BG)

            status_item = QTableWidgetItem(status_text)
            status_item.setBackground(status_color)

            # Actions
            if self.can_edit:
                actions = QWidget()
                actions_layout = QHBoxLayout(actions)
                actions_layout.setContentsMargins(4, 4, 4, 4)
                actions_layout.setSpacing(6)

                edit_btn = QPushButton("✏️ Edit")
                edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                edit_btn.setFixedHeight(28)
                edit_btn.setStyleSheet(Theme.btn_table_action())
                edit_btn.clicked.connect(lambda _, it=item: self._edit_item(it))

                del_btn = QPushButton("🗑️")
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_btn.setFixedSize(36, 28)
                del_btn.setStyleSheet(f"""
                    QPushButton {{
                        color: {Colors.RED};
                        border: 1px solid {Colors.BORDER};
                        border-radius: 4px;
                        background: white;
                    }}
                    QPushButton:hover {{ background: {Colors.ERROR_BG}; }}
                """)
                del_btn.clicked.connect(lambda _, it=item: self._delete_item(it))

                actions_layout.addWidget(edit_btn)
                actions_layout.addWidget(del_btn)
                self.table.setCellWidget(row, 4, actions)

            # Center-align numeric columns
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setRowHeight(row, 42)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, price_item)
            self.table.setItem(row, 2, stock_item)
            self.table.setItem(row, 3, status_item)

    @handle_permissions
    def _add_item(self):
        dialog = ItemDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"] or not data["sku"]:
                QMessageBox.warning(self, "Required", "Name and SKU are required.")
                return
            if self._inventory_service.create(**data):
                QMessageBox.information(self, "Success", "Item added.")
                self.refresh_data()

    @handle_permissions
    def _edit_item(self, item: dict):
        dialog = ItemDialog(self, item)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if self._inventory_service.update(str(item["id"]), **data):
                QMessageBox.information(self, "Success", "Item updated.")
                self.refresh_data()

    @handle_permissions
    def _delete_item(self, item: dict):
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete {item['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if self._inventory_service.delete(str(item["id"])):
                self.refresh_data()

    def _filter_table(self, text: str):
        """Live filter as user types in search box."""
        query = text.strip().lower()
        if not query:
            self._populate_table(self._all_items)
            return

        filtered = [item for item in self._all_items if query in item["name"].lower()]
        self._populate_table(filtered)
