from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtWidgets import QPushButton
from ui.inventory_window import InventoryWindow


class DashboardWindow(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        title = QLabel("Nakama Furniture ERP Dashboard")

        self.inventory_button = QPushButton("Inventory")
        self.inventory_button.clicked.connect(self.open_inventory)
        
        stock_alerts = QLabel("Low Stock Items: Loading...")

        layout.addWidget(title)
        layout.addWidget(self.inventory_button)
        layout.addWidget(stock_alerts)

        self.setLayout(layout)
    
    def open_inventory(self):

        self.inventory = InventoryWindow()
        self.inventory.show()