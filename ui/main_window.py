"""
ui/main_window.py

Main application shell — dark sidebar with emoji icons, active state,
auto-refresh on page switch, and themed layout.
"""

import logging

import requests

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QDialog,
    QStackedWidget,
    QLabel,
    QMessageBox,
    QFrame,
    QScrollArea,
    QTableWidget,
)
from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication

from services import notifications_service as ns
from ui.assets import logo_path, scaled_pixmap
from ui.components.bootstrap import Button
from ui.components.carvings import attach_empty_state
from ui.components.navbar import Navbar
from ui.components.goto_dialog import GoToDialog
from ui import icons
from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts, Radius, Spacing

from ui.dashboard_window import DashboardWindow
from ui.inventory_window import InventoryWindow
from ui.sales_screen import SalesScreen
from ui.customers_screen import CustomersScreen
from ui.reports_screen import ReportsScreen
from ui.sales_history_screen import SalesHistoryScreen
from ui.attendance_screen import AttendanceScreen
from ui.lab_screen import LabScreen
from ui.materials_screen import MaterialsScreen
from ui.purchases_screen import PurchasesScreen
from ui.roles_screen import RolesScreen
from ui.staff_screen import StaffScreen, change_my_password
from ui.expenses_screen import ExpensesScreen
from ui.payroll_screen import PayrollScreen
from ui.profit_screen import ProfitScreen
from ui.restoration_screen import RestorationScreen
from ui.orders_screen import OrdersScreen
from ui.designs_screen import DesignsScreen
from ui.letters_screen import LettersScreen
from ui.places_screen import PlacesScreen
from ui.machines_screen import MachinesScreen
from ui.budgets_screen import BudgetsScreen
from ui.finance_screen import FinanceScreen
from ui.notifier import Notifier
from ui.workers import on_busy_changed, run_async
from ui.updater import UpdateBanner, Updater
from services.version import APP_VERSION
from services.api_client import SessionExpiredError, set_session_expired_hook
from services.session import Session
from services.sync_service import SyncService
from services.event_bus import EventBus, SALE_CREATED

logger = logging.getLogger(__name__)

# How often to run a background push/pull sync cycle, in milliseconds.
SYNC_INTERVAL_MS = 60_000

SIDEBAR_WIDTH = 232
COMPACT_WIDTH = 80  # icons only, on a window narrower than COMPACT_BELOW
COMPACT_BELOW = 1280
LOGO_BOX = QSize(56, 76)  # the logo is 3:4; this box keeps it sharp and inside the header

# What each list screen says when it has no rows (title, hint, carving set). The screens
# need no change: MainWindow lays the empty state over each screen's table.
EMPTY_STATES = {
    "New Bill": ("No items on this bill yet", "Search for an item above, or scan its code, to start the bill.", "temple"),
    "Bill History": ("No bills found", "Bills you save will be listed here. Change the date filter to look at another day.", "dark"),
    "Orders": ("No orders yet", "Orders from the counter and from the website will appear here.", "horse"),
    "Buyers": ("No buyers yet", "Add a buyer to keep their name, phone and bills together.", "dark-horse"),
    "Letters": ("No letters yet", "Quotes and letters you issue will be listed here.", "pillar"),
    "Stock": ("Nothing in stock yet", "Add your first product to start keeping stock.", "temple"),
    "Places": ("No stock counted at a place yet", "Move stock to a place, or receive a purchase there, and it will be listed here.", "horse"),
    "Materials": ("No materials yet", "Wood and other materials you add will be listed here.", "dark"),
    "Purchases": ("No purchases yet", "Record what you buy and it will show here.", "horse"),
    "3D Lab": ("No 3D models yet", "Scan a carving and its model will appear here.", "dark-horse"),
    "Restoration": ("No restoration jobs yet", "Temple and heritage work you take up will be tracked here.", "pillar"),
    "Designs": ("No designs yet", "Designs you save will be listed here.", "temple"),
    "Machines and tools": ("No machines or tools yet", "Add a machine or tool to keep track of its service and who has it.", "pillar"),
    "Attendance": ("No attendance marked", "Mark who came in and it will be listed here.", "dark"),
    "Wages": ("No wages to show", "Wages due and paid will appear here.", "horse"),
    "Staff": ("No staff accounts yet", "People you add will be listed here.", "dark-horse"),
    "Expenses": ("No expenses yet", "Add an expense to see it here.", "pillar"),
    "Profit": ("No figures yet", "Profit shows once there are bills and expenses.", "temple"),
    "Budgets": ("No budgets set yet", "The owner can set a monthly or yearly budget for machines and raw materials.", "horse"),
    "Reports": ("No report data yet", "Reports fill in as bills are saved.", "dark"),
}


class MainWindow(QMainWindow):
    # Emitted when the server rejects our token. A signal, not a direct call: the
    # update check runs on a worker thread, and dialogs belong to the GUI thread.
    session_expired = pyqtSignal()

    # (icon, label, page index in content_stack). Listed in the order they appear in the side
    # panel, grouped under the headings in NAV_SECTIONS; Home stands alone at the top.
    NAV_ITEMS = [
        ("🏠", "Home", 0),
        ("🧾", "New Bill", 1),
        ("📜", "Bill History", 4),
        ("📋", "Orders", 15),
        ("👤", "Buyers", 3),
        ("✉️", "Letters", 17),
        ("📦", "Stock", 2),
        ("🌳", "Materials", 8),
        ("🛒", "Purchases", 9),
        ("📍", "Places", 18),
        ("🧊", "3D Lab", 7),
        ("🏛️", "Restoration", 14),
        ("🎨", "Designs", 16),
        ("🛠️", "Machines and tools", 19),
        ("👷", "Attendance", 6),
        ("💰", "Wages", 11),
        ("👥", "Staff", 10),
        ("💸", "Expenses", 12),
        ("💹", "Profit", 13),
        ("🎯", "Budgets", 20),
        ("📒", "Accounts", 21),
        ("📊", "Reports", 5),
        ("🔑", "Roles", 22),
    ]
    NAV_SECTIONS = {
        "Selling": ["New Bill", "Bill History", "Orders", "Buyers", "Letters"],
        "Stock and buying": ["Stock", "Materials", "Purchases", "Places"],
        "Workshop": ["3D Lab", "Restoration", "Designs", "Machines and tools"],
        "People and pay": ["Attendance", "Wages", "Staff"],
        "Money": ["Expenses", "Profit", "Budgets", "Accounts", "Reports"],
        "Access": ["Roles"],
    }
    # A menu entry shows when the user may use its main action (any one of these).
    NAV_ACTIONS = {
        "Home": ("items:item:read", "attendance:record:read_own", "sales:sale:create", "reports:dashboard:read"),
        "New Bill": ("sales:sale:create",),
        "Bill History": ("sales:sale:read",),
        "Orders": ("sales:order:read",),
        "Buyers": ("sales:customer:read",),
        "Letters": ("letters:quotation:issue", "letters:order_confirmation:issue", "letters:purchase_receipt:issue", "letters:completion_certificate:issue"),
        "Stock": ("items:item:read",),
        "Materials": ("inventory:raw_material:read",),
        "Purchases": ("purchases:purchase:create",),
        "Places": ("inventory:stock_location:view",),
        "3D Lab": ("lab:part:read",),
        "Restoration": ("restoration:project:access",),
        "Designs": ("restoration:project:access",),
        "Machines and tools": ("machines:tool:view",),
        "Attendance": ("attendance:record:read_own", "attendance:record:read_all"),
        "Wages": ("payroll:records:read_all",),  # plus the self-service rule in _can_see
        "Staff": ("people:user:create", "people:user:update"),
        "Expenses": ("expenses:expense:write",),
        "Profit": ("items:cost:read",),
        "Budgets": ("budgets:budget:read",),
        "Accounts": ("finance:ledger:read",),
        "Reports": ("reports:report:read",),
        "Roles": ("iam:role:read",),
    }

    def __init__(self):
        super().__init__()
        self._signing_out = False
        self._sync_running = False
        self.session_expired.connect(self._on_session_expired)
        set_session_expired_hook(self.session_expired.emit)
        self.setWindowTitle("Vriksha Studios — Staff desk")
        self.setStyleSheet(Theme.global_stylesheet())
        app = QApplication.instance()
        if app is not None:
            Theme.install(app)

        # Open at 1200x750, or the whole usable screen on a small one (1366x768 laptops
        # lose a strip to the taskbar), and centre it.
        screen = self.screen().availableGeometry()
        width, height = min(1200, screen.width()), min(750, screen.height())
        self.setMinimumSize(min(1024, screen.width()), min(600, screen.height()))
        self.resize(width, height)
        self.move(screen.x() + (screen.width() - width) // 2, screen.y() + (screen.height() - height) // 2)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ───────────────────────────────────
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_WIDTH)
        self.sidebar.setStyleSheet(
            f"QFrame#sidebar {{ background-color: {Colors.SIDEBAR_BG};"
            f" border-right: 1px solid {Colors.CARD_BORDER}; }}"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Brand header: the Vriksha logo beside the name
        brand_container = QFrame()
        brand_container.setStyleSheet(
            f"QFrame {{ background-color: {Colors.SIDEBAR_BG}; border: none;"
            f" border-bottom: 1px solid {Colors.CARD_BORDER}; }}"
            "QLabel { border: none; background: transparent; }"
        )
        brand_layout = QHBoxLayout(brand_container)
        self._brand_layout = brand_layout
        brand_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        brand_layout.setSpacing(Spacing.SM + 4)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(LOGO_BOX)
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = scaled_pixmap(logo_path(), LOGO_BOX.height(), False, self.devicePixelRatioF())
        if not logo.isNull():
            self.logo_lbl.setPixmap(logo)
        brand_layout.addWidget(self.logo_lbl)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addStretch()
        brand_lbl = QLabel("Vriksha Studios")
        brand_lbl.setStyleSheet(f"""
            font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif;
            font-size: 20px;
            font-weight: bold;
            color: {Colors.BRAND_BROWN};
        """)
        brand_lbl.setWordWrap(True)  # the name wraps to two lines rather than being cut off
        brand_text.addWidget(brand_lbl)
        brand_sub = QLabel("Staff desk")
        brand_sub.setStyleSheet(f"font-size: {Fonts.CAPTION}px; color: {Colors.TEXT_MUTED};")
        brand_text.addWidget(brand_sub)
        self._brand_words = [brand_lbl, brand_sub]
        brand_text.addStretch()
        brand_layout.addLayout(brand_text, 1)

        sidebar_layout.addWidget(brand_container)

        # Nav buttons
        sidebar_layout.addSpacing(Spacing.SM)
        self._nav_buttons: list[QPushButton] = []
        self._nav_mapping: dict[int, QPushButton] = {}
        self._headings: list[QPushButton] = []
        self._groups: dict[str, list[QPushButton]] = {}
        self._collapsed: set[str] = set()
        self._page_group: dict[int, str] = {}
        self._compact = False

        nav_box = QWidget()
        nav_box.setStyleSheet(f"background-color: {Colors.SIDEBAR_BG};")
        nav_layout = QVBoxLayout(nav_box)
        nav_layout.setContentsMargins(Spacing.SM, 0, Spacing.SM, Spacing.SM)
        nav_layout.setSpacing(2)
        section_of = {label: name for name, labels in self.NAV_SECTIONS.items() for label in labels}
        current_section = None
        for icon, label, index in self._get_allowed_nav_items():
            section = section_of.get(label)
            if section and section != current_section:
                self._headings.append(self._section_heading(section))
                nav_layout.addWidget(self._headings[-1])
            current_section = section
            btn = self._create_nav_button(icon, label, index)
            if section:
                self._groups.setdefault(section, []).append(btn)
                self._page_group[index] = section
            self._nav_buttons.append(btn)
            self._nav_mapping[index] = btn
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {Colors.SIDEBAR_BG}; border: none; }}"
            f"QScrollBar:vertical {{ width: 6px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {Colors.INPUT_BORDER}; border-radius: 3px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        nav_scroll.setWidget(nav_box)
        self.nav_scroll = nav_scroll
        sidebar_layout.addWidget(nav_scroll, 1)

        # Version, and a manual "check for updates"
        self.update_btn = IconButton(f"⬆  Updates  ·  v{APP_VERSION}")
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet(self._footer_button_css())
        self.update_btn.clicked.connect(lambda: self.updater.check(manual=True))
        sidebar_layout.addWidget(self.update_btn)
        self._footer = [(self.update_btn, "⬆", f"Updates  ·  v{APP_VERSION}")]

        main_layout.addWidget(self.sidebar)

        # ── Navbar + content area ─────────────────────
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet(f"background-color: {Colors.BG};")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Navbar: page title on the left; notifications, who is signed in, sign out on the right
        self.navbar = Navbar()
        # Notifications: a count of what is new, and the list
        self.bell_btn = Button("🔔", "secondary", "sm", outline=True)
        self.bell_btn.setToolTip("Notifications")
        self.navbar.add_right(self.bell_btn)
        # Who is signed in: their role, and the menu with change password and sign out
        self.role_badge = self.navbar.make_account_button(
            self._role_text(), lambda: change_my_password(self), self._handle_logout
        )
        self.navbar.add_right(self.role_badge)
        self.navbar.goto_requested.connect(self._open_goto)
        content_layout.addWidget(self.navbar)
        on_busy_changed(self.navbar.set_busy)  # "Loading…" while a screen fetches in the background

        self.content_stack = QStackedWidget()
        self.update_banner = UpdateBanner()
        content_layout.addWidget(self.update_banner)
        content_layout.addWidget(self.content_stack)
        main_layout.addWidget(content_wrapper)

        # Initialize screens
        self.dashboard_view = DashboardWindow()
        self.sales_view = SalesScreen()
        self.inventory_view = InventoryWindow()
        self.customers_view = CustomersScreen()
        self.sales_history_view = SalesHistoryScreen()
        self.reports_view = ReportsScreen()
        self.attendance_view = AttendanceScreen()
        self.lab_view = LabScreen()
        self.materials_view = MaterialsScreen()
        self.purchases_view = PurchasesScreen()
        self.staff_view = StaffScreen()
        self.payroll_view = PayrollScreen()
        self.expenses_view = ExpensesScreen()
        self.profit_view = ProfitScreen()
        self.restoration_view = RestorationScreen()
        self.orders_view = OrdersScreen()
        self.designs_view = DesignsScreen()
        self.letters_view = LettersScreen()
        self.places_view = PlacesScreen()
        self.machines_view = MachinesScreen()
        self.budgets_view = BudgetsScreen()
        self.finance_view = FinanceScreen()
        self.roles_view = RolesScreen()

        self.content_stack.addWidget(self.dashboard_view)  # 0
        self.content_stack.addWidget(self.sales_view)  # 1
        self.content_stack.addWidget(self.inventory_view)  # 2
        self.content_stack.addWidget(self.customers_view)  # 3
        self.content_stack.addWidget(self.sales_history_view)  # 4
        self.content_stack.addWidget(self.reports_view)  # 5
        self.content_stack.addWidget(self.attendance_view)  # 6
        self.content_stack.addWidget(self.lab_view)  # 7
        self.content_stack.addWidget(self.materials_view)  # 8
        self.content_stack.addWidget(self.purchases_view)  # 9
        self.content_stack.addWidget(self.staff_view)  # 10
        self.content_stack.addWidget(self.payroll_view)  # 11
        self.content_stack.addWidget(self.expenses_view)  # 12
        self.content_stack.addWidget(self.profit_view)  # 13
        self.content_stack.addWidget(self.restoration_view)  # 14
        self.content_stack.addWidget(self.orders_view)  # 15
        self.content_stack.addWidget(self.designs_view)  # 16
        self.content_stack.addWidget(self.letters_view)  # 17
        self.content_stack.addWidget(self.places_view)  # 18
        self.content_stack.addWidget(self.machines_view)  # 19
        self.content_stack.addWidget(self.budgets_view)  # 20
        self.content_stack.addWidget(self.finance_view)  # 21
        self.content_stack.addWidget(self.roles_view)  # 22

        Theme.stripe_tables(self)
        self._decorate_empty_states()
        self._install_shortcuts()

        # Show Home at once; its numbers load right after the window is on screen
        allowed = self._get_allowed_nav_items()
        self._switch_page(allowed[0][2] if allowed else 0, refresh=False)  # Home, or the first page this role has
        QTimer.singleShot(0, self._refresh_current)

        # ── Background sync ───────────────────────────
        # Runs the offline sync engine (push queued outbox operations, then
        # pull incremental updates) on a timer so it's actually exercised —
        # previously SyncService was never invoked from anywhere in the app.
        self._sync_service = SyncService()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_async)
        self._sync_timer.start(SYNC_INTERVAL_MS)

        # The connection chip in the top bar: is the server reachable, and how many bills wait
        self._conn_timer = QTimer(self)
        self._conn_timer.timeout.connect(self._refresh_connection)
        self._conn_timer.start(5000)
        self._refresh_connection()
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {Colors.CARD_BG}; color: {Colors.TEXT_SECONDARY};"
            f" border-top: 1px solid {Colors.CARD_BORDER}; font-size: {Fonts.BODY_SM}px; }}"
        )

        # Desktop notifications (website orders, money received, low stock, finished scans)
        self.notifier = Notifier(self)
        self.notifier.changed.connect(self._show_unread)
        self.notifier.open_screen.connect(self._open_screen)
        self.bell_btn.clicked.connect(lambda: self.notifier.show_list())
        self._show_unread()
        self.notifier.start()

        # Tell the user when a newer version is published (installed builds only)
        self.updater = Updater(self, self.update_banner)
        self.updater.start()
        # Run one cycle shortly after startup too, rather than waiting a
        # full interval for the first sync.
        QTimer.singleShot(2000, self._sync_async)

    def _refresh_connection(self):
        """Online unless the last request found the server down; waiting = bills not yet sent."""
        import time

        from database.outbox_repository import OutboxRepository
        from services import api_client

        try:
            waiting = len(OutboxRepository().get_pending())
        except Exception:  # a locked or missing local database must not break the window
            waiting = 0
        self.navbar.set_connection(time.monotonic() >= api_client._down_until, waiting)

    def _show_unread(self):
        n = self.notifier.unread
        self.bell_btn.setText(f"🔔  {n}" if n else "🔔")
        self.bell_btn.setToolTip(f"Notifications, {n} new" if n else "Notifications")

    def _open_screen(self, screen: str):
        """Open the screen a notification is about, if this user has it in the side panel."""
        label = ns.SCREEN_LABELS.get(screen)
        index = next((i for _, name, i in self.NAV_ITEMS if name == label), None)
        if index is not None and index in self._nav_mapping:
            self._switch_page(index)

    # ------------------------------------------------------------------
    # Background sync cycle
    # ------------------------------------------------------------------
    def _sync_work(self):
        """
        The slow part of a sync cycle: the network and the local outbox. It touches no
        widget, so it can run on a background thread. Returns the push result, or None
        when the server cannot be reached.
        """
        if not self._sync_service.is_online():
            return None
        push_result = self._sync_service.push_sync()
        try:
            self._sync_service.pull_sync()
        except SessionExpiredError:
            raise
        except Exception:
            logger.exception("Background sync pull failed")
        return push_result

    def _sync_done(self, push_result):
        """What a finished cycle changes on screen. Runs on the GUI thread."""
        if not push_result:
            return
        if push_result.get("pushed"):
            # Offline sales just got official bill numbers and moved stock.
            EventBus.emit(SALE_CREATED)
        if push_result.get("failed"):
            logger.warning("Background sync push had failures: %s", push_result)
        held = push_result.get("held", 0)
        if held:
            self.statusBar().showMessage(
                (
                    "1 bill saved by another user is waiting for them to sign in."
                    if held == 1
                    else f"{held} bills saved by other users are waiting for them to sign in."
                ),
                15000,
            )

    def _run_sync_cycle(self):
        """
        Push any queued offline changes, then pull incremental updates, and wait for it.

        The timer uses _sync_async, which does the same without freezing the window. Silently
        skips when the backend is unreachable, and never raises: a background sync failure
        shouldn't interrupt the user.
        """
        try:
            self._sync_done(self._sync_work())
        except SessionExpiredError:
            return  # the expiry hook has signed the user out; the outbox is kept
        except Exception:
            logger.exception("Background sync cycle failed")

    def _sync_async(self):
        """A sync cycle on a background thread (runs on a timer, and once after startup)."""
        if self._sync_running:
            return  # the last cycle is still going: never two on one connection

        def done(push_result):
            self._sync_running = False
            self._sync_done(push_result)

        def failed(exc):
            self._sync_running = False
            if not isinstance(exc, SessionExpiredError):  # expiry: the hook has signed the user out
                logger.error("Background sync cycle failed", exc_info=exc)

        self._sync_running = True
        run_async(self._sync_work, done, failed)

    @classmethod
    def _can_see(cls, label: str) -> bool:
        if Session.can_any(*cls.NAV_ACTIONS[label]):
            return True
        if label == "Wages":  # people who are not on the sales desk see their own pay
            return Session.can("attendance:record:read_own") and not Session.can("attendance:record:read_all")
        return False

    def _get_allowed_nav_items(self):
        """The menu entries this user may use, from what the server says they can do."""
        return [i for i in self.NAV_ITEMS if self._can_see(i[1])]

    # ------------------------------------------------------------------
    # Nav button factory
    # ------------------------------------------------------------------
    def _section_heading(self, text: str) -> QPushButton:
        """A section title that folds its entries away when clicked."""
        heading = IconButton(text)
        heading.setProperty("section", text)
        heading.setCursor(Qt.CursorShape.PointingHandCursor)
        heading.setStyleSheet(
            f"QPushButton {{ color: {Colors.SIDEBAR_HEADING}; font-size: {Fonts.BODY_SM}px; font-weight: 600;"
            f" padding: {Spacing.MD}px 12px {Spacing.XS}px 12px; background: transparent; border: none;"
            " text-align: left; }"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        heading.clicked.connect(lambda _=False, name=text: self._toggle_group(name))
        self._set_heading_text(heading, text)
        return heading

    def _set_heading_text(self, heading: QPushButton, name: str) -> None:
        heading.setText(f"{'+' if name in self._collapsed else '−'}  {name}")  # a plus opens, a minus folds

    def _toggle_group(self, name: str) -> None:
        self._collapsed ^= {name}
        self._apply_groups()

    def _apply_groups(self) -> None:
        """Show each group's entries unless it is folded (a narrow, icons-only sidebar shows all)."""
        for heading in self._headings:
            name = heading.property("section")
            self._set_heading_text(heading, name)
            for btn in self._groups.get(name, []):
                btn.setVisible(self._compact or name not in self._collapsed)

    def _create_nav_button(self, icon: str, label: str, index: int) -> QPushButton:
        btn = IconButton(f"  {label}")
        btn.setProperty("icon_text", icon)
        btn.setProperty("label_text", label)
        btn.setIconSize(QSize(18, 18))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(40)
        self._style_nav(btn, active=False)
        btn.clicked.connect(lambda _, idx=index: self._switch_page(idx))
        return btn

    def _style_nav(self, btn: QPushButton, active: bool) -> None:
        """The button's look and its line icon, in the colour the state needs."""
        btn.setStyleSheet(self._nav_button_css(active))
        colour = Colors.SIDEBAR_ACTIVE_TEXT if active else Colors.SIDEBAR_TEXT
        btn.setIcon(icons.icon(icons.for_label(btn.property("label_text")), colour))

    def _nav_button_css(self, active: bool) -> str:
        align = "center" if self._compact else "left"
        if active:
            return f"""
                QPushButton {{
                    background-color: {Colors.SIDEBAR_ACTIVE};
                    color: {Colors.SIDEBAR_ACTIVE_TEXT};
                    border: none;
                    border-left: 3px solid {Colors.SIDEBAR_ACCENT};
                    border-radius: {Radius.MD}px;
                    padding: 0 12px;
                    font-size: {Fonts.BODY}px;
                    font-weight: 700;
                    text-align: {align};
                }}
            """
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.SIDEBAR_TEXT};
                border: none;
                border-left: 3px solid transparent;
                border-radius: {Radius.MD}px;
                padding: 0 12px;
                font-size: {Fonts.BODY}px;
                text-align: {align};
            }}
            QPushButton:hover {{
                background-color: {Colors.SIDEBAR_HOVER};
                color: {Colors.SIDEBAR_ACTIVE_TEXT};
            }}
        """

    def _footer_button_css(self) -> str:
        align = "center" if self._compact else "left"
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.SIDEBAR_TEXT};
                border: none;
                border-top: 1px solid {Colors.CARD_BORDER};
                padding: 12px {Spacing.MD}px;
                font-size: {Fonts.BODY_SM}px;
                text-align: {align};
            }}
            QPushButton:hover {{
                color: {Colors.SIDEBAR_ACTIVE_TEXT};
                background-color: {Colors.SIDEBAR_HOVER};
            }}
        """

    def _role_text(self) -> str:
        role = Session.get_role()
        return str(getattr(role, "value", role) or "staff").title()

    def _decorate_empty_states(self):
        """Lay an empty state (carving pair, title, hint) over each list screen's table."""
        by_index = {index: label for _, label, index in self.NAV_ITEMS}
        for index in range(self.content_stack.count()):
            spec = EMPTY_STATES.get(by_index.get(index, ""))
            if spec is None:
                continue
            view = self.content_stack.widget(index)
            table = getattr(view, "table", None)
            if not isinstance(table, QTableWidget):
                tables = view.findChildren(QTableWidget)
                table = tables[0] if tables else None
            if table is not None:
                attach_empty_state(table, *spec)
            # Any other list on the screen (a second tab, a history under the main list) says
            # so too, in words only, instead of showing a blank box.
            for other in view.findChildren(QTableWidget):
                if other is not table and other.parent() is not None and not other.property("no_empty_state"):
                    attach_empty_state(other, "Nothing here yet", "", show_carvings=False)

    # ------------------------------------------------------------------
    # Page switching with active state + auto-refresh
    # ------------------------------------------------------------------
    def _switch_page(self, index: int, refresh: bool = True):
        self.content_stack.setCurrentIndex(index)
        label = next((name for icon, name, i in self.NAV_ITEMS if i == index), "")
        self.navbar.set_title(label)

        # Update active state on nav buttons
        for i, btn in self._nav_mapping.items():
            self._style_nav(btn, active=(i == index))
        group = self._page_group.get(index)
        if group in self._collapsed:  # never leave the open page hidden in a folded section
            self._collapsed.discard(group)
            self._apply_groups()
        if index in self._nav_mapping:
            self.nav_scroll.ensureWidgetVisible(self._nav_mapping[index], 0, Spacing.XL)

        if refresh:
            self._refresh_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < COMPACT_BELOW
        if compact != self._compact:
            self._set_compact(compact)

    def _set_compact(self, on: bool):
        """A narrow window gives the sidebar's room to the page: icons only, labels as tooltips."""
        self._compact = on
        self.sidebar.setFixedWidth(COMPACT_WIDTH if on else SIDEBAR_WIDTH)
        m = Spacing.SM + 4 if on else Spacing.MD
        self._brand_layout.setContentsMargins(m, Spacing.MD, m, Spacing.MD)
        for w in self._brand_words + self._headings:
            w.setVisible(not on)
        self._apply_groups()
        current = self.content_stack.currentIndex()
        for index, btn in self._nav_mapping.items():
            icon, label = btn.property("icon_text"), btn.property("label_text")
            btn.setText("" if on else f"  {label}")
            btn.setToolTip(label if on else "")
            self._style_nav(btn, active=(index == current))
        for btn, icon, words in self._footer:
            btn.setText(icon if on else f"{icon}  {words}")
            btn.setToolTip(words if on else "")
            btn.setStyleSheet(self._footer_button_css())

    def _install_shortcuts(self):
        """F5 refreshes this screen, Ctrl+F jumps to its search box, Ctrl+1..9 open the first nine
        sidebar entries (the ones this role can see, in the order shown)."""
        keys = {"F5": self._refresh_current, "Ctrl+F": self._focus_search, "Ctrl+K": self._open_goto}
        for n in range(1, 10):
            keys[f"Ctrl+{n}"] = lambda n=n: self._go_to_nth(n)
        self._shortcuts = []
        for key, slot in keys.items():
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

    def _open_goto(self):
        """Ctrl+K: type a screen's name and press Enter."""
        entries = [(label, index) for _, label, index in self._get_allowed_nav_items()]
        dialog = GoToDialog(entries, self)
        if dialog.exec() and dialog.chosen is not None:
            self._switch_page(dialog.chosen)

    def _go_to_nth(self, n: int):
        if n <= len(self._nav_buttons):
            self._nav_buttons[n - 1].click()

    def _focus_search(self):
        from PyQt6.QtWidgets import QLineEdit

        for box in self.content_stack.currentWidget().findChildren(QLineEdit):
            if box.isVisibleTo(self) and box.isEnabled() and not box.isReadOnly():
                box.setFocus()
                box.selectAll()
                return

    def _refresh_current(self):
        # Auto-refresh data for the visible screen
        widget = self.content_stack.currentWidget()
        if hasattr(widget, "refresh_async"):
            widget.refresh_async()  # fetches in the background; the old rows stay until the new ones arrive
        elif hasattr(widget, "refresh_data"):
            try:
                widget.refresh_data()
            except requests.RequestException:
                # Server unreachable: keep the window usable (New Bill can
                # still save sales offline) instead of crashing.
                logger.warning(
                    "Could not refresh %s: backend unreachable", type(widget).__name__
                )
                self.statusBar().showMessage(
                    "No connection to the server. This screen shows older data.", 8000
                )

    # ------------------------------------------------------------------
    # Public method for dashboard quick-action navigation
    # ------------------------------------------------------------------
    def navigate_to(self, page_name: str):
        mapping = {
            "new_bill": 1,
            "stock": 2,
            "buyers": 3,
            "machines": 19,
            "budgets": 20,
        }
        idx = mapping.get(page_name, 0)
        self._switch_page(idx)

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    def _on_session_expired(self):
        """The server no longer accepts our login: say so once and go to sign-in.
        Bills saved offline stay in the outbox and are sent after the next sign-in."""
        if self._signing_out:
            return  # a 401 while handing over bills at sign-out: we are leaving anyway
        self._sync_timer.stop()
        self.notifier.stop()
        Session.clear_token()
        self._close_open_dialogs()
        QMessageBox.information(
            self,
            "Signed out",
            "Your sign-in has expired, so you have been signed out.\n\n"
            "Sign in again to continue. Bills saved offline are kept on this "
            "computer and are sent after you sign in.",
        )
        from ui.login_window import LoginWindow

        self._login_window = LoginWindow()
        self._login_window.show()
        self.close()

    @staticmethod
    def _close_open_dialogs():
        """A form left open must not stay on screen after the user is signed out."""
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible():
                w.reject()

    def _flush_outbox(self):
        """Best effort: hand queued bills to the server under this user's own login
        before it is cleared, so they do not wait for this user's next sign-in."""
        if self._sync_running:
            return  # a cycle on the background thread is already sending them
        try:
            if self._sync_service.is_online():
                self._sync_service.push_sync()
        except Exception:
            logger.exception("Could not send queued bills at sign-out")

    def _handle_logout(self):
        self._signing_out = True
        self._sync_timer.stop()
        self.notifier.stop()
        self._flush_outbox()

        from services.auth_service import AuthService

        AuthService().logout()
        self._close_open_dialogs()
        from ui.login_window import LoginWindow

        self._login_window = LoginWindow()
        self._login_window.show()
        self.close()
