"""
ui/customers_screen.py

Buyers screen — hides UUIDs, user-friendly labels, styled buttons.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit,
    QLabel,
)
from PyQt6.QtCore import Qt

from ui.theme import Theme, Colors, Fonts
from services.customer_service import CustomerService
from services.session import Session
from services.enums import UserRole


class CustomerDialog(QDialog):
    """Add/Edit buyer form dialog — styled."""

    def __init__(self, parent=None, customer=None):
        super().__init__(parent)
        self.setWindowTitle("Add Buyer" if not customer else "Edit Buyer")
        self.setFixedWidth(420)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BG};
                font-family: '{Fonts.FAMILY}';
            }}
        """)

        layout = QFormLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Ramesh Kumar")
        self.name_edit.setStyleSheet(Theme.input_style())

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("e.g. 9876543210")
        self.phone_edit.setStyleSheet(Theme.input_style())

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("e.g. MG Road, Bangalore")
        self.address_edit.setStyleSheet(Theme.input_style())

        if customer:
            self.name_edit.setText(customer.get("name") or "")
            self.phone_edit.setText(customer.get("phone") or "")
            self.address_edit.setText(customer.get("address") or "")

        name_lbl = QLabel("Name *")
        name_lbl.setStyleSheet(Theme.label())
        phone_lbl = QLabel("Phone")
        phone_lbl.setStyleSheet(Theme.label())
        addr_lbl = QLabel("Address")
        addr_lbl.setStyleSheet(Theme.label())

        layout.addRow(name_lbl, self.name_edit)
        layout.addRow(phone_lbl, self.phone_edit)
        layout.addRow(addr_lbl, self.address_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(Theme.btn_secondary())
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("💾  Save")
        self.save_btn.setStyleSheet(Theme.btn_primary())
        self.save_btn.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        layout.addRow(btn_row)

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "phone": self.phone_edit.text().strip(),
            "address": self.address_edit.text().strip(),
        }


class CustomersScreen(QWidget):

    def __init__(self):
        super().__init__()
        self._customer_service = CustomerService()
        self._all_customers: list[dict] = []
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("👤  Buyers")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()

        self.add_btn = QPushButton("➕  Add Buyer")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self.add_customer)
        header_row.addWidget(self.add_btn)

        # RBAC: Hide add button for unauthorized roles
        role = Session.get_role()
        can_edit = role in [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]
        self.add_btn.setVisible(can_edit)

        layout.addLayout(header_row)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search buyers by name or phone...")
        self.search_input.setStyleSheet(Theme.input_style())
        self.search_input.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_input)

        # Table — NO UUID ID column, NO "Created At"
        self.table = QTableWidget()
        
        role = Session.get_role()
        can_edit = role in [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]
        
        self.table.setColumnCount(4 if can_edit else 3)
        headers = ["Name", "Phone", "Address"]
        if can_edit:
            headers.append("Actions")
        self.table.setHorizontalHeaderLabels(headers)
        
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        if can_edit:
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(3, 160)
            
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Theme.table_style())

        layout.addWidget(self.table)

    def refresh_data(self):
        customers = self._customer_service.get_all()
        self._all_customers = customers or []
        self._populate_table(self._all_customers)

    def _populate_table(self, customers: list[dict]):
        self.table.setRowCount(0)
        for row, c in enumerate(customers):
            self.table.insertRow(row)
            self.table.setRowHeight(row, 42)
            self.table.setItem(row, 0, QTableWidgetItem(c["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(c.get("phone", "") or ""))
            self.table.setItem(row, 2, QTableWidgetItem(c.get("address", "") or ""))

            # Action buttons — compact style for table cells
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)

            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet(Theme.btn_table_action())
            edit_btn.clicked.connect(lambda _, cust=c: self.edit_customer(cust))

            del_btn = QPushButton("🗑️")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setFixedSize(36, 28)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Colors.RED};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 4px;
                    padding: 2px;
                    background: white;
                }}
                QPushButton:hover {{
                    background: {Colors.ERROR_BG};
                }}
            """)
            del_btn.clicked.connect(lambda _, cust=c: self.delete_customer(cust))

            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(del_btn)
            
            role = Session.get_role()
            if role in [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]:
                self.table.setCellWidget(row, 3, actions)

    def _filter_table(self, text: str):
        query = text.strip().lower()
        if not query:
            self._populate_table(self._all_customers)
            return
        filtered = [
            c for c in self._all_customers
            if query in c["name"].lower() or query in (c.get("phone", "") or "")
        ]
        self._populate_table(filtered)

    def add_customer(self):
        dialog = CustomerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Required", "Buyer name is required.")
                return
            result = self._customer_service.create(**data)
            if result:
                QMessageBox.information(self, "Success ✅", "Buyer added successfully!")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Failed to add buyer.")

    def edit_customer(self, customer: dict):
        dialog = CustomerDialog(self, customer)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Required", "Buyer name is required.")
                return
            result = self._customer_service.update(str(customer["id"]), **data)
            if result:
                QMessageBox.information(self, "Updated ✅", "Buyer updated successfully!")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Failed to update buyer.")

    def delete_customer(self, customer: dict):
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete {customer['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if self._customer_service.delete(str(customer["id"])):
                QMessageBox.information(self, "Deleted ✅", "Buyer deleted.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete buyer.")
