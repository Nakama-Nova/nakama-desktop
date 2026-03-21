"""
ui/sales_history_screen.py

Bill History screen — no UUID customer IDs visible, styled actions.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QLabel,
    QDateEdit,
)
from PyQt6.QtCore import Qt, QDate

from ui.theme import Theme, Fonts
from services.sales_service import SalesService
from services.event_bus import EventBus, SALE_CREATED


class SalesHistoryScreen(QWidget):

    def __init__(self):
        super().__init__()
        self._sales_service = SalesService()
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

        EventBus.subscribe(SALE_CREATED, self.refresh_data)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("📜  Bill History")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()

        refresh_btn = QPushButton("🔄  Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(Theme.btn_secondary())
        refresh_btn.clicked.connect(self.refresh_data)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        date_lbl = QLabel("Filter by Date:")
        date_lbl.setStyleSheet(Theme.label())
        filter_row.addWidget(date_lbl)

        self.date_filter = QDateEdit()
        self.date_filter.setCalendarPopup(True)
        self.date_filter.setDate(QDate.currentDate())
        self.date_filter.setStyleSheet(Theme.input_style())
        self.date_filter.setFixedWidth(160)
        filter_row.addWidget(self.date_filter)

        apply_btn = QPushButton("🔍  Filter")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(Theme.btn_secondary())
        apply_btn.clicked.connect(self._apply_filter)
        filter_row.addWidget(apply_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(Theme.btn_secondary())
        clear_btn.clicked.connect(self.refresh_data)
        filter_row.addWidget(clear_btn)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Table — NO UUID Customer ID column
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Bill No.", "Amount (₹)", "Date", "Actions"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 180)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Theme.table_style())

        layout.addWidget(self.table)

    def refresh_data(self):
        """EventBus-safe: no args. Loads all sales."""
        sales = self._sales_service.get_sales()
        self._populate_table(sales or [])

    def _load_sales(self, customer_id=None, date=None):
        """Load sales with optional filters."""
        sales = self._sales_service.get_sales(customer_id=customer_id, date=date)
        self._populate_table(sales or [])

    def _populate_table(self, sales: list[dict]):
        self.table.setRowCount(0)
        for row, sale in enumerate(sales):
            self.table.insertRow(row)
            self.table.setRowHeight(row, 42)

            bill_no = sale.get("invoice_number", "N/A")
            amount = float(sale.get("total_amount", 0))
            created = sale.get("created_at", "")
            # Format date nicely
            if created and "T" in str(created):
                created = str(created).split("T")[0]

            self.table.setItem(row, 0, QTableWidgetItem(bill_no))

            amount_item = QTableWidgetItem(f"₹{amount:,.2f}")
            amount_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 1, amount_item)

            self.table.setItem(row, 2, QTableWidgetItem(created))

            # Action buttons — compact style for table cells
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)

            view_btn = QPushButton("👁️ View")
            view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            view_btn.setFixedHeight(28)
            view_btn.setStyleSheet(Theme.btn_table_action())
            view_btn.clicked.connect(lambda _, s=sale: self._view_details(s))

            print_btn = QPushButton("🖨️ Print")
            print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            print_btn.setFixedHeight(28)
            print_btn.setStyleSheet(Theme.btn_table_action())
            print_btn.clicked.connect(lambda _, s=sale: self._reprint_invoice(s))

            actions_layout.addWidget(view_btn)
            actions_layout.addWidget(print_btn)
            self.table.setCellWidget(row, 3, actions)

    def _apply_filter(self):
        date_str = self.date_filter.date().toString("yyyy-MM-dd")
        self._load_sales(date=date_str)

    def _view_details(self, sale):
        sale_id = str(sale["id"])
        items = self._sales_service.get_sale_items(sale_id)
        if not items:
            QMessageBox.information(self, "No Items", "No items found for this bill.")
            return

        msg = f"Bill: {sale.get('invoice_number', 'N/A')}\n\n"
        for item in items:
            item_name = item.get("item_name", "Item")
            qty = item.get("quantity", 0)
            price = float(item.get("price_at_sale", 0))
            total = float(item.get("total_price", 0))
            msg += f"  • {item_name}:  {qty} × ₹{price:,.2f} = ₹{total:,.2f}\n"

        msg += f"\nTotal: ₹{float(sale.get('total_amount', 0)):,.2f}"
        QMessageBox.information(self, "📋 Bill Details", msg)

    def _reprint_invoice(self, sale):
        inv_num = sale.get("invoice_number")
        if not inv_num:
            return

        pdf_path = self._sales_service.fetch_and_save_pdf(inv_num)
        if pdf_path:
            self._sales_service.open_pdf(pdf_path)
        else:
            QMessageBox.critical(self, "Error", "Could not download the bill PDF.")
