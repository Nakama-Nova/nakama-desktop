"""
ui/forgot_password_dialog.py

"Forgot password?" on the sign-in screen, and the way a newly added person chooses their
password. Nobody types another person's password: the server emails a code, the person
types it here with a new password of their own.

    Step 1: your email -> a code is emailed.
    Step 2: email, code, new password (twice) -> the password is set; sign in with it.

The server answers step 1 the same for any address, so this never says whether an
account exists.
"""

import requests
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.api_client import APIClient, APIError
from ui.theme import Colors, Theme
from ui.workers import run_async

MIN_PASSWORD = 8


def _field(placeholder="", password=False) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(Theme.input_style())
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    return e


def _link(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setFlat(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton {{ color: {Colors.BRAND_BROWN}; border: none; text-decoration: underline;"
        " background: transparent; padding: 2px 0; }}"
    )
    return b


def code_problem(email: str, code: str, new: str, repeat: str) -> str | None:
    if "@" not in email:
        return "Enter the email the code was sent to."
    if len(code.strip()) < 4:
        return "Enter the code from the email."
    if len(new) < MIN_PASSWORD:
        return f"The password needs at least {MIN_PASSWORD} characters."
    if new != repeat:
        return "The two passwords do not match."
    return None


class ForgotPasswordDialog(QDialog):
    def __init__(self, parent=None, email: str = "", api: APIClient | None = None, have_code: bool = False):
        super().__init__(parent)
        self._api = api or APIClient()
        self.setWindowTitle("Forgot password")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        outer.addWidget(self.message)

        # step 1: ask for a code
        ask = QWidget()
        v = QVBoxLayout(ask)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        intro = QLabel("Enter your email and we will send you a code. You then choose your own password.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        v.addWidget(intro)
        self.ask_email = _field("name@example.com")
        self.ask_email.setText(email)
        self.ask_email.returnPressed.connect(self.send_code)
        v.addWidget(self.ask_email)
        self.send_btn = QPushButton("Send me a code")
        self.send_btn.setStyleSheet(Theme.btn_primary())
        self.send_btn.clicked.connect(self.send_code)
        self.have_code_link = _link("I already have a code")
        self.have_code_link.clicked.connect(lambda: self._go(1))
        row = QHBoxLayout()
        row.addWidget(self.have_code_link)
        row.addStretch()
        row.addWidget(self.send_btn)
        v.addLayout(row)
        self.stack.addWidget(ask)

        # step 2: the code and a new password
        setp = QWidget()
        form = QFormLayout(setp)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.email = _field("name@example.com")
        self.code = _field("8 letters and numbers")
        self.new = _field(f"at least {MIN_PASSWORD} characters", True)
        self.repeat = _field("", True)
        self.repeat.returnPressed.connect(self.set_password)
        for label, w in [("Email", self.email), ("Code", self.code), ("New password", self.new), ("Repeat", self.repeat)]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        self.set_btn = QPushButton("Set password")
        self.set_btn.setStyleSheet(Theme.btn_primary())
        self.set_btn.clicked.connect(self.set_password)
        self.again_link = _link("Send a new code")
        self.again_link.clicked.connect(lambda: self._go(0))
        row2 = QHBoxLayout()
        row2.addWidget(self.again_link)
        row2.addStretch()
        row2.addWidget(self.set_btn)
        form.addRow(row2)
        self.stack.addWidget(setp)

        self._go(1 if have_code else 0)

    def _go(self, step: int) -> None:
        if step == 1 and not self.email.text():
            self.email.setText(self.ask_email.text().strip())
        self.stack.setCurrentIndex(step)
        self.message.setText("")
        (self.code if step == 1 and self.email.text() else self.ask_email if step == 0 else self.email).setFocus()

    def _say(self, text: str, good: bool = False) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {Colors.SUCCESS if good else Colors.DANGER}; font-weight: 600;")

    def _busy(self, busy: bool) -> None:
        for b in (self.send_btn, self.set_btn):
            b.setEnabled(not busy)

    def _failed(self, exc: Exception) -> None:
        self._busy(False)
        if isinstance(exc, requests.RequestException):
            self._say("Cannot reach the server. Check the internet connection and try again.")
        elif isinstance(exc, APIError):
            self._say(APIError._plain(exc.detail) or "Something went wrong. Try again.")
        else:
            raise exc

    def send_code(self) -> None:
        email = self.ask_email.text().strip()
        if "@" not in email:
            self._say("Enter the email address on your account.")
            return
        self._busy(True)
        self._say("Sending…", good=True)

        def sent(_result):
            self._busy(False)
            self.email.setText(email)
            self._go(1)
            self._say("If that email belongs to an account, a code is on its way. It can take a minute.", good=True)

        run_async(lambda: self._api.forgot_password(email), sent, self._failed)

    def set_password(self) -> None:
        email, code = self.email.text().strip(), self.code.text().strip()
        problem = code_problem(email, code, self.new.text(), self.repeat.text())
        if problem:
            self._say(problem)
            return
        self._busy(True)
        self._say("Saving…", good=True)

        def done(_result):
            self._busy(False)
            self.accept()

        run_async(lambda: self._api.set_password_with_code(email, code, self.new.text()), done, self._failed)
