"""3D Lab screen: lists furniture, opens the Lab in the browser, role access."""

import pytest
from PyQt6.QtWidgets import QPushButton

import services.lab_service as lab_service_module
from services.enums import UserRole
from services.lab_service import LabService
from services.session import Session
from ui.lab_screen import LabScreen
from ui.main_window import MainWindow

CHAIR = {"id": "11111111-1111-1111-1111-111111111111", "name": "Dining Chair", "sku": "CH-1", "parts": 6, "sizes": ["S", "M", "L"]}
STOOL = {"id": "22222222-2222-2222-2222-222222222222", "name": "Stool", "sku": "ST-1", "parts": 0, "sizes": []}


@pytest.fixture
def opened(monkeypatch):
    """Record browser launches and fake the backend's answers."""
    urls, asked = [], []
    monkeypatch.setattr(lab_service_module.webbrowser, "open", lambda url: urls.append(url))
    monkeypatch.setattr(
        LabService, "list_furniture", lambda self: [CHAIR, STOOL]
    )

    def link(self, item_id, edit=False):
        asked.append((item_id, "edit" if edit else "view"))
        url = f"http://shop.invalid/lab/open?t=x&item={item_id}"
        lab_service_module.webbrowser.open(url)
        return url

    monkeypatch.setattr(LabService, "open", link)
    return urls, asked


def buttons(screen, row):
    return [b.text() for b in screen.table.cellWidget(row, screen.COL_ACTIONS).findChildren(QPushButton)]


def test_lists_furniture_with_parts_and_sizes(qapp, opened):
    s = LabScreen()
    s.refresh_data()
    assert s.table.rowCount() == 2
    assert s.table.item(0, s.COL_NAME).text() == "Dining Chair"
    assert s.table.item(0, s.COL_PARTS).text() == "6"
    assert s.table.item(0, s.COL_SIZES).text() == "Small, Medium, Large"
    assert s.table.item(1, s.COL_SIZES).text() == "Standard only"


def test_owner_can_open_and_edit(qapp, opened):
    urls, asked = opened
    s = LabScreen()  # logged in as owner (conftest)
    s.refresh_data()
    assert buttons(s, 0) == ["🧊 Open", "✏️ Edit parts"]
    assert s.setup_btn.isHidden() is False
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[0].click()
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[1].click()
    assert asked == [(CHAIR["id"], "view"), (CHAIR["id"], "edit")]
    assert len(urls) == 2 and "/lab/open?t=" in urls[0]


def test_achari_can_only_view(qapp, opened, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.ACHARI)
    s = LabScreen()
    s.refresh_data()
    assert buttons(s, 0) == ["🧊 Open"]
    assert s.setup_btn.isHidden() is True  # not shown: only owner/manager set pieces up


def test_a_failed_link_tells_the_user(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(LabService, "list_furniture", lambda self: [CHAIR])
    monkeypatch.setattr(LabService, "open", lambda self, item_id, edit=False: None)
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))
    s = LabScreen()
    s.refresh_data()
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[0].click()
    assert shown and "Could not open the Lab" in shown[0]


def test_link_is_requested_then_opened_in_the_browser(monkeypatch):
    calls = []

    class FakeApi:
        def create_lab_link(self, token, item_id, mode):
            calls.append((item_id, mode))
            return {"url": "http://shop.invalid/lab/open?t=abc", "path": "/lab/open?t=abc"}

    opened = []
    monkeypatch.setattr(lab_service_module.webbrowser, "open", lambda u: opened.append(u))
    svc = LabService(FakeApi())
    assert svc.open("abc-id") == "http://shop.invalid/lab/open?t=abc"
    assert svc.open("abc-id", edit=True)
    assert calls == [("abc-id", "view"), ("abc-id", "edit")]
    assert len(opened) == 2
    assert LabService(type("A", (), {"create_lab_link": lambda *a: None})()).open("x") is None


@pytest.mark.parametrize(
    "role,sees",
    [
        (UserRole.OWNER, True),
        (UserRole.MANAGER, True),
        (UserRole.ACHARI, True),
        (UserRole.WORKER, True),
        (UserRole.SALES, False),  # the backend refuses sales, so the menu hides it too
    ],
)
def test_who_sees_the_lab_in_the_menu(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    labels = [label for _, label, _ in w._get_allowed_nav_items()]
    assert ("3D Lab" in labels) is sees
