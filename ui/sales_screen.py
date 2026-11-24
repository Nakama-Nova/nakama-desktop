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
    QCompleter,
    QComboBox,
    QFrame,
)
from PyQt6.QtCore import Qt, QStringListModel, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut


from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts
from ui.components.place_picker import PlacePicker, fetch_places, selling_places
from ui.errors import handle_permissions
from ui.sales_history_screen import METHODS, is_cancelled
from ui.workers import load_async, run_async
from services.sales_service import BillPdfError, SalesService
from services.customer_service import CustomerService
from services.inventory_service import InventoryService
from services.event_bus import EventBus, SALE_CREATED
from services import app_settings
from services.money import inr


class QtyStepper(QFrame):
    """[ - 2 + ]: a quantity the counter can change with one tap, instead of a tiny spin box."""

    valueChanged = pyqtSignal(int)

    def __init__(self, value: int = 1, maximum: int = 9999):
        super().__init__()
        self._value, self._max = value, maximum
        self.setObjectName("qty")
        self.setFixedHeight(32)
        self.setStyleSheet(
            f"QFrame#qty {{ background: {Colors.CARD_BG}; border: 1px solid {Colors.INPUT_BORDER}; border-radius: 6px; }}"
            f"QFrame#qty QPushButton {{ background: transparent; border: none; color: {Colors.TEXT_SECONDARY};"
            f" font-size: 16px; min-width: 28px; max-width: 28px; }}"
            f"QFrame#qty QPushButton:hover {{ background: {Colors.SIDEBAR_HOVER}; color: {Colors.TEXT_PRIMARY}; }}"
            f"QFrame#qty QLabel {{ border: none; background: transparent; font-weight: 700; color: {Colors.TEXT_PRIMARY}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.minus = QPushButton("\u2212")
        self.minus.setToolTip("One less")
        self.minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minus.clicked.connect(lambda: self.setValue(self._value - 1))
        self.label = QLabel(str(value))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumWidth(34)
        self.plus = QPushButton("+")
        self.plus.setToolTip("One more")
        self.plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus.clicked.connect(lambda: self.setValue(self._value + 1))
        for w in (self.minus, self.label, self.plus):
            row.addWidget(w)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        value = max(1, min(self._max, int(value)))
        if value != self._value:
            self._value = value
            self.label.setText(str(value))
            self.valueChanged.emit(value)


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

        # The last few products put on a bill here, one tap to add again
        self.recent_row = QWidget()
        recent_layout = QHBoxLayout(self.recent_row)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(8)
        recent_label = QLabel("Recently sold")
        recent_label.setStyleSheet(f"font-size: {Fonts.BODY_SM}px; color: {Colors.TEXT_MUTED};")
        recent_layout.addWidget(recent_label)
        self._recent_layout = recent_layout
        self.recent_row.hide()
        left.addWidget(self.recent_row)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Item", "Price", "Qty", "GST", "Amount", ""]
        )
        for col, tip in ((1, "Price before GST"), (4, "Amount with GST")):
            self.table.horizontalHeaderItem(col).setToolTip(tip)
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
        self.buyer_note = QLabel("")
        self.buyer_note.setWordWrap(True)
        self.buyer_note.hide()
        col.addWidget(self.buyer_note)

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
        self.pay_pick.setCurrentIndex(self._default_payment_index())
        self.pay_pick.setStyleSheet(Theme.input_style())
        self.pay_pick.setMinimumHeight(38)
        col.addWidget(self.pay_pick)

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
        self._show_recent()
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
            self._note("Can't look up buyers while offline. Type the name; it is saved with the bill.", "muted")
            self.customer_input.setFocus()
            return
        if customer:
            name = customer.get("name", "")
            self.customer_input.setText(name)
            self._note(f"{name} is already a buyer.", "good")
            customer_id = customer.get("id")
            if customer_id:  # how many bills they have had, without holding up the sale
                run_async(
                    lambda: SalesService().get_sales(customer_id=str(customer_id)),
                    lambda sales, n=name, p=phone: self._show_history(n, p, sales),
                    lambda _exc: None,
                )
        else:
            self._note("No buyer has this number yet. The name you type is saved as a new buyer.", "warn")
            self.customer_input.setFocus()

    def _note(self, text: str, tone: str) -> None:
        """A line under the buyer fields, instead of a pop-up in the middle of a sale."""
        colour = {"good": Colors.SUCCESS, "warn": Colors.ORANGE, "muted": Colors.TEXT_MUTED}[tone]
        self.buyer_note.setText(text)
        self.buyer_note.setStyleSheet(f"font-size: {Fonts.BODY_SM}px; color: {colour};")
        self.buyer_note.setVisible(bool(text))

    def _show_history(self, name: str, phone: str, sales) -> None:
        """The earlier-bills count, if this is still the buyer on screen."""
        if self.phone_input.text().strip() != phone or sales is None:
            return
        earlier = sum(1 for s in sales if not is_cancelled(s))
        self._note(
            f"{name} is already a buyer, with {earlier} earlier bill{'s' if earlier != 1 else ''}."
            if earlier
            else f"{name} is already a buyer, with no earlier bills.",
            "good",
        )

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
        self._add_item(item_data)

    def _add_item(self, item_data: dict) -> None:
        """Put one more of this product on the bill (the search box and the chips both land here)."""
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
        self._remember_recent(item_id)
        self._refresh_table()

    def _remember_recent(self, item_id: str) -> None:
        try:
            ids = [item_id] + [i for i in app_settings.get("recent_items") if i != item_id]
            app_settings.set_value("recent_items", ids[:5])
        except OSError:
            pass  # a preference that could not be saved is not worth stopping a sale for
        self._show_recent()

    def _show_recent(self) -> None:
        """Chips for the products most recently put on a bill (hidden until there are any)."""
        while self._recent_layout.count() > 1:  # keep the "Recently sold" label
            item = self._recent_layout.takeAt(1)
            old = item.widget()
            if old is not None:
                old.hide()
                old.setParent(None)  # gone at once, not when Qt gets round to deleting it
                old.deleteLater()
        by_id = {str(i["id"]): i for i in self._all_items}
        shown = 0
        for item_id in app_settings.get("recent_items"):
            data = by_id.get(item_id)
            if data is None:
                continue
            name = data["name"]
            chip = QPushButton(name if len(name) <= 26 else name[:25] + "…")
            chip.setToolTip(f"Add {name}")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background: {Colors.CARD_BG}; color: {Colors.TEXT_SECONDARY};"
                f" border: 1px solid {Colors.INPUT_BORDER}; border-radius: 14px; padding: 4px 12px;"
                f" font-size: {Fonts.BODY_SM}px; }}"
                f"QPushButton:hover {{ border-color: {Colors.BRAND_GOLD}; color: {Colors.TEXT_PRIMARY}; }}"
            )
            chip.clicked.connect(lambda _=False, d=data: self._add_item(d))
            self._recent_layout.addWidget(chip)
            shown += 1
        self._recent_layout.addStretch()
        self.recent_row.setVisible(shown > 0)

    def _remove_item(self, row: int):
        if 0 <= row < len(self._cart):
            self._cart.pop(row)
            self._refresh_table()

    def _payment(self) -> dict:
        """What to tell the server about payment: the method and "paid", or just "pending"."""
        method = self.pay_pick.currentData()
        if method is None:
            return {"payment_status": "pending"}
        return {"payment_method": method, "payment_status": "paid"}

    def _default_payment_index(self) -> int:
        """Settings: a new bill starts as Cash or as Not paid yet."""
        return self.pay_pick.count() - 1 if app_settings.get("default_payment") == "none" else 0

    def apply_settings(self) -> None:
        """Settings were saved: an empty bill takes the new starting choice at once."""
        if not self._cart:
            self.pay_pick.setCurrentIndex(self._default_payment_index())

    def _clear_cart(self):
        self._bill_key = None
        self._note("", "muted")
        self.pay_pick.setCurrentIndex(self._default_payment_index())  # back to the usual for the next bill
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
            self.table.setItem(row, self.COL_PRICE, self._number_cell(inr(ci.price)))
            self.table.setItem(row, self.COL_GST, self._number_cell(f"{ci.gst_pct:g}%"))
            self.table.setItem(row, self.COL_TOTAL, self._number_cell(inr(ci.line_total), bold=True))

            # Quantity: - n +
            stepper = QtyStepper(ci.quantity)
            stepper.valueChanged.connect(lambda val, idx=row: self._on_qty_changed(idx, val))
            self.table.setCellWidget(row, self.COL_QTY, stepper)

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
                    background: {Colors.CARD_BG};
                }}
                QPushButton:hover {{
                    background: {Colors.ERROR_BG};
                    color: {Colors.RED};
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
        grand_total = subtotal + total_gst

        self.subtotal_lbl.setText(inr(subtotal))
        self.cgst_lbl.setText(inr(cgst))
        self.sgst_lbl.setText(inr(sgst))
        self.grandtotal_lbl.setText(inr(grand_total))

    # ------------------------------------------------------------------
    # Offline billing
    # ------------------------------------------------------------------
    def _client_id_for_cart(self, phone: str) -> str:
        """One id per distinct bill. If the connection drops after the server
        recorded it, the offline copy carries the same id and the server skips
        it instead of billing the buyer twice. Changing the cart makes a new bill."""
        key = (phone, tuple((c.item_id, c.quantity) for c in self._cart))
        if key != self._bill_key:
            self._bill_key, self._bill_client_id = key, str(uuid.uuid4())
        return self._bill_client_id

    def _save_offline(self, customer_name: str, phone: str, client_id: str):
        lines = [
            {"item_id": c.item_id, "quantity": c.quantity, "price": c.price}
            for c in self._cart
        ]
        pay = self._payment()
        ref = self._sales_service.queue_offline_sale(
            lines, customer_name, phone, client_id, self._sold_from(),
            payment_method=pay.get("payment_method"), payment_status=pay["payment_status"],
        )
        paid_note = (
            "\n\nHow it was paid is kept with it. A server that has not been updated yet shows it as "
            "not paid until you correct it in Bill History."
            if pay["payment_status"] == "paid"
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
            sale_data = self._sales_service.create_sale(
                items=payload_items, customer_id=customer_id, client_id=client_id, **extra, **self._payment()
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
            pdf = self._sales_service.fetch_and_save_pdf(invoice_number)
            if app_settings.get("open_bill_pdf"):  # Settings: some counters would rather not have it pop up
                self._sales_service.open_pdf(pdf)
        except BillPdfError as exc:
            QMessageBox.warning(
                self,
                "Bill saved, PDF not shown",
                f"Bill {invoice_number} was saved, but its PDF could not be opened.\n\n{exc}\n\n"
                "You can open it again from Bill History.",
            )

        QMessageBox.information(
            self,
            "Bill created",
            f"Bill {invoice_number} created successfully!",
        )

        EventBus.emit(SALE_CREATED)
        self._clear_cart()
        self.customer_input.clear()
        self.phone_input.clear()
