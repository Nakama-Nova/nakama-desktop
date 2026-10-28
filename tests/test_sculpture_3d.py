"""A sculpture in Stock: photo scan to 3D, viewing the model, and who gets the buttons."""

import pytest
from PyQt6.QtWidgets import QDialog, QFileDialog, QPushButton, QWidget

from services import api_client
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.restoration_service import RestorationService
from services.sculpture_service import SculptureService
from services.session import Session
from services.stock_service import StockService
from ui import item_scan
from ui.inventory_window import InventoryWindow
from ui.item_scan import ItemScanDialog, view_3d
from ui.restoration_screen import ScanOptionsDialog

CARVING = {"id": "i2", "name": "Hoysala Madhanika", "sku": "SCU-0001", "item_type": "sculpture", "selling_price": "48000", "current_stock": 1, "min_stock": 0, "unit": "pcs"}
CHAIR = {"id": "i1", "name": "Teak Armchair", "sku": "FUR-0001", "item_type": "furniture", "selling_price": "18500", "current_stock": 2, "min_stock": 5, "unit": "pcs"}


@pytest.fixture
def stock(monkeypatch):
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: [CHAIR, CARVING])
    monkeypatch.setattr(StockService, "rows", lambda self, kind: [])


def buttons(table, row, col):
    return [b.text() for b in table.cellWidget(row, col).findChildren(QPushButton)]


def rows_by_sku(w):
    return {w.table.item(r, w.COL_SKU).text(): r for r in range(w.table.rowCount())}


# ---------------------------------------------------------------- who gets the buttons
def test_the_owner_gets_the_3d_buttons_on_sculptures_only(qapp, stock):
    w = InventoryWindow()
    w.refresh_data()
    rows = rows_by_sku(w)
    assert buttons(w.table, rows["SCU-0001"], w.COL_ACTIONS)[-2:] == ["📷 3D scan", "🧊 View 3D"]
    assert "✏️ Edit" in buttons(w.table, rows["SCU-0001"], w.COL_ACTIONS)  # the usual tools stay
    assert buttons(w.table, rows["FUR-0001"], w.COL_ACTIONS) == ["✏️ Edit", "± Stock", "🕘", "🖼️", "🗑️"]


def test_an_artisan_gets_only_the_3d_buttons_on_sculptures(qapp, stock, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.ARTISAN)
    w = InventoryWindow()
    w.refresh_data()
    rows = rows_by_sku(w)
    assert buttons(w.table, rows["SCU-0001"], w.COL_ACTIONS) == ["📷 3D scan", "🧊 View 3D"]  # no edit, no stock changes
    assert buttons(w.table, rows["FUR-0001"], w.COL_ACTIONS) == []
    assert not w.add_btn.isVisible() and not w.can_edit


@pytest.mark.parametrize("role", [UserRole.SALES, UserRole.ACHARI, UserRole.WORKER])
def test_other_staff_get_no_actions_at_all(qapp, stock, monkeypatch, role):
    monkeypatch.setattr(Session, "_role", role)
    w = InventoryWindow()
    w.refresh_data()
    assert w.table.columnCount() == 7 and not w.has_actions  # just the list


def test_a_manager_manages_stock_but_does_not_scan_carvings(qapp, stock, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.MANAGER)
    w = InventoryWindow()
    w.refresh_data()
    assert "📷 3D scan" not in buttons(w.table, rows_by_sku(w)["SCU-0001"], w.COL_ACTIONS)


# --------------------------------------------------------------- sending photos
class FakeService:
    def __init__(self):
        self.sent = []

    def upload_item_capture(self, item_id, kind, paths, params, progress):
        progress(1, 2, "Uploading 1 of 1")
        self.sent.append((item_id, kind, len(paths), params))
        return {"status": "uploaded"}


def photos(tmp_path, n):
    out = []
    for i in range(n):
        p = tmp_path / f"{i}.jpg"
        p.write_bytes(b"j")
        out.append(str(p))
    return out


def test_scanning_a_sculpture_sends_its_photos_in_the_background(qapp, dialogs, monkeypatch, tmp_path):
    files = photos(tmp_path, 1)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: (files, "")))
    monkeypatch.setattr(ScanOptionsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)  # flat carving by default
    svc = FakeService()
    d = ItemScanDialog(None, CARVING, svc)
    d.photos_btn.click()
    assert not d.photos_btn.isEnabled()  # busy while it uploads
    d._thread.wait()
    qapp.processEvents()
    assert svc.sent == [("i2", "photos", 1, {"real_width_mm": None, "quality": "normal", "gcode": False, "shape": "relief"})]
    assert dialogs[-1][0] == "information" and "workshop PC" in dialogs[-1][2]
    assert d.result() == QDialog.DialogCode.Accepted


def test_a_full_object_scan_needs_eight_photos_and_nothing_is_sent_otherwise(qapp, dialogs, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: (photos(tmp_path, 3), "")))
    monkeypatch.setattr(ScanOptionsDialog, "exec", lambda self: (self.shape.setCurrentIndex(self.shape.findData("full")), QDialog.DialogCode.Accepted)[-1])
    svc = FakeService()
    d = ItemScanDialog(None, CARVING, svc)
    d.photos_btn.click()
    assert dialogs[-1][0] == "warning" and "at least 8" in dialogs[-1][2] and svc.sent == [] and d._thread is None


def test_a_failed_upload_says_why_and_lets_you_try_again(qapp, dialogs, monkeypatch, tmp_path):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: (photos(tmp_path, 1), "")))
    monkeypatch.setattr(ScanOptionsDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    class Broken:
        def upload_item_capture(self, *a, **k):
            raise RuntimeError("The connection dropped")

    d = ItemScanDialog(None, CARVING, Broken())
    d.photos_btn.click()
    d._thread.wait()
    qapp.processEvents()
    assert dialogs[-1][0] == "warning" and "The connection dropped" in dialogs[-1][2]
    assert d.photos_btn.isEnabled() and d.result() != QDialog.DialogCode.Accepted


def test_the_service_files_the_scan_under_the_item(monkeypatch, tmp_path):
    posts = []

    class Api:
        def _post(self, path, token, json=None, quiet=False, **kw):
            posts.append((path, json))
            if path == "/scans":
                return {"id": "s9"}
            if path.endswith("/presign"):
                return {"files": [{"key": "k", "url": "https://store.invalid/1", "method": "PUT", "headers": {}}]}
            return {"status": "uploaded"}

    monkeypatch.setattr(api_client, "_send", lambda *a, **k: type("R", (), {"status_code": 200})())
    RestorationService(Api()).upload_item_capture("i2", "photos", photos(tmp_path, 1), {"shape": "relief"}, lambda *a: None)
    body = posts[0][1]
    assert body["item_id"] == "i2" and "restoration_id" not in body and body["source_kind"] == "photos"


# ------------------------------------------------------------------ viewing the model
def test_viewing_with_no_model_says_so(qapp, dialogs):
    class Empty:
        def models(self, item_id):
            return []

    view_3d(None, CARVING, Empty())
    assert dialogs[-1][0] == "information" and "no 3D model yet" in dialogs[-1][2]


def test_viewing_saves_the_newest_model_and_opens_it(qapp, monkeypatch):
    opened, asked = [], []

    class Svc:
        def models(self, item_id):
            return [{"id": "old", "kind": "glb"}, {"id": "new", "kind": "glb"}]

        def download(self, item_id, asset_id, dest, progress):
            asked.append((item_id, asset_id))
            progress(5, 10, "Saving the model")
            open(dest, "wb").write(b"glTF")
            return dest

    parent = QWidget()
    view_3d(parent, CARVING, Svc(), opener=opened.append)
    parent._model_thread.wait()
    qapp.processEvents()
    assert asked == [("i2", "new")]  # the newest
    assert len(opened) == 1 and opened[0].endswith("SCU-0001.glb")
    assert open(opened[0], "rb").read() == b"glTF"


def test_a_failed_download_says_why(qapp, dialogs):
    class Svc:
        def models(self, item_id):
            return [{"id": "m", "kind": "glb"}]

        def download(self, *a):
            raise RuntimeError("Download failed (503). Try again.")

    parent, opened = QWidget(), []
    view_3d(parent, CARVING, Svc(), opener=opened.append)
    parent._model_thread.wait()
    qapp.processEvents()
    assert dialogs[-1][0] == "warning" and "503" in dialogs[-1][2] and opened == []


def test_the_model_service_keeps_only_glb_files_and_saves_in_chunks(monkeypatch, tmp_path):
    class Api:
        _base_url = "https://shop.test"

        def _headers(self, token):
            return {"Authorization": f"Bearer {token}"}

        def _get(self, path, token, params=None, quiet=False):
            assert path == "/items/i2/assets" and quiet
            return [{"id": "a", "kind": "image"}, {"id": "b", "kind": "glb"}, {"id": "c", "kind": "stl"}]

    class R:
        status_code = 200
        headers = {"Content-Length": "6"}

        def iter_content(self, n):
            yield b"abc"
            yield b"def"

    seen = {}
    monkeypatch.setattr(api_client, "_send", lambda method, url, **k: seen.update(url=url, headers=k["headers"]) or R())
    svc = SculptureService(Api())
    assert [m["id"] for m in svc.models("i2")] == ["b"]
    progress = []
    out = svc.download("i2", "b", str(tmp_path / "m.glb"), lambda d, t, label: progress.append((d, t)))
    assert open(out, "rb").read() == b"abcdef" and progress[-1] == (6, 6)
    assert seen["url"].endswith("/items/i2/assets/b/download") and seen["headers"]["Authorization"].startswith("Bearer ")
    monkeypatch.setattr(api_client, "_send", lambda *a, **k: type("Bad", (), {"status_code": 503, "headers": {}})())
    with pytest.raises(RuntimeError, match="503"):
        svc.download("i2", "b", str(tmp_path / "x.glb"), lambda *a: None)


def test_opening_uses_the_systems_viewer(monkeypatch):
    started = []
    monkeypatch.setattr(item_scan.os, "startfile", started.append, raising=False)
    item_scan.open_file("C:/tmp/model.glb")
    assert started == ["C:/tmp/model.glb"]
