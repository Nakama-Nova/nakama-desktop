"""Product photos go straight to the storage bucket, and every failure says why."""

import pytest
import requests
from PyQt6.QtWidgets import QFileDialog

import services.stock_service as stock_module
from services.api_client import APIClient, APIError
from services.stock_service import AssetUploadError, StockService, check_asset_file
from ui.stock_dialogs import PhotosDialog

MB = 1024 * 1024


class Resp:
    def __init__(self, status=200):
        self.status_code = status


@pytest.fixture
def wire(monkeypatch):
    """Fake server and bucket: records every call, lets a test change an answer."""
    calls = []
    state = {"put": Resp(200), "presign": None, "register": {"id": "a1", "kind": "image", "storage": "public", "url": "/media/public/x.jpg"}}

    def post(self, path, token, json=None, quiet=False):
        calls.append(("post", path, json))
        if path == "/uploads/presign":
            if isinstance(state["presign"], Exception):
                raise state["presign"]
            return {"key": f"items/{json['item_id']}/{json['kind']}/k.jpg", "url": "https://bucket.test/put?sig=1", "method": "PUT", "headers": {"Content-Type": json["content_type"]}}
        return state["register"]

    def send(method, url, fast_fail=True, **kw):
        calls.append(("send", method, url, kw["headers"], kw["data"].read()))
        if isinstance(state["put"], Exception):
            raise state["put"]
        return state["put"]

    monkeypatch.setattr(APIClient, "_post", post)
    monkeypatch.setattr(APIClient, "_upload", lambda self, path, token, file_path, alt="": calls.append(("fallback", path)) or {"id": "fb"})
    monkeypatch.setattr(stock_module.api_client, "_send", send)
    return calls, state


def photo(tmp_path, name="chair.jpg", size=1000):
    p = tmp_path / name
    p.write_bytes(b"x" * size)
    return str(p)


# ------------------------------------------------------------------ the checks
def test_the_file_checks_say_what_is_wrong(tmp_path):
    assert check_asset_file(photo(tmp_path)) is None
    assert check_asset_file(photo(tmp_path, "m.glb")) is None
    assert "only JPG, PNG, WebP" in check_asset_file(photo(tmp_path, "doc.pdf"))
    assert "is empty" in check_asset_file(photo(tmp_path, "e.jpg", 0))
    big = check_asset_file(photo(tmp_path, "big.png", 11 * MB))
    assert "11.0 MB" in big and "limit is 10 MB" in big
    assert "limit is 25 MB" in check_asset_file(photo(tmp_path, "big.glb", 26 * MB))
    assert "could not be read" in check_asset_file(str(tmp_path / "missing.jpg"))


# ------------------------------------------------------------------ the upload
def test_a_photo_goes_to_the_bucket_then_is_registered_as_public(wire, tmp_path):
    calls, _ = wire
    out = StockService().upload_asset("item-1", photo(tmp_path, size=2048), alt="Front")
    assert out["storage"] == "public"
    presign = next(c for c in calls if c[1] == "/uploads/presign")[2]
    assert presign == {"item_id": "item-1", "kind": "image", "filename": "chair.jpg", "content_type": "image/jpeg", "size": 2048}
    put = next(c for c in calls if c[0] == "send")
    assert put[1] == "put" and put[2] == "https://bucket.test/put?sig=1" and put[3] == {"Content-Type": "image/jpeg"} and put[4] == b"x" * 2048
    register = next(c for c in calls if c[1] == "/items/item-1/assets/register")[2]
    assert register == {"key": "items/item-1/image/k.jpg", "kind": "image", "visibility": "public", "content_type": "image/jpeg", "alt": "Front"}
    assert [c[0] for c in calls] == ["post", "send", "post"]  # presign, upload, register: in that order


def test_a_model_uses_the_glb_kind(wire, tmp_path):
    calls, _ = wire
    StockService().upload_asset("item-1", photo(tmp_path, "chair.glb"))
    assert next(c for c in calls if c[1] == "/uploads/presign")[2]["kind"] == "glb"
    assert next(c for c in calls if c[1].endswith("/register"))[2]["content_type"] == "model/gltf-binary"


def test_a_server_without_a_bucket_still_takes_the_plain_upload(wire, tmp_path):
    calls, state = wire
    state["presign"] = APIError(503, '{"detail": "File storage is not set up yet"}')
    assert StockService().upload_asset("item-1", photo(tmp_path)) == {"id": "fb"}
    assert ("fallback", "/items/item-1/assets") in calls


def test_every_failure_has_a_reason(wire, tmp_path, monkeypatch):
    _, state = wire
    svc = StockService()
    with pytest.raises(AssetUploadError, match="limit is 10 MB"):
        svc.upload_asset("i", photo(tmp_path, "big.jpg", 11 * MB))  # refused before anything is sent
    state["presign"] = APIError(413, '{"detail": "File must be 1 byte to 10 MB"}')
    with pytest.raises(AssetUploadError, match=r"chair\.jpg: File must be 1 byte to 10 MB"):
        svc.upload_asset("i", photo(tmp_path))
    state["presign"] = None
    state["put"] = Resp(403)
    with pytest.raises(AssetUploadError, match=r"storage service refused it \(403\)"):
        svc.upload_asset("i", photo(tmp_path))
    state["put"] = requests.ConnectionError("down")
    with pytest.raises(AssetUploadError, match="connection dropped"):
        svc.upload_asset("i", photo(tmp_path))
    state["put"] = Resp(200)
    monkey_register = APIError(400, '{"detail": "Not a valid image"}')

    def bad_register(self, path, token, json=None, quiet=False):
        if path == "/uploads/presign":
            return {"key": "k", "url": "https://bucket.test/p", "method": "PUT", "headers": {}}
        raise monkey_register

    monkeypatch.setattr(APIClient, "_post", bad_register)
    with pytest.raises(AssetUploadError, match=r"chair\.jpg: Not a valid image"):
        svc.upload_asset("i", photo(tmp_path))


# ------------------------------------------------------------------- the dialog
def test_the_dialog_adds_what_it_can_and_names_what_it_could_not(qapp, wire, tmp_path, monkeypatch, dialogs):
    _, state = wire
    good, bad = photo(tmp_path, "ok.jpg"), photo(tmp_path, "huge.jpg", 11 * MB)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([good, bad], "")))
    monkeypatch.setattr(StockService, "assets", lambda self, item_id: [])
    d = PhotosDialog(None, StockService(), {"id": "item-1", "name": "Chair"})
    d._add()
    kind, title, text = dialogs[-1]
    assert kind == "warning" and title == "Some files were not added"
    assert "1 of 2 added." in text and "huge.jpg is 11.0 MB" in text


def test_the_dialog_stays_quiet_when_everything_uploads(qapp, wire, tmp_path, monkeypatch, dialogs):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([photo(tmp_path)], "")))
    monkeypatch.setattr(StockService, "assets", lambda self, item_id: [])
    PhotosDialog(None, StockService(), {"id": "item-1", "name": "Chair"})._add()
    assert dialogs == []
