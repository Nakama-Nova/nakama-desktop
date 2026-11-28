"""
ui/customers_screen.py

Buyers screen — hides UUIDs, user-friendly labels, styled buttons.
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
    QDialog,
    QFormLayout,
    QLineEdit,
    QLabel,
)
from PyQt6.QtCore import Qt

from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts
from ui.errors import handle_permissions
from services.customer_service import CustomerService
from services.session import Session
from ui.workers import load_async
from services import dues
from services.money import inr
from services.sales_service import SalesService


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

        self.cancel_btn = IconButton("Cancel")
        self.cancel_btn.setStyleSheet(Theme.btn_secondary())
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = IconButton("💾  Save")
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


class DuesDialog(QDialog):
    """What one buyer owes, bill by bill, with a reminder that opens in WhatsApp (you press send)."""

    def __init__(self, parent, customer: dict, owed: dict):
        super().__init__(parent)
        self._customer, self._owed = customer, owed
        self.setWindowTitle(f"Dues: {customer.get('name', '')}")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(10)
        v.addWidget(QLabel(f"{customer.get('name', '')} owes {inr(owed['owed'])}", styleSheet=Theme.subheading()))
        t = QTableWidget(len(owed["bills"]), 3)
        t.setHorizontalHeaderLabels(["Bill", "Date", "Still to pay"])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        Theme.style_table(t)
        for r, s in enumerate(owed["bills"]):
            for c, text in enumerate([s.get("invoice_number") or "", str(s.get("created_at") or "")[:10], inr(dues.due_of(s))]):
                t.setItem(r, c, QTableWidgetItem(text))
        v.addWidget(t)
        if any(s.get("balance_due") is None and s.get("payment_status") == "partial" for s in owed["bills"]):
            v.addWidget(QLabel("A part-paid bill is counted in full: this server does not say how much was paid.", styleSheet=f"color: {Colors.TEXT_SECONDARY};"))
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.accept)
        self.remind_btn = QPushButton("💬  Remind on WhatsApp")
        self.remind_btn.setStyleSheet(Theme.btn_primary())
        self.remind_btn.clicked.connect(self._remind)
        row.addWidget(close)
        row.addWidget(self.remind_btn)
        v.addLayout(row)

    def link(self) -> str | None:
        text = dues.reminder_text(
            self._customer.get("name", ""), inr(self._owed["owed"]), [b.get("invoice_number") for b in self._owed["bills"] if b.get("invoice_number")]
        )
        return dues.whatsapp_link(self._customer.get("phone") or "", text)

    def _remind(self):
        import webbrowser

        link = self.link()
        if not link:
            QMessageBox.information(self, "Reminder", "This buyer has no usable phone number.")
            return
        webbrowser.open(link)  # opens the chat with the words typed in; nothing is sent until you press send


class CustomersScreen(QWidget):

    def __init__(self):
        super().__init__()
        self._customer_service = CustomerService()
        self._all_customers: list[dict] = []
        self._dues: dict = {}
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("Buyers")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()

        self.add_btn = IconButton("➕  Add Buyer")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self.add_customer)
        header_row.addWidget(self.add_btn)

        # RBAC: Hide add button for unauthorized roles
        self._can_edit = Session.can("sales:customer:write")
        self.add_btn.setVisible(self._can_edit)

        layout.addLayout(header_row)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search buyers by name or phone...")
        self.search_input.setStyleSheet(Theme.input_style())
        self.search_input.textChanged.connect(self._filter_table)
        layout.addWidget(self.search_input)

        # Table — NO UUID ID column, NO "Created At"
        self.table = QTableWidget()

        self.table.setColumnCount(6 if self._can_edit else 5)
        headers = ["Name", "Phone", "Address", "Owes", "Open since"]
        if self._can_edit:
            headers.append("Actions")
        self.table.setHorizontalHeaderLabels(headers)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        if self._can_edit:
            hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(5, 250)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        Theme.style_table(self.table)

        layout.addWidget(self.table)

    def _fetch(self):
        """The buyers, and the bills (to show who owes what)."""
        customers = self._customer_service.get_all()
        try:
            sales = SalesService().get_sales() if Session.can("sales:sale:read") else []
        except Exception:  # offline or refused: the list still shows, without the dues
            sales = []
        return customers, sales

    @handle_permissions
    def refresh_data(self):
        self._show_customers(self._fetch())

    def refresh_async(self):
        """Same as refresh_data, but the list is fetched in the background."""
        load_async(self, self._fetch, self._show_customers)

    def _show_customers(self, data):
        customers, sales = data if isinstance(data, tuple) else (data, [])
        self._dues = dues.dues_by_customer(sales or [])
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
            owed = self._dues.get(str(c.get("id")))
            owes = QTableWidgetItem(inr(owed["owed"]) if owed else "")
            owes.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if owed:
                owes.setForeground(Qt.GlobalColor.darkRed)
            self.table.setItem(row, 3, owes)
            self.table.setItem(row, 4, QTableWidgetItem(f"{owed['days']} days" if owed else ""))

            # Action buttons — compact style for table cells
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(4, 4, 4, 4)
            actions_layout.setSpacing(6)

            edit_btn = IconButton("✏️ Edit")
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet(Theme.btn_table_action())
            edit_btn.clicked.connect(lambda _, cust=c: self.edit_customer(cust))

            del_btn = IconButton("🗑️")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setFixedSize(36, 28)
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Colors.RED};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 4px;
                    padding: 2px;
                    background: {Colors.CARD_BG};
                }}
                QPushButton:hover {{
                    background: {Colors.ERROR_BG};
                }}
            """)
            del_btn.clicked.connect(lambda _, cust=c: self.delete_customer(cust))

            if owed:
                due_btn = IconButton("💬 Dues")
                due_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                due_btn.setFixedHeight(28)
                due_btn.setStyleSheet(Theme.btn_table_action())
                due_btn.setToolTip("Unpaid bills and a WhatsApp reminder")
                due_btn.clicked.connect(lambda _, cust=c, o=owed: self.show_dues(cust, o))
                actions_layout.addWidget(due_btn)
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(del_btn)

            if self._can_edit:
                self.table.setCellWidget(row, 5, actions)

    def show_dues(self, customer: dict, owed: dict):
        """The buyer's unpaid bills, and a WhatsApp reminder to send them."""
        DuesDialog(self, customer, owed).exec()

    def _filter_table(self, text: str):
        query = text.strip().lower()
        if not query:
            self._populate_table(self._all_customers)
            return
        filtered = [
            c
            for c in self._all_customers
            if query in c["name"].lower() or query in (c.get("phone", "") or "")
        ]
        self._populate_table(filtered)

    @handle_permissions
    def add_customer(self):
        dialog = CustomerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Required", "Buyer name is required.")
                return
            result = self._customer_service.create(**data)
            if result:
                QMessageBox.information(self, "Buyer added", "Buyer added successfully!")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Failed to add buyer.")

    @handle_permissions
    def edit_customer(self, customer: dict):
        dialog = CustomerDialog(self, customer)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Required", "Buyer name is required.")
                return
            result = self._customer_service.update(str(customer["id"]), **data)
            if result:
                QMessageBox.information(
                    self, "Buyer updated", "Buyer updated successfully!"
                )
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Failed to update buyer.")

    @handle_permissions
    def delete_customer(self, customer: dict):
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {customer['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            if self._customer_service.delete(str(customer["id"])):
                QMessageBox.information(self, "Buyer deleted", "Buyer deleted.")
                self.refresh_data()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete buyer.")
