"""
ui/places_screen.py

Places: where the stock is. Pick a place (or "Not placed yet") to see what it holds, search,
and move stock from one place to another. Owner and manager move stock, sales staff can look,
and only the owner adds or changes a place (the plant units and the shop).
"""

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.enums import UserRole
from services.places_service import NOT_PLACED, PlacesService, place_name, thing_key
from services.session import Session
from ui.components.interactive import ChipBar, action_buttons
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme
from ui.workers import load_async

KIND_WORDS = {"item": "Product", "material": "Material"}
PLACE_KINDS = [("Plant unit", "plant"), ("Shop", "shop")]


def _qty(value) -> str:
    return f"{float(value or 0):g}"


def _right(text: str) -> QTableWidgetItem:
    cell = QTableWidgetItem(text)
    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return cell


def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setStyleSheet(Theme.table_style())
    return t


def _button_row(dialog: QDialog, ok_text: str) -> tuple[QHBoxLayout, QPushButton]:
    row = QHBoxLayout()
    row.addStretch()
    cancel = QPushButton("Cancel")
    cancel.setStyleSheet(Theme.btn_secondary())
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setStyleSheet(Theme.btn_primary())
    row.addWidget(cancel)
    row.addWidget(ok)
    return row, ok


class MoveStockDialog(QDialog):
    """Move stock between places. Choose where from first; the list shows only what is there,
    the amount is limited to it, and a line shows what each place will hold afterwards."""

    def __init__(self, parent, places: list, levels: list, preset: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Move stock")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        self._places, self._levels = places, levels
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)

        self.from_box = QComboBox()
        self.thing_box = QComboBox()
        self.to_box = QComboBox()
        self.qty = QDoubleSpinBox()
        self.qty.setRange(0, 0)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Optional, e.g. for the weekend sale")
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        for w in (self.from_box, self.thing_box, self.to_box, self.qty, self.notes):
            w.setStyleSheet(Theme.input_style())

        # only places that hold something can be moved from
        held: list = []
        for r in levels:
            if float(r["quantity"]) > 0 and r.get("location_id") not in held:
                held.append(r.get("location_id"))
        for loc in held:
            self.from_box.addItem(place_name(places, loc), loc)
        form.addRow(QLabel("Move from", styleSheet=Theme.label()), self.from_box)
        form.addRow(QLabel("What", styleSheet=Theme.label()), self.thing_box)
        form.addRow(QLabel("Move to", styleSheet=Theme.label()), self.to_box)
        form.addRow(QLabel("How many", styleSheet=Theme.label()), self.qty)
        form.addRow(QLabel("Note", styleSheet=Theme.label()), self.notes)
        form.addRow(self.preview)
        row, self.ok = _button_row(self, "Move")
        self.ok.clicked.connect(self.accept)
        form.addRow(row)

        self.from_box.currentIndexChanged.connect(self._fill_things)
        self.thing_box.currentIndexChanged.connect(self._fill_destinations)
        self.to_box.currentIndexChanged.connect(self._update)
        self.qty.valueChanged.connect(self._update)
        if preset:
            i = self.from_box.findData(preset.get("location_id"))
            if i >= 0:
                self.from_box.setCurrentIndex(i)
        self._fill_things()
        if preset:
            kind, ident = thing_key(preset)
            for i in range(self.thing_box.count()):
                if self.thing_box.itemData(i)[0] == (kind, ident):
                    self.thing_box.setCurrentIndex(i)
                    break

    def _here(self, location_id) -> list:
        return [r for r in self._levels if r.get("location_id") == location_id and float(r["quantity"]) > 0]

    def _fill_things(self, *_):
        self.thing_box.blockSignals(True)
        self.thing_box.clear()
        for r in self._here(self.from_box.currentData()):
            self.thing_box.addItem(f"{r['name']}  ·  {_qty(r['quantity'])} here", (thing_key(r), float(r["quantity"]), r))
        self.thing_box.blockSignals(False)
        self._fill_destinations()

    def _fill_destinations(self, *_):
        origin = self.from_box.currentData()
        keep = self.to_box.currentData()
        self.to_box.blockSignals(True)
        self.to_box.clear()
        for loc in [None] + [str(p["id"]) for p in self._places if p.get("is_active", True)]:
            if loc != origin:
                self.to_box.addItem(place_name(self._places, loc), loc)
        i = self.to_box.findData(keep)
        self.to_box.setCurrentIndex(max(i, 0))
        self.to_box.blockSignals(False)
        data = self.thing_box.currentData()
        available = data[1] if data else 0
        is_material = bool(data and data[0][0] == "material")
        self.qty.blockSignals(True)
        self.qty.setDecimals(2 if is_material else 0)
        self.qty.setRange(1 if available >= 1 and not is_material else 0, available)
        self.qty.setValue(min(1.0, available))
        self.qty.blockSignals(False)
        self._update()

    def _after(self, location_id, delta: float, key) -> tuple[float, float]:
        now = sum(
            float(r["quantity"]) for r in self._levels if r.get("location_id") == location_id and thing_key(r) == key
        )
        return now, now + delta

    def _update(self, *_):
        data = self.thing_box.currentData()
        ready = bool(data) and self.qty.value() > 0 and self.to_box.count() > 0
        self.ok.setEnabled(ready)
        if not data:
            self.preview.setText("Nothing to move: no place holds any stock yet.")
            return
        key, q = data[0], self.qty.value()
        a0, a1 = self._after(self.from_box.currentData(), -q, key)
        b0, b1 = self._after(self.to_box.currentData(), +q, key)
        self.preview.setText(
            f"After the move:  {self.from_box.currentText()} {_qty(a0)} → {_qty(a1)}"
            f"   ·   {self.to_box.currentText()} {_qty(b0)} → {_qty(b1)}"
        )

    def get_data(self) -> dict:
        (kind, ident), _avail, _row = self.thing_box.currentData()
        return {
            "item_id": ident if kind == "item" else None,
            "raw_material_id": ident if kind == "material" else None,
            "from_location_id": self.from_box.currentData(),
            "to_location_id": self.to_box.currentData(),
            "quantity": self.qty.value(),
            "notes": self.notes.text().strip(),
        }


class PlaceDialog(QDialog):
    def __init__(self, parent, place: dict | None = None):
        super().__init__(parent)
        p = place or {}
        self.setWindowTitle("Edit place" if place else "Add place")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        self.name = QLineEdit(p.get("name") or "")
        self.name.setPlaceholderText("e.g. Carving unit")
        self.code = QLineEdit(p.get("code") or "")
        self.code.setPlaceholderText("Short code, e.g. U1")
        self.code.setMaxLength(10)
        self.kind = QComboBox()
        for label, value in PLACE_KINDS:
            self.kind.addItem(label, value)
        self.kind.setCurrentIndex(max(self.kind.findData(p.get("kind") or "plant"), 0))
        self.till = QCheckBox("Has a till (takes payment at the counter)")
        self.till.setChecked(bool(p.get("has_till")))
        self.lat, self.lng = QDoubleSpinBox(), QDoubleSpinBox()
        for box, lo, hi, v in ((self.lat, -90, 90, p.get("latitude")), (self.lng, -180, 180, p.get("longitude"))):
            box.setRange(lo, hi)
            box.setDecimals(6)
            box.setValue(float(v or 0))
        self.radius = QDoubleSpinBox()
        self.radius.setRange(1, 5000)
        self.radius.setSuffix(" m")
        self.radius.setValue(float(p.get("radius_m") or 100))
        self.active = QCheckBox("In use")
        self.active.setChecked(p.get("is_active", True))
        for w in (self.name, self.code, self.kind, self.lat, self.lng, self.radius):
            w.setStyleSheet(Theme.input_style())
        for label, w in [
            ("Name *", self.name),
            ("Code *", self.code),
            ("Kind", self.kind),
            ("", self.till),
            ("Latitude", self.lat),
            ("Longitude", self.lng),
            ("Attendance radius", self.radius),
            ("", self.active),
        ]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        row, ok = _button_row(self, "Save")
        ok.clicked.connect(self._check)
        form.addRow(row)

    def _check(self):
        if not self.name.text().strip() or not self.code.text().strip():
            QMessageBox.warning(self, "Required", "Name and code are required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "code": self.code.text().strip(),
            "kind": self.kind.currentData(),
            "has_till": self.till.isChecked(),
            "latitude": self.lat.value(),
            "longitude": self.lng.value(),
            "radius_m": self.radius.value(),
            "is_active": self.active.isChecked(),
        }


class PlacesScreen(QWidget):
    COL_NAME, COL_KIND, COL_PLACE, COL_QTY, COL_ACTIONS = range(5)

    def __init__(self):
        super().__init__()
        self._svc = PlacesService()
        self._places: list[dict] = []
        self._levels: list[dict] = []
        self._shown: list[dict] = []
        self._can_move = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        self._is_owner = Session.is_authorized([UserRole.OWNER])
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel("📍  Places")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_async)
        head.addWidget(refresh)
        self.add_place_btn = QPushButton("➕  Add place")
        self.add_place_btn.setStyleSheet(Theme.btn_secondary())
        self.add_place_btn.clicked.connect(self._add_place)
        self.add_place_btn.setVisible(self._is_owner)
        head.addWidget(self.add_place_btn)
        self.move_btn = QPushButton("↔️  Move stock")
        self.move_btn.setStyleSheet(Theme.btn_primary())
        self.move_btn.clicked.connect(lambda: self._move(None))
        self.move_btn.setVisible(self._can_move)
        head.addWidget(self.move_btn)
        layout.addLayout(head)

        hint = QLabel(
            "Each place keeps its own count; the total on a product or material does not change when "
            "you move it. Pick a place below to see what it holds."
            + (" Double-click a row to move it." if self._can_move else "")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # -- what is where
        stock = QWidget()
        sv = QVBoxLayout(stock)
        sv.setContentsMargins(0, 12, 0, 0)
        sv.setSpacing(10)
        self.chips = ChipBar()
        self.chips.changed.connect(lambda _k: self._apply_filter())
        sv.addWidget(self.chips)
        find = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Search by name...")
        self.search.setStyleSheet(Theme.input_style())
        self.search.textChanged.connect(lambda _t: self._apply_filter())
        find.addWidget(self.search, 1)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("Products and materials", None)
        self.kind_filter.addItem("Products", "item")
        self.kind_filter.addItem("Materials", "material")
        self.kind_filter.setStyleSheet(Theme.input_style())
        self.kind_filter.currentIndexChanged.connect(lambda _i: self._apply_filter())
        find.addWidget(self.kind_filter)
        sv.addLayout(find)
        self.table = _table(["Stock", "Kind", "Place", "Quantity", ""])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(self.COL_ACTIONS, 110 if self._can_move else 0)
        self.table.setColumnHidden(self.COL_ACTIONS, not self._can_move)
        self.table.cellDoubleClicked.connect(self._row_double_clicked)
        sv.addWidget(self.table)
        self.tabs.addTab(stock, "What is where")

        # -- recent moves
        self.moves_table = _table(["When", "What", "From", "To", "Quantity", "Note"])
        self.tabs.addTab(self.moves_table, "Recent moves")

        # -- the places themselves
        self.places_table = _table(["Code", "Name", "Kind", "Till", "Radius", "Status", ""])
        self.places_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.places_table.setColumnWidth(6, 100 if self._is_owner else 0)
        self.places_table.setColumnHidden(6, not self._is_owner)
        self.tabs.addTab(self.places_table, "Places")

    # ------------------------------------------------------------------ data
    def _fetch(self):
        return self._svc.places(), self._svc.levels(), self._svc.transfers()

    @handle_permissions
    def refresh_data(self):
        self._show(self._fetch())

    def refresh_async(self, _checked=False):
        load_async(self, self._fetch, self._show)

    def _show(self, data):
        self._places, self._levels, moves = data
        self._fill_chips()
        self._apply_filter()
        self._fill_moves(moves)
        self._fill_places()

    def _fill_chips(self):
        chips = [("all", "Everywhere", len(self._levels))]
        for p in self._places:
            n = sum(1 for r in self._levels if str(r.get("location_id")) == str(p["id"]))
            chips.append((str(p["id"]), p["name"], n))
        chips.append(("none", NOT_PLACED, sum(1 for r in self._levels if not r.get("location_id"))))
        self.chips.set_chips(chips)

    def _apply_filter(self):
        where = self.chips.current()
        text = self.search.text().strip().lower()
        kind = self.kind_filter.currentData()
        rows = []
        for r in self._levels:
            if where == "none" and r.get("location_id"):
                continue
            if where not in ("all", "none") and str(r.get("location_id")) != where:
                continue
            if kind and thing_key(r)[0] != kind:
                continue
            if text and text not in r["name"].lower():
                continue
            rows.append(r)
        self._shown = rows
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, self.COL_NAME, QTableWidgetItem(r["name"]))
            self.table.setItem(i, self.COL_KIND, QTableWidgetItem(KIND_WORDS[thing_key(r)[0]]))
            place = QTableWidgetItem(r.get("location_name") or NOT_PLACED)
            if not r.get("location_id"):
                place.setForeground(Qt.GlobalColor.darkYellow)
            self.table.setItem(i, self.COL_PLACE, place)
            self.table.setItem(i, self.COL_QTY, _right(_qty(r["quantity"])))
            if self._can_move:
                self.table.setCellWidget(i, self.COL_ACTIONS, action_buttons([("↔️ Move", lambda rr=r: self._move(rr), "Move this to another place")]))
            self.table.setRowHeight(i, 48)

    def _fill_moves(self, moves: list):
        names = {thing_key(r): r["name"] for r in self._levels}
        self.moves_table.setRowCount(len(moves))
        for i, m in enumerate(moves):
            kind, ident = ("item", str(m["item_id"])) if m.get("item_id") else ("material", str(m["raw_material_id"]))
            try:
                when = datetime.fromisoformat(m["created_at"]).strftime("%d %b %Y, %H:%M")
            except (KeyError, ValueError):
                when = m.get("created_at") or ""
            cells = [
                when,
                names.get((kind, ident), KIND_WORDS[kind]),
                place_name(self._places, m.get("from_location_id")),
                place_name(self._places, m.get("to_location_id")),
                _qty(m["quantity"]),
                m.get("notes") or "",
            ]
            for c, text in enumerate(cells):
                self.moves_table.setItem(i, c, _right(text) if c == 4 else QTableWidgetItem(text))

    def _fill_places(self):
        self.places_table.setRowCount(len(self._places))
        for i, p in enumerate(self._places):
            cells = [
                p["code"],
                p["name"],
                "Shop" if p.get("kind") == "shop" else "Plant unit",
                "Yes" if p.get("has_till") else "",
                f"{float(p['radius_m']):g} m",
                "In use" if p.get("is_active", True) else "Switched off",
            ]
            for c, text in enumerate(cells):
                self.places_table.setItem(i, c, QTableWidgetItem(text))
            if self._is_owner:
                self.places_table.setCellWidget(i, 6, action_buttons([("✏️ Edit", lambda pp=p: self._edit_place(pp), "Change this place")]))
            self.places_table.setRowHeight(i, 48)

    # ------------------------------------------------------------------ actions
    def _row_double_clicked(self, row: int, _col: int):
        if self._can_move and 0 <= row < len(self._shown):
            self._move(self._shown[row])

    @handle_permissions
    def _move(self, preset: dict | None):
        if not any(float(r["quantity"]) > 0 for r in self._levels):
            QMessageBox.information(self, "Move stock", "There is no stock to move yet.")
            return
        d = MoveStockDialog(self, self._places, self._levels, preset)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        self._svc.move(**d.get_data())
        self.refresh_data()

    @handle_permissions
    def _add_place(self, _checked=False):
        d = PlaceDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.save_place(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _edit_place(self, place: dict):
        d = PlaceDialog(self, place)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.save_place(d.get_data(), place["id"])
            self.refresh_data()
