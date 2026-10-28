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
    QStackedWidget,
    QLabel,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from ui.theme import Theme, Colors, Fonts

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
from ui.staff_screen import StaffScreen, change_my_password
from ui.expenses_screen import ExpensesScreen
from ui.payroll_screen import PayrollScreen
from ui.profit_screen import ProfitScreen
from ui.restoration_screen import RestorationScreen
from ui.orders_screen import OrdersScreen
from ui.designs_screen import DesignsScreen
from ui.updater import UpdateBanner, Updater
from services.version import APP_VERSION
from services.api_client import SessionExpiredError, set_session_expired_hook
from services.session import Session
from services.enums import UserRole
from services.sync_service import SyncService
from services.event_bus import EventBus, SALE_CREATED

logger = logging.getLogger(__name__)

# How often to run a background push/pull sync cycle, in milliseconds.
SYNC_INTERVAL_MS = 60_000


class MainWindow(QMainWindow):
    # Emitted when the server rejects our token. A signal, not a direct call: the
    # update check runs on a worker thread, and dialogs belong to the GUI thread.
    session_expired = pyqtSignal()

    NAV_ITEMS = [
        ("🏠", "Home", 0),
        ("🧾", "New Bill", 1),
        ("📦", "Stock", 2),
        ("👤", "Buyers", 3),
        ("📜", "Bill History", 4),
        ("📊", "Reports", 5),
        ("👷", "Workforce", 6),
        ("🧊", "3D Lab", 7),
        ("🌳", "Materials", 8),
        ("🛒", "Purchases", 9),
        ("👥", "Staff", 10),
        ("💰", "Wages", 11),
        ("💸", "Expenses", 12),
        ("💹", "Profit", 13),
        ("🏛️", "Restoration", 14),
        ("📋", "Orders", 15),
        ("🎨", "Designs", 16),
    ]

    def __init__(self):
        super().__init__()
        self._signing_out = False
        self.session_expired.connect(self._on_session_expired)
        set_session_expired_hook(self.session_expired.emit)
        self.setWindowTitle("Vriksha Studio — Staff desk")
        self.resize(1200, 750)
        self.setStyleSheet(Theme.global_stylesheet())

        # Center on screen
        screen = self.screen().availableGeometry()
        x = (screen.width() - 1200) // 2
        y = (screen.height() - 750) // 2
        self.move(x, y)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ───────────────────────────────────
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet(f"background-color: {Colors.SIDEBAR_BG};")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Brand header
        brand_container = QWidget()
        brand_container.setStyleSheet(
            f"background-color: {Colors.SIDEBAR_BG}; border-bottom: 1px solid {Colors.SIDEBAR_HOVER};"
        )
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(20, 24, 20, 20)

        brand_lbl = QLabel("Vriksha Studio")
        brand_lbl.setStyleSheet(f"""
            font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif;
            font-size: 26px;
            font-weight: bold;
            color: {Colors.BG};
        """)
        brand_layout.addWidget(brand_lbl)

        brand_sub = QLabel("Staff desk")
        brand_sub.setStyleSheet(f"""
            font-size: {Fonts.CAPTION}px;
            color: {Colors.SIDEBAR_TEXT};
            margin-top: 2px;
        """)
        brand_layout.addWidget(brand_sub)

        sidebar_layout.addWidget(brand_container)

        # Nav buttons
        sidebar_layout.addSpacing(12)
        self._nav_buttons: list[QPushButton] = []
        self._nav_mapping: dict[int, QPushButton] = {}

        allowed_items = self._get_allowed_nav_items()
        for icon, label, index in allowed_items:
            btn = self._create_nav_button(icon, label, index)
            self._nav_buttons.append(btn)
            self._nav_mapping[index] = btn
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Everyone can change their own password
        pw_btn = QPushButton("🔑  My password")
        pw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pw_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.SIDEBAR_TEXT};
                border: none;
                border-top: 1px solid {Colors.SIDEBAR_HOVER};
                padding: 14px 20px;
                font-size: {Fonts.BODY}px;
                text-align: left;
            }}
            QPushButton:hover {{
                color: white;
                background-color: {Colors.SIDEBAR_HOVER};
            }}
        """)
        pw_btn.clicked.connect(lambda: change_my_password(self))
        sidebar_layout.addWidget(pw_btn)

        # Version, and a manual "check for updates"
        self.update_btn = QPushButton(f"⬆  Updates  ·  v{APP_VERSION}")
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet(pw_btn.styleSheet())
        self.update_btn.clicked.connect(lambda: self.updater.check(manual=True))
        sidebar_layout.addWidget(self.update_btn)

        # Logout at bottom
        logout_btn = QPushButton("🚪  Sign Out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.SIDEBAR_TEXT};
                border: none;
                border-top: 1px solid {Colors.SIDEBAR_HOVER};
                padding: 16px 20px;
                font-size: {Fonts.BODY}px;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {Colors.RED};
                background-color: {Colors.SIDEBAR_HOVER};
            }}
        """)
        logout_btn.clicked.connect(self._handle_logout)
        sidebar_layout.addWidget(logout_btn)

        main_layout.addWidget(self.sidebar)

        # ── Content area ──────────────────────────────
        content_wrapper = QWidget()
        content_wrapper.setStyleSheet(f"background-color: {Colors.BG};")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)

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

        # Show Home at once; its numbers load right after the window is on screen
        self._switch_page(0, refresh=False)
        QTimer.singleShot(0, self._refresh_current)

        # ── Background sync ───────────────────────────
        # Runs the offline sync engine (push queued outbox operations, then
        # pull incremental updates) on a timer so it's actually exercised —
        # previously SyncService was never invoked from anywhere in the app.
        self._sync_service = SyncService()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._run_sync_cycle)
        self._sync_timer.start(SYNC_INTERVAL_MS)

        # Tell the user when a newer version is published (installed builds only)
        self.updater = Updater(self, self.update_banner)
        self.updater.start()
        # Run one cycle shortly after startup too, rather than waiting a
        # full interval for the first sync.
        QTimer.singleShot(2000, self._run_sync_cycle)

    # ------------------------------------------------------------------
    # Background sync cycle
    # ------------------------------------------------------------------
    def _run_sync_cycle(self):
        """
        Push any queued offline changes, then pull incremental updates.

        Runs on a timer (see SYNC_INTERVAL_MS) and once shortly after
        startup. Silently skips when the backend is unreachable, and never
        raises — a background sync failure shouldn't interrupt the user.
        """
        try:
            if not self._sync_service.is_online():
                return
            push_result = self._sync_service.push_sync()
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
            self._sync_service.pull_sync()
        except SessionExpiredError:
            return  # the expiry hook has signed the user out; the outbox is kept
        except Exception:
            logger.exception("Background sync cycle failed")

    def _get_allowed_nav_items(self):
        role = Session.get_role()

        # OWNER sees everything; a manager sees everything except staff accounts
        if role == UserRole.OWNER:
            return self.NAV_ITEMS
        if role == UserRole.MANAGER:
            # restoration is for the owner and artisans only
            return [i for i in self.NAV_ITEMS if i[1] not in ("Staff", "Restoration", "Designs")]

        allowed = []
        for icon, label, index in self.NAV_ITEMS:
            if role == UserRole.SALES:
                # Sales can sell and manage buyers, but not see reports, the Lab,
                # or the buying side (materials and purchases)
                if label not in ["Reports", "3D Lab", "Materials", "Purchases", "Staff", "Wages", "Expenses", "Profit", "Restoration", "Designs"]:
                    allowed.append((icon, label, index))
            elif role == UserRole.ACHARI:
                # Achari focuses on stock/manufacturing and the 3D Lab, no billing/reports
                if label in ["Home", "Stock", "Workforce", "Wages", "3D Lab"]:
                    allowed.append((icon, label, index))
            elif role == UserRole.ARTISAN:
                # Artisans: stock and the 3D Lab to look things up, their pay, and Restoration
                if label in ["Home", "Stock", "Workforce", "Wages", "3D Lab", "Restoration", "Designs"]:
                    allowed.append((icon, label, index))
            elif role == UserRole.WORKER:
                # Worker sees home, stock, workforce and the 3D Lab (view only)
                if label in ["Home", "Stock", "Workforce", "Wages", "3D Lab"]:
                    allowed.append((icon, label, index))
            else:
                # Default safety
                if label == "Home":
                    allowed.append((icon, label, index))
        return allowed

    # ------------------------------------------------------------------
    # Nav button factory
    # ------------------------------------------------------------------
    def _create_nav_button(self, icon: str, label: str, index: int) -> QPushButton:
        btn = QPushButton(f"  {icon}   {label}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(48)
        btn.setStyleSheet(self._nav_button_css(active=False))
        btn.clicked.connect(lambda _, idx=index: self._switch_page(idx))
        return btn

    def _nav_button_css(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background-color: {Colors.SIDEBAR_ACTIVE};
                    color: {Colors.SIDEBAR_ACTIVE_TEXT};
                    border: none;
                    border-left: 3px solid {Colors.SIDEBAR_ACCENT};
                    padding: 0 20px;
                    font-size: 15px;
                    font-weight: 600;
                    text-align: left;
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Colors.SIDEBAR_TEXT};
                    border: none;
                    border-left: 3px solid transparent;
                    padding: 0 20px;
                    font-size: 15px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {Colors.SIDEBAR_HOVER};
                    color: white;
                }}
            """

    # ------------------------------------------------------------------
    # Page switching with active state + auto-refresh
    # ------------------------------------------------------------------
    def _switch_page(self, index: int, refresh: bool = True):
        self.content_stack.setCurrentIndex(index)

        # Update active state on nav buttons
        for i, btn in self._nav_mapping.items():
            btn.setStyleSheet(self._nav_button_css(active=(i == index)))

        if refresh:
            self._refresh_current()

    def _refresh_current(self):
        # Auto-refresh data for the visible screen
        widget = self.content_stack.currentWidget()
        if hasattr(widget, "refresh_data"):
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
        Session.clear_token()
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

    def _flush_outbox(self):
        """Best effort: hand queued bills to the server under this user's own login
        before it is cleared, so they do not wait for this user's next sign-in."""
        try:
            if self._sync_service.is_online():
                self._sync_service.push_sync()
        except Exception:
            logger.exception("Could not send queued bills at sign-out")

    def _handle_logout(self):
        self._signing_out = True
        self._sync_timer.stop()
        self._flush_outbox()

        from services.auth_service import AuthService

        AuthService().logout()
        from ui.login_window import LoginWindow

        self._login_window = LoginWindow()
        self._login_window.show()
        self.close()
