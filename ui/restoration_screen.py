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

from services.restoration_service import (
    KIND_WORDS,
    SCAN_WORDS,
    STATUS_WORDS,
    STATUSES,
    RestorationService,
    check_capture,
)
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
    def __init__(self, parent, team: list[dict], project: dict | None = None):
        super().__init__(parent)
        p = project or {}
        self.setWindowTitle("Edit restoration" if project else "New restoration")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        self.title = _line(p.get("title"), "e.g. Dwarapalaka, left door")
        self.temple = _line(p.get("temple_name"), "e.g. Veerabhadra Temple")
        self.location = _line(p.get("location"), "town or village")
        self.piece = _line(p.get("piece"), "what the piece is")
        self.notes = QPlainTextEdit(p.get("condition_notes") or "")
        self.notes.setPlaceholderText("Condition: what is missing or damaged, what the temple wants")
        self.notes.setFixedHeight(90)
        self.notes.setStyleSheet(Theme.input_style())
        self.lead = QComboBox()
        self.lead.addItem("Not decided", None)
        for t in team:
            self.lead.addItem(t["name"], t["id"])
        self.lead.setCurrentIndex(max(0, self.lead.findData(p.get("lead_artisan_id"))))
        self.lead.setStyleSheet(Theme.input_style())
        for label, w in [("Title *", self.title), ("Temple *", self.temple), ("Place", self.location), ("Piece", self.piece), ("Condition", self.notes), ("Lead artisan", self.lead)]:
            form.addRow(QLabel(label, styleSheet=Theme.label()), w)
        form.addRow(_buttons(self))

    def _check(self):
        if not self.title.text().strip() or not self.temple.text().strip():
            QMessageBox.warning(self, "Check the form", "Enter a title and the temple's name.")
        else:
            self.accept()

    def get_data(self) -> dict:
        return {
            "title": self.title.text().strip(),
            "temple_name": self.temple.text().strip(),
            "location": self.location.text().strip() or None,
            "piece": self.piece.text().strip() or None,
            "condition_notes": self.notes.toPlainText().strip() or None,
            "lead_artisan_id": self.lead.currentData(),
        }


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
        what = f"{len(paths)} photos" if kind == "photos" else "1 video"
        info = QLabel(f"{what} chosen. They go to the workshop PC, which builds the 3D model.")
        info.setWordWrap(True)
        form.addRow(info)
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
        self.gcode = QCheckBox("Also make CNC G-code for a flat carving (needs the width)")
        form.addRow(QLabel("Real width", styleSheet=Theme.label()), self.width_mm)
        form.addRow(QLabel("Quality", styleSheet=Theme.label()), self.quality)
        form.addRow(self.gcode)
        form.addRow(_buttons(self, "Upload"))

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

        self.table = _table(["Title", "Temple", "Piece", "Status", "Lead", "Scans", "Files"], self.COL_TITLE)
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

        actions = QHBoxLayout()
        self.edit_btn = QPushButton("✏️  Edit")
        self.photos_btn = QPushButton("📷  Add photos…")
        self.video_btn = QPushButton("🎥  Add video…")
        for b, slot in ((self.edit_btn, self._edit), (self.photos_btn, lambda: self._capture("photos")), (self.video_btn, lambda: self._capture("video"))):
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
            values = [p["title"], p["temple_name"], p.get("piece") or "", STATUS_WORDS.get(p["status"], p["status"]), p.get("lead_artisan_name") or "", str(p["scan_count"]), str(p["file_count"])]
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
        self.heading.setText(f"{d['title']}  ·  {d['temple_name']}" + (f", {d['location']}" if d.get("location") else ""))
        self.notes.setText(d.get("condition_notes") or "No condition notes yet.")
        self.status.setCurrentIndex(max(0, self.status.findData(d["status"])))
        self.scans.setRowCount(len(d["scans"]))
        for r, s in enumerate(d["scans"]):
            note = s.get("error") or s.get("note") or ""
            values = [str(s["created_at"])[:16].replace("T", " "), "Video" if s["source_kind"] == "video" else "Photos", str(s["files"]), SCAN_WORDS.get(s["status"], s["status"]), f"{s['progress']}%", note]
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
        d = ProjectDialog(self, self._svc.team())
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.create(d.get_data())
            self.refresh_data()

    @handle_permissions
    def _edit(self):
        if not self._current:
            return
        d = ProjectDialog(self, self._svc.team(), self._current)
        if d.exec() == QDialog.DialogCode.Accepted:
            self._svc.update(self._current["id"], d.get_data())
            self.refresh_data()

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
        problem = check_capture(kind, paths)
        if problem:
            QMessageBox.warning(self, "Cannot upload", problem)
            return
        opts = ScanOptionsDialog(self, kind, paths)
        if opts.exec() != QDialog.DialogCode.Accepted:
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
