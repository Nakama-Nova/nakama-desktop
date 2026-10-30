"""
ui/dashboard_window.py

Home dashboard — greeting, KPI metric cards, quick action buttons.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtCore import Qt

from ui.theme import Theme, Colors, Fonts, Spacing
from ui.components.bootstrap import Card, Grid12
from ui.components.carvings import CarvingRow
from ui.components.metric_card import MetricCard
from services.report_service import ReportService
from services.event_bus import EventBus, SALE_CREATED
from services.session import Session
from services.enums import UserRole


class DashboardWindow(QWidget):

    def __init__(self):
        super().__init__()
        self._report_service = ReportService()
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()
        # refresh_data() is NOT called here — MainWindow._switch_page(0) triggers it
        EventBus.subscribe(SALE_CREATED, self.refresh_data)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.LG + 4, Spacing.XL, Spacing.LG + 4)
        layout.setSpacing(Spacing.LG)

        # ── Greeting ──────────────────────────────────
        self.greeting_lbl = QLabel("")
        self.greeting_lbl.setStyleSheet(Theme.heading(Fonts.HEADING_XL))
        layout.addWidget(self.greeting_lbl)

        self.subtitle_lbl = QLabel("Here's your business at a glance")
        self.subtitle_lbl.setStyleSheet(f"""
            font-size: {Fonts.BODY}px;
            color: {Colors.TEXT_SECONDARY};
            margin-top: 0px;
        """)
        layout.addWidget(self.subtitle_lbl)

        # ── Metric Cards ──────────────────────────────
        # A 12-column grid: four cards across on a wide window, two by two on a
        # medium one, stacked on a narrow one.
        cards_grid = Grid12()

        self.card_sales = MetricCard("Today's Sales", "0", Colors.GREEN, icon="🧾")
        self.card_revenue = MetricCard(
            "Today's Revenue", "₹0.00", Colors.BLUE, icon="💰"
        )
        self.card_low_stock = MetricCard("Low Stock Alert", "0", Colors.RED, icon="⚠️")
        self.card_wages = MetricCard("Wages Due", "₹0.00", Colors.PURPLE, icon="👷")

        for card in (self.card_sales, self.card_revenue, self.card_low_stock, self.card_wages):
            cards_grid.add(card, lg=3, md=6, sm=12)

        self.metrics_container = QWidget()
        metrics_layout = QVBoxLayout(self.metrics_container)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.addWidget(cards_grid)
        layout.addWidget(self.metrics_container)

        # ── Quick Actions ─────────────────────────────
        self.qa_header = QLabel("Quick Actions")
        self.qa_header.setStyleSheet(Theme.subheading())
        layout.addWidget(self.qa_header)

        self.qa_container = QWidget()
        qa_row = QHBoxLayout(self.qa_container)
        qa_row.setContentsMargins(0, 0, 0, 0)
        qa_row.setSpacing(Spacing.MD)

        self.btn_new_bill = QPushButton("🧾  New Bill")
        self.btn_new_bill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_bill.setStyleSheet(Theme.btn_quick_action("success"))
        self.btn_new_bill.clicked.connect(lambda: self._navigate("new_bill"))

        self.btn_view_stock = QPushButton("📦  View Stock")
        self.btn_view_stock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_stock.setStyleSheet(Theme.btn_quick_action("primary"))
        self.btn_view_stock.clicked.connect(lambda: self._navigate("stock"))

        self.btn_add_buyer = QPushButton("👤  Add Buyer")
        self.btn_add_buyer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_buyer.setStyleSheet(Theme.btn_quick_action("secondary"))
        self.btn_add_buyer.clicked.connect(lambda: self._navigate("buyers"))

        qa_row.addWidget(self.btn_new_bill)
        qa_row.addWidget(self.btn_view_stock)
        qa_row.addWidget(self.btn_add_buyer)
        qa_row.addStretch()

        layout.addWidget(self.qa_container)

        # ── Welcome card: the carving pair facing the god, from the website ──
        self.welcome_card = Card()
        self.welcome_card.body.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self.carvings = CarvingRow("temple")
        self.carvings.setMinimumHeight(96)
        self.carvings.setMaximumHeight(320)
        self.welcome_card.body.addWidget(self.carvings, 1)
        layout.addWidget(self.welcome_card, 1)

    def refresh_data(self):
        # Update greeting dynamically
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good Morning! ☀️"
        elif hour < 17:
            greeting = "Good Afternoon! 👋"
        else:
            greeting = "Good Evening! 🌙"
        self.greeting_lbl.setText(greeting)

        role = Session.get_role()
        is_admin = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        can_sell = Session.is_authorized(
            [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]
        )

        # Role-based UI visibility
        self.metrics_container.setVisible(is_admin)
        self.btn_new_bill.setVisible(can_sell)
        self.btn_add_buyer.setVisible(can_sell)

        if role == UserRole.ACHARI:
            self.subtitle_lbl.setText("Manage manufacturing and stock")
        elif role == UserRole.WORKER:
            self.subtitle_lbl.setText("Your daily attendance and basic stock")
        else:
            self.subtitle_lbl.setText("Here's your business at a glance")

        if is_admin:
            summary = self._report_service.get_dashboard_summary()
            if summary:
                self.card_sales.set_value(summary.get("today_sales_count", 0))
                self.card_revenue.set_value(
                    f"₹{float(summary.get('today_revenue', 0)):,.2f}"
                )
                self.card_low_stock.set_value(summary.get("low_stock_count", 0))
                self.card_wages.set_value(
                    f"₹{float(summary.get('pending_wages_total', 0)):,.2f}"
                )

    def _navigate(self, page_name: str):
        """Navigate to another page via MainWindow."""
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(page_name)
