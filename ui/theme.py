"""
ui/theme.py

Centralized design system for FurniBiz Desktop.
All colors, fonts, and shared stylesheets live here.
Import from any screen:  from ui.theme import Theme
"""


class Colors:
    """Application color palette."""

    # Sidebar
    SIDEBAR_BG = "#1a1f36"
    SIDEBAR_HOVER = "#252b48"
    SIDEBAR_ACTIVE = "#2d3555"
    SIDEBAR_TEXT = "#a0a8c4"
    SIDEBAR_ACTIVE_TEXT = "#ffffff"
    SIDEBAR_ACCENT = "#4a90d9"

    # Content area
    BG = "#f0f2f5"
    CARD_BG = "#ffffff"
    CARD_BORDER = "#e4e7ec"

    # Text
    TEXT_PRIMARY = "#1a1f36"
    TEXT_SECONDARY = "#6b7280"
    TEXT_MUTED = "#9ca3af"

    # Accent colors
    GREEN = "#10b981"
    GREEN_DARK = "#059669"
    ORANGE = "#f59e0b"
    RED = "#ef4444"
    PURPLE = "#8b5cf6"
    BLUE = "#3b82f6"
    TEAL = "#14b8a6"

    # Borders & misc
    BORDER = "#e5e7eb"
    INPUT_BORDER = "#d1d5db"
    INPUT_FOCUS = "#4a90d9"
    TABLE_HEADER_BG = "#f8fafc"
    TABLE_ALT_ROW = "#f9fafb"
    LOW_STOCK_BG = "#fef3c7"

    # Status
    SUCCESS_BG = "#d1fae5"
    WARNING_BG = "#fef3c7"
    ERROR_BG = "#fee2e2"


class Fonts:
    """Font sizes used across the app."""
    FAMILY = "Segoe UI"
    HEADING_XL = 24
    HEADING_LG = 20
    HEADING_MD = 16
    BODY = 14
    BODY_SM = 13
    CAPTION = 12


class Theme:
    """Stylesheet generators for common elements."""

    @staticmethod
    def app_font() -> str:
        return f"font-family: '{Fonts.FAMILY}'; font-size: {Fonts.BODY}px;"

    # ------------------------------------------------------------------
    # Global application stylesheet
    # ------------------------------------------------------------------
    @staticmethod
    def global_stylesheet() -> str:
        return f"""
            * {{
                font-family: '{Fonts.FAMILY}';
            }}
            QWidget {{
                font-size: {Fonts.BODY}px;
            }}
            QMessageBox {{
                font-size: {Fonts.BODY}px;
            }}
            QMessageBox QPushButton {{
                min-width: 80px;
                padding: 6px 16px;
            }}
        """

    # ------------------------------------------------------------------
    # Content area background
    # ------------------------------------------------------------------
    @staticmethod
    def content_bg() -> str:
        return f"background-color: {Colors.BG};"

    # ------------------------------------------------------------------
    # Input fields
    # ------------------------------------------------------------------
    @staticmethod
    def input_style() -> str:
        return f"""
            QLineEdit, QSpinBox, QDateEdit {{
                border: 1.5px solid {Colors.INPUT_BORDER};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: {Fonts.BODY}px;
                background: {Colors.CARD_BG};
                color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus, QSpinBox:focus, QDateEdit:focus {{
                border-color: {Colors.INPUT_FOCUS};
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_MUTED};
            }}
        """

    # ------------------------------------------------------------------
    # Primary action button (green)
    # ------------------------------------------------------------------
    @staticmethod
    def btn_primary() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.GREEN};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: {Fonts.BODY}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.GREEN_DARK};
            }}
            QPushButton:pressed {{
                background-color: #047857;
            }}
        """

    # ------------------------------------------------------------------
    # Secondary / outline button
    # ------------------------------------------------------------------
    @staticmethod
    def btn_secondary() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.CARD_BG};
                color: {Colors.TEXT_PRIMARY};
                border: 1.5px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 10px 20px;
                font-size: {Fonts.BODY}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG};
                border-color: {Colors.INPUT_FOCUS};
            }}
        """

    # ------------------------------------------------------------------
    # Compact button for table cell actions
    # ------------------------------------------------------------------
    @staticmethod
    def btn_table_action() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.CARD_BG};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: {Fonts.CAPTION}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG};
                border-color: {Colors.INPUT_FOCUS};
            }}
        """

    # ------------------------------------------------------------------
    # Danger button (red)
    # ------------------------------------------------------------------
    @staticmethod
    def btn_danger() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.RED};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: {Fonts.BODY}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #dc2626;
            }}
        """

    # ------------------------------------------------------------------
    # Quick-action button (large, colored)
    # ------------------------------------------------------------------
    @staticmethod
    def btn_quick_action(color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 16px 28px;
                font-size: 15px;
                font-weight: bold;
                min-height: 48px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """

    # ------------------------------------------------------------------
    # Table styling
    # ------------------------------------------------------------------
    @staticmethod
    def table_style() -> str:
        return f"""
            QTableWidget {{
                background-color: {Colors.CARD_BG};
                border: 1px solid {Colors.CARD_BORDER};
                border-radius: 8px;
                gridline-color: {Colors.BORDER};
                font-size: {Fonts.BODY}px;
            }}
            QTableWidget::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {Colors.BORDER};
            }}
            QTableWidget::item:selected {{
                background-color: #dbeafe;
                color: {Colors.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {Colors.TABLE_HEADER_BG};
                color: {Colors.TEXT_SECONDARY};
                font-weight: bold;
                font-size: {Fonts.BODY_SM}px;
                padding: 10px 12px;
                border: none;
                border-bottom: 2px solid {Colors.BORDER};
            }}
            QTableWidget QTableCornerButton::section {{
                background-color: {Colors.TABLE_HEADER_BG};
                border: none;
            }}
        """

    # ------------------------------------------------------------------
    # Page heading
    # ------------------------------------------------------------------
    @staticmethod
    def heading(size: int = Fonts.HEADING_LG) -> str:
        return f"""
            font-size: {size}px;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
        """

    # ------------------------------------------------------------------
    # Section sub-heading
    # ------------------------------------------------------------------
    @staticmethod
    def subheading() -> str:
        return f"""
            font-size: {Fonts.HEADING_MD}px;
            font-weight: 600;
            color: {Colors.TEXT_PRIMARY};
            margin-top: 8px;
        """

    # ------------------------------------------------------------------
    # Label / caption
    # ------------------------------------------------------------------
    @staticmethod
    def label() -> str:
        return f"""
            font-size: {Fonts.BODY}px;
            font-weight: 600;
            color: {Colors.TEXT_SECONDARY};
            margin-bottom: 2px;
        """
