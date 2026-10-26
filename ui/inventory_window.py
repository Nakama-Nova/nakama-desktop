"""
ui/inventory_window.py

Stock screen: every product with its stock level, a search box, and (for owner
and manager) the full product form, stock changes with a reason, the stock
history, photos for the website, and categories and brands.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
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
from services.inventory_service import InventoryService
from services.session import Session
from services.stock_service import StockService
from ui.errors import handle_permissions
from ui.item_form import ItemDialog
from ui.stock_dialogs import (
    CATEGORY_FIELDS,
    AdjustStockDialog,
    ManageRowsDialog,
    MovementsDialog,
    PhotosDialog,
)
from ui.theme import Colors, Fonts, Theme


class InventoryWindow(QWidget):
    COL_NAME, COL_SKU, COL_PRICE, COL_STOCK, COL_STATUS, COL_ACTIONS = range(6)

    def __init__(self):
        super().__init__()
        self._inventory_service = InventoryService()
        self._stock = StockService()
        self._all_items: list[dict] = []
        # Owner and manager manage stock; everyone else reads it.
        self.can_edit = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])

        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header = QLabel("📦  Stock")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()

        def head_button(text, style, slot, visible=True):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(style)
            b.clicked.connect(slot)
            b.setVisible(visible)
            header_row.addWidget(b)
            return b

        self.categories_btn = head_button(
            "🏷️  Categories", Theme.btn_secondary(), self._categories, self.can_edit
        )
        self.brands_btn = head_button(
            "🏭  Brands", Theme.btn_secondary(), self._brands, self.can_edit
        )
        head_button("🔄  Refresh", Theme.btn_secondary(), self.refresh_data)
        self.add_btn = head_button(
            "➕  Add product", Theme.btn_primary(), self._add_item, self.can_edit
        )
        layout.addLayout(header_row)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search by name or code...")
        self.search_input.setStyleSheet(Theme.input_style())
        self.search_input.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_input)

        self.table = QTableWidget()
        cols = ["Product", "Code", "Price (₹)", "In stock", "Status"]
        if self.can_edit:
            cols.append("")
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(90)
        if self.can_edit:
            self.table.horizontalHeader().setSectionResizeMode(
                self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed
            )
            self.table.setColumnWidth(self.COL_ACTIONS, 330)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

    # ------------------------------------------------------------------ data
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
        self._filter_table(self.search_input.text())

    def _populate_table(self, items: list[dict]):
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            stock_val = int(item.get("current_stock") or 0)
            min_stock = int(item.get("min_stock") or 0)
            low = stock_val <= min_stock

            values = [
                item["name"],
                item.get("sku") or "",
                f"₹{float(item.get('selling_price') or 0):,.2f}",
                str(stock_val),
                "⚠️ Low" if low else "✅ OK",
            ]
            for col, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if col == self.COL_PRICE:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                elif col in (self.COL_STOCK, self.COL_STATUS):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == self.COL_STATUS:
                    cell.setBackground(
                        QColor(Colors.LOW_STOCK_BG if low else Colors.SUCCESS_BG)
                    )
                self.table.setItem(row, col, cell)

            if self.can_edit:
                self.table.setCellWidget(row, self.COL_ACTIONS, self._actions(item))
            self.table.setRowHeight(row, 52)

    def _actions(self, item: dict) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        for text, slot in [
            ("✏️ Edit", self._edit_item),
            ("± Stock", self._adjust),
            ("🕘", self._history),
            ("🖼️", self._photos),
            ("🗑️", self._delete_item),
        ]:
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(30)
            b.setStyleSheet(Theme.btn_table_action())
            if text in ("🕘", "🖼️", "🗑️"):
                b.setFixedWidth(40)
            b.setToolTip(
                {"🕘": "Stock history", "🖼️": "Photos and model", "🗑️": "Delete"}.get(
                    text, ""
                )
            )
            b.clicked.connect(lambda _=False, it=item, s=slot: s(it))
            h.addWidget(b)
        return box

    # --------------------------------------------------------------- actions
    def _lookups(self):
        return self._stock.rows("categories"), self._stock.rows("brands")

    @handle_permissions
    def _add_item(self, _checked=False):
        cats, brands = self._lookups()
        dialog = ItemDialog(self, None, cats, brands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        if not data["name"] or not data["sku"]:
            QMessageBox.warning(self, "Required", "Name and code (SKU) are required.")
            return
        if self._inventory_service.create(**data):
            self.refresh_data()

    @handle_permissions
    def _edit_item(self, item: dict):
        cats, brands = self._lookups()
        dialog = ItemDialog(self, item, cats, brands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        if not data["name"] or not data["sku"]:
            QMessageBox.warning(self, "Required", "Name and code (SKU) are required.")
            return
        if self._inventory_service.update(str(item["id"]), **data):
            self.refresh_data()

    @handle_permissions
    def _adjust(self, item: dict):
        dialog = AdjustStockDialog(
            self, item["name"], item.get("unit") or "pcs", item.get("current_stock", 0)
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._stock.adjust_item(str(item["id"]), int(dialog.change()), dialog.notes())
            self.refresh_data()

    @handle_permissions
    def _history(self, item: dict):
        rows = self._stock.movements(item_id=str(item["id"]))
        MovementsDialog(self, f"Stock history: {item['name']}", rows).exec()

    @handle_permissions
    def _photos(self, item: dict):
        PhotosDialog(self, self._stock, item).exec()

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

    @handle_permissions
    def _categories(self, _checked=False):
        ManageRowsDialog(
            self, self._stock, "categories", "Categories", CATEGORY_FIELDS
        ).exec()

    @handle_permissions
    def _brands(self, _checked=False):
        ManageRowsDialog(self, self._stock, "brands", "Brands", CATEGORY_FIELDS).exec()

    def _filter_table(self, text: str):
        """Live filter as the user types in the search box."""
        query = text.strip().lower()
        if not query:
            self._populate_table(self._all_items)
            return
        self._populate_table(
            [
                i
                for i in self._all_items
                if query in i["name"].lower() or query in (i.get("sku") or "").lower()
            ]
        )
