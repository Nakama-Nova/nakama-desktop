from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from services.api_client import APIClient
from services.session import Session

class MetricCard(QFrame):
    def __init__(self, title, value="0", color="#3498db"):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: white;
                border-radius: 10px;
                border: 1px solid #ddd;
            }}
            QLabel {{
                border: none;
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 14px; color: #7f8c8d;")
        
        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)

    def set_value(self, value):
        self.value_lbl.setText(str(value))

class ReportsScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.api_client = APIClient()
        self.setup_ui()
        self.load_reports()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header + Refresh
        header_layout = QHBoxLayout()
        header_lbl = QLabel("Business Reports & Analytics")
        header_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")
        
        self.refresh_btn = QPushButton("Refresh Reports")
        self.refresh_btn.clicked.connect(self.load_reports)
        self.refresh_btn.setFixedWidth(150)
        
        header_layout.addWidget(header_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.refresh_btn)
        layout.addLayout(header_layout)
        
        # Metrics Cards
        metrics_layout = QGridLayout()
        
        self.card_today_sales = MetricCard("Today's Sales", "0", "#2ecc71")
        self.card_today_items = MetricCard("Items Sold Today", "0", "#9b59b6")
        self.card_today_revenue = MetricCard("Today's Revenue", "₹0.00", "#f1c40f")
        self.card_all_sales = MetricCard("All-Time Sales", "0", "#34495e")
        self.card_total_revenue = MetricCard("Total Revenue", "₹0.00", "#e67e22")
        self.card_low_stock = MetricCard("Low Stock Count", "0", "#e74c3c")
        
        metrics_layout.addWidget(self.card_today_sales, 0, 0)
        metrics_layout.addWidget(self.card_today_items, 0, 1)
        metrics_layout.addWidget(self.card_today_revenue, 0, 2)
        metrics_layout.addWidget(self.card_all_sales, 1, 0)
        metrics_layout.addWidget(self.card_total_revenue, 1, 1)
        metrics_layout.addWidget(self.card_low_stock, 1, 2)
        
        layout.addLayout(metrics_layout)
        
        # Low Stock Section
        low_stock_header = QLabel("Low Stock Alerts")
        low_stock_header.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(low_stock_header)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Category", "Stock"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.table)

    def load_reports(self):
        token = Session.token
        
        # Daily Sales
        daily = self.api_client.get_reports_daily(token)
        if daily:
            self.card_today_sales.set_value(daily.get("total_sales", 0))
            self.card_today_items.set_value(daily.get("items_sold", 0))
            self.card_today_revenue.set_value(f"₹{daily.get('total_revenue', 0):.2f}")
            
        # Summary
        summary = self.api_client.get_reports_summary(token)
        if summary:
            self.card_all_sales.set_value(summary.get("total_sales", 0))
            self.card_total_revenue.set_value(f"₹{summary.get('total_revenue', 0):.2f}")
            
        # Dashboard Summary for Low Stock Count
        dash_summary = self.api_client.get_dashboard_summary(token)
        if dash_summary:
            self.card_low_stock.set_value(dash_summary.get("low_stock_count", 0))
            
        # Low Stock
        low_stock = self.api_client.get_low_stock_items(token)
        if low_stock is not None:
            self.table.setRowCount(0)
            for row, item in enumerate(low_stock):
                self.table.insertRow(row)
                
                # Highlight row if stock is very low
                bg_color = QColor("#fff3cd") # Light amber for warning
                
                id_item = QTableWidgetItem(str(item["id"]))
                name_item = QTableWidgetItem(item["name"])
                cat_item = QTableWidgetItem(item.get("category", "Uncategorized"))
                stock_item = QTableWidgetItem(str(item["stock_quantity"]))
                
                for itm in (id_item, name_item, cat_item, stock_item):
                    itm.setBackground(bg_color)
                
                self.table.setItem(row, 0, id_item)
                self.table.setItem(row, 1, name_item)
                self.table.setItem(row, 2, cat_item)
                self.table.setItem(row, 3, stock_item)
