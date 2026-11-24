"""
ui/theme.py

Centralized design system for FurniBiz Desktop.
All colors, fonts, and shared stylesheets live here.
Import from any screen:  from ui.theme import Theme

The look follows Bootstrap 5: contextual colour roles (primary, secondary, success,
danger, warning, info, light, dark), a 4/8/16/24 spacing scale, 6px radius controls,
outline and solid buttons in three sizes, badges, alerts, striped tables with a light
header, and form controls with a focus ring. The brand colours are mapped onto those
roles (primary = brand brown, secondary = brand gold), so any screen that already
calls Theme.btn_primary(), Theme.input_style() or Theme.table_style() picks the new
look up without changes. New code can use the generic helpers: Theme.btn(),
Theme.badge(), Theme.alert(), Theme.card().
"""

from functools import lru_cache


def _arrow(name: str) -> str:
    """Path of a small interface arrow, in the form a style sheet's url() wants."""
    from ui.assets import ICON_DIR

    return (ICON_DIR / f"{name}.png").as_posix()


@lru_cache(maxsize=None)
def mix(color: str, other: str, weight: float) -> str:
    """Blend `color` towards `other` (0 = color, 1 = other), like Sass mix()."""
    a = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * weight):02X}" for x, y in zip(a, b))


def tint(color: str, weight: float) -> str:
    """Lighten towards white (Bootstrap's tint-color)."""
    return mix(color, "#FFFFFF", weight)


def shade(color: str, weight: float) -> str:
    """Darken towards black (Bootstrap's shade-color)."""
    return mix(color, "#000000", weight)


class Colors:
    """Application color palette."""

    # Brand tokens: docs/brand/design-tokens.json in nakamadesk-backend
    BRAND_BROWN = "#5A2A06"
    BRAND_GOLD = "#BF830B"
    BRAND_GOLD_LIGHT = "#D9A441"
    BRAND_DARK = "#2A1A10"

    # Bootstrap contextual roles, mapped onto the brand
    PRIMARY = BRAND_BROWN
    SECONDARY = BRAND_GOLD
    SUCCESS = "#2B7149"
    DANGER = "#B3261E"
    WARNING = BRAND_GOLD_LIGHT
    INFO = "#8C5A2B"
    LIGHT = "#FBF6EC"
    DARK = BRAND_DARK

    # Sidebar (light, so the brown and gold logo shows on it)
    SIDEBAR_BG = "#FFFFFF"
    SIDEBAR_HOVER = "#F5EEDF"
    SIDEBAR_ACTIVE = "#F7E7C2"
    SIDEBAR_TEXT = "#5A3A22"
    SIDEBAR_ACTIVE_TEXT = "#5A2A06"
    SIDEBAR_ACCENT = "#BF830B"  # brand gold
    SIDEBAR_HEADING = "#A38A6D"

    # Navbar
    NAVBAR_BG = "#FFFFFF"

    # Content area
    BG = "#FBF6EC"  # warm surface
    CARD_BG = "#ffffff"
    CARD_BORDER = "#E8DCC8"

    # Text
    TEXT_PRIMARY = "#3A1B04"
    TEXT_SECONDARY = "#7A5A3C"
    TEXT_MUTED = "#7E6648"  # 4.5:1 on every surface (was #A38A6D, 3:1)

    # Accent colors
    GREEN = SUCCESS
    GREEN_DARK = "#256640"
    ORANGE = "#8F5F00"  # text-safe amber; BRAND_GOLD stays for borders and fills
    RED = "#B3261E"
    PURPLE = "#7A4620"
    BLUE = "#8C5A2B"
    TEAL = "#2F7D4F"

    # Borders & misc
    BORDER = "#E8DCC8"
    INPUT_BORDER = "#D9C9AD"
    INPUT_FOCUS = "#BF830B"
    INPUT_FOCUS_RING = "#EBD3A0"  # the soft ring around a focused control
    INPUT_DISABLED_BG = "#F5EEDF"
    TABLE_HEADER_BG = "#F5EEDF"
    TABLE_ALT_ROW = "#FBF6EC"
    TABLE_HOVER = "#F7E7C2"
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


class Spacing:
    """The 4 / 8 / 16 / 24 spacing scale (Bootstrap's 1, 2, 3, 4 steps, at 16px = 1rem)."""

    XS = 4
    SM = 8
    MD = 16
    LG = 24
    XL = 32  # page margins


class Radius:
    SM = 4
    MD = 6  # Bootstrap's default control radius
    LG = 8  # cards
    PILL = 999


# role -> (base colour, text colour on that base)
ROLES = {
    "primary": (Colors.PRIMARY, "#FFFFFF"),
    "secondary": (Colors.SECONDARY, Colors.BRAND_DARK),
    "success": (Colors.SUCCESS, "#FFFFFF"),
    "danger": (Colors.DANGER, "#FFFFFF"),
    "warning": (Colors.WARNING, Colors.BRAND_DARK),
    "info": (Colors.INFO, "#FFFFFF"),
    "light": (Colors.LIGHT, Colors.TEXT_PRIMARY),
    "dark": (Colors.DARK, "#FFFFFF"),
}

# button sizes: (vertical padding, horizontal padding, font px)
BUTTON_SIZES = {
    "sm": (Spacing.XS, Spacing.SM, Fonts.CAPTION),
    "md": (Spacing.SM, Spacing.MD, Fonts.BODY),
    "lg": (Spacing.MD, Spacing.LG, Fonts.HEADING_MD),
}


def _role(name: str) -> tuple[str, str]:
    if name not in ROLES:
        raise ValueError(f"unknown role {name!r}; use one of {', '.join(ROLES)}")
    return ROLES[name]


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
            QToolTip {{
                background-color: {Colors.DARK};
                color: white;
                border: none;
                border-radius: {Radius.SM}px;
                padding: {Spacing.XS}px {Spacing.SM}px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.INPUT_BORDER};
                border-radius: 5px;
                min-height: 32px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Colors.TEXT_MUTED};
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 10px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {Colors.INPUT_BORDER};
                border-radius: 5px;
                min-width: 32px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {Colors.TEXT_MUTED};
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                width: 0;
                height: 0;
            }}
            QScrollBar::add-page, QScrollBar::sub-page {{
                background: transparent;
            }}
        """

    @staticmethod
    def install(app) -> None:
        """Apply the global stylesheet and the behaviours QSS cannot express: the soft
        focus ring on form controls."""
        from ui.components.bootstrap import BootstrapBehaviour

        if getattr(app, "_bootstrap_behaviour", None) is not None:
            return  # once is enough: re-applying a style sheet re-polishes every open window
        app.setStyleSheet(Theme.global_stylesheet())
        app._bootstrap_behaviour = BootstrapBehaviour(app)

    @staticmethod
    def stripe_tables(widget) -> None:
        """Striped rows, content-fitted columns and a details popup for every table under `widget` (a style sheet cannot)."""
        from PyQt6.QtWidgets import QTableWidget

        from ui.components.elastic import make_elastic
        from ui.components.row_details import make_inspectable

        for table in widget.findChildren(QTableWidget):
            table.setAlternatingRowColors(True)
            make_elastic(table)
            make_inspectable(table)

    # ------------------------------------------------------------------
    # Content area background
    # ------------------------------------------------------------------
    @staticmethod
    def content_bg() -> str:
        return f"background-color: {Colors.BG};"

    # ------------------------------------------------------------------
    # Form controls (Bootstrap .form-control / .form-select)
    # ------------------------------------------------------------------
    @staticmethod
    def input_style() -> str:
        return f"""
            QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QPlainTextEdit {{
                border: 1px solid {Colors.INPUT_BORDER};
                border-radius: {Radius.MD}px;
                padding: {Spacing.SM}px 12px;
                font-size: {Fonts.BODY}px;
                background: {Colors.CARD_BG};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.SIDEBAR_ACTIVE};
                selection-color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
            QComboBox:focus, QPlainTextEdit:focus {{
                border: 1px solid {Colors.INPUT_FOCUS};
            }}
            QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled,
            QComboBox:disabled, QPlainTextEdit:disabled {{
                background: {Colors.INPUT_DISABLED_BG};
                color: {Colors.TEXT_MUTED};
            }}
            QLineEdit[invalid="true"], QSpinBox[invalid="true"], QDoubleSpinBox[invalid="true"],
            QDateEdit[invalid="true"], QComboBox[invalid="true"], QPlainTextEdit[invalid="true"] {{
                border: 1px solid {Colors.DANGER};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow, QDateEdit::down-arrow {{
                image: url({_arrow("chevron-down")});
                width: 12px;
                height: 12px;
            }}
            QDateEdit::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                border: none;
                width: 28px;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                subcontrol-origin: border;
                border: none;
                background: transparent;
                width: 22px;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                image: url({_arrow("chevron-up")});
                width: 10px;
                height: 10px;
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                image: url({_arrow("chevron-down")});
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {Colors.INPUT_BORDER};
                background: {Colors.CARD_BG};
                selection-background-color: {Colors.SIDEBAR_ACTIVE};
                selection-color: {Colors.TEXT_PRIMARY};
                outline: none;
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_MUTED};
            }}
        """

    # ------------------------------------------------------------------
    # Buttons (Bootstrap .btn, .btn-{role}, .btn-outline-{role}, .btn-sm/.btn-lg)
    # ------------------------------------------------------------------
    @staticmethod
    @lru_cache(maxsize=None)  # a table of 500 rows asks for the same button style 2,500 times
    def btn(role: str = "primary", size: str = "md", outline: bool = False) -> str:
        """Style sheet for a QPushButton: `role` is a Bootstrap role, `size` is sm/md/lg."""
        base, on_base = _role(role)
        pad_y, pad_x, font = BUTTON_SIZES[size]
        # A line is one text row; Qt adds the padding on top of it.
        if outline:
            # Gold and the light tints are too pale as text on white: use the dark form.
            text = (tint(base, 0.15) if Colors.DARK_MODE else shade(base, 0.45)) if role in ("secondary", "warning") else base
            if role == "light":
                text = Colors.TEXT_SECONDARY
            hover_bg, hover_text = base, on_base
            border = base if role != "light" else Colors.BORDER
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {text};
                    border: 1px solid {border};
                    border-radius: {Radius.MD}px;
                    padding: {pad_y}px {pad_x}px;
                    font-size: {font}px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border-color: {hover_bg};
                    color: {hover_text};
                }}
                QPushButton:pressed {{
                    background-color: {shade(hover_bg, 0.15)};
                    border-color: {shade(hover_bg, 0.15)};
                    color: {hover_text};
                }}
                QPushButton:disabled {{
                    background-color: transparent;
                    color: {shade(text, 0.45) if Colors.DARK_MODE else tint(text, 0.5)};
                    border-color: {shade(border, 0.45) if Colors.DARK_MODE else tint(border, 0.5)};
                }}
            """
        hover = shade(base, 0.15) if role != "light" else Colors.SIDEBAR_HOVER
        pressed = shade(base, 0.25) if role != "light" else Colors.BORDER
        border = base if role != "light" else Colors.BORDER
        return f"""
            QPushButton {{
                background-color: {base};
                color: {on_base};
                border: 1px solid {border};
                border-radius: {Radius.MD}px;
                padding: {pad_y}px {pad_x}px;
                font-size: {font}px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {hover};
                border-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
                border-color: {pressed};
            }}
            QPushButton:disabled {{
                background-color: {shade(base, 0.5) if Colors.DARK_MODE else tint(base, 0.6)};
                border-color: {shade(base, 0.5) if Colors.DARK_MODE else tint(base, 0.6)};
                color: {tint(on_base, 0.3) if on_base != "#FFFFFF" else "#FFFFFF"};
            }}
        """

    @staticmethod
    def btn_primary() -> str:
        """Primary action (brand brown)."""
        return Theme.btn("primary", "md")

    @staticmethod
    def btn_secondary() -> str:
        """Everyday secondary action: outline in the secondary (gold) role."""
        return Theme.btn("secondary", "md", outline=True)

    @staticmethod
    def btn_table_action() -> str:
        """Compact button for table cell actions."""
        return Theme.btn("secondary", "sm", outline=True)

    @staticmethod
    def btn_danger() -> str:
        return Theme.btn("danger", "md")

    @staticmethod
    def btn_success() -> str:
        return Theme.btn("success", "md")

    @staticmethod
    def btn_quick_action(color: str) -> str:
        """Large coloured button. `color` is a hex colour or a role name."""
        if color in ROLES:
            return Theme.btn(color, "lg")
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: 1px solid {color};
                border-radius: {Radius.MD}px;
                padding: {Spacing.MD}px {Spacing.LG}px;
                font-size: {Fonts.HEADING_MD}px;
                font-weight: 600;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {shade(color, 0.15)};
                border-color: {shade(color, 0.15)};
            }}
            QPushButton:pressed {{
                background-color: {shade(color, 0.25)};
            }}
        """

    # ------------------------------------------------------------------
    # Badges and alerts (Bootstrap .badge, .alert)
    # ------------------------------------------------------------------
    @staticmethod
    @lru_cache(maxsize=None)
    def badge(role: str = "primary", pill: bool = True) -> str:
        base, on_base = _role(role)
        radius = 10 if pill else Radius.SM
        return f"""
            background-color: {base};
            color: {on_base};
            border-radius: {radius}px;
            padding: 2px 10px;
            font-size: {Fonts.CAPTION - 1}px;
            font-weight: 700;
        """

    @staticmethod
    @lru_cache(maxsize=None)
    def alert(role: str = "primary") -> str:
        base, _ = _role(role)
        if role in ("light",):
            base = Colors.TEXT_SECONDARY
        return f"""
            background-color: {soft(base, 0.85, 0.78)};
            color: {ink(base)};
            border: 1px solid {mix(base, Colors.CARD_BG, 0.55) if Colors.DARK_MODE else tint(base, 0.6)};
            border-radius: {Radius.MD}px;
            padding: 12px {Spacing.MD}px;
            font-size: {Fonts.BODY_SM}px;
        """

    # ------------------------------------------------------------------
    # Card (Bootstrap .card)
    # ------------------------------------------------------------------
    @staticmethod
    def card(selector: str = "QFrame") -> str:
        return f"""
            {selector} {{
                background-color: {Colors.CARD_BG};
                border: 1px solid {Colors.CARD_BORDER};
                border-radius: {Radius.LG}px;
            }}
        """

    # ------------------------------------------------------------------
    # Table (Bootstrap .table .table-striped, light header)
    # ------------------------------------------------------------------
    @staticmethod
    def table_style() -> str:
        return f"""
            QTableWidget, QTableView {{
                background-color: {Colors.CARD_BG};
                alternate-background-color: {Colors.TABLE_ALT_ROW};
                border: 1px solid {Colors.CARD_BORDER};
                border-radius: {Radius.LG}px;
                gridline-color: transparent;
                font-size: {Fonts.BODY}px;
                selection-background-color: {Colors.SIDEBAR_ACTIVE};
                selection-color: {Colors.TEXT_PRIMARY};
            }}
            QTableWidget::item, QTableView::item {{
                padding: {Spacing.SM}px 12px;
                border-bottom: 1px solid {Colors.BORDER};
            }}
            QTableWidget::item:hover, QTableView::item:hover {{
                background-color: {Colors.TABLE_HOVER};
            }}
            QTableWidget::item:selected, QTableView::item:selected {{
                background-color: {Colors.SIDEBAR_ACTIVE};
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

    @staticmethod
    def style_tabs(tabs) -> None:
        """Tabs as rounded pills in the brand colours, instead of the grey system tabs."""
        tabs.setDocumentMode(True)  # no frame around the page
        tabs.tabBar().setDrawBase(False)
        tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{ border: none; background: transparent; top: 6px; }}
            QTabBar::tab {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid transparent;
                border-radius: {Radius.MD}px;
                padding: 7px 16px;
                margin: 0 4px 0 0;
                font-size: {Fonts.BODY}px;
                font-weight: 500;
            }}
            QTabBar::tab:hover {{ background: {Colors.SIDEBAR_HOVER}; color: {Colors.TEXT_PRIMARY}; }}
            QTabBar::tab:selected {{
                background: {Colors.SIDEBAR_ACTIVE};
                color: {Colors.TEXT_PRIMARY};
                border-color: {Colors.BRAND_GOLD_LIGHT};
                font-weight: 700;
            }}
            """
        )

    @staticmethod
    def style_table(table) -> None:
        """Table look plus column titles aligned left, like the text under them (Qt centres them)."""
        from PyQt6.QtCore import QTimer, Qt

        table.setStyleSheet(Theme.table_style())
        header = getattr(table, "horizontalHeader", None)
        if callable(header):
            header().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            # A table whose columns all fit their contents leaves the right side empty: let its
            # last column take the rest. Decided after the screen has set its own column modes.
            QTimer.singleShot(0, lambda: Theme._fill_width(table))

    @staticmethod
    def _fill_width(table) -> None:
        from PyQt6.QtWidgets import QHeaderView

        try:
            header = table.horizontalHeader()
            stretching = any(
                header.sectionResizeMode(i) == QHeaderView.ResizeMode.Stretch for i in range(header.count())
            )
            if not stretching and header.count():
                header.setStretchLastSection(True)
        except RuntimeError:  # the table was closed before this ran
            pass

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
    # Label / caption (Bootstrap .form-label)
    # ------------------------------------------------------------------
    @staticmethod
    def label() -> str:
        return f"""
            font-size: {Fonts.BODY}px;
            font-weight: 600;
            color: {Colors.TEXT_SECONDARY};
            margin-bottom: 2px;
        """

    @staticmethod
    def muted() -> str:
        """Secondary text (Bootstrap .text-muted)."""
        return f"font-size: {Fonts.BODY_SM}px; color: {Colors.TEXT_MUTED};"


# ----------------------------------------------------------------------
# Light and dark: one palette applied before any screen is built
# ----------------------------------------------------------------------
Colors.DARK_MODE = False
LIGHT_PALETTE = {k: v for k, v in vars(Colors).items() if k.isupper() and isinstance(v, str)}

# Warm, not blue-grey: the same teak and gold, with the lights turned down. Text colours are the
# ones meant for a dark surface (brighter greens, ambers and reds), and the primary button turns
# gold so it still stands out.
DARK_PALETTE = {
    "BRAND_BROWN": "#E2B25A",  # where the brand brown was text on a light page, it is gold on a dark one
    "PRIMARY": "#D9A441",
    "SECONDARY": "#E2B25A",
    "SUCCESS": "#3E9C6A",
    "DANGER": "#D2453D",
    "WARNING": "#E2B25A",
    "INFO": "#C48A4A",
    "LIGHT": "#2E2116",
    "DARK": "#120C07",
    "SIDEBAR_BG": "#21170F",
    "SIDEBAR_HOVER": "#2E2116",
    "SIDEBAR_ACTIVE": "#4A3414",
    "SIDEBAR_TEXT": "#D8C3A4",
    "SIDEBAR_ACTIVE_TEXT": "#FFE2A8",
    "SIDEBAR_ACCENT": "#D9A441",
    "SIDEBAR_HEADING": "#A78F70",
    "NAVBAR_BG": "#21170F",
    "BG": "#1B130C",
    "CARD_BG": "#261B12",
    "CARD_BORDER": "#3A2B1B",
    "TEXT_PRIMARY": "#F4E9D6",
    "TEXT_SECONDARY": "#CDB89A",
    "TEXT_MUTED": "#B39B7B",
    "GREEN": "#6CC391",
    "GREEN_DARK": "#4FAE7A",
    "ORANGE": "#E8B64F",
    "RED": "#F0877F",
    "PURPLE": "#D1A06F",
    "BLUE": "#D1A06F",
    "TEAL": "#6CC391",
    "BORDER": "#3A2B1B",
    "INPUT_BORDER": "#4A3822",
    "INPUT_FOCUS": "#D9A441",
    "INPUT_FOCUS_RING": "#6B4C16",
    "INPUT_DISABLED_BG": "#2A1E14",
    "TABLE_HEADER_BG": "#2E2116",
    "TABLE_ALT_ROW": "#21170F",
    "TABLE_HOVER": "#3D2C14",
    "LOW_STOCK_BG": "#3E2E12",
    "SUCCESS_BG": "#17301F",
    "WARNING_BG": "#3E2E12",
    "ERROR_BG": "#3B1A17",
}


def _build_roles() -> dict:
    primary_text = Colors.BRAND_DARK if Colors.DARK_MODE else "#FFFFFF"  # dark text on the gold button
    return {
        "primary": (Colors.PRIMARY, primary_text),
        "secondary": (Colors.SECONDARY, Colors.BRAND_DARK),
        "success": (Colors.SUCCESS, "#FFFFFF"),
        "danger": (Colors.DANGER, "#FFFFFF"),
        "warning": (Colors.WARNING, Colors.BRAND_DARK),
        "info": (Colors.INFO, "#FFFFFF"),
        "light": (Colors.LIGHT, Colors.TEXT_PRIMARY),
        "dark": (Colors.DARK, "#FFFFFF"),
    }


def apply_theme(name: str) -> None:
    """Switch the whole palette to "light" or "dark". Call it before any screen is built (the
    program does at start-up, from the saved setting): screens read the colours as they are built."""
    dark = name == "dark"
    for key, value in LIGHT_PALETTE.items():
        setattr(Colors, key, DARK_PALETTE.get(key, value) if dark else value)
    Colors.DARK_MODE = dark
    ROLES.clear()
    ROLES.update(_build_roles())
    Theme.btn.cache_clear()


def soft(color: str, light: float = 0.88, dark: float = 0.80) -> str:
    """A quiet background in `color`'s hue that suits the current surface: pale on a light page,
    a deep tint of the card colour on a dark one."""
    return mix(color, Colors.CARD_BG, dark if Colors.DARK_MODE else light)


def ink(color: str) -> str:
    """Text in `color`'s hue that reads on `soft(color)`."""
    return tint(color, 0.45) if Colors.DARK_MODE else shade(color, 0.4)


def native_dark_palette():
    """A Qt palette to match, so the parts a style sheet cannot reach (message boxes, menus,
    the calendar) are dark too."""
    from PyQt6.QtGui import QColor, QPalette

    p = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, Colors.BG),
        (QPalette.ColorRole.WindowText, Colors.TEXT_PRIMARY),
        (QPalette.ColorRole.Base, Colors.CARD_BG),
        (QPalette.ColorRole.AlternateBase, Colors.TABLE_ALT_ROW),
        (QPalette.ColorRole.Text, Colors.TEXT_PRIMARY),
        (QPalette.ColorRole.Button, Colors.CARD_BG),
        (QPalette.ColorRole.ButtonText, Colors.TEXT_PRIMARY),
        (QPalette.ColorRole.ToolTipBase, Colors.DARK),
        (QPalette.ColorRole.ToolTipText, "#FFFFFF"),
        (QPalette.ColorRole.Highlight, Colors.SIDEBAR_ACTIVE),
        (QPalette.ColorRole.HighlightedText, Colors.TEXT_PRIMARY),
        (QPalette.ColorRole.PlaceholderText, Colors.TEXT_MUTED),
        (QPalette.ColorRole.Link, Colors.BRAND_GOLD_LIGHT),
    ):
        p.setColor(role, QColor(color))
    return p


def _transparent_cell_widgets() -> None:
    """A widget put in a table cell (a row of buttons) took the page colour as its background,
    which showed as a patch against the row's own colour (white, striped or dark). Unless it
    paints its own background, it is now transparent."""
    from PyQt6.QtWidgets import QTableWidget

    original = QTableWidget.setCellWidget

    def set_cell_widget(self, row, column, widget):
        if widget is not None and not widget.property("cell_background_set"):
            widget.setProperty("cell_background_set", True)
            widget.setStyleSheet("QWidget { background: transparent; }" + widget.styleSheet())
        original(self, row, column, widget)

    QTableWidget.setCellWidget = set_cell_widget


_transparent_cell_widgets()
