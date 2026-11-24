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
)
from PyQt6.QtCore import Qt

from ui.icons import IconButton
from ui.theme import Theme, Colors, Fonts, Spacing
from ui.components.bootstrap import Card, Grid12
from ui.components.carvings import CarvingRow
from ui.components.cards import HeroCard, elevate
from ui.components.metric_card import MetricCard
from services.money import inr
from services.report_service import ReportService
from services.event_bus import EventBus, SALE_CREATED
from services.session import Session
from ui.workers import load_async


HERO_TEXT = "#FFF3DC"  # cream on the deep-teak panel
HERO_MUTED = "#E5CFA8"
HERO_PRIMARY = (
    f"QPushButton {{ background: {Colors.BRAND_GOLD_LIGHT}; color: #2A1306; border: none; border-radius: 10px;"
    f" padding: 11px 20px; font-size: {Fonts.BODY + 1}px; font-weight: 700; }}"
    f"QPushButton:hover {{ background: #E6B957; }}"
)
HERO_GHOST = (
    f"QPushButton {{ background: rgba(255, 243, 220, 0.08); color: {HERO_TEXT}; border: 1px solid rgba(255, 243, 220, 0.35);"
    f" border-radius: 10px; padding: 10px 18px; font-size: {Fonts.BODY + 1}px; font-weight: 600; }}"
    f"QPushButton:hover {{ background: rgba(255, 243, 220, 0.18); }}"
)


class _Figure:
    """The revenue figure in the hero, which Home sets the way it sets a card."""

    def __init__(self, label):
        self.value_lbl = label

    def set_value(self, value) -> None:
        self.value_lbl.setText(str(value))


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
        """A hero panel first (greeting, today's takings, the three things done most), then the
        numbers as cards, then what needs attention."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.XL, Spacing.LG + 4, Spacing.XL, Spacing.LG + 4)
        layout.setSpacing(Spacing.LG + 2)

        # ── Hero: deep teak, gold light, the carvings standing on its lower edge ──
        self.hero = HeroCard()
        hero_row = QHBoxLayout(self.hero)
        hero_row.setContentsMargins(34, 24, 20, 0)
        hero_row.setSpacing(Spacing.LG)

        words = QVBoxLayout()
        words.setSpacing(Spacing.XS)
        self.greeting_lbl = QLabel("")
        self.greeting_lbl.setStyleSheet(
            f"font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif; font-size: 34px; font-weight: 700;"
            f" color: {HERO_TEXT}; background: transparent;"
        )
        words.addWidget(self.greeting_lbl)
        self.subtitle_lbl = QLabel("Here's your business at a glance")
        self.subtitle_lbl.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {HERO_MUTED}; background: transparent;")
        words.addWidget(self.subtitle_lbl)
        words.addSpacing(Spacing.MD)

        # Today's takings: the one number the owner opens the program for
        self.metrics_container = QWidget()
        self.metrics_container.setStyleSheet("background: transparent;")
        figure = QVBoxLayout(self.metrics_container)
        figure.setContentsMargins(0, 0, 0, 0)
        figure.setSpacing(0)
        figure_name = QLabel("Today's revenue")
        figure_name.setStyleSheet(f"font-size: {Fonts.BODY}px; font-weight: 600; color: {Colors.BRAND_GOLD_LIGHT}; background: transparent;")
        self.revenue_lbl = QLabel(inr(0))
        self.revenue_lbl.setStyleSheet(f"font-size: 42px; font-weight: 700; color: {HERO_TEXT}; background: transparent;")
        self.bills_hint = QLabel("No bills yet today")
        self.bills_hint.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {HERO_MUTED}; background: transparent;")
        figure.addWidget(figure_name)
        figure.addWidget(self.revenue_lbl)
        figure.addWidget(self.bills_hint)
        words.addWidget(self.metrics_container)
        self.card_revenue = _Figure(self.revenue_lbl)  # Home still sets it like a card

        words.addSpacing(Spacing.SM)
        words.addStretch(1)
        self.qa_container = QWidget()
        self.qa_container.setStyleSheet("background: transparent;")
        qa_row = QHBoxLayout(self.qa_container)
        qa_row.setContentsMargins(0, 0, 0, Spacing.LG)
        qa_row.setSpacing(Spacing.SM + 2)

        self.btn_new_bill = IconButton("🧾  New bill")
        self.btn_new_bill.setStyleSheet(HERO_PRIMARY)
        self.btn_new_bill.clicked.connect(lambda: self._navigate("new_bill"))
        self.btn_view_stock = IconButton("📦  View stock")
        self.btn_view_stock.setStyleSheet(HERO_GHOST)
        self.btn_view_stock.clicked.connect(lambda: self._navigate("stock"))
        self.btn_add_buyer = IconButton("👤  Add buyer")
        self.btn_add_buyer.setStyleSheet(HERO_GHOST)
        self.btn_add_buyer.clicked.connect(lambda: self._navigate("buyers"))
        for b in (self.btn_new_bill, self.btn_view_stock, self.btn_add_buyer):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            qa_row.addWidget(b)
        qa_row.addStretch()
        words.addWidget(self.qa_container)
        hero_row.addLayout(words, 3)

        self.carvings = CarvingRow("temple")
        self.carvings.setMinimumWidth(300)
        self.carvings.setMinimumHeight(170)
        hero_row.addWidget(self.carvings, 2)
        layout.addWidget(self.hero)

        # ── The numbers, as cards ──
        cards_grid = Grid12(gap=Spacing.MD + 2)
        self.card_sales = MetricCard("Bills today", "0", Colors.GREEN, icon="🧾")
        self.card_low_stock = MetricCard("Items running low", "0", Colors.RED, icon="⚠️")
        self.card_wages = MetricCard("Wages due", "₹0.00", Colors.ORANGE, icon="👷")
        self.stat_cards = QWidget()
        self.stat_cards.setStyleSheet("background: transparent;")
        stat_layout = QVBoxLayout(self.stat_cards)
        stat_layout.setContentsMargins(0, 0, 0, 0)
        for card in (self.card_sales, self.card_low_stock, self.card_wages):
            cards_grid.add(card, lg=4, md=6, sm=12)
        stat_layout.addWidget(cards_grid)
        layout.addWidget(self.stat_cards)

        # ── Needs attention (owner and manager) ──
        self.attention_card = Card()
        elevate(self.attention_card, blur=22, dy=5, alpha=26)
        self.attention_card.body.setContentsMargins(Spacing.LG, Spacing.MD + 2, Spacing.LG, Spacing.LG)
        self.attention_card.body.setSpacing(Spacing.SM + 2)
        self.attention_title = QLabel("Needs attention")
        self.attention_title.setStyleSheet(Theme.subheading())
        self.attention_card.body.addWidget(self.attention_title)
        self.attention_list = QVBoxLayout()
        self.attention_list.setSpacing(Spacing.SM)
        self.attention_card.body.addLayout(self.attention_list)
        self.attention_card.setVisible(False)  # shown only when there is something to say
        layout.addWidget(self.attention_card)
        layout.addStretch(1)

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
        self.stat_cards.setVisible(is_admin)
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
            bills = int(summary.get("today_sales_count", 0) or 0)
            self.card_sales.set_value(bills)
            self.bills_hint.setText("No bills yet today" if not bills else f"{bills} bill{'s' if bills != 1 else ''} today")
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
            btn.setStyleSheet(Theme.alert(role) + "text-align: left; padding: 10px 14px; min-height: 22px;")
            btn.clicked.connect(lambda _=False, p=page: self._navigate(p))
            self.attention_list.addWidget(btn)
        self.attention_card.setVisible(bool(rows))

    def _navigate(self, page_name: str):
        """Navigate to another page via MainWindow."""
        parent = self.window()
        if hasattr(parent, "navigate_to"):
            parent.navigate_to(page_name)
