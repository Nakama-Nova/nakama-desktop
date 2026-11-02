"""
ui/machines_screen.py

Machines and tools. Machines: what each is worth now, when it is next due for service, record a
service or repair, mark it stopped and working again. Tools: who has which tool, hand one out,
take it back (fine, damaged or lost). Owner and manager manage both; the achari can see tools.
"""

from datetime import date, datetime

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.enums import UserRole
from services.places_service import PlacesService
from services.registers_service import RegistersService
from services.session import Session
from ui.components.interactive import ChipBar, action_buttons
from ui.errors import handle_permissions
from ui.places_screen import _button_row, _right, _table
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async

DUE_SOON_DAYS = 14
STATUS_WORDS = {
    "active": "Working",
    "down": "Stopped",
    "retired": "Retired",
    "available": "Available",
    "issued": "Handed out",
    "broken": "Broken",
    "lost": "Lost",
}
STATUS_COLOURS = {
    "active": Colors.SUCCESS,
    "available": Colors.SUCCESS,
    "down": Colors.DANGER,
    "broken": Colors.DANGER,
    "lost": Colors.DANGER,
    "issued": Colors.ORANGE,
    "retired": Colors.TEXT_MUTED,
}
CONDITIONS = [("New", "new"), ("Good", "good"), ("Worn", "worn"), ("Damaged", "damaged")]


def money(value) -> str:
    if value in (None, ""):
        return ""
    v = float(value)
    return f"{'-' if v < 0 else ''}₹{abs(v):,.2f}"


def parse_date(text) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def due_state(machine: dict, today: date | None = None) -> str:
    """'overdue', 'soon' (within two weeks) or '' for a machine that is not retired."""
    if machine.get("status") == "retired":
        return ""
    if machine.get("service_overdue"):
        return "overdue"
    due = parse_date(machine.get("service_due_on"))
    if due and (due - (today or date.today())).days <= DUE_SOON_DAYS:
        return "soon"
    return ""


def _coloured(text: str, colour: str) -> QTableWidgetItem:
    cell = QTableWidgetItem(text)
    cell.setForeground(QColor(colour))
    f = cell.font()
    f.setBold(True)
    cell.setFont(f)
    return cell


def _date_edit(value: str | None = None, today_default: bool = False) -> QDateEdit:
    """A date box; the earliest date means 'not set' (shown as such) unless today is the default."""
    d = QDateEdit()
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd MMM yyyy")
    d.setStyleSheet(Theme.input_style())
    if today_default:
        d.setDate(QDate.currentDate())
        return d
    d.setMinimumDate(QDate(1990, 1, 1))
    d.setSpecialValueText("Not set")
    parsed = parse_date(value)
    d.setDate(QDate(parsed.year, parsed.month, parsed.day) if parsed else d.minimumDate())
    return d


def _date_value(d: QDateEdit) -> str | None:
    return None if d.date() == d.minimumDate() and d.specialValueText() else d.date().toString("yyyy-MM-dd")


def _money_box(value=None) -> QDoubleSpinBox:
    b = QDoubleSpinBox()
    b.setRange(0, 100_000_000)
    b.setPrefix("₹")
    b.setValue(float(value or 0))
    b.setStyleSheet(Theme.input_style())
    return b


def _place_combo(places: list, current=None) -> QComboBox:
    c = QComboBox()
    c.addItem("Not set", None)
    for p in places:
        c.addItem(p["name"], str(p["id"]))
    c.setCurrentIndex(max(c.findData(str(current)) if current else 0, 0))
    c.setStyleSheet(Theme.input_style())
    return c


def _form_dialog(parent, title: str, width: int = 420) -> tuple[QDialog, QFormLayout]:
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.setMinimumWidth(width)
    d.setStyleSheet(f"background-color: {Colors.BG};")
    form = QFormLayout(d)
    form.setContentsMargins(24, 20, 24, 20)
    form.setSpacing(12)
    return d, form


def _row(form: QFormLayout, label: str, widget) -> None:
    form.addRow(QLabel(label, styleSheet=Theme.label()), widget)


class MachineDialog(QDialog):
    def __init__(self, parent, places: list, machine: dict | None = None):
        super().__init__(parent)
        m = machine or {}
        self._editing = bool(machine)
        self.setWindowTitle("Edit machine" if machine else "Add machine")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        self.tag = QLineEdit(m.get("tag") or "")
        self.tag.setPlaceholderText("Number painted on the machine, e.g. M-01")
        self.name = QLineEdit(m.get("name") or "")
        self.name.setPlaceholderText("e.g. Table saw")
        self.make = QLineEdit(m.get("make_model") or "")
        self.serial = QLineEdit(m.get("serial_number") or "")
        self.place = _place_combo(places, m.get("location_id"))
        self.bought = _date_edit(m.get("purchase_date"))
        self.cost = _money_box(m.get("purchase_cost"))
        self.life = QSpinBox()
        self.life.setRange(0, 50)
        self.life.setSpecialValueText("Not set")
        self.life.setSuffix(" years")
        self.life.setValue(int(m.get("useful_life_years") or 0))
        self.salvage = _money_box(m.get("salvage_value"))
        self.every = QSpinBox()
        self.every.setRange(0, 3650)
        self.every.setSpecialValueText("No schedule")
        self.every.setSuffix(" days")
        self.every.setValue(int(m.get("maintenance_every_days") or 0))
        self.notes = QLineEdit(m.get("notes") or "")
        self.status = QComboBox()
        self.status.addItem("Working", "active")
        self.status.addItem("Retired (no longer used)", "retired")
        self.status.setCurrentIndex(1 if m.get("status") == "retired" else 0)
        for w in (self.tag, self.name, self.make, self.serial, self.life, self.every, self.notes, self.status):
            w.setStyleSheet(Theme.input_style())
        for label, w in [
            ("Tag *", self.tag),
            ("Name *", self.name),
            ("Make / model", self.make),
            ("Serial number", self.serial),
            ("Kept at", self.place),
            ("Bought on", self.bought),
            ("Bought for", self.cost),
            ("Lasts about", self.life),
            ("Worth at the end", self.salvage),
            ("Service every", self.every),
            ("Notes", self.notes),
        ]:
            _row(form, label, w)
        if self._editing:
            _row(form, "Status", self.status)
            self.status.setEnabled(m.get("status") != "down")
            self.status.setToolTip("A machine is marked Stopped from the Stopped button, not here")
        row, ok = _button_row(self, "Save")
        ok.clicked.connect(self._check)
        form.addRow(row)

    def _check(self):
        if not self.tag.text().strip() or not self.name.text().strip():
            QMessageBox.warning(self, "Required", "Tag and name are required.")
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "tag": self.tag.text().strip(),
            "name": self.name.text().strip(),
            "make_model": self.make.text().strip() or None,
            "serial_number": self.serial.text().strip() or None,
            "location_id": self.place.currentData(),
            "purchase_date": _date_value(self.bought),
            "purchase_cost": str(self.cost.value()) if self.cost.value() else None,
            "useful_life_years": self.life.value() or None,
            "salvage_value": str(self.salvage.value()),
            "maintenance_every_days": self.every.value() or None,
            "notes": self.notes.text().strip() or None,
        }
        if self._editing and self.status.isEnabled():
            data["status"] = self.status.currentData()
        return data


class MaintenanceDialog(QDialog):
    def __init__(self, parent, machine: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Service or repair: {machine['name']}")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        self.kind = QComboBox()
        self.kind.addItem("Scheduled service", "scheduled")
        self.kind.addItem("Repair", "repair")
        self.on = _date_edit(today_default=True)
        self.cost = _money_box()
        self.by = QLineEdit()
        self.by.setPlaceholderText("Who did it")
        self.what = QLineEdit()
        self.what.setPlaceholderText("What was done")
        for w in (self.kind, self.by, self.what):
            w.setStyleSheet(Theme.input_style())
        for label, w in [("Kind", self.kind), ("Done on", self.on), ("Cost", self.cost), ("Done by", self.by), ("What was done", self.what)]:
            _row(form, label, w)
        row, ok = _button_row(self, "Save")
        ok.clicked.connect(self.accept)
        form.addRow(row)

    def get_data(self) -> dict:
        return {
            "kind": self.kind.currentData(),
            "performed_on": self.on.date().toString("yyyy-MM-dd"),
            "cost": str(self.cost.value()),
            "done_by": self.by.text().strip() or None,
            "description": self.what.text().strip() or None,
        }


class MachineDetailDialog(QDialog):
    """A machine's service and stoppage history side by side."""

    def __init__(self, parent, machine: dict, maintenance: list, downtime: list):
        super().__init__(parent)
        self.setWindowTitle(f"{machine['tag']} · {machine['name']}")
        self.resize(720, 460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        worth = money(machine.get("book_value")) or "not worked out (add the price and life)"
        due = machine.get("service_due_on")
        summary = QLabel(
            f"<b>{STATUS_WORDS.get(machine.get('status'), machine.get('status'))}</b>"
            f" · worth today {worth} · spent on service {money(machine.get('maintenance_spent')) or '₹0.00'}"
            + (f" · next service {due}" if due else "")
        )
        summary.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        summary.setWordWrap(True)
        root.addWidget(summary)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        t = _table(["Date", "Kind", "Cost", "Done by", "What was done"])
        t.setRowCount(len(maintenance))
        for i, r in enumerate(maintenance):
            cells = [r["performed_on"], "Repair" if r["kind"] == "repair" else "Service", money(r.get("cost")), r.get("done_by") or "", r.get("description") or ""]
            for c, text in enumerate(cells):
                t.setItem(i, c, _right(text) if c == 2 else QTableWidgetItem(text))
        tabs.addTab(t, f"Services and repairs ({len(maintenance)})")
        d = _table(["Stopped", "Working again", "Reason"])
        d.setRowCount(len(downtime))
        for i, r in enumerate(downtime):
            ended = r.get("ended_at")
            for c, text in enumerate([_stamp(r["started_at"]), _stamp(ended) if ended else "Still stopped", r.get("reason") or ""]):
                d.setItem(i, c, QTableWidgetItem(text))
        tabs.addTab(d, f"Stoppages ({len(downtime)})")
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        root.addLayout(row)


def _stamp(text: str) -> str:
    try:
        return datetime.fromisoformat(text).strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return text or ""


class ToolDialog(QDialog):
    def __init__(self, parent, places: list, tool: dict | None = None):
        super().__init__(parent)
        t = tool or {}
        self._editing = bool(tool)
        self.setWindowTitle("Edit tool" if tool else "Add tool")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        self.tag = QLineEdit(t.get("tag") or "")
        self.tag.setPlaceholderText("e.g. T-014")
        self.name = QLineEdit(t.get("name") or "")
        self.name.setPlaceholderText("e.g. 12 mm chisel")
        self.category = QLineEdit(t.get("category") or "")
        self.category.setPlaceholderText("e.g. Carving, Hand tool, Power tool")
        self.condition = QComboBox()
        for label, value in CONDITIONS:
            self.condition.addItem(label, value)
        self.condition.setCurrentIndex(max(self.condition.findData(t.get("condition") or "good"), 0))
        self.place = _place_combo(places, t.get("location_id"))
        self.bought = _date_edit(t.get("purchase_date"))
        self.cost = _money_box(t.get("purchase_cost"))
        self.notes = QLineEdit(t.get("notes") or "")
        self.status = QComboBox()
        self.status.addItem("Available", "available")
        self.status.addItem("Retired (no longer used)", "retired")
        self.status.setCurrentIndex(1 if t.get("status") == "retired" else 0)
        for w in (self.tag, self.name, self.category, self.condition, self.notes, self.status):
            w.setStyleSheet(Theme.input_style())
        for label, w in [
            ("Tag *", self.tag),
            ("Name *", self.name),
            ("Category", self.category),
            ("Condition", self.condition),
            ("Kept at", self.place),
            ("Bought on", self.bought),
            ("Bought for", self.cost),
            ("Notes", self.notes),
        ]:
            _row(form, label, w)
        if self._editing:
            _row(form, "Status", self.status)
            # handed-out, broken and lost tools change by handing out and taking back
            self.status.setEnabled(t.get("status") in ("available", "retired"))
        row, ok = _button_row(self, "Save")
        ok.clicked.connect(self._check)
        form.addRow(row)

    def _check(self):
        if not self.tag.text().strip() or not self.name.text().strip():
            QMessageBox.warning(self, "Required", "Tag and name are required.")
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "tag": self.tag.text().strip(),
            "name": self.name.text().strip(),
            "category": self.category.text().strip() or None,
            "condition": self.condition.currentData(),
            "location_id": self.place.currentData(),
            "purchase_date": _date_value(self.bought),
            "purchase_cost": str(self.cost.value()) if self.cost.value() else None,
            "notes": self.notes.text().strip() or None,
        }
        if self._editing and self.status.isEnabled():
            data["status"] = self.status.currentData()
        return data


class MachinesScreen(QWidget):
    M_TAG, M_NAME, M_STATUS, M_WORTH, M_DUE, M_SPENT, M_ACTIONS = range(7)
    T_TAG, T_NAME, T_CATEGORY, T_CONDITION, T_STATUS, T_WITH, T_ACTIONS = range(7)

    def __init__(self):
        super().__init__()
        self._svc = RegistersService()
        self._places: list[dict] = []
        self._machines: list[dict] = []
        self._tools: list[dict] = []
        self._staff: dict[str, str] = {}
        self._shown_machines: list[dict] = []
        self._shown_tools: list[dict] = []
        self._can_manage = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("🛠️  Machines and tools")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_async)
        head.addWidget(refresh)
        self.add_btn = QPushButton("➕  Add")
        self.add_btn.setStyleSheet(Theme.btn_primary())
        self.add_btn.clicked.connect(self._add)
        self.add_btn.setVisible(self._can_manage)
        head.addWidget(self.add_btn)
        layout.addLayout(head)

        self.alert = QLabel("")
        self.alert.setWordWrap(True)
        self.alert.setStyleSheet(Theme.alert("warning"))
        self.alert.setVisible(False)
        layout.addWidget(self.alert)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)

        if self._can_manage:
            machines = QWidget()
            mv = QVBoxLayout(machines)
            mv.setContentsMargins(0, 12, 0, 0)
            mv.setSpacing(10)
            self.m_chips = ChipBar()
            self.m_chips.changed.connect(lambda _k: self._show_machines())
            mv.addWidget(self.m_chips)
            self.m_search = QLineEdit()
            self.m_search.setPlaceholderText("🔍  Search by tag, name or make...")
            self.m_search.setStyleSheet(Theme.input_style())
            self.m_search.textChanged.connect(lambda _t: self._show_machines())
            mv.addWidget(self.m_search)
            self.m_table = _table(["Tag", "Machine", "Status", "Worth today", "Next service", "Spent on service", ""])
            self.m_table.horizontalHeader().setSectionResizeMode(self.M_ACTIONS, QHeaderView.ResizeMode.Fixed)
            self.m_table.setColumnWidth(self.M_ACTIONS, 330)
            self.m_table.horizontalHeader().setSectionResizeMode(self.M_DUE, QHeaderView.ResizeMode.ResizeToContents)
            self.m_table.cellDoubleClicked.connect(lambda r, _c: self._machine_detail(self._shown_machines[r]) if r < len(self._shown_machines) else None)
            mv.addWidget(self.m_table)
            self.tabs.addTab(machines, "Machines")

        tools = QWidget()
        tv = QVBoxLayout(tools)
        tv.setContentsMargins(0, 12, 0, 0)
        tv.setSpacing(10)
        self.t_chips = ChipBar()
        self.t_chips.changed.connect(lambda _k: self._show_tools())
        tv.addWidget(self.t_chips)
        self.t_search = QLineEdit()
        self.t_search.setPlaceholderText("🔍  Search by tag, name or category...")
        self.t_search.setStyleSheet(Theme.input_style())
        self.t_search.textChanged.connect(lambda _t: self._show_tools())
        tv.addWidget(self.t_search)
        self.t_table = _table(["Tag", "Tool", "Category", "Condition", "Status", "With", ""])
        hh = self.t_table.horizontalHeader()
        hh.setSectionResizeMode(self.T_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.t_table.setColumnWidth(self.T_ACTIONS, 270 if self._can_manage else 0)
        self.t_table.setColumnHidden(self.T_ACTIONS, not self._can_manage)
        if self._can_manage:
            self.t_table.cellDoubleClicked.connect(lambda r, _c: self._tool_history(self._shown_tools[r]) if r < len(self._shown_tools) else None)
        tv.addWidget(self.t_table)
        self.tabs.addTab(tools, "Tools")

    def _tab_changed(self, _i: int):
        self.add_btn.setText("➕  Add machine" if self._on_machines() else "➕  Add tool")

    def _on_machines(self) -> bool:
        return self._can_manage and self.tabs.currentIndex() == 0

    # ------------------------------------------------------------------ data
    def _fetch(self):
        machines = self._svc.machines() if self._can_manage else []
        staff = {}
        if self._can_manage:
            staff = {str(u["id"]): u.get("full_name") or u.get("username") for u in self._svc.staff()}
        return PlacesService().places(), machines, self._svc.tools(), staff

    @handle_permissions
    def refresh_data(self):
        self._show(self._fetch())

    def refresh_async(self, _checked=False):
        load_async(self, self._fetch, self._show)

    def _show(self, data):
        self._places, self._machines, self._tools, self._staff = data
        self._tab_changed(0)
        if self._can_manage:
            self._machine_chips()
            self._show_machines()
            late = [m for m in self._machines if due_state(m) == "overdue"]
            down = [m for m in self._machines if m.get("status") == "down"]
            parts = []
            if late:
                parts.append(f"{len(late)} overdue for service: " + ", ".join(m["name"] for m in late[:4]) + ("…" if len(late) > 4 else ""))
            if down:
                parts.append(f"{len(down)} stopped: " + ", ".join(m["name"] for m in down[:4]) + ("…" if len(down) > 4 else ""))
            self.alert.setText("⚠️  " + "   ·   ".join(parts) if parts else "")
            self.alert.setVisible(bool(parts))
        self._tool_chips()
        self._show_tools()

    # ------------------------------------------------------------------ machines
    def _machine_chips(self):
        ms = self._machines
        self.m_chips.set_chips(
            [
                ("all", "All", len(ms)),
                ("due", "Due for service", sum(1 for m in ms if due_state(m))),
                ("down", "Stopped", sum(1 for m in ms if m.get("status") == "down")),
                ("active", "Working", sum(1 for m in ms if m.get("status") == "active")),
                ("retired", "Retired", sum(1 for m in ms if m.get("status") == "retired")),
            ]
        )

    def _show_machines(self):
        which, text = self.m_chips.current(), self.m_search.text().strip().lower()
        rows = []
        for m in self._machines:
            if which == "due" and not due_state(m):
                continue
            if which in ("down", "active", "retired") and m.get("status") != which:
                continue
            if text and text not in " ".join(str(m.get(k) or "") for k in ("tag", "name", "make_model")).lower():
                continue
            rows.append(m)
        self._shown_machines = rows
        t = self.m_table
        t.setRowCount(len(rows))
        for i, m in enumerate(rows):
            t.setItem(i, self.M_TAG, QTableWidgetItem(m["tag"]))
            t.setItem(i, self.M_NAME, QTableWidgetItem(m["name"]))
            t.setItem(i, self.M_STATUS, _coloured(STATUS_WORDS.get(m["status"], m["status"]), STATUS_COLOURS.get(m["status"], Colors.TEXT_PRIMARY)))
            t.setItem(i, self.M_WORTH, _right(money(m.get("book_value")) or "—"))
            state, due = due_state(m), m.get("service_due_on")
            if state == "overdue":
                t.setItem(i, self.M_DUE, _coloured(f"Overdue · {due}" if due else "Overdue", Colors.DANGER))
            elif state == "soon":
                t.setItem(i, self.M_DUE, _coloured(f"Soon · {due}", Colors.ORANGE))
            else:
                t.setItem(i, self.M_DUE, QTableWidgetItem(due or "—"))
            t.setItem(i, self.M_SPENT, _right(money(m.get("maintenance_spent")) or "₹0.00"))
            actions = [("🔧 Serviced", lambda mm=m: self._service(mm), "Record a service or repair")]
            if m["status"] == "down":
                actions.append(("✅ Working", lambda mm=m: self._working(mm), "The machine works again"))
            elif m["status"] == "active":
                actions.append(("⛔ Stopped", lambda mm=m: self._stopped(mm), "The machine stopped working"))
            actions += [("📜", lambda mm=m: self._machine_detail(mm), "Service and stoppage history"), ("✏️", lambda mm=m: self._edit_machine(mm), "Change the details")]
            t.setCellWidget(i, self.M_ACTIONS, action_buttons(actions))
            t.setRowHeight(i, 48)

    @handle_permissions
    def _service(self, m: dict):
        d = MaintenanceDialog(self, m)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.add_maintenance(m["id"], d.get_data())
            self.refresh_data()

    @handle_permissions
    def _stopped(self, m: dict):
        reason, ok = QInputDialog.getText(self, "Machine stopped", f"What happened to {m['name']}? (optional)")
        if ok:
            self._svc.start_downtime(m["id"], reason.strip())
            self.refresh_data()

    @handle_permissions
    def _working(self, m: dict):
        self._svc.end_downtime(m["id"])
        self.refresh_data()

    @handle_permissions
    def _machine_detail(self, m: dict):
        MachineDetailDialog(self, m, self._svc.maintenance(m["id"]), self._svc.downtime(m["id"])).exec()

    @handle_permissions
    def _edit_machine(self, m: dict):
        d = MachineDialog(self, self._places, m)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.save_machine(d.get_data(), m["id"])
            self.refresh_data()

    # ------------------------------------------------------------------ tools
    def _tool_chips(self):
        ts = self._tools

        def count(status: str) -> int:
            return sum(1 for t in ts if t.get("status") == status)

        self.t_chips.set_chips(
            [
                ("all", "All", len(ts)),
                ("available", "Available", count("available")),
                ("issued", "Handed out", count("issued")),
                ("broken", "Broken", count("broken")),
                ("lost", "Lost", count("lost")),
                ("retired", "Retired", count("retired")),
            ]
        )

    def _show_tools(self):
        which, text = self.t_chips.current(), self.t_search.text().strip().lower()
        rows = [
            t
            for t in self._tools
            if (which in ("", "all") or t.get("status") == which)
            and (not text or text in " ".join(str(t.get(k) or "") for k in ("tag", "name", "category")).lower())
        ]
        self._shown_tools = rows
        tb = self.t_table
        tb.setRowCount(len(rows))
        for i, t in enumerate(rows):
            cond = next((label for label, v in CONDITIONS if v == t.get("condition")), t.get("condition") or "")
            holder = self._staff.get(str(t.get("held_by")), "Someone") if t.get("held_by") else ""
            tb.setItem(i, self.T_TAG, QTableWidgetItem(t["tag"]))
            tb.setItem(i, self.T_NAME, QTableWidgetItem(t["name"]))
            tb.setItem(i, self.T_CATEGORY, QTableWidgetItem(t.get("category") or ""))
            tb.setItem(i, self.T_CONDITION, QTableWidgetItem(cond))
            tb.setItem(i, self.T_STATUS, _coloured(STATUS_WORDS.get(t["status"], t["status"]), STATUS_COLOURS.get(t["status"], Colors.TEXT_PRIMARY)))
            tb.setItem(i, self.T_WITH, QTableWidgetItem(holder))
            if self._can_manage:
                actions = []
                if t["status"] == "issued":
                    actions.append(("↩️ Take back", lambda tt=t: self._take_back(tt), "The tool is returned"))
                elif t["status"] == "available":
                    actions.append(("🤝 Hand out", lambda tt=t: self._hand_out(tt), "Give the tool to someone"))
                actions += [("📜", lambda tt=t: self._tool_history(tt), "Who has had it"), ("✏️", lambda tt=t: self._edit_tool(tt), "Change the details")]
                tb.setCellWidget(i, self.T_ACTIONS, action_buttons(actions))
            tb.setRowHeight(i, 48)

    @handle_permissions
    def _hand_out(self, t: dict):
        people = [(uid, name) for uid, name in self._staff.items()]
        if not people:
            QMessageBox.information(self, "Hand out", "There are no staff accounts to hand a tool to.")
            return
        names = [n for _, n in people]
        choice, ok = QInputDialog.getItem(self, "Hand out", f"Who is taking {t['name']}?", names, 0, False)
        if ok:
            self._svc.issue_tool(t["id"], people[names.index(choice)][0])
            self.refresh_data()

    @handle_permissions
    def _take_back(self, t: dict):
        words = ["Returned in good order", "Returned damaged", "Lost"]
        choice, ok = QInputDialog.getItem(self, "Take back", f"{t['name']} is:", words, 0, False)
        if ok:
            self._svc.return_tool(t["id"], ["ok", "damaged", "lost"][words.index(choice)])
            self.refresh_data()

    @handle_permissions
    def _tool_history(self, t: dict):
        rows = self._svc.tool_history(t["id"])
        d = QDialog(self)
        d.setWindowTitle(f"{t['tag']} · {t['name']}")
        d.resize(640, 380)
        d.setStyleSheet(f"background-color: {Colors.BG};")
        v = QVBoxLayout(d)
        table = _table(["Given to", "Handed out", "Back", "Outcome"])
        table.setRowCount(len(rows))
        outcome = {"ok": "Fine", "damaged": "Damaged", "lost": "Lost"}
        for i, r in enumerate(rows):
            back = _stamp(r["returned_at"]) if r.get("returned_at") else "Still out"
            for c, text in enumerate([r.get("user_name") or "", _stamp(r["issued_at"]), back, outcome.get(r.get("outcome"), "")]):
                table.setItem(i, c, QTableWidgetItem(text))
        v.addWidget(table)
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(d.accept)
        v.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        d.exec()

    @handle_permissions
    def _edit_tool(self, t: dict):
        d = ToolDialog(self, self._places, t)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.save_tool(d.get_data(), t["id"])
            self.refresh_data()

    # ------------------------------------------------------------------ add
    @handle_permissions
    def _add(self, _checked=False):
        if self._on_machines():
            d = MachineDialog(self, self._places)
            if d.exec() == QDialog.DialogCode.Accepted:
                self._svc.save_machine(d.get_data())
                self.refresh_data()
        else:
            d = ToolDialog(self, self._places)
            if d.exec() == QDialog.DialogCode.Accepted:
                self._svc.save_tool(d.get_data())
                self.refresh_data()
