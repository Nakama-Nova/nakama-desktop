"""
ui/sales_screen.py

Billing POS screen — simplified for non-technical users.
- "Item ID" column hidden (users don't need UUIDs)
- Labels: "Buyer Phone", "Buyer Name"
- Button text: "✅ Create Bill"
- Remove item button per row
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QSpinBox,
    QCompleter,
)
from PyQt6.QtCore import Qt, QStringListModel


from ui.theme import Theme, Colors, Fonts
from ui.errors import handle_permissions
from services.sales_service import SalesService
from services.customer_service import CustomerService
from services.inventory_service import InventoryService
from services.event_bus import EventBus, SALE_CREATED


class CartItem:
    __slots__ = ("item_id", "name", "price", "gst_pct", "quantity")

    def __init__(
        self, item_id: str, name: str, price: float, gst_pct: float, quantity: int = 1
    ):
        self.item_id = item_id
        self.name = name
        self.price = price
        self.gst_pct = gst_pct
        self.quantity = quantity

    @property
    def line_total(self) -> float:
        return self.price * self.quantity * (1 + self.gst_pct / 100)


class SalesScreen(QWidget):
    """Billing / POS screen."""

    COL_NAME = 0
    COL_PRICE = 1
    COL_QTY = 2
    COL_GST = 3
    COL_TOTAL = 4
    COL_REMOVE = 5

    def __init__(self):
        super().__init__()
        self._sales_service = SalesService()
        self._customer_service = CustomerService()
        self._inventory_service = InventoryService()
        self._all_items: list[dict] = []
        self._cart: list[CartItem] = []

        self.setStyleSheet(Theme.content_bg())
        self._build_ui()
        self._load_items()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        # ── Header ────────────────────────────────────
        header = QLabel("🧾  New Bill")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        root.addWidget(header)

        # ── Buyer section ─────────────────────────────
        buyer_row = QHBoxLayout()
        buyer_row.setSpacing(12)

        # Phone
        phone_col = QVBoxLayout()
        phone_lbl = QLabel("Buyer Phone")
        phone_lbl.setStyleSheet(Theme.label())
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Enter phone number...")
        self.phone_input.setStyleSheet(Theme.input_style())
        phone_col.addWidget(phone_lbl)
        phone_col.addWidget(self.phone_input)
        buyer_row.addLayout(phone_col, 2)

        # Name
        name_col = QVBoxLayout()
        name_lbl = QLabel("Buyer Name")
        name_lbl.setStyleSheet(Theme.label())
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Name (auto-fills on search)")
        self.customer_input.setStyleSheet(Theme.input_style())
        name_col.addWidget(name_lbl)
        name_col.addWidget(self.customer_input)
        buyer_row.addLayout(name_col, 2)

        # Search button
        self.search_btn = QPushButton("🔍  Search")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setFixedHeight(44)
        self.search_btn.setStyleSheet(Theme.btn_secondary())
        self.search_btn.clicked.connect(self._handle_customer_lookup)
        buyer_row.addWidget(self.search_btn, 0, Qt.AlignmentFlag.AlignBottom)

        root.addLayout(buyer_row)

        # ── Item search ───────────────────────────────
        item_row = QHBoxLayout()
        item_row.setSpacing(12)

        item_col = QVBoxLayout()
        item_lbl = QLabel("Search Item")
        item_lbl.setStyleSheet(Theme.label())
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type item name to search...")
        self.search_input.setStyleSheet(Theme.input_style())
        self._completer = QCompleter()
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_input.setCompleter(self._completer)
        self.search_input.returnPressed.connect(self._add_item_to_cart)
        item_col.addWidget(item_lbl)
        item_col.addWidget(self.search_input)
        item_row.addLayout(item_col, 1)

        add_btn = QPushButton("➕  Add")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(44)
        add_btn.setStyleSheet(Theme.btn_primary())
        add_btn.clicked.connect(self._add_item_to_cart)
        item_row.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignBottom)

        root.addLayout(item_row)

        # ── Cart table ────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Item Name", "Price (₹)", "Qty", "GST %", "Total (₹)", ""]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 60)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Theme.table_style())
        root.addWidget(self.table)

        # ── Totals ────────────────────────────────────
        totals_widget = QWidget()
        totals_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.CARD_BG};
                border-radius: 10px;
                border: 1px solid {Colors.CARD_BORDER};
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        totals_layout = QHBoxLayout(totals_widget)
        totals_layout.setContentsMargins(20, 14, 20, 14)

        self.subtotal_lbl = QLabel("Subtotal: ₹0.00")
        self.subtotal_lbl.setStyleSheet(
            f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};"
        )
        self.cgst_lbl = QLabel("CGST: ₹0.00")
        self.cgst_lbl.setStyleSheet(
            f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};"
        )
        self.sgst_lbl = QLabel("SGST: ₹0.00")
        self.sgst_lbl.setStyleSheet(
            f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};"
        )

        self.grandtotal_lbl = QLabel("Total: ₹0.00")
        self.grandtotal_lbl.setStyleSheet(f"""
            font-size: 18px; font-weight: bold; color: {Colors.GREEN};
        """)

        totals_layout.addWidget(self.subtotal_lbl)
        totals_layout.addWidget(self.cgst_lbl)
        totals_layout.addWidget(self.sgst_lbl)
        totals_layout.addStretch()
        totals_layout.addWidget(self.grandtotal_lbl)

        root.addWidget(totals_widget)

        # ── Action buttons ────────────────────────────
        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)

        clear_btn = QPushButton("🗑️  Clear")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(Theme.btn_secondary())
        clear_btn.clicked.connect(self._clear_cart)

        invoice_btn = QPushButton("✅  Create Bill")
        invoice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        invoice_btn.setFixedHeight(48)
        invoice_btn.setStyleSheet(Theme.btn_primary())
        invoice_btn.clicked.connect(self._generate_invoice)

        actions_row.addWidget(clear_btn)
        actions_row.addWidget(invoice_btn)
        root.addLayout(actions_row)

        # ── RBAC Enforcement ──────────────────────────
        self._enforce_rbac()

    def _enforce_rbac(self):
        from services.session import Session
        from services.enums import UserRole

        # Acharis and Workers cannot create bills
        can_bill = Session.is_authorized(
            [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]
        )

        # self.btn_new_bill.setEnabled(can_bill) # This button doesn't exist in SalesScreen
        self.search_btn.setEnabled(can_bill)

        if not can_bill:
            self.subtitle_lbl = QLabel("⚠️ You do not have permission to create bills.")
            self.subtitle_lbl.setStyleSheet(
                f"color: {Colors.RED}; font-size: {Fonts.BODY}px;"
            )
            self.layout().insertWidget(1, self.subtitle_lbl)

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    @handle_permissions
    def _load_items(self):
        items = self._inventory_service.get_items()
        if not items:
            return
        self._all_items = items
        names = [item["name"] for item in items]
        self._completer.setModel(QStringListModel(names))

    def refresh_data(self):
        self._load_items()

    # ------------------------------------------------------------------
    # Customer lookup
    # ------------------------------------------------------------------
    @handle_permissions
    def _handle_customer_lookup(self):
        phone = self.phone_input.text().strip()
        if not phone:
            QMessageBox.warning(self, "Missing Info", "Please enter a phone number.")
            return

        customer = self._customer_service.search_by_phone(phone)
        if customer:
            self.customer_input.setText(customer.get("name", ""))
            QMessageBox.information(
                self, "Found ✅", f"Buyer found: {customer.get('name')}"
            )
        else:
            QMessageBox.information(
                self,
                "Not Found",
                "No buyer found. Enter the name — we'll create a new record automatically.",
            )
            self.customer_input.setFocus()

    # ------------------------------------------------------------------
    # Cart operations
    # ------------------------------------------------------------------
    def _find_item_by_name(self, name: str) -> dict | None:
        name_lower = name.strip().lower()
        return next(
            (i for i in self._all_items if i["name"].lower() == name_lower), None
        )

    def _add_item_to_cart(self):
        name = self.search_input.text().strip()
        if not name:
            return

        item_data = self._find_item_by_name(name)
        if item_data is None:
            QMessageBox.warning(self, "Not Found", f"Item '{name}' not found.")
            return

        item_id = str(item_data["id"])
        existing = next((c for c in self._cart if c.item_id == item_id), None)
        if existing:
            existing.quantity += 1
        else:
            self._cart.append(
                CartItem(
                    item_id=item_id,
                    name=item_data["name"],
                    price=float(item_data.get("selling_price", 0) or 0.0),
                    gst_pct=float(item_data.get("gst_percent", 0.0) or 0.0),
                )
            )

        self.search_input.clear()
        self._refresh_table()

    def _remove_item(self, row: int):
        if 0 <= row < len(self._cart):
            self._cart.pop(row)
            self._refresh_table()

    def _clear_cart(self):
        self._cart.clear()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------
    def _refresh_table(self):
        self.table.setRowCount(len(self._cart))

        for row, ci in enumerate(self._cart):
            self.table.setRowHeight(row, 42)
            self.table.setItem(row, self.COL_NAME, QTableWidgetItem(ci.name))
            self.table.setItem(
                row, self.COL_PRICE, QTableWidgetItem(f"₹{ci.price:,.2f}")
            )
            self.table.setItem(
                row, self.COL_GST, QTableWidgetItem(f"{ci.gst_pct:.1f}%")
            )
            self.table.setItem(
                row, self.COL_TOTAL, QTableWidgetItem(f"₹{ci.line_total:,.2f}")
            )

            # Quantity spinner — compact style for table cells
            qty_spin = QSpinBox()
            qty_spin.setRange(1, 9999)
            qty_spin.setValue(ci.quantity)
            qty_spin.setFixedHeight(30)
            qty_spin.setStyleSheet(f"""
                QSpinBox {{
                    border: 1px solid {Colors.INPUT_BORDER};
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: {Fonts.BODY}px;
                    background: white;
                }}
                QSpinBox:focus {{
                    border-color: {Colors.INPUT_FOCUS};
                }}
            """)
            qty_spin.valueChanged.connect(
                lambda val, idx=row: self._on_qty_changed(idx, val)
            )
            self.table.setCellWidget(row, self.COL_QTY, qty_spin)

            # Remove button — visible with border
            rm_btn = QPushButton("✕")
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.setFixedSize(32, 30)
            rm_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Colors.RED};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                    background: white;
                }}
                QPushButton:hover {{
                    background: {Colors.ERROR_BG};
                    color: #dc2626;
                }}
            """)
            rm_btn.clicked.connect(lambda _, r=row: self._remove_item(r))
            self.table.setCellWidget(row, self.COL_REMOVE, rm_btn)

        self._update_totals()

    def _on_qty_changed(self, row: int, value: int):
        if row < len(self._cart):
            self._cart[row].quantity = value
            self.table.setItem(
                row,
                self.COL_TOTAL,
                QTableWidgetItem(f"₹{self._cart[row].line_total:,.2f}"),
            )
            self._update_totals()

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    def _update_totals(self):
        subtotal = sum(c.price * c.quantity for c in self._cart)
        total_gst = sum(c.price * c.quantity * c.gst_pct / 100 for c in self._cart)
        cgst = total_gst / 2
        sgst = total_gst / 2
        grand_total = subtotal + total_gst

        self.subtotal_lbl.setText(f"Subtotal: ₹{subtotal:,.2f}")
        self.cgst_lbl.setText(f"CGST: ₹{cgst:,.2f}")
        self.sgst_lbl.setText(f"SGST: ₹{sgst:,.2f}")
        self.grandtotal_lbl.setText(f"Total: ₹{grand_total:,.2f}")

    # ------------------------------------------------------------------
    # Invoice generation
    # ------------------------------------------------------------------
    @handle_permissions
    def _generate_invoice(self):
        phone = self.phone_input.text().strip()
        customer_name = self.customer_input.text().strip()

        if not phone:
            QMessageBox.warning(
                self, "Missing Info", "Please enter the buyer's phone number."
            )
            return
        if not customer_name:
            QMessageBox.warning(self, "Missing Info", "Please enter the buyer's name.")
            return
        if not self._cart:
            QMessageBox.warning(self, "Empty Bill", "Please add at least one item.")
            return

        customer_id = self._customer_service.ensure_customer(customer_name, phone)
        if customer_id is None:
            QMessageBox.critical(
                self, "Error", "Could not create buyer record. Check connection."
            )
            return

        payload_items = [
            {"item_id": c.item_id, "quantity": c.quantity} for c in self._cart
        ]
        sale_data = self._sales_service.create_sale(
            items=payload_items, customer_id=customer_id
        )
        if sale_data is None:
            QMessageBox.critical(
                self, "Error", "Failed to create bill. Check backend connection."
            )
            return

        invoice_number = sale_data.get("invoice_number")
        if not invoice_number:
            QMessageBox.critical(
                self, "Error", "Bill created but invoice number missing."
            )
            return

        pdf_path = self._sales_service.fetch_and_save_pdf(invoice_number)
        if pdf_path:
            self._sales_service.open_pdf(pdf_path)

        QMessageBox.information(
            self,
            "Bill Created ✅",
            f"Bill {invoice_number} created successfully!",
        )

        EventBus.emit(SALE_CREATED)
        self._clear_cart()
        self.customer_input.clear()
        self.phone_input.clear()
