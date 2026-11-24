"""
ui/dashboard_window.py

Home dashboard — greeting, KPI metric cards, quick action buttons, and a
"Needs attention" list (machines due for service, budgets nearly used up).
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

from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts, Spacing
from ui.components.bootstrap import Card, Grid12
from ui.components.carvings import CarvingRow
from ui.components.metric_card import MetricCard
from services.money import inr
from services.report_service import ReportService
from services.event_bus import EventBus, SALE_CREATED
from services.session import Session
from ui.workers import load_async


def _money(value) -> str:
    return f"{inr(float(value or 0), 0)}"


def attention_lines(attention: dict) -> list[tuple[str, str, str]]:
    """(text, colour role, page to open) for each thing that needs a look, worst first."""
    rows = []
    for m in attention.get("machines", []):
        name = f"{m.get('name', 'Machine')} ({m.get('tag', '')})".replace(" ()", "")
        due = m.get("service_due_on") or "soon"
        if m.get("service_overdue"):
            rows.append((f"{name}: service was due {due}", "danger", "machines"))
        else:
            rows.append((f"{name}: service due {due}", "warning", "machines"))
    labels = {"machines": "Machines", "raw_materials": "Raw materials"}
    periods = {"month": "this month", "financial_year": "this financial year"}
    for b in attention.get("budgets", []):
        what = f"{labels.get(b.get('category'), 'Budget')} budget {periods.get(b.get('period'), '')}".strip()
        used = b.get("percent_used")
        pct = f"{float(used):.0f}% used" if used is not None else "nearly used up"
        if b.get("state") == "over":
            rows.append((f"{what}: over by {_money(abs(float(b.get('remaining') or 0)))}", "danger", "budgets"))
        else:
            rows.append((f"{what}: {pct}, {_money(b.get('remaining'))} left", "warning", "budgets"))
    rows.sort(key=lambda r: r[1] != "danger")
    return rows


class DashboardWindow(QWidget):

    def __init__(self):
        super().__init__()
        self._report_service = ReportService()
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()
        # refresh_data() is NOT called here — MainWindow._switch_page(0) triggers it
        EventBus.subscribe(SALE_CREATED, self.refresh_async)

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

        self.btn_new_bill = IconButton("🧾  New Bill")
        self.btn_new_bill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_bill.setStyleSheet(Theme.btn_quick_action("primary"))
        self.btn_new_bill.clicked.connect(lambda: self._navigate("new_bill"))

        self.btn_view_stock = IconButton("📦  View Stock")
        self.btn_view_stock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_stock.setStyleSheet(Theme.btn("primary", "lg", outline=True))
        self.btn_view_stock.clicked.connect(lambda: self._navigate("stock"))

        self.btn_add_buyer = IconButton("👤  Add Buyer")
        self.btn_add_buyer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_buyer.setStyleSheet(Theme.btn("primary", "lg", outline=True))
        self.btn_add_buyer.clicked.connect(lambda: self._navigate("buyers"))

        qa_row.addWidget(self.btn_new_bill)
        qa_row.addWidget(self.btn_view_stock)
        qa_row.addWidget(self.btn_add_buyer)
        qa_row.addStretch()

        layout.addWidget(self.qa_container)

        # ── Needs attention (owner and manager) ──────
        self.attention_card = Card()
        self.attention_card.body.setSpacing(Spacing.SM)
        self.attention_title = QLabel("Needs attention")
        self.attention_title.setStyleSheet(Theme.subheading())
        self.attention_card.body.addWidget(self.attention_title)
        self.attention_list = QVBoxLayout()
        self.attention_list.setSpacing(Spacing.XS)
        self.attention_card.body.addLayout(self.attention_list)
        self.attention_card.setVisible(False)  # shown only when there is something to say
        layout.addWidget(self.attention_card)

        # ── Welcome card: the carving pair facing the god, from the website ──
        self.welcome_card = Card()
        self.welcome_card.body.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self.carvings = CarvingRow("temple")
        self.carvings.setMinimumHeight(96)
        self.carvings.setMaximumHeight(320)
        self.welcome_card.body.addWidget(self.carvings, 1)
        layout.addWidget(self.welcome_card, 1)

    def _fetch(self):
        return (
            self._report_service.get_dashboard_summary(),
            self._report_service.get_attention(),
        )

    def _show(self, result):
        summary, attention = result
        self._show_summary(summary)
        self._show_attention(attention)

    def refresh_data(self):
        if self._prepare():
            self._show(self._fetch())

    def refresh_async(self):
        """Same as refresh_data, but the numbers are fetched in the background."""
        if self._prepare():
            load_async(self, self._fetch, self._show)

    def _prepare(self) -> bool:
        """Greeting and who sees what (no server call). True when the numbers are wanted."""
        # Update greeting dynamically
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        self.greeting_lbl.setText(greeting)

        role = Session.get_role()
        is_admin = Session.can("reports:dashboard:read")
        can_sell = Session.can("sales:sale:create")

        # Role-based UI visibility
        self.metrics_container.setVisible(is_admin)
        self.btn_new_bill.setVisible(can_sell)
        self.btn_add_buyer.setVisible(can_sell)

        if role == "achari":
            self.subtitle_lbl.setText("Manage manufacturing and stock")
        elif role == "worker":
            self.subtitle_lbl.setText("Your daily attendance and basic stock")
        else:
            self.subtitle_lbl.setText("Here's your business at a glance")

        return is_admin

    def _show_summary(self, summary):
        if summary:
            self.card_sales.set_value(summary.get("today_sales_count", 0))
            self.card_revenue.set_value(
                f"{inr(float(summary.get('today_revenue', 0)))}"
            )
            self.card_low_stock.set_value(summary.get("low_stock_count", 0))
            self.card_wages.set_value(
                f"{inr(float(summary.get('pending_wages_total', 0)))}"
            )

    def _show_attention(self, attention):
        """One line per machine due and per budget close to its limit; hidden when none."""
        while self.attention_list.count():
            item = self.attention_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = attention_lines(attention or {})
        for text, role, page in rows:
            btn = IconButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(Theme.alert(role) + "text-align: left;")
            btn.clicked.connect(lambda _=False, p=page: self._navigate(p))
            self.attention_list.addWidget(btn)
        self.attention_card.setVisible(bool(rows))

    def _navigate(self, page_name: str):
        """Navigate to another page via MainWindow."""
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(page_name)
