"""
ui/profit_screen.py

What the business really earned: sales billed minus timber bought, wages paid and
expenses, month by month. Owner and manager only.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.money_service import PERIODS, MoneyService, period_range, rupees
from ui.components.metric_card import MetricCard
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme


class ProfitScreen(QWidget):
    def __init__(self):
        super().__init__()
        self._svc = MoneyService()
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("💹  Profit")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.period = QComboBox()
        for label, key in PERIODS:
            self.period.addItem(label, key)
        self.period.setStyleSheet(Theme.input_style())
        self.period.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.period)
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        layout.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {
            "sales": MetricCard("Sales billed", "₹0.00", Colors.GREEN, icon="🧾"),
            "purchases": MetricCard("Timber & materials bought", "₹0.00", Colors.BLUE, icon="🌳"),
            "wages": MetricCard("Wages paid", "₹0.00", Colors.PURPLE, icon="👷"),
            "expenses": MetricCard("Other expenses", "₹0.00", Colors.ORANGE, icon="💸"),
            "profit": MetricCard("Profit", "₹0.00", Colors.GREEN, icon="💹"),
            "margin": MetricCard("Margin", "0%", Colors.GREEN, icon="📈"),
        }
        for i, key in enumerate(self.cards):
            grid.addWidget(self.cards[key], i // 3, i % 3)
        layout.addLayout(grid)

        self.owed = QLabel("")
        self.owed.setWordWrap(True)
        self.owed.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: 600;")
        layout.addWidget(self.owed)
        self.where = QLabel("")
        self.where.setWordWrap(True)
        self.where.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(self.where)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Month", "Sales", "Materials", "Wages", "Expenses", "Profit"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

        note = QLabel(
            "Profit here is what came in minus what went out in the same dates. Timber counts "
            "when you buy it, so a big purchase lowers that month; the stock still on the shelf "
            "is shown above and is not lost."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        layout.addWidget(note)

    @staticmethod
    def _tint(card: MetricCard, color: str):
        card.value_lbl.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {color}; margin-top: 4px;"
        )

    @handle_permissions
    def refresh_data(self, _checked=False):
        start, end = period_range(self.period.currentData())
        rep = self._svc.profit(start, end)
        for key in ("sales", "purchases", "wages", "expenses", "profit"):
            self.cards[key].set_value(rupees(rep[key]))
        self.cards["margin"].set_value(f"{float(rep['margin_pct']):.1f}%")
        loss = float(rep["profit"]) < 0
        for key in ("profit", "margin"):
            self._tint(self.cards[key], Colors.RED if loss else Colors.GREEN)

        self.owed.setText(
            f"Owed to staff now {rupees(rep['unpaid_wages'])}   ·   "
            f"Advances staff owe you {rupees(rep['advances_outstanding'])}   ·   "
            f"Timber and materials in stock {rupees(rep['raw_material_stock_value'])}"
        )
        cats = [f"{c['category']} {rupees(c['total'])}" for c in rep["expenses_by_category"]]
        self.where.setText("Expenses: " + "   ·   ".join(cats) if cats else "")

        months = rep["months"]
        self.table.setRowCount(len(months))
        for r, m in enumerate(months):
            values = [m["month"], *(rupees(m[k]) for k in ("sales", "purchases", "wages", "expenses", "profit"))]
            for c, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if c:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 5 and float(m["profit"]) < 0:
                    cell.setForeground(Qt.GlobalColor.red)
                self.table.setItem(r, c, cell)
