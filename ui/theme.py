"""
ui/theme.py

Centralized design system for FurniBiz Desktop.
All colors, fonts, and shared stylesheets live here.
Import from any screen:  from ui.theme import Theme
"""


class Colors:
    """Application color palette."""

    # Brand tokens: docs/brand/design-tokens.json in nakamadesk-backend
    BRAND_BROWN = "#5A2A06"
    BRAND_GOLD = "#BF830B"

    # Sidebar
    SIDEBAR_BG = "#5A2A06"  # brand brown
    SIDEBAR_HOVER = "#6E3A12"
    SIDEBAR_ACTIVE = "#7A4620"
    SIDEBAR_TEXT = "#E8DCC8"
    SIDEBAR_ACTIVE_TEXT = "#ffffff"
    SIDEBAR_ACCENT = "#BF830B"  # brand gold

    # Content area
    BG = "#FBF6EC"  # warm surface
    CARD_BG = "#ffffff"
    CARD_BORDER = "#E8DCC8"

    # Text
    TEXT_PRIMARY = "#3A1B04"
    TEXT_SECONDARY = "#7A5A3C"
    TEXT_MUTED = "#A38A6D"

    # Accent colors
    GREEN = "#2F7D4F"
    GREEN_DARK = "#256640"
    ORANGE = "#BF830B"
    RED = "#B3261E"
    PURPLE = "#7A4620"
    BLUE = "#8C5A2B"
    TEAL = "#2F7D4F"

    # Borders & misc
    BORDER = "#E8DCC8"
    INPUT_BORDER = "#D9C9AD"
    INPUT_FOCUS = "#BF830B"
    TABLE_HEADER_BG = "#F5EEDF"
    TABLE_ALT_ROW = "#FBF6EC"
    LOW_STOCK_BG = "#F7E7C2"

    # Status
    SUCCESS_BG = "#DDEFE4"
    WARNING_BG = "#F7E7C2"
    ERROR_BG = "#F6DAD7"


class Fonts:
    """Font sizes used across the app."""

    FAMILY = "Inter"  # falls back to the system UI font when not installed
    HEADING_FAMILY = "Cormorant Garamond"  # falls back to Georgia
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
                font-family: '{Fonts.FAMILY}', 'Segoe UI';
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
            QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QPlainTextEdit {{
                border: 1.5px solid {Colors.INPUT_BORDER};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: {Fonts.BODY}px;
                background: {Colors.CARD_BG};
                color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
            QComboBox:focus, QPlainTextEdit:focus {{
                border-color: {Colors.INPUT_FOCUS};
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_MUTED};
            }}
        """

    # ------------------------------------------------------------------
    # Primary action button (brand brown)
    # ------------------------------------------------------------------
    @staticmethod
    def btn_primary() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.BRAND_BROWN};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: {Fonts.BODY}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #6E3A12;
            }}
            QPushButton:pressed {{
                background-color: #4A2005;
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
                background-color: #8F1D17;
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
                background-color: #F1E3C6;
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
            font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif;
            font-size: {size + 4}px;
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
