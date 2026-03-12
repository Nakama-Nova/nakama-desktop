from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit,
    QLabel
)
from PyQt6.QtCore import Qt
from services.api_client import APIClient
from services.session import Session

class CustomerDialog(QDialog):
    def __init__(self, parent=None, customer=None):
        super().__init__(parent)
        self.setWindowTitle("Add Customer" if not customer else "Edit Customer")
        self.setFixedWidth(400)
        
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit()
        self.phone_edit = QLineEdit()
        self.address_edit = QLineEdit()
        
        if customer:
            self.name_edit.setText(customer.get("name", ""))
            self.phone_edit.setText(customer.get("phone", ""))
            self.address_edit.setText(customer.get("address", ""))
            
        layout.addRow("Name*", self.name_edit)
        layout.addRow("Phone", self.phone_edit)
        layout.addRow("Address", self.address_edit)
        
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addRow(button_layout)

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "address": self.address_edit.text().strip()
        }

class CustomersScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.api_client = APIClient()
        self.setup_ui()
        self.load_customers()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Add Customer")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.refresh_btn = QPushButton("Refresh")
        
        self.add_btn.clicked.connect(self.add_customer)
        self.edit_btn.clicked.connect(self.edit_customer)
        self.delete_btn.clicked.connect(self.delete_customer)
        self.refresh_btn.clicked.connect(self.load_customers)
        
        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(self.refresh_btn)
        
        layout.addLayout(toolbar)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Phone", "Address", "Created At"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        layout.addWidget(self.table)

    def load_customers(self):
        customers = self.api_client.get_customers(Session.token)
        if customers is None:
            QMessageBox.critical(self, "Error", "Failed to load customers.")
            return
        
        self.table.setRowCount(0)
        for row, customer in enumerate(customers):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(customer["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(customer["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(customer.get("phone", "")))
            self.table.setItem(row, 3, QTableWidgetItem(customer.get("address", "")))
            self.table.setItem(row, 4, QTableWidgetItem(customer.get("created_at", "")))

    def add_customer(self):
        dialog = CustomerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Warning", "Name is required.")
                return
            
            result = self.api_client.create_customer(Session.token, **data)
            if result:
                QMessageBox.information(self, "Success", "Customer added successfully.")
                self.load_customers()
            else:
                QMessageBox.critical(self, "Error", "Failed to add customer.")

    def edit_customer(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a customer to edit.")
            return
        
        customer_id = int(self.table.item(selected_row, 0).text())
        customer = {
            "name": self.table.item(selected_row, 1).text(),
            "phone": self.table.item(selected_row, 2).text(),
            "address": self.table.item(selected_row, 3).text()
        }
        
        dialog = CustomerDialog(self, customer)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Warning", "Name is required.")
                return
            
            result = self.api_client.update_customer(Session.token, customer_id, **data)
            if result:
                QMessageBox.information(self, "Success", "Customer updated successfully.")
                self.load_customers()
            else:
                QMessageBox.critical(self, "Error", "Failed to update customer.")

    def delete_customer(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a customer to delete.")
            return
        
        customer_id = int(self.table.item(selected_row, 0).text())
        confirm = QMessageBox.question(
            self, "Confirm Delete", 
            "Are you sure you want to delete this customer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            if self.api_client.delete_customer(Session.token, customer_id):
                QMessageBox.information(self, "Success", "Customer deleted successfully.")
                self.load_customers()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete customer.")
