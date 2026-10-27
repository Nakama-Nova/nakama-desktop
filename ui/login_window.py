"""
ui/login_window.py

Branded login screen — centered, styled, with inline error feedback.
"""

import requests
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QSpacerItem,
    QSizePolicy,
)
from PyQt6.QtCore import Qt
# No QtGui imports needed here

from ui.theme import Theme, Colors, Fonts
import requests

from services.api_client import BASE_URL, APIError, insecure_remote
from services.auth_service import AuthService


class LoginWindow(QWidget):

    def __init__(self):
        super().__init__()
        self._auth = AuthService()

        self.setWindowTitle("Vriksha Studio — Staff sign in")
        self.setFixedSize(420, 520)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.BG};
                font-family: '{Fonts.FAMILY}';
            }}
        """)

        # Center on screen
        screen = self.screen().availableGeometry()
        x = (screen.width() - 420) // 2
        y = (screen.height() - 520) // 2
        self.move(x, y)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(0)

        # ── Brand ─────────────────────────────────────
        root.addSpacerItem(
            QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        brand = QLabel("Vriksha Studio")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(f"""
            font-family: '{Fonts.HEADING_FAMILY}', Georgia, serif;
            font-size: 40px;
            font-weight: bold;
            color: {Colors.BRAND_BROWN};
            margin-bottom: 8px;
        """)
        root.addWidget(brand)

        tagline = QLabel("Staff sign in")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"""
            font-size: {Fonts.BODY}px;
            color: {Colors.TEXT_SECONDARY};
            margin-bottom: 32px;
        """)
        root.addWidget(tagline)

        if insecure_remote(BASE_URL):
            warn = QLabel(
                "⚠ This server address is not encrypted (http://). Passwords and bills could be seen on "
                "the network. Ask for an https:// address."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(f"""
                color: {Colors.RED};
                background-color: {Colors.ERROR_BG};
                border-radius: 6px;
                padding: 8px;
                font-size: {Fonts.BODY_SM}px;
            """)
            root.addWidget(warn)
            root.addSpacing(12)

        # ── Form Card ─────────────────────────────────
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.CARD_BG};
                border-radius: 12px;
                border: 1px solid {Colors.CARD_BORDER};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(16)

        # Username
        lbl_user = QLabel("Username")
        lbl_user.setStyleSheet(Theme.label())
        self.username = QLineEdit()
        self.username.setPlaceholderText("Enter your username")
        self.username.setStyleSheet(self._input_css())

        # Password
        lbl_pass = QLabel("Password")
        lbl_pass.setStyleSheet(Theme.label())
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter your password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setStyleSheet(self._input_css())

        # Error label (hidden by default)
        self.error_lbl = QLabel("")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_lbl.setStyleSheet(f"""
            color: {Colors.RED};
            font-size: {Fonts.BODY_SM}px;
            padding: 8px;
            background-color: {Colors.ERROR_BG};
            border-radius: 6px;
        """)
        self.error_lbl.hide()

        # Sign In button
        self.button = QPushButton("Sign In")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BRAND_BROWN};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 14px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #6E3A12;
            }}
            QPushButton:disabled {{
                background-color: {Colors.TEXT_MUTED};
            }}
        """)
        self.button.clicked.connect(self.handle_login)
        self.password.returnPressed.connect(self.handle_login)

        card_layout.addWidget(lbl_user)
        card_layout.addWidget(self.username)
        card_layout.addWidget(lbl_pass)
        card_layout.addWidget(self.password)
        card_layout.addWidget(self.error_lbl)
        card_layout.addWidget(self.button)

        root.addWidget(card)

        root.addSpacerItem(
            QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

    def _input_css(self) -> str:
        return f"""
            QLineEdit {{
                border: 1.5px solid {Colors.INPUT_BORDER};
                border-radius: 8px;
                padding: 12px 14px;
                font-size: {Fonts.BODY}px;
                background: white;
                color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {Colors.INPUT_FOCUS};
            }}
        """

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
