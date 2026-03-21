"""
ui/components/metric_card.py

Reusable MetricCard widget for displaying KPI values.
Redesigned: emoji icon support, softer shadows, hover effect.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from ui.theme import Colors, Fonts


class MetricCard(QFrame):
    """A styled card displaying an icon+title and a large value."""

    def __init__(
        self, title: str, value: str = "0", color: str = "#3b82f6", icon: str = ""
    ):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._color = color

        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {Colors.CARD_BG};
                border-radius: 12px;
                border: 1px solid {Colors.CARD_BORDER};
                padding: 4px;
            }}
            MetricCard:hover {{
                border-color: {color};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        # Title row (with optional emoji icon)
        display_title = f"{icon}  {title}" if icon else title
        self.title_lbl = QLabel(display_title)
        self.title_lbl.setStyleSheet(f"""
            font-size: {Fonts.BODY}px;
            color: {Colors.TEXT_SECONDARY};
            font-weight: 500;
        """)

        self.value_lbl = QLabel(str(value))
        self.value_lbl.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {color};
            margin-top: 4px;
        """)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)

    def set_value(self, value) -> None:
        self.value_lbl.setText(str(value))
