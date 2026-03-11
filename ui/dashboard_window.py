from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout


class DashboardWindow(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        title = QLabel("Nakama Furniture ERP Dashboard")

        today_sales = QLabel("Today's Sales: Loading...")
        stock_alerts = QLabel("Low Stock Items: Loading...")

        layout.addWidget(title)
        layout.addWidget(today_sales)
        layout.addWidget(stock_alerts)

        self.setLayout(layout)