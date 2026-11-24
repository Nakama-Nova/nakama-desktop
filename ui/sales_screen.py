"""
ui/sales_screen.py

Billing POS screen — simplified for non-technical users.
- "Item ID" column hidden (users don't need UUIDs)
- Labels: "Buyer Phone", "Buyer Name"
- Button text: "✅ Create Bill"
- Remove item button per row
"""

import uuid

import requests
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
    QDoubleSpinBox,
    QComboBox,
    QCompleter,
    QComboBox,
    QFrame,
)
from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtGui import QKeySequence, QShortcut


from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts
from ui.components.place_picker import PlacePicker, fetch_places, selling_places
from ui.errors import handle_permissions
from ui.sales_history_screen import METHODS
from ui.workers import load_async
from services.sales_service import BillPdfError, SalesService
from services.customer_service import CustomerService
from services.inventory_service import InventoryService
from services.event_bus import EventBus, SALE_CREATED
from services.money import inr
from services.billing import change_or_balance, discount_amount, payment_status


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
    # The id of the bill being rung up (see _client_id_for_cart).
    _bill_key = None
    _bill_client_id = None
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
        self._held: dict = {}  # item id -> units set aside for confirmed orders

        self.setStyleSheet(Theme.content_bg())
        self._build_ui()
        # items load when the screen is first opened (refresh_data), not while the
        # window is still being built, so starting the app never waits on the server

    def _build_ui(self):
        """Counter layout: items on the left, the buyer and the bill's total always in view on
        the right, so Create bill never scrolls away."""
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(12)

        header = QLabel("New bill")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        root.addWidget(header)
        hint = QLabel("Search or scan to add items. The server numbers the bill once it is saved.")
        hint.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};")
        root.addWidget(hint)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        # ── Left: add items, then the lines of the bill ──
        left = QVBoxLayout()
        left.setSpacing(12)
        body.addLayout(left, 1)

        item_row = QHBoxLayout()
        item_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by item name, or scan its tag")
        self.search_input.setStyleSheet(Theme.input_style())
        self.search_input.setMinimumHeight(40)
        self._completer = QCompleter()
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_input.setCompleter(self._completer)
        self.search_input.returnPressed.connect(self._add_item_to_cart)
        item_row.addWidget(self.search_input, 1)

        add_btn = IconButton("Add item")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setMinimumHeight(40)
        add_btn.setStyleSheet(Theme.btn("primary", "md"))
        add_btn.clicked.connect(self._add_item_to_cart)
        item_row.addWidget(add_btn)
        left.addLayout(item_row)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Item", "Price (before GST)", "Qty", "GST", "Amount (with GST)", ""]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(self.COL_REMOVE, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_REMOVE, 52)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        Theme.style_table(self.table)
        left.addWidget(self.table, 1)

        # ── Right: buyer, totals, Create bill ──
        panel = QFrame()
        panel.setObjectName("billpanel")
        panel.setFixedWidth(340)
        panel.setStyleSheet(
            f"QFrame#billpanel {{ background: {Colors.CARD_BG}; border: 1px solid {Colors.CARD_BORDER};"
            f" border-radius: 10px; }} QFrame#billpanel QLabel {{ border: none; background: transparent; }}"
        )
        col = QVBoxLayout(panel)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(10)
        body.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)

        buyer_lbl = QLabel("Buyer")
        buyer_lbl.setStyleSheet(Theme.subheading())
        col.addWidget(buyer_lbl)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Phone number")
        self.phone_input.setStyleSheet(Theme.input_style())
        self.phone_input.setMinimumHeight(38)
        col.addWidget(self.phone_input)
        self.customer_input = QLineEdit()
        self.customer_input.setPlaceholderText("Name (fills in when the phone is found)")
        self.customer_input.setStyleSheet(Theme.input_style())
        self.customer_input.setMinimumHeight(38)
        col.addWidget(self.customer_input)
        self.search_btn = IconButton("Find buyer by phone")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setStyleSheet(Theme.btn("secondary", "sm", outline=True))
        self.search_btn.clicked.connect(self._handle_customer_lookup)
        col.addWidget(self.search_btn)

        # Where the bill is sold from: shown only when more than one place can sell
        self.place_box = QWidget()
        place_col = QVBoxLayout(self.place_box)
        place_col.setContentsMargins(0, 0, 0, 0)
        place_col.setSpacing(4)
        place_lbl = QLabel("Sold from")
        place_lbl.setStyleSheet(Theme.label())
        self.place_pick = PlacePicker("sale")
        place_col.addWidget(place_lbl)
        place_col.addWidget(self.place_pick)
        self.place_box.setVisible(False)
        col.addWidget(self.place_box)

        col.addSpacing(6)
        self.subtotal_lbl = self._money_row(col, "Subtotal")
        self.cgst_lbl = self._money_row(col, "CGST")
        self.sgst_lbl = self._money_row(col, "SGST")

        # Discount: rupees or per cent off the bill total (the server takes the rupees off items + GST)
        drow = QHBoxLayout()
        drow_lbl = QLabel("Give discount")
        drow_lbl.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};")
        self.discount_in = QDoubleSpinBox()
        self.discount_in.setRange(0, 10_000_000)
        self.discount_in.setDecimals(2)
        self.discount_in.setStyleSheet(Theme.input_style())
        self.discount_in.valueChanged.connect(self._update_totals)
        self.discount_kind = QComboBox()
        self.discount_kind.addItem("₹", "amount")
        self.discount_kind.addItem("%", "percent")
        self.discount_kind.setStyleSheet(Theme.input_style())
        self.discount_kind.currentIndexChanged.connect(self._update_totals)
        drow.addWidget(drow_lbl)
        drow.addWidget(self.discount_in, 1)
        drow.addWidget(self.discount_kind)
        col.addLayout(drow)
        self.discount_lbl = self._money_row(col, "Discount")

        total_row = QHBoxLayout()
        total_name = QLabel("Total")
        total_name.setStyleSheet(f"font-size: {Fonts.BODY}px; font-weight: 600; color: {Colors.TEXT_SECONDARY};")
        self.grandtotal_lbl = QLabel(inr(0))
        self.grandtotal_lbl.setStyleSheet(
            f"font-size: 30px; font-weight: 700; color: {Colors.TEXT_PRIMARY};"
        )
        self.grandtotal_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_row.addWidget(total_name)
        total_row.addWidget(self.grandtotal_lbl, 1)
        col.addLayout(total_row)

        # How the buyer paid. Cash is the usual counter sale; "Not paid yet" leaves the bill open.
        pay_lbl = QLabel("Paid by")
        pay_lbl.setStyleSheet(Theme.label())
        col.addWidget(pay_lbl)
        self.pay_pick = QComboBox()
        for label, value in METHODS:
            self.pay_pick.addItem(label, value)
        self.pay_pick.addItem("Not paid yet", None)
        self.pay_pick.setStyleSheet(Theme.input_style())
        self.pay_pick.setMinimumHeight(38)
        col.addWidget(self.pay_pick)
        rrow = QHBoxLayout()
        rrow_lbl = QLabel("Received")
        rrow_lbl.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};")
        self.received_in = QDoubleSpinBox()
        self.received_in.setRange(0, 10_000_000)
        self.received_in.setDecimals(2)
        self.received_in.setPrefix("₹")
        self.received_in.setStyleSheet(Theme.input_style())
        self.received_in.valueChanged.connect(self._received_changed)
        self.pay_pick.currentIndexChanged.connect(self._pay_pick_changed)
        rrow.addWidget(rrow_lbl)
        rrow.addWidget(self.received_in, 1)
        col.addLayout(rrow)
        self.pay_note = QLabel("")
        self.pay_note.setStyleSheet(f"font-size: {Fonts.BODY}px; font-weight: 600;")
        self.pay_note.setAlignment(Qt.AlignmentFlag.AlignRight)
        col.addWidget(self.pay_note)

        self.invoice_btn = IconButton("Create bill")
        self.invoice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.invoice_btn.setMinimumHeight(48)
        self.invoice_btn.setStyleSheet(Theme.btn("primary", "lg"))
        self.invoice_btn.clicked.connect(self._generate_invoice)
        self.invoice_btn.setToolTip("Ctrl+Enter")
        col.addWidget(self.invoice_btn)

        # Quiet on purpose: next to Create bill it must not be the easy button to hit
        self.clear_btn = IconButton("Clear bill")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {Colors.TEXT_SECONDARY};"
            f" font-size: {Fonts.BODY}px; padding: 6px; }}"
            f"QPushButton:hover {{ color: {Colors.RED}; }}"
        )
        self.clear_btn.clicked.connect(self._clear_cart)
        col.addWidget(self.clear_btn)

        self._bill_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._bill_shortcut.activated.connect(self._generate_invoice)

        # ── RBAC Enforcement ──────────────────────────
        self._enforce_rbac()

    @staticmethod
    def _money_row(layout, name: str) -> QLabel:
        """A 'Subtotal ........ amount' line; returns the amount label."""
        row = QHBoxLayout()
        label = QLabel(name)
        label.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};")
        value = QLabel(inr(0))
        value.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_PRIMARY};")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)
        row.addWidget(value, 1)
        layout.addLayout(row)
        return value

    def _enforce_rbac(self):
        from services.session import Session

        # Acharis and Workers cannot create bills
        can_bill = Session.can("sales:sale:create")

        # self.btn_new_bill.setEnabled(can_bill) # This button doesn't exist in SalesScreen
        self.search_btn.setEnabled(can_bill)

        if not can_bill:
            self.subtitle_lbl = QLabel("You do not have permission to create bills.")
            self.subtitle_lbl.setStyleSheet(
                f"color: {Colors.RED}; font-size: {Fonts.BODY}px;"
            )
            self.layout().insertWidget(1, self.subtitle_lbl)

    # ------------------------------------------------------------------
    # Data Loading
    # ------------------------------------------------------------------
    @handle_permissions
    def _load_items(self):
        self._apply_items(self._inventory_service.get_items(allow_cached=True))

    def _apply_items(self, items):
        if not items:
            return
        self._all_items = items
        names = [item["name"] for item in items]
        self._completer.setModel(QStringListModel(names))

    def refresh_data(self):
        self._load_items()
        load_async(self, self._fetch_context, self._show_context)

    def refresh_async(self, _checked=False):
        """The items (the last saved list when offline), the places and the holds, all in the
        background: the window never waits for the server."""
        load_async(self, self._fetch_context, self._show_context)

    def _fetch_context(self):
        return self._inventory_service.get_items(allow_cached=True), fetch_places(), self._inventory_service.held()

    def _show_context(self, data):
        items, places, held = data
        self._apply_items(items)
        self._show_places(places)
        if held is not None:  # unreadable: keep what was known
            self._held = held

    def _sellable_now(self, item_data: dict) -> int | None:
        """What can be sold of this item now (the shelf minus what is held for confirmed orders),
        or None when nothing is held. The server is the judge; this only explains it early."""
        held = int(self._held.get(str(item_data["id"]), 0))
        if not held:
            return None
        return int(item_data.get("current_stock") or 0) - held

    def _show_places(self, places):
        """Ask where a bill is sold from only when there is a choice; with one shop the server
        fills it in. A failed read (None) leaves the picker as it was."""
        if places is None:
            return
        sellers = selling_places(places)
        self.place_pick.set_places(sellers)
        self.place_box.setVisible(len(sellers) >= 2)

    def _sold_from(self) -> str | None:
        return self.place_pick.place_id() if not self.place_box.isHidden() else None

    # ------------------------------------------------------------------
    # Customer lookup
    # ------------------------------------------------------------------
    @handle_permissions
    def _handle_customer_lookup(self):
        phone = self.phone_input.text().strip()
        if not phone:
            QMessageBox.warning(self, "Missing Info", "Please enter a phone number.")
            return

        try:
            customer = self._customer_service.search_by_phone(phone)
        except requests.RequestException:
            QMessageBox.information(
                self,
                "No internet",
                "Can't look up buyers right now. Type the buyer's name — it is "
                "saved with the bill.",
            )
            self.customer_input.setFocus()
            return
        if customer:
            self.customer_input.setText(customer.get("name", ""))
            QMessageBox.information(
                self, "Buyer found", f"Buyer found: {customer.get('name')}"
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
        sellable = self._sellable_now(item_data)
        if sellable is not None and (existing.quantity if existing else 0) + 1 > sellable:
            held = int(self._held.get(item_id, 0))
            QMessageBox.warning(
                self,
                "Stock set aside",
                f"{item_data['name']}: {held} {'is' if held == 1 else 'are'} set aside for confirmed orders, "
                f"so only {max(sellable, 0)} can be sold now.\n\nThe rest is promised to a customer.",
            )
            return
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
        self._bill_key = None
        self.pay_pick.setCurrentIndex(0)  # back to cash for the next bill
        self._cart.clear()
        self._received_touched = False  # the next bill starts as "paid in full, cash, no discount"
        self.discount_in.setValue(0)
        self._refresh_table()

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------
    def _refresh_table(self):
        self.table.setRowCount(len(self._cart))

        for row, ci in enumerate(self._cart):
            self.table.setRowHeight(row, 42)
            self.table.setItem(row, self.COL_NAME, QTableWidgetItem(ci.name))
            self.table.setItem(row, self.COL_PRICE, self._number_cell(inr(ci.price)))
            self.table.setItem(row, self.COL_GST, self._number_cell(f"{ci.gst_pct:.1f}%"))
            self.table.setItem(row, self.COL_TOTAL, self._number_cell(inr(ci.line_total), bold=True))

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
            rm_btn = IconButton("✕")
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
                    color: #B3261E;
                }}
            """)
            rm_btn.clicked.connect(lambda _, r=row: self._remove_item(r))
            self.table.setCellWidget(row, self.COL_REMOVE, rm_btn)

        self._update_totals()

    @staticmethod
    def _number_cell(text: str, bold: bool = False) -> QTableWidgetItem:
        """A money or percent cell: right-aligned so the digits line up down the column."""
        cell = QTableWidgetItem(text)
        cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if bold:
            font = cell.font()
            font.setBold(True)
            cell.setFont(font)
        return cell

    def _on_qty_changed(self, row: int, value: int):
        if row < len(self._cart):
            self._cart[row].quantity = value
            self.table.setItem(row, self.COL_TOTAL, self._number_cell(inr(self._cart[row].line_total), bold=True))
            self._update_totals()

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    def _update_totals(self):
        subtotal = sum(c.price * c.quantity for c in self._cart)
        total_gst = sum(c.price * c.quantity * c.gst_pct / 100 for c in self._cart)
        cgst = total_gst / 2
        sgst = total_gst / 2
        gross = subtotal + total_gst
        discount = discount_amount(gross, self.discount_kind.currentData(), self.discount_in.value())
        grand_total = gross - discount
        self._discount, self._total = discount, grand_total

        self.subtotal_lbl.setText(inr(subtotal))
        self.cgst_lbl.setText(inr(cgst))
        self.sgst_lbl.setText(inr(sgst))
        self.discount_lbl.setText(f"-{inr(discount)}" if discount else inr(0))
        self.grandtotal_lbl.setText(inr(grand_total))
        if not self._received_touched:  # until the cashier types an amount, the customer pays it all
            self.received_in.blockSignals(True)
            self.received_in.setValue(round(grand_total, 2))
            self.received_in.blockSignals(False)
        self._show_pay_note()

    _received_touched = False
    _discount = 0.0
    _total = 0.0

    def _pay_pick_changed(self, _i=0):
        self.received_in.setEnabled(self.pay_pick.currentData() is not None)  # "Not paid yet": nothing handed over
        self._show_pay_note()

    def _received_changed(self, _v=0):
        self._received_touched = True
        self._show_pay_note()

    def _show_pay_note(self):
        kind, rupees = change_or_balance(self._total, self.received_in.value())
        if not self._cart or rupees == 0 or self.pay_pick.currentData() is None:
            self.pay_note.setText("")
            return
        word, colour = ("Hand back", Colors.SUCCESS) if kind == "change" else ("Balance to pay", Colors.ORANGE)
        self.pay_note.setStyleSheet(f"font-size: {Fonts.BODY}px; font-weight: 600; color: {colour};")
        self.pay_note.setText(f"{word} {inr(rupees)}")

    def _payment(self) -> dict:
        """What to tell the server about payment: the method and paid / part paid, or just "pending"."""
        method = self.pay_pick.currentData()
        if method is None:  # "Not paid yet"
            return {"payment_status": "pending"}
        return {"payment_method": method, "payment_status": payment_status(self._total, self.received_in.value())}

    # ------------------------------------------------------------------
    # Offline billing
    # ------------------------------------------------------------------
    def _client_id_for_cart(self, phone: str) -> str:
        """One id per distinct bill. If the connection drops after the server
        recorded it, the offline copy carries the same id and the server skips
        it instead of billing the buyer twice. Changing the cart makes a new bill."""
        pay = self._payment()
        key = (phone, tuple((c.item_id, c.quantity) for c in self._cart), self._discount, pay.get("payment_method"), pay["payment_status"])
        if key != self._bill_key:
            self._bill_key, self._bill_client_id = key, str(uuid.uuid4())
        return self._bill_client_id

    def _save_offline(self, customer_name: str, phone: str, client_id: str) -> bool:
        pay = self._payment()
        if self._discount:  # the sync does not carry a discount yet: a bill saved now would come out at full price
            QMessageBox.warning(
                self,
                "Discount needs a connection",
                "There is no connection, and a discount cannot be saved offline yet.\n\n"
                "Take the discount off to save this bill on this computer, or press Create bill again "
                "when the connection is back (it will not be billed twice).",
            )
            return False
        lines = [
            {"item_id": c.item_id, "quantity": c.quantity, "price": c.price}
            for c in self._cart
        ]
        ref = self._sales_service.queue_offline_sale(
            lines, customer_name, phone, client_id, self._sold_from(),
            payment_method=pay.get("payment_method"), payment_status=pay["payment_status"],
        )
        paid_note = (
            "\n\nHow it was paid is kept with it, but the server shows it as not paid until "
            "you correct it in Bill History."
            if pay["payment_status"] != "pending"
            else ""
        )
        QMessageBox.information(
            self,
            "Saved offline",
            f"No internet, so this bill is saved on this computer (ref {ref}).\n\n"
            "It is sent automatically when the connection is back, and the "
            "official bill number is given then. A printed bill is not "
            "available until then." + paid_note,
        )
        self._clear_cart()
        self.customer_input.clear()
        self.phone_input.clear()
        return True

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

        client_id = self._client_id_for_cart(phone)

        # No connection: keep the sale on this computer and sync it later.
        if not self._sales_service.is_online():
            self._save_offline(customer_name, phone, client_id)
            return

        try:
            customer_id = self._customer_service.ensure_customer(customer_name, phone)
            if customer_id is None:
                QMessageBox.critical(
                    self, "Error", "Could not create buyer record. Check connection."
                )
                return

            payload_items = [
                {"item_id": c.item_id, "quantity": c.quantity} for c in self._cart
            ]
            place = self._sold_from()
            extra = {"location_id": place} if place else {}  # one shop: the server fills it in
            pay = self._payment()
            extra.update(pay)
            if self._discount:
                extra["discount"] = self._discount
            sale_data = self._sales_service.create_sale(
                items=payload_items, customer_id=customer_id, client_id=client_id, **extra
            )
        except requests.RequestException:
            # The connection dropped after the online check. The server may or
            # may not have recorded the bill; the shared client_id covers both.
            self._save_offline(customer_name, phone, client_id)
            return
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

        try:
            self._sales_service.open_pdf(self._sales_service.fetch_and_save_pdf(invoice_number))
        except BillPdfError as exc:
            QMessageBox.warning(
                self,
                "Bill saved, PDF not shown",
                f"Bill {invoice_number} was saved, but its PDF could not be opened.\n\n{exc}\n\n"
                "You can open it again from Bill History.",
            )

        note = ""
        kind, rupees = change_or_balance(self._total, self.received_in.value())
        if pay["payment_status"] != "pending" and kind == "change" and rupees and pay.get("payment_method") == "cash":
            note = f"\n\nHand back {inr(rupees)}."
        elif kind == "balance":
            note = f"\n\nBalance to collect: {inr(rupees)}."
        # An older server would ignore the discount or the payment and bill in full: say so, never silently.
        if float(sale_data.get("discount") or 0) != self._discount or (
            sale_data.get("payment_status") and sale_data["payment_status"] != pay["payment_status"]
        ):
            note += (
                "\n\n⚠️ The server did not record the discount or payment as entered. "
                "Check this bill in Bill History and correct it."
            )
        QMessageBox.information(
            self,
            "Bill created",
            f"Bill {invoice_number} created successfully!{note}",
        )

        EventBus.emit(SALE_CREATED)
        self._clear_cart()
        self.customer_input.clear()
        self.phone_input.clear()
