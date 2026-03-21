"""
ui/inventory_window.py

Stock screen — auto-loads, search filter, hides UUIDs,
shows stock status indicator (OK / Low).
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui.theme import Theme, Colors, Fonts
from services.inventory_service import InventoryService


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

        layout.addLayout(header_row)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search items by name...")
        self.search_input.setStyleSheet(Theme.input_style())
        self.search_input.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_input)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Item Name", "Price (₹)", "In Stock", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())

        layout.addWidget(self.table)

    def refresh_data(self):
        """Auto-called on page switch or manual refresh."""
        items = self._inventory_service.get_items()
        if items is None:
            QMessageBox.warning(self, "Connection Issue", "Could not load stock from server.")
            return

        self._all_items = items
        self._populate_table(items)

    def _populate_table(self, items: list[dict]):
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            name_item = QTableWidgetItem(item["name"])
            price_item = QTableWidgetItem(f"₹{float(item.get('selling_price', 0)):,.2f}")
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

            # Center-align numeric columns
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setRowHeight(row, 42)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, price_item)
            self.table.setItem(row, 2, stock_item)
            self.table.setItem(row, 3, status_item)

    def _filter_table(self, text: str):
        """Live filter as user types in search box."""
        query = text.strip().lower()
        if not query:
            self._populate_table(self._all_items)
            return

        filtered = [
            item for item in self._all_items
            if query in item["name"].lower()
        ]
        self._populate_table(filtered)