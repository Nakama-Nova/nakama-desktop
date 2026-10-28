"""
ui/designs_screen.py

Designs (DES-0001): reusable patterns, taken from a restoration or made fresh. A design
builds sculpture products (it can build several, and a product can come from several
designs) and shows the 3D files of the restoration it came from. Only the owner and
artisans can open this screen.
"""

import requests
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.designs_service import DESIGN_STATUS_WORDS, DESIGN_STATUSES, TYPE_WORDS, DesignsService
from services.inventory_service import InventoryService
from services.money_service import rupees
from services.restoration_service import KIND_WORDS, PROJECT_KINDS, RestorationService
from ui.errors import handle_permissions
from ui.expenses_screen import dialog_buttons, money_spin
from ui.restoration_screen import TransferThread, _size
from ui.theme import Colors, Fonts, Theme

KIND_LABEL = {value: label for label, value in PROJECT_KINDS}


def _table(headers, stretch=None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch is not None:
        h.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setStyleSheet(Theme.table_style())
    return t


def _line(text="", placeholder="") -> QLineEdit:
    e = QLineEdit(text or "")
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(Theme.input_style())
    return e


class DesignDialog(QDialog):
    """A new design, or the name and notes of an existing one."""

    def __init__(self, parent, restorations: list[dict], design: dict | None = None):
        super().__init__(parent)
        d = design or {}
        self.setWindowTitle("Edit design" if design else "New design")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        self.name = _line(d.get("name"), "e.g. Hoysala Madhanika")
        self.description = QPlainTextEdit(d.get("description") or "")
        self.description.setPlaceholderText("What it is, size, wood, notes for the carver")
        self.description.setFixedHeight(90)
        self.description.setStyleSheet(Theme.input_style())
        self.source = QComboBox()
        self.source.addItem("Not taken from a restoration", None)
        for r in restorations:
            self.source.addItem(f"{r['title']}  ({KIND_LABEL.get(r.get('kind', 'temple'), '')})", r["id"])
        self.source.setCurrentIndex(max(0, self.source.findData(d.get("restoration_id"))))
        self.source.setStyleSheet(Theme.input_style())
        for label, w in [("Name *", self.name), ("Notes", self.description), ("Taken from", self.source)]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(dialog_buttons(self))

    def _check(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Check the form", "Give the design a name.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "description": self.description.toPlainText().strip() or None,
            "restoration_id": self.source.currentData(),
        }


class PickProductDialog(QDialog):
    """Choose one product (by code or name) to link to the design."""

    def __init__(self, parent, items: list[dict]):
        super().__init__(parent)
        self._items = items
        self.setWindowTitle("Link a product")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        self.search = _line(placeholder="type a code or a name to narrow the list")
        self.pick = QComboBox()
        self.pick.setStyleSheet(Theme.input_style())
        self.search.textChanged.connect(self._fill)
        self._fill("")
        form.addRow(QLabel("Find", styleSheet=Theme.label()), self.search)
        form.addRow(QLabel("Product *", styleSheet=Theme.label()), self.pick)
        form.addRow(dialog_buttons(self, "Link"))

    def _fill(self, text):
        q = (text or "").strip().lower()
        self.pick.clear()
        for i in self._items:
            if not q or q in i["name"].lower() or q in (i.get("sku") or "").lower():
                self.pick.addItem(f"{i.get('sku', '')}  {i['name']}  ({TYPE_WORDS.get(i.get('item_type') or 'furniture', '')})", i["id"])

    def _check(self):
        if not self.pick.currentData():
            QMessageBox.warning(self, "Link a product", "Choose a product.")
        else:
            self.accept()

    def item_id(self) -> str:
        return self.pick.currentData()


class ProductFromDesignDialog(QDialog):
    """Build a new sculpture product out of the design."""

    def __init__(self, parent, design: dict):
        super().__init__(parent)
        self.setWindowTitle(f"New product from {design['sku']}")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        self.name = _line(design["name"])
        self.price = money_spin(10_000_000)
        self.wood = _line(placeholder="e.g. Teak (optional)")
        note = QLabel("It is added to Stock as a Sculpture with its own code and linked to this design. Stock starts at 0; add it when the piece is carved.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow(note)
        for label, w in [("Name *", self.name), ("Selling price", self.price), ("Wood", self.wood)]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(dialog_buttons(self, "Create product"))

    def _check(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Check the form", "Give the product a name.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "selling_price": round(self.price.value(), 2),
            "wood_type": self.wood.text().strip() or None,
        }


class DesignsScreen(QWidget):
    COL_SKU, COL_NAME, COL_FROM, COL_PRODUCTS, COL_STATUS = range(5)
    PCOL_SKU, PCOL_NAME, PCOL_TYPE, PCOL_PRICE, PCOL_STOCK, PCOL_ACTION = range(6)
    FCOL_KIND, FCOL_SIZE, FCOL_SAVE = range(3)

    def __init__(self):
        super().__init__()
        self._svc = DesignsService()
        self._rows: list[dict] = []
        self._current: dict | None = None
        self._thread: TransferThread | None = None
        self.setStyleSheet(Theme.content_bg())
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)
        self._search_timer.timeout.connect(self.refresh_data)
        self._build_ui()

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("🎨  Designs")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.search = _line(placeholder="Search code or name")
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        head.addWidget(self.search)
        self.status_filter = QComboBox()
        self.status_filter.addItem("All designs", None)
        for label, value in DESIGN_STATUSES:
            self.status_filter.addItem(label, value)
        self.status_filter.setStyleSheet(Theme.input_style())
        self.status_filter.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.status_filter)
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        self.new_btn = QPushButton("➕  New design")
        self.new_btn.setStyleSheet(Theme.btn_primary())
        self.new_btn.clicked.connect(self._new)
        head.addWidget(self.new_btn)
        root.addLayout(head)

        hint = QLabel(
            "A design is a pattern to carve, with its own code. Take it from a restoration (it then shows that "
            "piece's 3D files) or make it fresh, then build sculpture products from it. Only the owner and artisans see this."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(hint)

        self.table = _table(["Code", "Design", "Taken from", "Products", "Status"], self.COL_NAME)
        self.table.setMaximumHeight(220)
        self.table.itemSelectionChanged.connect(self._selected)
        root.addWidget(self.table)

        self.detail = QWidget()
        d = QVBoxLayout(self.detail)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(8)
        self.heading = QLabel("")
        self.heading.setStyleSheet(Theme.subheading())
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        d.addWidget(self.heading)
        d.addWidget(self.notes)
        actions = QHBoxLayout()
        self.edit_btn = QPushButton("✏️  Edit")
        self.link_btn = QPushButton("🔗  Link a product…")
        self.make_btn = QPushButton("🪵  Create a product")
        for b, slot in ((self.edit_btn, self._edit), (self.link_btn, self._link), (self.make_btn, self._make)):
            b.setStyleSheet(Theme.btn_secondary())
            b.clicked.connect(lambda _c=False, s=slot: s())
            actions.addWidget(b)
        actions.addWidget(QLabel("Status:", styleSheet=Theme.label()))
        self.status = QComboBox()
        for label, value in DESIGN_STATUSES:
            self.status.addItem(label, value)
        self.status.setStyleSheet(Theme.input_style())
        self.status.activated.connect(self._status_chosen)
        actions.addWidget(self.status)
        actions.addStretch()
        d.addLayout(actions)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        d.addWidget(self.bar)
        d.addWidget(QLabel("Products built from this design", styleSheet=Theme.subheading()))
        self.products = _table(["Code", "Product", "Type", "Price", "In stock", ""], self.PCOL_NAME)
        self.products.setMaximumHeight(170)
        d.addWidget(self.products)
        self.files_title = QLabel("3D files from the restoration", styleSheet=Theme.subheading())
        d.addWidget(self.files_title)
        self.files = _table(["What", "Size", ""], self.FCOL_KIND)
        d.addWidget(self.files)
        self.detail.setVisible(False)
        root.addWidget(self.detail)

    # ------------------------------------------------------------- data
    @handle_permissions
    def refresh_data(self, _checked=False):
        keep = self._current["id"] if self._current else None
        self._rows = self._svc.designs(self.status_filter.currentData(), self.search.text().strip())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for r, d in enumerate(self._rows):
            values = [d["sku"], d["name"], d.get("restoration_title") or "", str(d["product_count"]), DESIGN_STATUS_WORDS.get(d["status"], d["status"])]
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
            self.table.setRowHeight(r, 42)
            if d["id"] == keep:
                self.table.selectRow(r)
        self.table.blockSignals(False)
        if keep and any(d["id"] == keep for d in self._rows):
            self._load_detail(keep)
        else:
            self._current = None
            self.detail.setVisible(False)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._load_detail(self._rows[rows[0].row()]["id"])

    @handle_permissions
    def _load_detail(self, design_id: str):
        d = self._svc.design(design_id)
        self._current = d
        self.detail.setVisible(True)
        self.heading.setText(f"{d['sku']}  ·  {d['name']}")
        source = d.get("restoration")
        self.notes.setText((d.get("description") or "No notes yet.") + (f"\nTaken from: {source['title']}" if source else ""))
        self.status.setCurrentIndex(max(0, self.status.findData(d["status"])))
        prods = d.get("products") or []
        self.products.setRowCount(len(prods))
        for r, p in enumerate(prods):
            values = [p["sku"], p["name"], TYPE_WORDS.get(p["item_type"], p["item_type"]), rupees(p["selling_price"]), str(p["current_stock"])]
            for c, text in enumerate(values):
                self.products.setItem(r, c, QTableWidgetItem(text))
            un = QPushButton("Unlink")
            un.setStyleSheet(Theme.btn_table_action())
            un.clicked.connect(lambda _c=False, pp=p: self._unlink(pp))
            self.products.setCellWidget(r, self.PCOL_ACTION, un)
            self.products.setRowHeight(r, 40)
        files = d.get("files") or []
        self.files_title.setVisible(bool(source))
        self.files.setVisible(bool(source))
        self.files.setRowCount(len(files))
        for r, f in enumerate(files):
            self.files.setItem(r, 0, QTableWidgetItem(KIND_WORDS.get(f["kind"], f["kind"])))
            self.files.setItem(r, 1, QTableWidgetItem(_size(f["size_bytes"])))
            save = QPushButton("💾  Save…")
            save.setStyleSheet(Theme.btn_table_action())
            save.clicked.connect(lambda _c=False, ff=f: self._save(ff))
            self.files.setCellWidget(r, self.FCOL_SAVE, save)
            self.files.setRowHeight(r, 40)

    # ---------------------------------------------------------- actions
    def _restorations(self) -> list[dict]:
        try:
            return RestorationService().projects()
        except requests.RequestException:
            return []

    @handle_permissions
    def _new(self, _checked=False):
        d = DesignDialog(self, self._restorations())
        if d.exec() == QDialog.DialogCode.Accepted:
            made = self._svc.create(d.get_data())
            QMessageBox.information(self, "Saved", f"{made['name']} was saved as {made['sku']}.")
            self.refresh_data()

    @handle_permissions
    def _edit(self):
        cur = self._current
        if not cur:
            return
        d = DesignDialog(self, self._restorations(), cur)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.update(cur["id"], d.get_data())
            self.refresh_data()

    @handle_permissions
    def _status_chosen(self, _index=0):
        if self._current and self.status.currentData() != self._current["status"]:
            self._svc.update(self._current["id"], {"status": self.status.currentData()})
            self.refresh_data()

    @handle_permissions
    def _link(self):
        cur = self._current
        if not cur:
            return
        linked = {p["id"] for p in cur.get("products") or []}
        items = [i for i in (InventoryService().get_items(allow_cached=True) or []) if i["id"] not in linked]
        items.sort(key=lambda i: (i.get("item_type") != "sculpture", i.get("sku") or ""))  # sculptures first
        if not items:
            QMessageBox.information(self, "Link a product", "Every product is already linked, or Stock is empty. Use Create a product to make a new one.")
            return
        d = PickProductDialog(self, items)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.link(cur["id"], d.item_id())
            self.refresh_data()

    @handle_permissions
    def _unlink(self, product: dict):
        cur = self._current
        ask = QMessageBox.question(self, "Unlink", f"Take {product['name']} out of {cur['sku']}? The product stays in Stock.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if cur and ask == QMessageBox.StandardButton.Yes:
            self._svc.unlink(cur["id"], product["id"])
            self.refresh_data()

    @handle_permissions
    def _make(self):
        cur = self._current
        if not cur:
            return
        d = ProductFromDesignDialog(self, cur)
        if d.exec() == QDialog.DialogCode.Accepted:
            made = self._svc.create_product(cur["id"], d.get_data())
            QMessageBox.information(self, "Product created", f"{made['name']} is in Stock as {made['sku']} and linked to {cur['sku']}.")
            self.refresh_data()

    def _save(self, f: dict):
        cur = self._current
        source = (cur or {}).get("restoration")
        if not source or (self._thread and self._thread.isRunning()):
            return
        ext = {"glb": ".glb", "stl": ".stl", "obj": ".obj", "ply": ".ply", "nc": ".nc", "render": ".png"}.get(f["kind"], "")
        dest, _ = QFileDialog.getSaveFileName(self, "Save the file", f"{cur['sku'].lower()}-{f['kind']}{ext}")
        if not dest:
            return
        rid, fid = source["id"], f["id"]
        svc = RestorationService()
        self._thread = TransferThread(lambda progress: svc.download_file(rid, fid, dest, progress))
        self._thread.progress.connect(lambda pct, label: (self.bar.setValue(pct), self.bar.setFormat(f"{label}  %p%")))
        self._thread.succeeded.connect(lambda path: (self.bar.setVisible(False), QMessageBox.information(self, "Saved", f"Saved to {path}")))
        self._thread.failed.connect(lambda msg: (self.bar.setVisible(False), QMessageBox.warning(self, "Did not finish", msg)))
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self._thread.start()
