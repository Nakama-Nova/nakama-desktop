"""
ui/reports_screen.py

Reports screen — hides UUID item IDs, user-friendly column names.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui.theme import Theme, Colors, Fonts
from ui.components.metric_card import MetricCard
from services.report_service import ReportService


class ReportsScreen(QWidget):

    def __init__(self):
        super().__init__()
        self._report_service = ReportService()
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # Header
        header_row = QHBoxLayout()
        header = QLabel("📊  Reports")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()

        refresh_btn = QPushButton("🔄  Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(Theme.btn_secondary())
        refresh_btn.clicked.connect(self.refresh_data)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Metric cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(14)

        self.card_today_orders = MetricCard(
            "Today's Bills", "0", Colors.GREEN, icon="🧾"
        )
        self.card_today_revenue = MetricCard(
            "Today's Revenue", "₹0.00", Colors.BLUE, icon="💰"
        )
        self.card_all_orders = MetricCard(
            "Total Bills", "0", Colors.TEAL, icon="📜"
        )
        self.card_total_revenue = MetricCard(
            "Total Revenue", "₹0.00", Colors.ORANGE, icon="📈"
        )
        self.card_total_tax = MetricCard(
            "Total Tax", "₹0.00", Colors.PURPLE, icon="🏛️"
        )
        self.card_low_stock = MetricCard(
            "Low Stock Items", "0", Colors.RED, icon="⚠️"
        )

        cards_grid.addWidget(self.card_today_orders, 0, 0)
        cards_grid.addWidget(self.card_today_revenue, 0, 1)
        cards_grid.addWidget(self.card_all_orders, 0, 2)
        cards_grid.addWidget(self.card_total_revenue, 1, 0)
        cards_grid.addWidget(self.card_total_tax, 1, 1)
        cards_grid.addWidget(self.card_low_stock, 1, 2)

        layout.addLayout(cards_grid)

        # Low stock alerts
        alert_header = QLabel("⚠️  Low Stock Alerts")
        alert_header.setStyleSheet(Theme.subheading())
        layout.addWidget(alert_header)

        # Table — NO UUID Item ID, friendly column names
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Item Name", "Code", "In Stock", "Reorder At"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Theme.table_style())

        layout.addWidget(self.table)

    def refresh_data(self):
        # Dashboard summary (today's data)
        dash = self._report_service.get_dashboard_summary()
        if dash:
            self.card_today_orders.set_value(dash.get("today_sales_count", 0))
            self.card_today_revenue.set_value(
                f"₹{float(dash.get('today_revenue', 0)):,.2f}"
            )
            self.card_low_stock.set_value(dash.get("low_stock_count", 0))

        # Sales report (all-time)
        sales = self._report_service.get_sales_report()
        if sales:
            self.card_all_orders.set_value(sales.get("total_orders", 0))
            self.card_total_revenue.set_value(
                f"₹{float(sales.get('total_revenue', 0)):,.2f}"
            )
            self.card_total_tax.set_value(
                f"₹{float(sales.get('total_tax', 0)):,.2f}"
            )

        # Low stock items
        low_stock = self._report_service.get_low_stock_items()
        self.table.setRowCount(0)
        for row, item in enumerate(low_stock):
            self.table.insertRow(row)

            bg = QColor(Colors.LOW_STOCK_BG)

            name_item = QTableWidgetItem(item["name"])
            code_item = QTableWidgetItem(item.get("sku", ""))
            stock_item = QTableWidgetItem(str(item["current_stock"]))
            reorder_item = QTableWidgetItem(str(item["min_stock"]))

            stock_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            reorder_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            for cell in (name_item, code_item, stock_item, reorder_item):
                cell.setBackground(bg)

            self.table.setRowHeight(row, 42)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, code_item)
            self.table.setItem(row, 2, stock_item)
            self.table.setItem(row, 3, reorder_item)
