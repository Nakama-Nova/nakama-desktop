"""
ui/staff_screen.py

Staff accounts (owner only): add someone, change their details, role and daily
wage, switch an account off (they can no longer sign in) or back on, and reset a
forgotten password. Everyone can change their own password.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.staff_service import StaffService
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme

ROLES = [
    ("Owner", "owner"),
    ("Manager", "manager"),
    ("Sales", "sales"),
    ("Achari (carpenter)", "achari"),
    ("Worker", "worker"),
]
ROLE_WORDS = {value: label for label, value in ROLES}
MIN_PASSWORD = 8


def _line(text="", placeholder="", password=False) -> QLineEdit:
    e = QLineEdit(text or "")
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(Theme.input_style())
    if password:
        e.setEchoMode(QLineEdit.EchoMode.Password)
    return e


def _buttons(dialog, ok_text="Save"):
    row = QHBoxLayout()
    row.addStretch()
    cancel = QPushButton("Cancel")
    cancel.setStyleSheet(Theme.btn_secondary())
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setStyleSheet(Theme.btn_primary())
    ok.clicked.connect(dialog._check)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row


def password_problem(new: str, repeat: str) -> str | None:
    if len(new) < MIN_PASSWORD:
        return f"The password needs at least {MIN_PASSWORD} characters."
    if new != repeat:
        return "The two passwords do not match."
    return None


class StaffDialog(QDialog):
    """Add a person (password asked) or edit one (role locked for yourself)."""

    def __init__(self, parent, user: dict | None = None, is_me: bool = False):
        super().__init__(parent)
        self._adding = user is None
        user = user or {}
        self.setWindowTitle("Add staff" if self._adding else "Edit staff")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)

        self.username = _line(user.get("username"), "used to sign in, e.g. asha")
        self.username.setEnabled(self._adding)
        self.full_name = _line(user.get("full_name"), "e.g. Asha Kumari")
        self.email = _line(user.get("email"), "name@example.com")
        self.phone = _line(user.get("phone"), "optional")
        self.role = QComboBox()
        for label, value in ROLES:
            self.role.addItem(label, value)
        self.role.setCurrentIndex(
            max(0, self.role.findData(user.get("role") or "worker"))
        )
        self.role.setStyleSheet(Theme.input_style())
        if is_me:
            self.role.setEnabled(False)
            self.role.setToolTip("You cannot change your own role")
        self.wage = QDoubleSpinBox()
        self.wage.setRange(0, 100000)
        self.wage.setPrefix("₹")
        self.wage.setSuffix(" / day")
        self.wage.setValue(float(user.get("base_daily_wage") or 0))
        self.wage.setStyleSheet(Theme.input_style())
        self.overtime = QDoubleSpinBox()
        self.overtime.setRange(0, 10000)
        self.overtime.setPrefix("₹")
        self.overtime.setSuffix(" / hour")
        self.overtime.setSpecialValueText("not set")
        self.overtime.setValue(float(user.get("overtime_rate_per_hour") or 0))
        self.overtime.setStyleSheet(Theme.input_style())

        for label, w in [
            ("Username *", self.username),
            ("Name", self.full_name),
            ("Email *", self.email),
            ("Phone", self.phone),
            ("Role", self.role),
            ("Daily wage", self.wage),
            ("Overtime rate", self.overtime),
        ]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        if self._adding:
            self.password = _line("", f"at least {MIN_PASSWORD} characters", True)
            self.repeat = _line("", "", True)
            form.addRow(QLabel("Password *", styleSheet=Theme.label()), self.password)
            form.addRow(QLabel("Repeat *", styleSheet=Theme.label()), self.repeat)
        form.addRow(_buttons(self))

    def _check(self):
        problem = None
        if self._adding and not self.username.text().strip():
            problem = "Enter a username."
        elif "@" not in self.email.text():
            problem = "Enter a valid email."
        elif self._adding:
            problem = password_problem(self.password.text(), self.repeat.text())
        if problem:
            QMessageBox.warning(self, "Check the form", problem)
        else:
            self.accept()

    def get_data(self) -> dict:
        data = {
            "full_name": self.full_name.text().strip() or None,
            "email": self.email.text().strip(),
            "phone": self.phone.text().strip() or None,
            "base_daily_wage": self.wage.value(),
            "overtime_rate_per_hour": self.overtime.value() or None,
        }
        if self.role.isEnabled():
            data["role"] = self.role.currentData()
        if self._adding:
            data["username"] = self.username.text().strip()
            data["password"] = self.password.text()
        return data


class PasswordDialog(QDialog):
    """Set someone's password (owner) or your own (needs the current one)."""

    def __init__(self, parent, title: str, ask_current: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        self.current = _line("", "", True) if ask_current else None
        self.new = _line("", f"at least {MIN_PASSWORD} characters", True)
        self.repeat = _line("", "", True)
        if self.current:
            form.addRow(QLabel("Current password", styleSheet=Theme.label()), self.current)
        form.addRow(QLabel("New password", styleSheet=Theme.label()), self.new)
        form.addRow(QLabel("Repeat", styleSheet=Theme.label()), self.repeat)
        form.addRow(_buttons(self))

    def _check(self):
        problem = password_problem(self.new.text(), self.repeat.text())
        if problem:
            QMessageBox.warning(self, "Check the form", problem)
        else:
            self.accept()


def change_my_password(parent, service: StaffService | None = None) -> bool:
    """The dialog behind the sidebar's Password button. True if it changed."""
    svc = service or StaffService()
    d = PasswordDialog(parent, "Change my password", ask_current=True)
    if d.exec() != QDialog.DialogCode.Accepted:
        return False
    svc.change_my_password(d.current.text(), d.new.text())
    QMessageBox.information(parent, "Password", "Your password was changed.")
    return True


class StaffScreen(QWidget):
    COL_NAME, COL_USER, COL_ROLE, COL_PHONE, COL_WAGE, COL_STATUS, COL_ACTIONS = range(7)

    def __init__(self):
        super().__init__()
        self._svc = StaffService()
        self._rows: list[dict] = []
        self._me: str | None = None
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("👥  Staff")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        self.add_btn = QPushButton("➕  Add staff")
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add)
        head.addWidget(self.add_btn)
        layout.addLayout(head)

        hint = QLabel(
            "Switching someone off stops them signing in; their history stays. The daily wage"
            " is what attendance uses to work out wages."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Username", "Role", "Phone", "Daily wage", "Status", ""]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_ACTIONS, 300)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

    @handle_permissions
    def refresh_data(self, _checked=False):
        self._me = self._svc.me().get("id")
        self._rows = sorted(self._svc.users(), key=lambda u: (not u["is_active"], u["username"]))
        self.table.setRowCount(len(self._rows))
        for r, u in enumerate(self._rows):
            name = u.get("full_name") or u["username"]
            values = [
                name + ("  (you)" if u["id"] == self._me else ""),
                u["username"],
                ROLE_WORDS.get(u.get("role"), u.get("role") or ""),
                u.get("phone") or "",
                f"₹{float(u.get('base_daily_wage') or 0):,.0f}",
                "Active" if u.get("is_active") else "Switched off",
            ]
            for c, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if c == self.COL_WAGE:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if not u.get("is_active"):
                    cell.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(r, c, cell)
            self.table.setCellWidget(r, self.COL_ACTIONS, self._actions(u))
            self.table.setRowHeight(r, 52)

    def _actions(self, u: dict) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        is_me = u["id"] == self._me
        buttons = [("✏️ Edit", self._edit), ("🔑 Password", self._reset)]
        if not is_me:  # you cannot switch yourself off
            buttons.append(("Switch on" if not u.get("is_active") else "Switch off", self._toggle))
        for text, slot in buttons:
            b = QPushButton(text)
            b.setFixedHeight(30)
            b.setStyleSheet(Theme.btn_table_action())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, uu=u, s=slot: s(uu))
            h.addWidget(b)
        return box

    @handle_permissions
    def _add(self, _checked=False):
        d = StaffDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.create(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _edit(self, u: dict):
        d = StaffDialog(self, u, is_me=u["id"] == self._me)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.update(u["id"], d.get_data())
            self.refresh_data()

    @handle_permissions
    def _reset(self, u: dict):
        d = PasswordDialog(self, f"New password for {u['username']}")
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.reset_password(u["id"], d.new.text())
            QMessageBox.information(self, "Password", f"{u['username']} can sign in with the new password.")

    @handle_permissions
    def _toggle(self, u: dict):
        turning_off = bool(u.get("is_active"))
        ask = QMessageBox.question(
            self,
            "Switch off" if turning_off else "Switch on",
            (f"Switch off {u['username']}? They will not be able to sign in."
             if turning_off else f"Let {u['username']} sign in again?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask == QMessageBox.StandardButton.Yes:
            self._svc.update(u["id"], {"is_active": not turning_off})
            self.refresh_data()
