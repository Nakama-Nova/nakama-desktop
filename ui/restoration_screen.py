"""
ui/restoration_screen.py

Temple restorations: the owner and artisans keep a record of each old carving being
restored (which temple, which piece, its condition, where the work stands), add photos
or a video of it, watch the workshop PC build the 3D model, and save the 3D files and
CNC G-code. Nobody else can open this screen.

Uploads and saves can be hundreds of MB, so they run on a background thread with a
progress bar; the window stays usable.
"""

import requests
from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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

from services.designs_service import DesignsService
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.money_service import rupees
from services.restoration_service import (
    KIND_WORDS,
    PROJECT_KINDS,
    SCAN_WORDS,
    SHAPE_WORDS,
    STATUSES,
    RestorationService,
    check_capture,
    stages,
    status_word,
)
from services.session import Session
from services.stock_service import StockService
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme


def _size(n) -> str:
    n = float(n or 0)
    return f"{n / 1024 ** 3:.2f} GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.1f} MB" if n >= 1024 ** 2 else f"{n / 1024:.0f} KB"


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


def _line(text="", placeholder="") -> QLineEdit:
    e = QLineEdit(text or "")
    e.setPlaceholderText(placeholder)
    e.setStyleSheet(Theme.input_style())
    return e


class ProjectDialog(QDialog):
    """A temple restoration, or a piece bought from another artisan that is to be finished and painted."""

    def __init__(self, parent, team: list[dict], project: dict | None = None, items: list[dict] | None = None, suppliers: list[dict] | None = None):
        super().__init__(parent)
        p = project or {}
        self._editing = project is not None
        self.setWindowTitle("Edit project" if project else "New project")
        self.setMinimumWidth(500)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        self.kind = QComboBox()
        for label, value in PROJECT_KINDS:
            self.kind.addItem(label, value)
        self.kind.setCurrentIndex(max(0, self.kind.findData(p.get("kind") or "temple")))
        self.kind.setEnabled(not self._editing)  # a project never changes what kind it is
        self.kind.setStyleSheet(Theme.input_style())
        self.title = _line(p.get("title"), "e.g. Dwarapalaka, left door")
        self.temple = _line(p.get("temple_name"), "e.g. Veerabhadra Temple")
        self.location = _line(p.get("location"), "town or village")
        self.item = QComboBox()
        self.item.addItem("Choose the piece…", None)
        for i in items or []:
            self.item.addItem(f"{i['name']}  ({i.get('sku', '')})", i["id"])
        self.item.setCurrentIndex(max(0, self.item.findData(p.get("item_id"))))
        self.item.setStyleSheet(Theme.input_style())
        self.supplier = QComboBox()
        self.supplier.addItem("Not recorded", None)
        for s in suppliers or []:
            self.supplier.addItem(s["name"], s["id"])
        self.supplier.setCurrentIndex(max(0, self.supplier.findData(p.get("supplier_id"))))
        self.supplier.setStyleSheet(Theme.input_style())
        self.piece = _line(p.get("piece"), "what the piece is")
        self.notes = QPlainTextEdit(p.get("condition_notes") or "")
        self.notes.setFixedHeight(90)
        self.notes.setStyleSheet(Theme.input_style())
        self.lead = QComboBox()
        self.lead.addItem("Not decided", None)
        for t in team:
            self.lead.addItem(t["name"], t["id"])
        self.lead.setCurrentIndex(max(0, self.lead.findData(p.get("lead_artisan_id"))))
        self.lead.setStyleSheet(Theme.input_style())

        self._temple_rows, self._finish_rows = [], []

        def row(label, widget, group=None):
            lab = QLabel(label, styleSheet=Theme.label())
            form.addRow(lab, widget)
            if group is not None:
                group.extend([lab, widget])

        row("Kind", self.kind)
        row("Title *", self.title)
        row("Temple *", self.temple, self._temple_rows)
        row("Place", self.location, self._temple_rows)
        row("The piece *", self.item, self._finish_rows)
        row("Bought from", self.supplier, self._finish_rows)
        row("Piece", self.piece)
        self.notes_label = QLabel("Condition", styleSheet=Theme.label())
        form.addRow(self.notes_label, self.notes)
        row("Lead artisan", self.lead)
        form.addRow(_buttons(self))
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def _kind_changed(self, _i=0):
        finishing = self.kind.currentData() == "finishing"
        for w in self._temple_rows:
            w.setVisible(not finishing)
        for w in self._finish_rows:
            w.setVisible(finishing)
        self.notes.setPlaceholderText(
            "What needs doing: finish the surface, paint colours, anything to fix" if finishing
            else "Condition: what is missing or damaged, what the temple wants"
        )

    def _check(self):
        if self.kind.currentData() == "finishing":
            if not self.title.text().strip() or not self.item.currentData():
                QMessageBox.warning(self, "Check the form", "Enter a title and choose the piece being finished.")
                return
        elif not self.title.text().strip() or not self.temple.text().strip():
            QMessageBox.warning(self, "Check the form", "Enter a title and the temple's name.")
            return
        self.accept()

    def get_data(self) -> dict:
        finishing = self.kind.currentData() == "finishing"
        data = {
            "kind": self.kind.currentData(),
            "title": self.title.text().strip(),
            "piece": self.piece.text().strip() or None,
            "condition_notes": self.notes.toPlainText().strip() or None,
            "lead_artisan_id": self.lead.currentData(),
        }
        if finishing:
            data["item_id"] = self.item.currentData()
            data["supplier_id"] = self.supplier.currentData()
        else:
            data["temple_name"] = self.temple.text().strip()
            data["location"] = self.location.text().strip() or None
        return data


class ScanOptionsDialog(QDialog):
    """What the workshop PC should know before it builds the model."""

    def __init__(self, parent, kind: str, paths: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Add photos" if kind == "photos" else "Add video")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        what = f"{len(paths)} photo{'s' if len(paths) != 1 else ''}" if kind == "photos" else "1 video"
        info = QLabel(f"{what} chosen. They go to the workshop PC, which builds the 3D model.")
        info.setWordWrap(True)
        form.addRow(info)
        self.shape = QComboBox()
        self.shape.addItem("Flat carving: a relief or panel, one straight-on photo", "relief")
        self.shape.addItem("Full 3D object: photos all the way around it", "full")
        self.shape.setStyleSheet(Theme.input_style())
        self.shape_hint = QLabel("")
        self.shape_hint.setWordWrap(True)
        self.shape_hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        form.addRow(QLabel("This is a", styleSheet=Theme.label()), self.shape)
        form.addRow(self.shape_hint)
        self.shape.currentIndexChanged.connect(self._shape_changed)
        self.width_mm = QDoubleSpinBox()
        self.width_mm.setRange(0, 5000)
        self.width_mm.setDecimals(0)
        self.width_mm.setSuffix(" mm")
        self.width_mm.setSpecialValueText("not known")
        self.width_mm.setToolTip("The real width of the widest side of the piece")
        self.width_mm.setStyleSheet(Theme.input_style())
        self.quality = QComboBox()
        for label, value in [("Normal", "normal"), ("Fast (rougher)", "fast"), ("High (slow)", "high")]:
            self.quality.addItem(label, value)
        self.quality.setStyleSheet(Theme.input_style())
        self.gcode = QCheckBox("Also make CNC G-code (needs the width)")
        self._kind = kind
        form.addRow(QLabel("Real width", styleSheet=Theme.label()), self.width_mm)
        form.addRow(QLabel("Quality", styleSheet=Theme.label()), self.quality)
        form.addRow(self.gcode)
        form.addRow(_buttons(self, "Upload"))
        self._shape_changed()

    def _shape_changed(self, _i=0):
        if self.shape.currentData() == "relief":
            self.shape_hint.setText(
                "Add just the one photo taken straight on, facing the carving, in even light. If you add "
                "more, the sharpest is used. Any PC can build this, in a minute or two. The depth is "
                "estimated (front face only), so enter the real width."
            )
        else:
            self.shape_hint.setText(
                "Take 8 or more overlapping photos (or one slow video) walking all the way around. "
                "Needs a PC with an NVIDIA graphics card; the scan waits until one is running."
            )

    def _check(self):
        if self.gcode.isChecked() and self.width_mm.value() <= 0:
            QMessageBox.warning(self, "Check the form", "G-code needs the real width of the piece. Measure it and enter it.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "real_width_mm": self.width_mm.value() or None,
            "quality": self.quality.currentData(),
            "gcode": self.gcode.isChecked(),
            "shape": self.shape.currentData(),
        }


class TransferThread(QThread):
    """Runs one long upload/save off the UI thread and reports progress (at most once per percent)."""

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, work):
        super().__init__()
        self._work, self._last = work, -1

    def _report(self, done: int, total: int, label: str):
        pct = int(done * 100 / total) if total else 0
        if pct != self._last:
            self._last = pct
            self.progress.emit(pct, label)

    def run(self):
        try:
            self.succeeded.emit(self._work(self._report))
        except Exception as exc:  # shown to the user in plain words
            self.failed.emit(str(exc) or "Something went wrong. Try again.")


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


class RestorationScreen(QWidget):
    COL_TITLE, COL_TEMPLE, COL_PIECE, COL_STATUS, COL_LEAD, COL_SCANS, COL_FILES = range(7)
    FCOL_KIND, FCOL_SIZE, FCOL_ADDED, FCOL_SAVE = range(4)

    def __init__(self):
        super().__init__()
        self._svc = RestorationService()
        self._rows: list[dict] = []
        self._current: dict | None = None
        self._thread: TransferThread | None = None
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()
        self._timer = QTimer(self)  # keeps scan progress fresh while the screen is open
        self._timer.setInterval(20_000)
        self._timer.timeout.connect(self._auto_refresh)

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(14)
        head = QHBoxLayout()
        title = QLabel("🏛️  Restoration")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        head.addWidget(title)
        head.addStretch()
        self.filter = QComboBox()
        self.filter.addItem("All projects", None)
        for label, value in STATUSES:
            self.filter.addItem(label, value)
        self.filter.setStyleSheet(Theme.input_style())
        self.filter.currentIndexChanged.connect(lambda _i: self.refresh_data())
        head.addWidget(self.filter)
        refresh = QPushButton("🔄  Refresh")
        refresh.setStyleSheet(Theme.btn_secondary())
        refresh.clicked.connect(self.refresh_data)
        head.addWidget(refresh)
        self.new_btn = QPushButton("➕  New restoration")
        self.new_btn.setStyleSheet(Theme.btn_primary())
        self.new_btn.clicked.connect(self._new)
        head.addWidget(self.new_btn)
        root.addLayout(head)

        hint = QLabel(
            "Old temple carvings being documented and restored. Add photos or a video; the workshop PC "
            "builds the 3D model and, for flat carvings, CNC G-code. Only the owner and artisans can see this."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(hint)

        self.table = _table(["Title", "Temple / piece", "Piece", "Status", "Lead", "Scans", "Files"], self.COL_TITLE)
        self.table.setMaximumHeight(230)
        self.table.itemSelectionChanged.connect(self._selected)
        root.addWidget(self.table)

        # detail of the chosen project
        self.detail = QWidget()
        d = QVBoxLayout(self.detail)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(10)
        self.heading = QLabel("")
        self.heading.setStyleSheet(Theme.subheading())
        d.addWidget(self.heading)
        self.notes = QLabel("")
        self.notes.setWordWrap(True)
        self.notes.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        d.addWidget(self.notes)
        self.designs_label = QLabel("")
        self.designs_label.setWordWrap(True)
        self.designs_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        d.addWidget(self.designs_label)

        actions = QHBoxLayout()
        self.edit_btn = QPushButton("✏️  Edit")
        self.photos_btn = QPushButton("📷  Add photos…")
        self.video_btn = QPushButton("🎥  Add video…")
        self.design_btn = QPushButton("🎨  Make a design")
        self.cost_btn = QPushButton("💰  Cost")
        self.cost_btn.setVisible(Session.is_authorized([UserRole.OWNER]))  # money: the owner only
        for b, slot in ((self.edit_btn, self._edit), (self.photos_btn, lambda: self._capture("photos")), (self.video_btn, lambda: self._capture("video")), (self.design_btn, self._make_design), (self.cost_btn, self._cost)):
            b.setStyleSheet(Theme.btn_secondary())
            b.clicked.connect(lambda _c=False, s=slot: s())
            actions.addWidget(b)
        actions.addWidget(QLabel("Status:", styleSheet=Theme.label()))
        self.status = QComboBox()
        for label, value in STATUSES:
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

        d.addWidget(QLabel("Scans", styleSheet=Theme.subheading()))
        self.scans = _table(["Added", "Type", "Files", "Status", "Done", "Note"], 5)
        self.scans.setMaximumHeight(150)
        d.addWidget(self.scans)
        d.addWidget(QLabel("3D files and G-code", styleSheet=Theme.subheading()))
        self.files = _table(["What", "Size", "Added", ""], self.FCOL_KIND)
        d.addWidget(self.files)
        self.detail.setVisible(False)
        root.addWidget(self.detail)

    # ------------------------------------------------------------- data
    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _auto_refresh(self):
        if self._thread and self._thread.isRunning():
            return
        try:
            self.refresh_data()
        except requests.RequestException:
            pass  # offline: keep showing what we have

    @handle_permissions
    def refresh_data(self, _checked=False):
        keep = self._current["id"] if self._current else None
        self._rows = self._svc.projects(self.filter.currentData())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for r, p in enumerate(self._rows):
            where = p.get("temple_name") or (f"{p.get('item_sku') or ''}  {p.get('item_name') or ''}".strip() if p.get("item_id") else "")
            values = [p["title"], where, p.get("piece") or "", status_word(p["status"], p.get("kind", "temple")), p.get("lead_artisan_name") or "", str(p["scan_count"]), str(p["file_count"])]
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
            if p["id"] == keep:
                self.table.selectRow(r)
        self.table.blockSignals(False)
        if keep and any(p["id"] == keep for p in self._rows):
            self._load_detail(keep)
        else:
            self._current = None
            self.detail.setVisible(False)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._load_detail(self._rows[rows[0].row()]["id"])

    @handle_permissions
    def _load_detail(self, restoration_id: str):
        d = self._svc.project(restoration_id)
        self._current = d
        self.detail.setVisible(True)
        kind = d.get("kind", "temple")
        if kind == "finishing":
            head = f"{d['title']}  ·  {d.get('item_name') or ''} ({d.get('item_sku') or ''})"
            if d.get("supplier_name"):
                head += f"  ·  bought from {d['supplier_name']}"
        else:
            head = f"{d['title']}  ·  {d.get('temple_name') or ''}" + (f", {d['location']}" if d.get("location") else "")
        self.heading.setText(head)
        self.notes.setText(d.get("condition_notes") or ("No notes yet." if kind == "finishing" else "No condition notes yet."))
        made = d.get("designs") or []
        self.designs_label.setText("Designs: " + ",  ".join(f"{x['sku']} {x['name']}" for x in made) if made else "No design made from this yet.")
        self.status.blockSignals(True)  # the stages depend on the kind of project
        self.status.clear()
        for label, value in stages(kind):
            self.status.addItem(label, value)
        self.status.setCurrentIndex(max(0, self.status.findData(d["status"])))
        self.status.blockSignals(False)
        self.scans.setRowCount(len(d["scans"]))
        for r, s in enumerate(d["scans"]):
            note = s.get("error") or s.get("note") or ""
            values = [str(s["created_at"])[:16].replace("T", " "), f"{SHAPE_WORDS.get((s.get('params') or {}).get('shape', 'full'), '3D object')}, {'video' if s['source_kind'] == 'video' else 'photos'}", str(s["files"]), SCAN_WORDS.get(s["status"], s["status"]), f"{s['progress']}%", note]
            for c, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if s["status"] == "failed":
                    cell.setForeground(Qt.GlobalColor.red)
                self.scans.setItem(r, c, cell)
        self.files.setRowCount(len(d["files"]))
        for r, f in enumerate(d["files"]):
            for c, text in enumerate([KIND_WORDS.get(f["kind"], f["kind"]), _size(f["size_bytes"]), str(f["created_at"])[:10]]):
                self.files.setItem(r, c, QTableWidgetItem(text))
            save = QPushButton("💾  Save…")
            save.setStyleSheet(Theme.btn_table_action())
            save.clicked.connect(lambda _c=False, ff=f: self._save(ff))
            self.files.setCellWidget(r, self.FCOL_SAVE, save)
            self.files.setRowHeight(r, 44)

    # ---------------------------------------------------------- actions
    @handle_permissions
    def _new(self, _checked=False):
        try:
            items = [i for i in (InventoryService().get_items(allow_cached=True) or []) if i.get("item_type") == "sculpture"]
            suppliers = StockService().rows("suppliers")
        except requests.RequestException:
            items, suppliers = [], []
        d = ProjectDialog(self, self._svc.team(), None, items, suppliers)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.create(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _edit(self):
        if not self._current:
            return
        items = suppliers = []
        if self._current.get("kind") == "finishing":
            items = [i for i in (InventoryService().get_items(allow_cached=True) or []) if i.get("item_type") == "sculpture"]
            suppliers = StockService().rows("suppliers")
        d = ProjectDialog(self, self._svc.team(), self._current, items, suppliers)
        if d.exec() == QDialog.DialogCode.Accepted:
            data = d.get_data()
            data.pop("kind", None)  # a project never changes kind
            self._svc.update(self._current["id"], data)
            self.refresh_data()

    @handle_permissions
    def _make_design(self):
        d = self._current
        if not d:
            return
        name, ok = QInputDialog.getText(self, "Make a design", "Name of the design:", text=d["title"])
        if not ok or not name.strip():
            return
        made = DesignsService().create({"name": name.strip(), "restoration_id": d["id"], "description": d.get("piece")})
        QMessageBox.information(self, "Design saved", f"{made['name']} was saved as {made['sku']}. Find it under Designs, where you can build products from it.")
        self._load_detail(d["id"])

    @handle_permissions
    def _cost(self):
        d = self._current
        if not d:
            return
        c = self._svc.cost(d["id"])
        lines = [
            f"Bought for        {rupees(c['purchase_price'])}",
            f"Labour paid       {rupees(c['labour'])}",
            f"Paint and others  {rupees(c['expenses'])}",
            f"Total so far      {rupees(c['total'])}",
        ]
        if c.get("selling_price") is not None:
            lines.append(f"\nPriced at {rupees(c['selling_price'])}: {'profit' if float(c['profit_if_sold']) >= 0 else 'loss'} {rupees(abs(float(c['profit_if_sold'])))} if sold")
        elif not c.get("item_id"):
            lines.append("\nThis project is not tied to a piece, so only linked expenses are counted.")
        QMessageBox.information(self, f"What {c.get('item_name') or d['title']} has cost", "\n".join(lines))

    @handle_permissions
    def _status_chosen(self, _index=0):
        if self._current and self.status.currentData() != self._current["status"]:
            self._svc.update(self._current["id"], {"status": self.status.currentData()})
            self.refresh_data()

    def _capture(self, kind: str):
        if not self._current or self._busy():
            return
        if kind == "photos":
            paths, _ = QFileDialog.getOpenFileNames(self, "Choose the photos", "", "Photos (*.jpg *.jpeg *.png)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose the video", "", "Video (*.mp4 *.mov)")
            paths = [path] if path else []
        if not paths:
            return
        opts = ScanOptionsDialog(self, kind, paths)
        if opts.exec() != QDialog.DialogCode.Accepted:
            return
        problem = check_capture(kind, paths, opts.get_data()["shape"])
        if problem:
            QMessageBox.warning(self, "Cannot upload", problem)
            return
        rid, params = self._current["id"], opts.get_data()
        self._run(lambda progress: self._svc.upload_capture(rid, kind, paths, params, progress), self._uploaded)

    def _uploaded(self, _scan):
        QMessageBox.information(self, "Uploaded", "The files are uploaded. The workshop PC will build the 3D model; the scan list below shows how far it is.")
        self.refresh_data()

    def _save(self, f: dict):
        if not self._current or self._busy():
            return
        ext = {"glb": ".glb", "stl": ".stl", "obj": ".obj", "ply": ".ply", "nc": ".nc", "render": ".png"}.get(f["kind"], "")
        stem = "".join(ch if ch.isalnum() else "-" for ch in self._current["title"]).strip("-").lower() or "restoration"
        dest, _ = QFileDialog.getSaveFileName(self, "Save the file", f"{stem}-{f['kind']}{ext}")
        if not dest:
            return
        rid, fid = self._current["id"], f["id"]
        self._run(lambda progress: self._svc.download_file(rid, fid, dest, progress), lambda path: QMessageBox.information(self, "Saved", f"Saved to {path}"))

    # --------------------------------------------------------- transfers
    def _busy(self) -> bool:
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "Please wait", "A transfer is still running.")
            return True
        return False

    def _run(self, work, on_done):
        self._thread = TransferThread(work)
        self._thread.progress.connect(lambda pct, label: (self.bar.setValue(pct), self.bar.setFormat(f"{label}  %p%")))
        self._thread.succeeded.connect(lambda result: (self._transfer_over(), on_done(result)))
        self._thread.failed.connect(lambda msg: (self._transfer_over(), QMessageBox.warning(self, "Did not finish", msg)))
        for b in (self.photos_btn, self.video_btn, self.new_btn):
            b.setEnabled(False)
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self._thread.start()

    def _transfer_over(self):
        self.bar.setVisible(False)
        for b in (self.photos_btn, self.video_btn, self.new_btn):
            b.setEnabled(True)
