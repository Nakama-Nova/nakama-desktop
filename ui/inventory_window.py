from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem
)

import requests
from services.session import Session

class InventoryWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Inventory")

        layout = QVBoxLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Price", "Stock"]
        )

        refresh_button = QPushButton("Refresh Items")
        refresh_button.clicked.connect(self.load_items)

        layout.addWidget(refresh_button)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def load_items(self):

        headers = {
            "Authorization": f"Bearer {Session.token}"
        }

        response = requests.get(
            "http://127.0.0.1:8000/items",
            headers=headers
        )

        items = response.json()

        self.table.setRowCount(len(items))

        for row, item in enumerate(items):

            self.table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(item["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(item["price"])))
            self.table.setItem(row, 3, QTableWidgetItem(str(item["stock_quantity"])))