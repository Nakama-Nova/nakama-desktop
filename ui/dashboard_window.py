from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout


class DashboardWindow(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        title = QLabel("Nakama Furniture ERP Dashboard")
        stock_alerts = QLabel("Low Stock Items: Loading...")

        layout.addWidget(title)
        layout.addWidget(stock_alerts)
        layout.addStretch()

        self.setLayout(layout)