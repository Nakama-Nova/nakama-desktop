"""
ui/login_window.py

Branded login screen: a split layout with the Vriksha logo and a pair of carvings
facing a god sculpture on the left, and a Bootstrap-style sign-in card on the right.
Inline error feedback.
"""

import requests
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QSize, Qt

from ui.assets import logo_path, scaled_pixmap
from ui.components.bootstrap import Alert, Card
from ui.components.carvings import CarvingRow
from ui.theme import Theme, Colors, Fonts, Spacing

from services.api_client import BASE_URL, APIError, insecure_remote
from services.auth_service import AuthService

LOGO_SIZE = QSize(120, 162)  # the logo is 3:4
FORM_MAX_WIDTH = 420


class LoginWindow(QWidget):

    def __init__(self):
        super().__init__()
        self._auth = AuthService()

        self.setWindowTitle("Vriksha Studio — Staff sign in")
        self.setObjectName("login")
        self.setStyleSheet(f"QWidget#login {{ background-color: {Colors.CARD_BG}; }}")

        # 1000x640 is comfortable; a small screen gets all it has. Everything inside
        # scales with the window, so 1366x768 up to 1920x1080 (and high-DPI) all fit.
        screen = self.screen().availableGeometry()
        width, height = min(1000, screen.width()), min(640, screen.height())
        self.setMinimumSize(min(820, screen.width()), min(560, screen.height()))
        self.resize(width, height)
        self.move(screen.x() + (screen.width() - width) // 2, screen.y() + (screen.height() - height) // 2)

        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_brand_panel(), 5)
        root.addWidget(self._build_form_panel(), 4)

    # ── Left: logo and carvings ───────────────────────
    def _build_brand_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("brandPanel")
        panel.setStyleSheet(
            "QFrame#brandPanel { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f" stop:0 {Colors.BG}, stop:1 #F1E2C3); border: none;"
            f" border-right: 1px solid {Colors.CARD_BORDER}; }}"
            "QFrame#brandPanel QLabel { background: transparent; border: none; }"
        )
        col = QVBoxLayout(panel)
        col.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.LG)
        col.setSpacing(Spacing.SM)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedHeight(LOGO_SIZE.height())
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo = scaled_pixmap(logo_path(), LOGO_SIZE.height(), False, self.devicePixelRatioF())
        if not logo.isNull():
            self.logo_lbl.setPixmap(logo)
        col.addWidget(self.logo_lbl)

        tagline = QLabel("Wood furniture and temple carvings")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif; font-size: 22px;"
            f" font-weight: 600; color: {Colors.BRAND_BROWN};"
        )
        col.addWidget(tagline)

        # The painted pair faces the god between them; it takes the room that is left.
        self.carvings = CarvingRow("temple")
        self.carvings.setMinimumHeight(120)
        self.carvings.setMaximumHeight(520)
        col.addWidget(self.carvings, 1)
        return panel

    # ── Right: the sign-in card ───────────────────────
    def _build_form_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        outer.addStretch(1)

        column = QWidget()
        column.setMaximumWidth(FORM_MAX_WIDTH)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Spacing.MD)

        brand = QLabel("Vriksha Studio")
        brand.setStyleSheet(
            f"font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif; font-size: 36px;"
            f" font-weight: bold; color: {Colors.BRAND_BROWN};"
        )
        col.addWidget(brand)

        tagline = QLabel("Staff sign in")
        tagline.setStyleSheet(f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY};")
        col.addWidget(tagline)

        if insecure_remote(BASE_URL):
            warn = Alert(
                "⚠ This server address is not encrypted (http://). Passwords and bills could be seen on "
                "the network. Ask for an https:// address.",
                "danger",
            )
            col.addWidget(warn)

        # ── Form card ─────────────────────────────────
        card = Card()
        card.body.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        card.body.setSpacing(Spacing.MD)

        # Username
        lbl_user = QLabel("Username")
        lbl_user.setStyleSheet(Theme.label())
        self.username = QLineEdit()
        self.username.setPlaceholderText("Enter your username")
        self.username.setStyleSheet(Theme.input_style())

        # Password
        lbl_pass = QLabel("Password")
        lbl_pass.setStyleSheet(Theme.label())
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter your password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setStyleSheet(Theme.input_style())

        # Error label (hidden by default)
        self.error_lbl = Alert("", "danger")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.hide()

        # Sign In button
        self.button = QPushButton("Sign In")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setStyleSheet(Theme.btn("primary", "lg"))
        self.button.clicked.connect(self.handle_login)
        self.password.returnPressed.connect(self.handle_login)

        card.body.addWidget(lbl_user)
        card.body.addWidget(self.username)
        card.body.addWidget(lbl_pass)
        card.body.addWidget(self.password)
        card.body.addWidget(self.error_lbl)
        card.body.addWidget(self.button)

        col.addWidget(card)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(column, 100)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        return panel

    def handle_login(self):
        username = self.username.text().strip()
        password = self.password.text().strip()

        if not username or not password:
            self._show_error("Please enter both username and password.")
            return

        self.button.setText("Signing in...")
        self.button.setEnabled(False)
        self.error_lbl.hide()

        # Force UI repaint before network call
        from PyQt6.QtWidgets import QApplication

        QApplication.processEvents()

        try:
            result = self._auth.login(username, password)
        except requests.RequestException:
            self._login_failed(
                "Can't reach the server. Check the internet connection and try again."
            )
            return
        except APIError as e:
            if e.status_code == 429:  # too many wrong passwords: say so
                self._login_failed(str(e))
            else:
                self._login_failed(
                    f"The server had a problem ({e.status_code}). Please try again in a moment."
                )
            return

        if result:
            from ui.main_window import MainWindow

            self.main_window = MainWindow()
            self.main_window.show()
            self.close()
        else:
            self._login_failed("Invalid username or password. Please try again.")

    def _login_failed(self, msg: str):
        self.button.setText("Sign In")
        self.button.setEnabled(True)
        self._show_error(msg)

    def _show_error(self, msg: str):
        self.error_lbl.setText(msg)
        self.error_lbl.show()
