"""
ui/roles_screen.py

Roles: who may do what. Each role is a name plus a list of allowed actions, ticked here
grouped by module. The owner role is fixed. The server refuses to give a role more than
the person making the change holds, and says so; that message is shown as it is.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.icons import IconButton
from services.api_client import ForbiddenError
from services.iam_service import IamService, allowed_in
from services.session import Session
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async

FIXED_ROLE = "owner"


def group_actions(actions: list[dict]) -> dict[str, list[dict]]:
    """Known actions grouped by their first segment ("payroll:payment:create" -> "payroll")."""
    groups: dict[str, list[dict]] = {}
    for a in actions:
        groups.setdefault(a["action"].split(":")[0], []).append(a)
    return dict(sorted(groups.items()))


class RoleDialog(QDialog):
    """Create a role, or change one: its name, a note, and the actions ticked by module."""

    def __init__(self, parent, actions: list[dict], role: dict | None = None, ticked: set[str] | None = None, read_only: str = ""):
        super().__init__(parent)
        self.role = role
        self.setWindowTitle("New role" if role is None else f"Role: {role['label']}")
        self.setMinimumSize(520, 560)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)

        self.label = QLineEdit((role or {}).get("label") or "")
        self.label.setPlaceholderText("Role name, e.g. Shop supervisor")
        self.label.setStyleSheet(Theme.input_style())
        self.description = QLineEdit((role or {}).get("description") or "")
        self.description.setPlaceholderText("What this role is for (optional)")
        self.description.setStyleSheet(Theme.input_style())
        layout.addWidget(QLabel("Name *", styleSheet=Theme.label()))
        layout.addWidget(self.label)
        layout.addWidget(QLabel("Note", styleSheet=Theme.label()))
        layout.addWidget(self.description)

        layout.addWidget(QLabel("What this role may do", styleSheet=Theme.label()))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet(Theme.input_style())
        ticked = ticked or set()
        for module, rows in group_actions(actions).items():
            top = QTreeWidgetItem([module.replace("_", " ").title()])
            top.setFlags(top.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            for a in rows:
                child = QTreeWidgetItem([f"{a['description']}   ({a['action']})"])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setData(0, Qt.ItemDataRole.UserRole, a["action"])
                child.setCheckState(0, Qt.CheckState.Checked if a["action"] in ticked else Qt.CheckState.Unchecked)
                top.addChild(child)
            self.tree.addTopLevelItem(top)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        if read_only:
            note = QLabel(read_only)
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            layout.addWidget(note)
            for w in (self.label, self.description, self.tree):
                w.setEnabled(False)
        row.addStretch()
        cancel = IconButton("Close" if read_only else "Cancel")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        if not read_only:
            ok = IconButton("Save")
            ok.setStyleSheet(Theme.btn_primary())
            ok.clicked.connect(self._check)
            row.addWidget(ok)
        layout.addLayout(row)

    def _check(self):
        if not self.label.text().strip():
            QMessageBox.warning(self, "Check the form", "Give the role a name.")
        elif not self.chosen():
            QMessageBox.warning(self, "Check the form", "Tick at least one thing this role may do.")
        else:
            self.accept()

    def chosen(self) -> list[str]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    out.append(child.data(0, Qt.ItemDataRole.UserRole))
        return out


class RolesScreen(QWidget):
    COL_NAME, COL_KEY, COL_KIND, COL_NOTE, COL_ACTIONS = range(5)

    def __init__(self):
        super().__init__()
        self._svc = IamService()
        self._rows: list[dict] = []
        self._actions: list[dict] = []
        self._policies: dict[str, dict] = {}
        self.setStyleSheet(Theme.content_bg())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("🔑  Roles")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = IconButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_async)
        head.addWidget(refresh)
        self.add_btn = IconButton("➕  New role")
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add)
        self.add_btn.setVisible(Session.can("iam:role:write"))
        head.addWidget(self.add_btn)
        layout.addLayout(head)
        hint = QLabel(
            "A role is a name plus the things it may do. Give someone a role on the Staff screen. "
            "You can only give a role what you may do yourself."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Role", "Key", "Kind", "Note", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_NOTE, QHeaderView.ResizeMode.Stretch)
        Theme.style_table(self.table)
        layout.addWidget(self.table)

    def _fetch(self):
        return self._svc.roles(), self._svc.actions(), self._svc.policies()

    def refresh_data(self, _checked=False):
        self._show(self._fetch())

    def refresh_async(self, _checked=False):
        load_async(self, self._fetch, self._show)

    def _show(self, data):
        self._rows, self._actions, policies = data
        self._policies = {p["id"]: p for p in policies}
        self.table.setRowCount(len(self._rows))
        for r, role in enumerate(self._rows):
            values = [role["label"], role["key"], "Built-in" if role.get("is_system") else "Custom", role.get("description") or ""]
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
            self.table.setCellWidget(r, self.COL_ACTIONS, self._buttons(role))
            self.table.setRowHeight(r, 52)

    def _buttons(self, role: dict) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)
        can_write = Session.can("iam:role:write")
        buttons = [("✏️ Edit" if can_write and role["key"] != FIXED_ROLE else "👁 View", self._edit)]
        if can_write and not role.get("is_system"):
            buttons.append(("🗑 Delete", self._delete))
        for text, slot in buttons:
            b = IconButton(text)
            b.setFixedHeight(30)
            b.setStyleSheet(Theme.btn_table_action())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, rr=role, s=slot: s(rr))
            h.addWidget(b)
        return box

    def _refused(self, e: ForbiddenError):
        QMessageBox.warning(self, "Not allowed", e.reason or "You don't have permission for this.")

    def _add(self, _checked=False):
        d = RoleDialog(self, self._actions)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        label = d.label.text().strip()
        try:
            policy = self._svc.create_policy(f"{label} permissions", d.chosen())
            self._svc.create_role(label, d.description.text().strip(), [policy["id"]])
        except ForbiddenError as e:
            self._refused(e)
            return
        self.refresh_data()

    def _edit(self, role: dict):
        ids = [str(i) for i in role.get("policy_ids") or []]
        known = [a["action"] for a in self._actions]
        ticked: set[str] = set()
        for pid in ids:
            ticked |= allowed_in(self._policies.get(pid, {}).get("document", {}), known)
        read_only = ""
        if role["key"] == FIXED_ROLE:
            read_only = "The owner role holds everything and cannot be changed."
        elif not Session.can("iam:role:write"):
            read_only = "You may look at roles but not change them."
        elif len(ids) > 1:
            read_only = "This role is built from several policies, so it cannot be changed here."
        d = RoleDialog(self, self._actions, role, ticked, read_only)
        if d.exec() != QDialog.DialogCode.Accepted or read_only:
            return
        label = d.label.text().strip()
        try:
            if ids:
                policy = self._policies[ids[0]]
                self._svc.update_policy(ids[0], policy["name"], d.chosen())
            else:
                ids = [self._svc.create_policy(f"{label} permissions", d.chosen())["id"]]
            self._svc.update_role(role["id"], label, d.description.text().strip(), ids)
        except ForbiddenError as e:
            self._refused(e)
            return
        self.refresh_data()

    def _delete(self, role: dict):
        ask = QMessageBox.question(
            self,
            "Delete role",
            f"Delete the role {role['label']}? Roles people still hold cannot be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask != QMessageBox.StandardButton.Yes:
            return
        try:
            self._svc.delete_role(role["id"])
        except ForbiddenError as e:
            self._refused(e)
            return
        self.refresh_data()
