from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QDateEdit
)
from PyQt6.QtCore import Qt, QDate
from services.api_client import APIClient
from services.session import Session
from services.event_bus import EventBus, SALE_CREATED
import os
from pathlib import Path

class SalesHistoryScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.api_client = APIClient()
        self.setup_ui()
        self.load_sales()
        
        # Subscribe to new sales to refresh history
        EventBus.subscribe(SALE_CREATED, self.load_sales)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>Sales History</h2>"))
        header.addStretch()
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load_sales)
        header.addWidget(self.refresh_btn)
        
        layout.addLayout(header)
        
        # Filters (Optional but good)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Filter by Date:"))
        self.date_filter = QDateEdit()
        self.date_filter.setCalendarPopup(True)
        self.date_filter.setDate(QDate.currentDate())
        filters.addWidget(self.date_filter)
        
        self.apply_filter_btn = QPushButton("Apply Filter")
        self.apply_filter_btn.clicked.connect(self.apply_filter)
        filters.addWidget(self.apply_filter_btn)
        
        self.clear_filter_btn = QPushButton("Clear")
        self.clear_filter_btn.clicked.connect(self.load_sales)
        filters.addWidget(self.clear_filter_btn)
        
        filters.addStretch()
        layout.addLayout(filters)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Invoice #", "Customer ID", "Total Amount", "Date", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        layout.addWidget(self.table)

    def load_sales(self, customer_id=None, date=None):
        sales = self.api_client.get_sales(Session.token, customer_id=customer_id, date=date)
        if sales is None:
            QMessageBox.critical(self, "Error", "Failed to load sales history.")
            return
        
        self.table.setRowCount(0)
        for row, sale in enumerate(sales):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(sale.get("invoice_number", "N/A")))
            self.table.setItem(row, 1, QTableWidgetItem(str(sale.get("customer_id", "N/A"))))
            self.table.setItem(row, 2, QTableWidgetItem(f"₹{sale.get('total_amount', 0):.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(sale.get("created_at", "")))
            
            # Actions cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            
            view_btn = QPushButton("Details")
            view_btn.clicked.connect(lambda _, s=sale: self.view_details(s))
            
            print_btn = QPushButton("Reprint")
            print_btn.clicked.connect(lambda _, s=sale: self.reprint_invoice(s))
            
            actions_layout.addWidget(view_btn)
            actions_layout.addWidget(print_btn)
            self.table.setCellWidget(row, 4, actions_widget)

    def apply_filter(self):
        date_str = self.date_filter.date().toString("yyyy-MM-dd")
        self.load_sales(date=date_str)

    def view_details(self, sale):
        items = self.api_client.get_sale_items(Session.token, sale["id"])
        if items is None:
            QMessageBox.critical(self, "Error", "Failed to load sale items.")
            return
        
        msg = f"Sale Details for Invoice: {sale.get('invoice_number')}\n\n"
        for item in items:
            msg += f"- Item ID: {item['item_id']}, Qty: {item['quantity']}, Total: ₹{item['total_price']:.2f}\n"
        
        QMessageBox.information(self, "Sale Details", msg)

    def reprint_invoice(self, sale):
        inv_num = sale.get("invoice_number")
        if not inv_num:
            return
            
        pdf_bytes = self.api_client.get_invoice_pdf(Session.token, inv_num)
        if pdf_bytes:
            invoice_dir = Path("invoices")
            invoice_dir.mkdir(exist_ok=True)
            path = invoice_dir / f"{inv_num}_reprint.pdf"
            path.write_bytes(pdf_bytes)
            os.startfile(str(path))
        else:
            QMessageBox.critical(self, "Error", "Failed to download invoice.")
