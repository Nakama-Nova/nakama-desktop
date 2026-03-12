"""
ui/sales_screen.py

Sales POS screen for the Nakama Furniture ERP desktop client.

Responsibilities (SRP):
  - Render the POS layout (customer input, item search, cart table, totals).
  - Delegate all HTTP communication to APIClient.
  - Delegate PDF file-save + open to SalesController.

No PDF generation logic lives here — the backend owns that.
"""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSpinBox, QCompleter,
)
from PyQt6.QtCore import Qt, QStringListModel

from services.api_client import APIClient
from services.session import Session
from services.event_bus import EventBus, SALE_CREATED

# ---------------------------------------------------------------------------
# Controller – isolates file I/O and orchestration from the widget
# ---------------------------------------------------------------------------
class SalesController:
    """
    Handles the multi-step sale + invoice workflow.
    Keeps business logic decoupled from the PyQt widget tree.
    """

    INVOICE_DIR = Path("invoices")

    def __init__(self, api: APIClient):
        self._api = api

    def lookup_customer(self, phone: str) -> dict | None:
        """Find an existing customer by phone number."""
        return self._api.get_customer_by_phone(Session.token, phone)

    def ensure_customer(self, name: str, phone: str) -> int | None:
        """
        Ensures a customer exists. If phone found, return ID. 
        If not, create and return new ID.
        """
        customer = self.lookup_customer(phone)
        if customer:
            return customer.get("id")
        
        # Create new customer
        new_customer = self._api.create_customer(Session.token, name=name, phone=phone, address="")
        return new_customer.get("id") if new_customer else None

    def submit_sale(self, items: list[dict], customer_id: int | None = None) -> dict | None:
        """POST /sales and return the response dict (SaleResponse)."""
        return self._api.create_sale(Session.token, items, customer_id)

    def fetch_and_save_pdf(self, invoice_number: str) -> Path | None:
        """
        Download the invoice PDF from the backend, persist it, and return the path.
        Returns None if the download fails.
        """
        pdf_bytes = self._api.get_invoice_pdf(Session.token, invoice_number)
        if pdf_bytes is None:
            return None

        self.INVOICE_DIR.mkdir(exist_ok=True)
        filepath = self.INVOICE_DIR / f"{invoice_number}.pdf"
        filepath.write_bytes(pdf_bytes)
        return filepath

    @staticmethod
    def open_pdf(filepath: Path) -> None:
        """Open a local PDF with the OS default application."""
        os.startfile(str(filepath))


# ---------------------------------------------------------------------------
# Cart row data-class (plain Python, no Qt dependency)
# ---------------------------------------------------------------------------
class CartItem:
    __slots__ = ("item_id", "name", "price", "gst_pct", "quantity")

    def __init__(self, item_id: int, name: str, price: float, gst_pct: float, quantity: int = 1):
        self.item_id = item_id
        self.name = name
        self.price = price
        self.gst_pct = gst_pct
        self.quantity = quantity

    @property
    def line_total(self) -> float:
        return self.price * self.quantity * (1 + self.gst_pct / 100)


# ---------------------------------------------------------------------------
# Sales POS Widget
# ---------------------------------------------------------------------------
class SalesScreen(QWidget):
    """
    POS billing screen.

    Depends on:
      - APIClient (via constructor injection for testability)
      - Session   (singleton, read-only)
    """

    COL_ID   = 0
    COL_NAME = 1
    COL_PRICE = 2
    COL_QTY  = 3
    COL_GST  = 4
    COL_TOTAL = 5

    def __init__(self, api: APIClient | None = None):
        super().__init__()
        self._api = api or APIClient()
        self._controller = SalesController(self._api)
        self._all_items: list[dict] = []   # raw items from backend
        self._cart: list[CartItem] = []

        self._build_ui()
        self._load_items()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # ── Customer lookup ──────────────────────────────────────────
        customer_group = QHBoxLayout()
        
        # Phone
        phone_vbox = QVBoxLayout()
        phone_vbox.addWidget(QLabel("<b>Customer Phone</b>"))
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Enter phone number...")
        phone_vbox.addWidget(self.phone_input)
        customer_group.addLayout(phone_vbox)

        # Name
        name_vbox = QVBoxLayout()
        name_vbox.addWidget(QLabel("<b>Customer Name</b>"))
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Customer Name")
        name_vbox.addWidget(self.customer_input)
        customer_group.addLayout(name_vbox)

        # Search Bio
        self.search_customer_btn = QPushButton("Search")
        self.search_customer_btn.setFixedWidth(80)
        self.search_customer_btn.clicked.connect(self._handle_customer_lookup)
        customer_group.addWidget(self.search_customer_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        
        root.addLayout(customer_group)

        # ── Item search row ──────────────────────────────────────────
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search item by name...")
        self._completer = QCompleter()
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_input.setCompleter(self._completer)

        add_btn = QPushButton("Add Item")
        add_btn.setFixedWidth(110)
        add_btn.clicked.connect(self._add_item_to_cart)

        search_row.addWidget(self.search_input)
        search_row.addWidget(add_btn)
        root.addLayout(search_row)

        # ── Cart table ───────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Item ID", "Item Name", "Price (₹)", "Quantity", "GST %", "Line Total (₹)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

        # ── Totals panel ─────────────────────────────────────────────
        totals_row = QHBoxLayout()
        self.subtotal_lbl  = QLabel("Subtotal: ₹0.00")
        self.cgst_lbl      = QLabel("CGST: ₹0.00")
        self.sgst_lbl      = QLabel("SGST: ₹0.00")
        self.grandtotal_lbl = QLabel("<b>Grand Total: ₹0.00</b>")

        for lbl in (self.subtotal_lbl, self.cgst_lbl, self.sgst_lbl, self.grandtotal_lbl):
            totals_row.addWidget(lbl)
        totals_row.addStretch()
        root.addLayout(totals_row)

        # ── Action buttons ───────────────────────────────────────────
        actions_row = QHBoxLayout()
        clear_btn   = QPushButton("Clear Cart")
        invoice_btn = QPushButton("Generate Invoice")
        invoice_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px;")

        clear_btn.clicked.connect(self._clear_cart)
        invoice_btn.clicked.connect(self._generate_invoice)

        actions_row.addStretch()
        actions_row.addWidget(clear_btn)
        actions_row.addWidget(invoice_btn)
        root.addLayout(actions_row)

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    def _load_items(self):
        """Fetch items from the backend and populate the autocomplete model."""
        items = self._api.get_items(Session.token)
        if items is None:
            # Non-fatal – user can still type manually; warn once
            QMessageBox.warning(self, "Warning", "Could not load items from backend.")
            return

        self._all_items = items
        names = [item["name"] for item in items]
        model = QStringListModel(names)
        self._completer.setModel(model)

    # ------------------------------------------------------------------
    # Customer operations
    # ------------------------------------------------------------------
    def _handle_customer_lookup(self):
        phone = self.phone_input.text().strip()
        if not phone:
            QMessageBox.warning(self, "Input Error", "Please enter a phone number.")
            return
        
        customer = self._controller.lookup_customer(phone)
        if customer:
            self.customer_input.setText(customer.get("name", ""))
            QMessageBox.information(self, "Found", f"Customer found: {customer.get('name')}")
        else:
            QMessageBox.information(self, "Not Found", "No customer found with this phone number. Please enter name manually.")
            self.customer_input.setFocus()

    # ------------------------------------------------------------------
    # Cart operations
    # ------------------------------------------------------------------
    def _find_item_by_name(self, name: str) -> dict | None:
        name_lower = name.strip().lower()
        return next((i for i in self._all_items if i["name"].lower() == name_lower), None)

    def _add_item_to_cart(self):
        name = self.search_input.text().strip()
        if not name:
            return

        item_data = self._find_item_by_name(name)
        if item_data is None:
            QMessageBox.warning(self, "Not Found", f"Item '{name}' not found.")
            return

        # If already in cart, bump quantity
        existing = next((c for c in self._cart if c.item_id == item_data["id"]), None)
        if existing:
            existing.quantity += 1
        else:
            self._cart.append(
                CartItem(
                    item_id=item_data["id"],
                    name=item_data["name"],
                    price=float(item_data["price"] or 0.0),
                    gst_pct=float(item_data.get("gst_percent", 0.0) or 0.0),
                )
            )

        self.search_input.clear()
        self._refresh_table()

    def _clear_cart(self):
        self._cart.clear()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------
    def _refresh_table(self):
        self.table.setRowCount(len(self._cart))

        for row, cart_item in enumerate(self._cart):
            self.table.setItem(row, self.COL_ID,    QTableWidgetItem(str(cart_item.item_id)))
            self.table.setItem(row, self.COL_NAME,  QTableWidgetItem(cart_item.name))
            self.table.setItem(row, self.COL_PRICE, QTableWidgetItem(f"{cart_item.price:.2f}"))
            self.table.setItem(row, self.COL_GST,   QTableWidgetItem(f"{cart_item.gst_pct:.1f}"))
            self.table.setItem(row, self.COL_TOTAL, QTableWidgetItem(f"{cart_item.line_total:.2f}"))

            # Editable quantity spinner embedded in the table cell
            qty_spin = QSpinBox()
            qty_spin.setRange(1, 9999)
            qty_spin.setValue(cart_item.quantity)
            # Capture the index in the closure, not the mutable loop variable
            qty_spin.valueChanged.connect(
                lambda val, idx=row: self._on_qty_changed(idx, val)
            )
            self.table.setCellWidget(row, self.COL_QTY, qty_spin)

        self._update_totals()

    def _on_qty_changed(self, row: int, value: int):
        if row < len(self._cart):
            self._cart[row].quantity = value
            # Update line total cell only; avoid full table rebuild (avoids focus-loss loop)
            self.table.setItem(
                row, self.COL_TOTAL,
                QTableWidgetItem(f"{self._cart[row].line_total:.2f}")
            )
            self._update_totals()

    # ------------------------------------------------------------------
    # Totals calculation
    # ------------------------------------------------------------------
    def _update_totals(self):
        subtotal = sum(c.price * c.quantity for c in self._cart)
        total_gst = sum((c.price * c.quantity * c.gst_pct / 100) for c in self._cart)
        cgst = total_gst / 2
        sgst = total_gst / 2
        grand_total = subtotal + total_gst

        self.subtotal_lbl.setText(f"Subtotal: ₹{subtotal:.2f}")
        self.cgst_lbl.setText(f"CGST: ₹{cgst:.2f}")
        self.sgst_lbl.setText(f"SGST: ₹{sgst:.2f}")
        self.grandtotal_lbl.setText(f"<b>Grand Total: ₹{grand_total:.2f}</b>")

    # ------------------------------------------------------------------
    # Invoice generation
    # ------------------------------------------------------------------
    def _generate_invoice(self):
        phone = self.phone_input.text().strip()
        customer_name = self.customer_input.text().strip()
        
        if not phone:
            QMessageBox.warning(self, "Missing Info", "Please enter a customer phone number.")
            return
        if not customer_name:
            QMessageBox.warning(self, "Missing Info", "Please enter a customer name.")
            return
        if not self._cart:
            QMessageBox.warning(self, "Empty Cart", "Please add at least one item.")
            return

        # Step 1 – Resolve Customer (Lookup or Create)
        customer_id = self._controller.ensure_customer(customer_name, phone)
        if customer_id is None:
            QMessageBox.critical(self, "Error", "Failed to resolve/create customer. Check backend.")
            return

        # Step 2 – POST /sales
        payload_items = [
            {"item_id": c.item_id, "quantity": c.quantity}
            for c in self._cart
        ]
        sale_data = self._controller.submit_sale(items=payload_items, customer_id=customer_id)
        if sale_data is None:
            QMessageBox.critical(self, "Error", "Failed to create sale. Check backend connection.")
            return

        # SaleResponse shape: {id, total_amount, invoice_number, ...}
        invoice_number = sale_data.get("invoice_number")
        if not invoice_number:
            QMessageBox.critical(self, "Error", "Sale created but invoice_number missing in response.")
            return

        # Step 3 – Download PDF  (route: GET /invoices/{invoice_number}/pdf)
        pdf_path = self._controller.fetch_and_save_pdf(invoice_number)
        if pdf_path is None:
            QMessageBox.critical(self, "Error", "Sale created but PDF download failed.")
            return

        # Step 4 – Open PDF with system viewer
        self._controller.open_pdf(pdf_path)

        QMessageBox.information(
            self,
            "Invoice Generated",
            f"Invoice {invoice_number} saved to:\n{pdf_path.resolve()}"
        )
        
        # Invalidate caches and trigger refreshes
        EventBus.emit(SALE_CREATED)
        
        self._clear_cart()
        self.customer_input.clear()
        self.phone_input.clear()
