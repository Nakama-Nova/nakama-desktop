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
    QScrollArea,
)
from PyQt6.QtCore import Qt, QStringListModel, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut


from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts
from ui.components.place_picker import PlacePicker, fetch_places, selling_places
from ui.errors import handle_permissions
from ui.sales_history_screen import METHODS, is_cancelled
from ui.receipt_dialog import ReceiptDialog, shop_details
from ui.receipt_render import receipt_from_sale
from ui.workers import load_async, run_async
from services.sales_service import BillPdfError, SalesService
from services.customer_service import CustomerService
from services.inventory_service import InventoryService
from services.event_bus import EventBus, SALE_CREATED
from services import app_settings
from services.money import inr
from services import gst
from services.billing import change_or_balance, discount_amount, payment_status, received_total


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
        # Sized by the column modes above, not by the generic column-shrinking: on a narrow window
        # the item name gives way (it is cut with ...), the money and the quantity never are.
        self.table.setProperty("elastic", True)
        left.addWidget(self.table, 1)

        # ── Right: buyer, totals, Create bill ──
        panel = QFrame()
        panel.setObjectName("billpanel")
        panel.setFixedWidth(340)
        panel.setStyleSheet(
            f"QFrame#billpanel {{ background: {Colors.CARD_BG}; border: 1px solid {Colors.CARD_BORDER};"
            f" border-radius: 10px; }} QFrame#billpanel QLabel {{ border: none; background: transparent; }}"
        )
        # The buyer and payment details scroll when the window is short. The total, Create bill and
        # the quiet buttons stay pinned under them, so they are never below the bottom of the screen.
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        col = QVBoxLayout(inner)
        col.setContentsMargins(18, 16, 18, 8)
        col.setSpacing(10)
        scroller.setWidget(inner)
        outer.addWidget(scroller, 1)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {Colors.CARD_BORDER}; border: none;")
        outer.addWidget(rule)
        foot_box = QWidget()
        foot_box.setStyleSheet("background: transparent;")
        foot = QVBoxLayout(foot_box)
        foot.setContentsMargins(18, 10, 18, 12)
        foot.setSpacing(6)
        outer.addWidget(foot_box)
        body.addWidget(panel)

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
        self.gstin_input = QLineEdit()
        self.gstin_input.setPlaceholderText("Buyer's GSTIN (only for a business buyer)")
        self.gstin_input.setStyleSheet(Theme.input_style())
        self.gstin_input.setMinimumHeight(38)
        self.gstin_input.setMaxLength(15)
        self.gstin_input.textChanged.connect(self._gstin_changed)
        col.addWidget(self.gstin_input)
        self.gstin_note = QLabel("")
        self.gstin_note.setWordWrap(True)
        self.gstin_note.setVisible(False)
        col.addWidget(self.gstin_note)
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
        foot.addLayout(total_row)

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
        self.split_box = QVBoxLayout()
        col.addLayout(self.split_box)
        self.split_btn = QPushButton("➕  Split payment (another method)")
        self.split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.split_btn.setStyleSheet(Theme.btn("secondary", "sm", outline=True))
        self.split_btn.clicked.connect(self._add_split_row)
        col.addWidget(self.split_btn)
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
        foot.addWidget(self.invoice_btn)

        # Quiet on purpose: next to Create bill it must not be the easy button to hit
        self.clear_btn = IconButton("Clear bill")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {Colors.TEXT_SECONDARY};"
            f" font-size: {Fonts.BODY}px; padding: 6px; }}"
            f"QPushButton:hover {{ color: {Colors.RED}; }}"
        )
        self.clear_btn.clicked.connect(self._clear_cart)
        foot.addWidget(self.clear_btn)

        # Quiet too: a paper receipt (80 mm roll, A5, A4) of the bill just made, even a provisional one made offline
        self.receipt_btn = IconButton("🧾  Print last receipt")
        self.receipt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.receipt_btn.setStyleSheet(self.clear_btn.styleSheet().replace(Colors.RED, Colors.TEXT_PRIMARY))
        self.receipt_btn.setEnabled(False)
        self.receipt_btn.clicked.connect(self._print_last_receipt)
        foot.addWidget(self.receipt_btn)

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
        self._clear_split_rows()
        self.gstin_input.clear()
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

    _split_rows: list = []

    def _add_split_row(self):
        """Another payment on the same bill (part cash, part UPI...): a method and an amount."""
        self._received_touched = True  # the cashier is now dividing the money: stop filling it in
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        method = QComboBox()
        for label, value in METHODS:
            method.addItem(label, value)
        method.setStyleSheet(Theme.input_style())
        amount = QDoubleSpinBox()
        amount.setRange(0, 10_000_000)
        amount.setDecimals(2)
        amount.setPrefix("₹")
        amount.setStyleSheet(Theme.input_style())
        amount.setValue(max(0.0, round(self._total - self._received(), 2)))
        amount.valueChanged.connect(self._received_changed)
        h.addWidget(method)
        h.addWidget(amount, 1)
        self.split_box.addWidget(row)
        self._split_rows = [*self._split_rows, (method, amount, row)]
        self._show_pay_note()

    def _clear_split_rows(self):
        for _m, _a, row in self._split_rows:
            row.setParent(None)
            row.deleteLater()
        self._split_rows = []

    def _received(self) -> float:
        """Everything handed over: the first amount plus any split rows."""
        return received_total(self.received_in.value(), *[a.value() for _m, a, _r in self._split_rows])

    _last_bill = None

    def _remember_bill(self, sale: dict, provisional: bool):
        """Keep the bill just made (before the cart is cleared) so its receipt can be printed."""
        items = sale.get("items") or [
            {"item_name": c.name, "quantity": c.quantity, "price_at_sale": c.price, "gst_percent": c.gst_pct} for c in self._cart
        ]
        sale = {
            **sale, "customer_name": self.customer_input.text().strip(), "customer_phone": self.phone_input.text().strip(),
            "customer_gstin": gst.clean(self.gstin_input.text()) or None,
        }
        self._last_bill = (sale, items, provisional)
        self.receipt_btn.setEnabled(True)

    def _print_last_receipt(self):
        if not self._last_bill:
            return
        sale, items, provisional = self._last_bill
        ReceiptDialog(self, receipt_from_sale(sale, items, shop_details(), provisional)).exec()

    def _gstin_changed(self, text: str):
        """Tell the cashier at once if a GSTIN is mistyped, or which state it belongs to."""
        problem, state = gst.gstin_problem(text), gst.state_of(text)
        if not text.strip() or (problem and len(text.strip()) < 15):
            self.gstin_note.setVisible(False)
        elif problem:
            self.gstin_note.setStyleSheet(f"color: {Colors.DANGER}; font-size: {Fonts.BODY}px;")
            self.gstin_note.setText(problem)
            self.gstin_note.setVisible(True)
        else:
            self.gstin_note.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: {Fonts.BODY}px;")
            self.gstin_note.setText(f"GSTIN looks right. State: {state}.")
            self.gstin_note.setVisible(True)

    def _pay_pick_changed(self, _i=0):
        paying = self.pay_pick.currentData() is not None  # "Not paid yet": nothing handed over
        self.received_in.setEnabled(paying)
        self.split_btn.setEnabled(paying)
        self._show_pay_note()

    def _received_changed(self, _v=0):
        self._received_touched = True
        self._show_pay_note()

    def _show_pay_note(self):
        kind, rupees = change_or_balance(self._total, self._received())
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
        status = payment_status(self._total, self._received())
        if self._split_rows:  # more than one way: the server gets each payment
            rows = [(self.pay_pick.currentData(), self.received_in.value())] + [(m.currentData(), a.value()) for m, a, _r in self._split_rows]
            return {"payments": [{"amount": round(v, 2), "method": m} for m, v in rows if v > 0], "payment_status": status}
        return {"payment_method": method, "payment_status": status}

    # ------------------------------------------------------------------
    # Offline billing
    # ------------------------------------------------------------------
    def _client_id_for_cart(self, phone: str) -> str:
        """One id per distinct bill. If the connection drops after the server
        recorded it, the offline copy carries the same id and the server skips
        it instead of billing the buyer twice. Changing the cart makes a new bill."""
        pay = self._payment()
        key = (phone, tuple((c.item_id, c.quantity) for c in self._cart), self._discount, pay.get("payment_method"), pay["payment_status"], str(pay.get("payments")))
        if key != self._bill_key:
            self._bill_key, self._bill_client_id = key, str(uuid.uuid4())
        return self._bill_client_id

    def _save_offline(self, customer_name: str, phone: str, client_id: str) -> bool:
        pay = self._payment()
        if self._discount or "payments" in pay:  # the sync carries neither yet: a bill saved now would lose them
            QMessageBox.warning(
                self,
                "This needs a connection",
                "There is no connection, and a discount or a split payment cannot be saved offline yet.\n\n"
                "Take it off to save this bill on this computer, or press Create bill again "
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
            "\n\nHow it was paid is kept with it. A server that has not been updated yet shows it as "
            "not paid until you correct it in Bill History."
            if pay["payment_status"] != "pending"
            else ""
        )
        self._remember_bill({"invoice_number": ref, "total_amount": self._total, "payment_status": pay["payment_status"], "payment_method": pay.get("payment_method")}, True)
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
        problem = gst.gstin_problem(self.gstin_input.text())
        if problem:
            QMessageBox.warning(self, "Buyer's GSTIN", problem + "\n\nCorrect it, or clear it for a buyer without one.")
            return

        client_id = self._client_id_for_cart(phone)

        # No connection: keep the sale on this computer and sync it later.
        if not self._sales_service.is_online():
            self._save_offline(customer_name, phone, client_id)
            return

        buyer_gstin = [gst.clean(self.gstin_input.text())] if gst.clean(self.gstin_input.text()) else []
        try:
            customer_id = self._customer_service.ensure_customer(customer_name, phone, *buyer_gstin)
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

        note = ""
        kind, rupees = change_or_balance(self._total, self._received())
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

        self._remember_bill(sale_data, False)
        EventBus.emit(SALE_CREATED)
        self._clear_cart()
        self.customer_input.clear()
        self.phone_input.clear()
