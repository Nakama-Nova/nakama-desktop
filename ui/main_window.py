"""
ui/main_window.py

Main application shell — dark sidebar with emoji icons, active state,
auto-refresh on page switch, and themed layout.
"""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QStackedWidget,
    QLabel,
)
from PyQt6.QtCore import Qt

from ui.theme import Theme, Colors, Fonts

from ui.dashboard_window import DashboardWindow
from ui.inventory_window import InventoryWindow
from ui.sales_screen import SalesScreen
from ui.customers_screen import CustomersScreen
from ui.reports_screen import ReportsScreen
from ui.sales_history_screen import SalesHistoryScreen
from services.session import Session
from services.enums import UserRole


class MainWindow(QMainWindow):

    NAV_ITEMS = [
        ("🏠", "Home", 0),
        ("🧾", "New Bill", 1),
        ("📦", "Stock", 2),
        ("👤", "Buyers", 3),
        ("📜", "Bill History", 4),
        ("📊", "Reports", 5),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FurniBiz — Furniture Business Manager")
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
            f"background-color: {Colors.SIDEBAR_BG}; border-bottom: 1px solid #252b48;"
        )
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(20, 24, 20, 20)

        brand_lbl = QLabel("🪑 FurniBiz")
        brand_lbl.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: white;
        """)
        brand_layout.addWidget(brand_lbl)

        brand_sub = QLabel("Business Manager")
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

        # Logout at bottom
        logout_btn = QPushButton("🚪  Sign Out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.SIDEBAR_TEXT};
                border: none;
                border-top: 1px solid #252b48;
                padding: 16px 20px;
                font-size: {Fonts.BODY}px;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {Colors.RED};
                background-color: #252b48;
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
        content_layout.addWidget(self.content_stack)
        main_layout.addWidget(content_wrapper)

        # Initialize screens
        self.dashboard_view = DashboardWindow()
        self.sales_view = SalesScreen()
        self.inventory_view = InventoryWindow()
        self.customers_view = CustomersScreen()
        self.sales_history_view = SalesHistoryScreen()
        self.reports_view = ReportsScreen()

        self.content_stack.addWidget(self.dashboard_view)  # 0
        self.content_stack.addWidget(self.sales_view)  # 1
        self.content_stack.addWidget(self.inventory_view)  # 2
        self.content_stack.addWidget(self.customers_view)  # 3
        self.content_stack.addWidget(self.sales_history_view)  # 4
        self.content_stack.addWidget(self.reports_view)  # 5

        # Set default (Home)
        self._switch_page(0)

    def _get_allowed_nav_items(self):
        role = Session.get_role()

        # OWNER and MANAGER see everything
        if role in [UserRole.OWNER, UserRole.MANAGER]:
            return self.NAV_ITEMS

        allowed = []
        for icon, label, index in self.NAV_ITEMS:
            if role == UserRole.SALES:
                # Sales can sell and manage buyers, but not see reports
                if label not in ["Reports"]:
                    allowed.append((icon, label, index))
            elif role == UserRole.ACHARI:
                # Achari focuses on stock/manufacturing, no billing/reports
                if label in ["Home", "Stock"]:
                    allowed.append((icon, label, index))
            elif role == UserRole.WORKER:
                # Worker only sees home and stock, no billing/buyers/reports
                if label in ["Home", "Stock"]:
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
    def _switch_page(self, index: int):
        self.content_stack.setCurrentIndex(index)

        # Update active state on nav buttons
        for i, btn in self._nav_mapping.items():
            btn.setStyleSheet(self._nav_button_css(active=(i == index)))

        # Auto-refresh data for the visible screen
        widget = self.content_stack.currentWidget()
        if hasattr(widget, "refresh_data"):
            widget.refresh_data()

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
    def _handle_logout(self):
        from services.auth_service import AuthService

        AuthService().logout()
        from ui.login_window import LoginWindow

        self._login_window = LoginWindow()
        self._login_window.show()
        self.close()
