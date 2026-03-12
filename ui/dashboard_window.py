from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame
from services.api_client import APIClient
from services.session import Session
from services.event_bus import EventBus, SALE_CREATED

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
            QLabel {{ border: none; }}
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

class DashboardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.api_client = APIClient()
        self.setup_ui()
        self.load_summary()
        EventBus.subscribe(SALE_CREATED, self.load_summary)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header = QLabel("Dashboard Overview")
        header.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)
        
        grid = QGridLayout()
        self.card_sales = MetricCard("Today's Sales", "0", "#2ecc71")
        self.card_revenue = MetricCard("Today's Revenue", "₹0.00", "#f1c40f")
        self.card_items = MetricCard("Items Sold Today", "0", "#9b59b6")
        self.card_low_stock = MetricCard("Low Stock Items", "0", "#e74c3c")
        
        grid.addWidget(self.card_sales, 0, 0)
        grid.addWidget(self.card_revenue, 0, 1)
        grid.addWidget(self.card_items, 1, 0)
        grid.addWidget(self.card_low_stock, 1, 1)
        
        layout.addLayout(grid)
        layout.addStretch()

    def load_summary(self):
        token = Session.token
        if not token:
            return
            
        summary = self.api_client.get_dashboard_summary(token)
        if summary:
            self.card_sales.set_value(summary.get("today_sales", 0))
            self.card_revenue.set_value(f"₹{summary.get('today_revenue', 0):.2f}")
            self.card_items.set_value(summary.get("items_sold", 0))
            self.card_low_stock.set_value(summary.get("low_stock_count", 0))