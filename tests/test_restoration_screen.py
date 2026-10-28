"""Restoration: the artisan role in the menu, the screen, the capture rules and the transfers."""

import io

import pytest
from PyQt6.QtWidgets import QFileDialog, QPushButton

from services import api_client
from services.enums import UserRole
from services.restoration_service import (
    PHOTO_MAX,
    RestorationService,
    check_capture,
)
from services.session import Session
from ui.main_window import MainWindow
from ui.restoration_screen import (
    ProjectDialog,
    RestorationScreen,
    ScanOptionsDialog,
    TransferThread,
)

P1 = {"id": "r1", "title": "Dwarapalaka left", "temple_name": "Veerabhadra Temple", "location": "Lepakshi", "piece": "Door guardian", "condition_notes": "Nose missing", "status": "review", "lead_artisan_id": "u9", "lead_artisan_name": "Asha K", "scan_count": 2, "file_count": 2}
P2 = {**P1, "id": "r2", "title": "Nandi", "status": "planned", "lead_artisan_name": None, "scan_count": 0, "file_count": 0}
DETAIL = {
    **P1,
    "scans": [
        {"id": "s1", "status": "done", "source_kind": "photos", "params": {"shape": "relief"}, "files": 40, "progress": 100, "note": "Finished", "error": None, "created_at": "2026-10-27T10:00:00Z"},
        {"id": "s2", "status": "failed", "source_kind": "video", "files": 1, "progress": 20, "note": None, "error": "Too few overlapping photos", "created_at": "2026-10-26T09:00:00Z"},
    ],
    "files": [
        {"id": "f1", "kind": "glb", "size_bytes": 5_242_880, "created_at": "2026-10-27T11:00:00Z"},
        {"id": "f2", "kind": "nc", "size_bytes": 2048, "created_at": "2026-10-27T11:00:00Z"},
    ],
}


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setattr(RestorationService, "projects", lambda self, status=None: [P2, P1] if status is None else [p for p in (P1, P2) if p["status"] == status])
    monkeypatch.setattr(RestorationService, "project", lambda self, rid: DETAIL)
    monkeypatch.setattr(RestorationService, "team", lambda self: [{"id": "u9", "name": "Asha K", "role": "artisan"}])
    monkeypatch.setattr(RestorationService, "update", lambda self, rid, data: calls.append(("update", rid, data)))
    monkeypatch.setattr(RestorationService, "create", lambda self, data: calls.append(("create", data)))
    return calls


def select(screen, row):
    screen.table.selectRow(row)
    screen._selected()


# ------------------------------------------------------------------ access
@pytest.mark.parametrize(
    "role,sees",
    [(UserRole.OWNER, True), (UserRole.ARTISAN, True), (UserRole.MANAGER, False), (UserRole.SALES, False), (UserRole.ACHARI, False), (UserRole.WORKER, False)],
)
def test_only_the_owner_and_artisans_see_restoration(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert ("Restoration" in [label for _, label, _ in w._get_allowed_nav_items()]) is sees


def test_an_artisan_gets_a_focused_menu(qapp, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.ARTISAN)
    w = MainWindow()
    w._sync_timer.stop()
    labels = [label for _, label, _ in w._get_allowed_nav_items()]
    assert labels == ["Home", "Stock", "Workforce", "3D Lab", "Wages", "Restoration", "Designs"]


def test_artisan_is_a_role_the_owner_can_pick(qapp):
    from ui.staff_screen import ROLE_WORDS, StaffDialog

    assert ROLE_WORDS["artisan"].startswith("Artisan")
    d = StaffDialog(None)
    assert d.role.findData("artisan") >= 0


# ------------------------------------------------------------------ screen
def test_lists_projects_and_shows_the_chosen_ones_scans_and_files(qapp, fake):
    s = RestorationScreen()
    s.refresh_data()
    assert s.table.rowCount() == 2
    assert s.table.item(1, s.COL_STATUS).text() == "Ready to review" and s.table.item(1, s.COL_LEAD).text() == "Asha K"
    assert not s.detail.isVisibleTo(s)  # nothing chosen yet
    select(s, 1)
    assert s.detail.isVisibleTo(s)
    assert "Dwarapalaka left" in s.heading.text() and "Lepakshi" in s.heading.text()
    assert s.notes.text() == "Nose missing"
    assert s.scans.item(0, 3).text() == "Done" and s.scans.item(1, 3).text() == "Failed"
    assert s.scans.item(0, 1).text() == "Flat carving, photos" and s.scans.item(1, 1).text() == "3D object, video"
    assert s.scans.item(1, 5).text() == "Too few overlapping photos"  # why it failed, so photos can be retaken
    assert [s.files.item(r, 0).text() for r in range(2)] == ["3D model (.glb)", "CNC G-code (.nc)"]
    assert s.files.item(0, s.FCOL_SIZE).text() == "5.0 MB"
    assert s.files.cellWidget(0, s.FCOL_SAVE).text().endswith("Save…")


def test_changing_the_status_sends_only_that(qapp, fake):
    s = RestorationScreen()
    s.refresh_data()
    select(s, 1)
    s.status.setCurrentIndex(s.status.findData("carving"))
    s._status_chosen()
    assert fake == [("update", "r1", {"status": "carving"})]
    fake.clear()
    s.status.setCurrentIndex(s.status.findData("review"))  # same as it already is
    s._status_chosen()
    assert fake == []


def test_project_dialog_collects_the_record_and_needs_a_title_and_temple(qapp, dialogs):
    team = [{"id": "u9", "name": "Asha K", "role": "artisan"}]
    d = ProjectDialog(None, team)
    d._check()
    assert d.result() == 0 and dialogs[-1][0] == "warning"
    d.title.setText("Nandi")
    d.temple.setText("Veerabhadra Temple")
    d.notes.setPlainText("Horn broken")
    d.lead.setCurrentIndex(d.lead.findData("u9"))
    assert d.get_data() == {"kind": "temple", "title": "Nandi", "temple_name": "Veerabhadra Temple", "location": None, "piece": None, "condition_notes": "Horn broken", "lead_artisan_id": "u9"}
    editing = ProjectDialog(None, team, P1)
    assert editing.get_data()["lead_artisan_id"] == "u9" and editing.title.text() == "Dwarapalaka left"


def test_scan_options_gcode_needs_a_width(qapp, dialogs):
    d = ScanOptionsDialog(None, "photos", ["a.jpg"] * 10)
    d.gcode.setChecked(True)
    d._check()
    assert d.result() == 0 and "real width" in dialogs[-1][2]
    d.width_mm.setValue(600)
    assert d.get_data() == {"real_width_mm": 600.0, "quality": "normal", "gcode": True, "shape": "relief"}
    plain = ScanOptionsDialog(None, "video", ["a.mp4"])
    assert plain.get_data() == {"real_width_mm": None, "quality": "normal", "gcode": False, "shape": "relief"}
    plain.shape.setCurrentIndex(plain.shape.findData("full"))
    assert plain.get_data()["shape"] == "full" and "NVIDIA" in plain.shape_hint.text()
    plain.shape.setCurrentIndex(plain.shape.findData("relief"))
    assert "straight on" in plain.shape_hint.text()


# ----------------------------------------------------------------- the rules
def test_capture_rules_match_the_server(tmp_path):
    def make(name, size=10):
        p = tmp_path / name
        p.write_bytes(b"x" * size)
        return str(p)

    ten = [make(f"{i}.jpg") for i in range(10)]
    assert check_capture("photos", ten) is None
    assert "at least 8" in check_capture("photos", ten[:5])
    assert check_capture("photos", ten[:1], "relief") is None  # one straight-on photo is enough for a flat carving
    assert "at least 8" in check_capture("photos", ten[:1], "full")
    assert "Choose the files" in check_capture("photos", [])
    assert ".png" in check_capture("photos", ten[:9] + [make("a.gif")])
    assert check_capture("video", [make("v.mp4")]) is None
    assert "one video" in check_capture("video", [make("a.mp4"), make("b.mp4")])
    assert "too big" in check_capture("photos", ten[:9] + [make("huge.jpg", PHOTO_MAX + 1)])


# --------------------------------------------------------------- transfers
class FakeApi:
    def __init__(self):
        self.calls = []

    def _post(self, path, token, json=None, quiet=False, **kw):
        assert quiet, "worker-thread calls must not raise pop-ups"
        self.calls.append(path)
        if path == "/scans":
            return {"id": "s9"}
        if path.endswith("/presign"):
            return {"files": [{"key": f"scans/s9/src/{i}.jpg", "url": f"https://store.invalid/{i}", "method": "PUT", "headers": {"Content-Type": "image/jpeg"}} for i in range(len(json["files"]))]}
        return {"id": "s9", "status": "uploaded"}

    def _get(self, path, token, params=None, quiet=False):
        assert quiet
        return {"url": "https://store.invalid/dl", "size_bytes": 6}


def test_upload_streams_every_file_reports_progress_and_queues_the_scan(tmp_path, monkeypatch):
    paths = []
    for i in range(10):
        p = tmp_path / f"{i}.jpg"
        p.write_bytes(b"j" * 1000)
        paths.append(str(p))
    sent, progress = [], []

    def fake_send(method, url, fast_fail=True, data=None, headers=None, **kw):
        assert method == "put" and fast_fail is False
        sent.append((url, len(data), len(data.read())))  # reads it as requests would
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(api_client, "_send", fake_send)
    api = FakeApi()
    scan = RestorationService(api).upload_capture("r1", "photos", paths, {"gcode": False}, lambda d, t, label: progress.append((d, t, label)))
    assert scan["status"] == "uploaded"
    assert api.calls == ["/scans", "/scans/s9/presign", "/scans/s9/complete"]
    assert [n for _, n, _ in sent] == [1000] * 10 and all(n == m for _, n, m in sent)
    assert progress[-1][:2] == (10000, 10000) and "10 of 10" in progress[-1][2]


def test_a_refused_upload_stops_and_does_not_queue(tmp_path, monkeypatch):
    paths = []
    for i in range(8):
        p = tmp_path / f"{i}.jpg"
        p.write_bytes(b"j")
        paths.append(str(p))
    monkeypatch.setattr(api_client, "_send", lambda *a, **k: type("R", (), {"status_code": 403})())
    api = FakeApi()
    with pytest.raises(RuntimeError, match="failed"):
        RestorationService(api).upload_capture("r1", "photos", paths, {}, lambda *a: None)
    assert "/scans/s9/complete" not in api.calls


def test_a_bad_choice_never_reaches_the_server(tmp_path):
    api = FakeApi()
    with pytest.raises(ValueError, match="Choose the files"):
        RestorationService(api).upload_capture("r1", "photos", [], {}, lambda *a: None)
    assert api.calls == []


def test_download_saves_the_file_in_chunks(tmp_path, monkeypatch):
    class R:
        status_code = 200

        def iter_content(self, n):
            yield b"abc"
            yield b"def"

    monkeypatch.setattr(api_client, "_send", lambda *a, **k: R())
    seen = []
    dest = tmp_path / "model.glb"
    out = RestorationService(FakeApi()).download_file("r1", "f1", str(dest), lambda d, t, label: seen.append((d, t)))
    assert out == str(dest) and dest.read_bytes() == b"abcdef" and seen[-1] == (6, 6)


def test_the_thread_reports_progress_once_per_percent_and_failures_in_words(qapp):
    got, bad = [], []
    t = TransferThread(lambda progress: [progress(i, 1000, "Uploading") for i in range(0, 1001, 5)] and "ok")
    t.progress.connect(lambda pct, label: got.append(pct))
    t.start()
    t.wait()
    qapp.processEvents()
    assert got == sorted(set(got)) and got[-1] == 100 and len(got) <= 101  # not one signal per chunk

    def boom(progress):
        raise RuntimeError("The connection dropped")

    f = TransferThread(boom)
    f.failed.connect(bad.append)
    f.start()
    f.wait()
    qapp.processEvents()
    assert bad == ["The connection dropped"]


def test_uploading_from_the_screen_runs_in_the_background_and_refreshes(qapp, fake, monkeypatch, dialogs, tmp_path):
    photos = []
    for i in range(9):
        p = tmp_path / f"{i}.jpg"
        p.write_bytes(b"j")
        photos.append(str(p))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: (photos, "")))
    monkeypatch.setattr(ScanOptionsDialog, "exec", lambda self: 1)
    uploaded = []
    monkeypatch.setattr(RestorationService, "upload_capture", lambda self, rid, kind, paths, params, progress: (progress(1, 2, "Uploading 1 of 9"), uploaded.append((rid, kind, len(paths), params)), {"status": "uploaded"})[-1])
    s = RestorationScreen()
    s.refresh_data()
    select(s, 1)
    s.photos_btn.click()
    assert not s.photos_btn.isEnabled()  # busy while it runs
    s._thread.wait()
    qapp.processEvents()
    assert uploaded == [("r1", "photos", 9, {"real_width_mm": None, "quality": "normal", "gcode": False, "shape": "relief"})]
    assert s.photos_btn.isEnabled() and not s.bar.isVisibleTo(s)
    assert dialogs[-1][0] == "information" and "workshop PC" in dialogs[-1][2]


def test_too_few_photos_for_a_full_object_are_refused_before_anything_is_sent(qapp, fake, monkeypatch, dialogs, tmp_path):
    only = tmp_path / "a.jpg"
    only.write_bytes(b"j")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([str(only)], "")))
    monkeypatch.setattr(ScanOptionsDialog, "exec", lambda self: (self.shape.setCurrentIndex(self.shape.findData("full")), 1)[1])
    s = RestorationScreen()
    s.refresh_data()
    select(s, 1)
    s.photos_btn.click()
    assert dialogs[-1][0] == "warning" and "at least 8" in dialogs[-1][2] and s._thread is None


def test_one_photo_is_enough_for_a_flat_carving(qapp, fake, monkeypatch, dialogs, tmp_path):
    only = tmp_path / "a.jpg"
    only.write_bytes(b"j")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([str(only)], "")))
    monkeypatch.setattr(ScanOptionsDialog, "exec", lambda self: 1)  # flat carving is the default
    sent = []
    monkeypatch.setattr(RestorationService, "upload_capture", lambda self, rid, kind, paths, params, progress: sent.append((len(paths), params["shape"])) or {})
    s = RestorationScreen()
    s.refresh_data()
    select(s, 1)
    s.photos_btn.click()
    s._thread.wait()
    qapp.processEvents()
    assert sent == [(1, "relief")]


def test_saving_a_result_downloads_it_in_the_background(qapp, fake, monkeypatch, dialogs, tmp_path):
    dest = str(tmp_path / "out.glb")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (dest, "")))
    got = []
    monkeypatch.setattr(RestorationService, "download_file", lambda self, rid, fid, d, progress: got.append((rid, fid, d)) or d)
    s = RestorationScreen()
    s.refresh_data()
    select(s, 1)
    s.files.cellWidget(0, s.FCOL_SAVE).click()
    s._thread.wait()
    qapp.processEvents()
    assert got == [("r1", "f1", dest)] and dialogs[-1][0] == "information" and "Saved to" in dialogs[-1][2]
