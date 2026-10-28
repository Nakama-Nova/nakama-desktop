"""
ui/item_scan.py

A sculpture in Stock: take photos (or a video) of it so the workshop PC builds a 3D model,
and open the finished model. For the owner and artisans only (the server enforces it).
"""

import os
import tempfile
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from services.restoration_service import RestorationService, check_capture
from services.sculpture_service import SculptureService
from ui.restoration_screen import ScanOptionsDialog, TransferThread
from ui.theme import Colors, Theme


def open_file(path: str) -> None:
    """Open a model with whatever the PC uses for .glb (the Windows 3D Viewer, Blender...)."""
    if hasattr(os, "startfile"):
        os.startfile(path)  # noqa: S606 - the user's own downloaded model
    else:
        webbrowser.open(Path(path).as_uri())


class ItemScanDialog(QDialog):
    """Choose the photos or the video of a sculpture and send them to the workshop PC."""

    def __init__(self, parent, item: dict, svc: RestorationService | None = None):
        super().__init__(parent)
        self._item, self._svc = item, svc or RestorationService()
        self._thread: TransferThread | None = None
        self.setWindowTitle(f"3D model of {item['name']}")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        info = QLabel(
            f"{item['name']} ({item.get('sku', '')}). Choose photos of the sculpture, or one video walking around it. "
            "The workshop PC builds a 3D model; when it is done, press “View 3D” on this product in Stock."
        )
        info.setWordWrap(True)
        root.addWidget(info)
        self.photos_btn = QPushButton("📷  Choose photos…")
        self.video_btn = QPushButton("🎥  Choose a video…")
        for b, kind in ((self.photos_btn, "photos"), (self.video_btn, "video")):
            b.setStyleSheet(Theme.btn_primary())
            b.clicked.connect(lambda _c=False, k=kind: self._pick(k))
            root.addWidget(b)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        root.addWidget(self.bar)
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.reject)
        root.addWidget(close)

    def _pick(self, kind: str):
        if self._thread and self._thread.isRunning():
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
        params = opts.get_data()
        problem = check_capture(kind, paths, params["shape"])
        if problem:
            QMessageBox.warning(self, "Cannot upload", problem)
            return
        item_id = self._item["id"]
        self._thread = TransferThread(lambda progress: self._svc.upload_item_capture(item_id, kind, paths, params, progress))
        self._thread.progress.connect(lambda pct, label: (self.bar.setValue(pct), self.bar.setFormat(f"{label}  %p%")))
        self._thread.succeeded.connect(self._uploaded)
        self._thread.failed.connect(self._failed)
        for b in (self.photos_btn, self.video_btn):
            b.setEnabled(False)
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self._thread.start()

    def _finish(self):
        self.bar.setVisible(False)
        for b in (self.photos_btn, self.video_btn):
            b.setEnabled(True)

    def _uploaded(self, _scan):
        self._finish()
        QMessageBox.information(self, "Uploaded", "The files are uploaded. The workshop PC will build the 3D model; open it later with “View 3D”.")
        self.accept()

    def _failed(self, message: str):
        self._finish()
        QMessageBox.warning(self, "Did not finish", message)


def view_3d(parent, item: dict, svc: SculptureService | None = None, opener=open_file) -> None:
    """Save the sculpture's newest 3D model to a temporary file and open it."""
    svc = svc or SculptureService()
    models = svc.models(item["id"])
    if not models:
        QMessageBox.information(
            parent,
            "No 3D model yet",
            f"{item['name']} has no 3D model yet. Use “3D scan” to send photos of it; the workshop PC builds the model.",
        )
        return
    asset = models[-1]
    folder = Path(tempfile.gettempdir()) / "vriksha-3d"
    folder.mkdir(exist_ok=True)
    dest = str(folder / f"{item.get('sku') or item['id']}.glb")
    box = QProgressDialog("Getting the 3D model…", None, 0, 100, parent)
    box.setWindowTitle(item["name"])
    box.setMinimumDuration(0)
    box.setValue(0)
    thread = TransferThread(lambda progress: svc.download(item["id"], asset["id"], dest, progress))
    thread.progress.connect(lambda pct, _label: box.setValue(pct))
    thread.succeeded.connect(lambda path: (box.close(), opener(path)))
    thread.failed.connect(lambda msg: (box.close(), QMessageBox.warning(parent, "Could not get the model", msg)))
    parent._model_thread = thread  # keep it alive until it finishes
    thread.start()
