"""Desktop notifications: what counts as new, the pop-up rules, the bell, and opening the right screen."""

import pytest
from PyQt6.QtWidgets import QDialog, QMainWindow

import ui.notifier as notifier_module
from services import notifications_service as ns
from services.enums import UserRole
from services.session import Session
from ui.main_window import MainWindow
from ui.notifier import Notifier, NotificationsDialog


def note(id_, title="Title", body="Body", screen="orders", at="2026-10-28T10:00:00+00:00"):
    return {"id": id_, "kind": "order_web", "title": title, "body": body, "created_at": at, "screen": screen, "target_id": None}


def feed(*items, at="2026-10-28T10:01:00+00:00"):
    return {"server_time": at, "items": list(items)}


# --------------------------------------------------------------- the bookkeeping
def test_only_what_has_not_been_seen_is_new_and_nothing_repeats():
    state = ns.load_state(ns.Path("nope-does-not-exist.json"))
    first = ns.absorb(state, feed(note("a"), note("b")))
    assert [n["id"] for n in first] == ["a", "b"] and state["since"] == "2026-10-28T10:01:00+00:00"
    again = ns.absorb(state, feed(note("b"), note("c"), at="2026-10-28T10:02:00+00:00"))
    assert [n["id"] for n in again] == ["c"] and state["unread"] == 3
    assert [n["id"] for n in state["recent"]] == ["c", "b", "a"]  # newest first
    assert ns.absorb(state, feed(at="2026-10-28T10:03:00+00:00")) == [] and state["since"].endswith("10:03:00+00:00")


def test_the_list_and_the_memory_are_bounded():
    state = ns.load_state(ns.Path("nope-does-not-exist.json"))
    ns.absorb(state, feed(*[note(f"n{i}") for i in range(400)]))
    assert len(state["recent"]) == ns.KEEP_RECENT and state["unread"] == ns.KEEP_RECENT and len(state["seen"]) == ns.KEEP_SEEN


def test_the_state_survives_a_restart_and_a_damaged_file_starts_fresh(tmp_path):
    path = tmp_path / "data" / "notifications-u1.json"
    state = ns.load_state(path)
    ns.absorb(state, feed(note("a")))
    ns.save_state(state, path)
    assert ns.load_state(path)["seen"] == ["a"] and ns.load_state(path)["since"]
    path.write_text("{not json", encoding="utf-8")
    assert ns.load_state(path) == ns.load_state(tmp_path / "missing.json")


def test_each_user_has_their_own_file(monkeypatch):
    monkeypatch.setattr(Session, "get_user_id", classmethod(lambda cls: "u-1"))
    assert ns.state_path().name == "notifications-u-1.json"
    monkeypatch.setattr(Session, "get_user_id", classmethod(lambda cls: None))
    assert ns.state_path().name == "notifications-anyone.json"


def test_the_pop_up_text():
    one = ns.popup_text([note("a", "New website order ORD-1", "Meena, Rs. 4,500.00")])
    assert one == ("New website order ORD-1", "Meena, Rs. 4,500.00")
    three = ns.popup_text([note("a", "One"), note("b", "Two"), note("c", "Three")])
    assert three == ("3 new notifications", "One\nTwo\nThree")
    many = ns.popup_text([note(str(i), f"T{i}") for i in range(5)])
    assert many[0] == "5 new notifications" and many[1].endswith("and 2 more")


# ------------------------------------------------------------------ the notifier
class FakeTray:
    available = True
    shown = []

    class MessageIcon:
        Information = 1

    def __init__(self, icon, parent=None):
        self.clicked = []
        FakeTray.instance = self

    @staticmethod
    def isSystemTrayAvailable():
        return FakeTray.available

    def setToolTip(self, text):
        pass

    @property
    def messageClicked(self):
        outer = self

        class Sig:
            def connect(self, fn):
                outer.on_click = fn

        return Sig()

    def show(self):
        pass

    def showMessage(self, title, body, icon, ms):
        FakeTray.shown.append((title, body))


@pytest.fixture
def window(qapp):
    return QMainWindow()


@pytest.fixture
def tray(monkeypatch):
    FakeTray.shown, FakeTray.available = [], True
    monkeypatch.setattr(notifier_module, "QSystemTrayIcon", FakeTray)
    return FakeTray


def make(window, tmp_path):
    return Notifier(window, service=object(), state_path=tmp_path / "n.json")


def test_a_new_thing_pops_up_when_the_window_is_not_in_front(window, tray, tmp_path, monkeypatch):
    n = make(window, tmp_path)
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    changes = []
    n.changed.connect(lambda: changes.append(n.unread))
    n.receive(feed(note("a", "New website order ORD-1", "Meena, Rs. 4,500.00")))
    assert tray.shown == [("New website order ORD-1", "Meena, Rs. 4,500.00")] and changes == [1]
    n.receive(feed(note("a")))  # the same thing again
    assert len(tray.shown) == 1 and n.unread == 1


def test_no_pop_up_when_they_are_already_looking_or_switched_it_off_or_there_is_no_tray(window, tray, tmp_path, monkeypatch):
    n = make(window, tmp_path)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    n.receive(feed(note("a", "Seen at once")))
    assert tray.shown == [] and window.statusBar().currentMessage() == "Seen at once"
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    n.set_popups(False)
    n.receive(feed(note("b")))
    n.set_popups(True)
    tray.available = False
    n.receive(feed(note("c")))
    assert tray.shown == [] and n.unread == 3  # still counted and listed


def test_clicking_a_single_pop_up_opens_its_screen_and_a_group_opens_the_list(window, tray, tmp_path, monkeypatch):
    n = make(window, tmp_path)
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    opened, lists = [], []
    n.open_screen.connect(opened.append)
    monkeypatch.setattr(n, "show_list", lambda: lists.append(1))
    n.receive(feed(note("a", screen="stock")))
    tray.instance.on_click()
    assert opened == ["stock"] and not lists
    n.receive(feed(note("b"), note("c")))
    tray.instance.on_click()
    assert lists == [1]


def test_the_first_poll_without_since_shows_nothing_and_remembers_where_to_start(window, tray, tmp_path):
    n = make(window, tmp_path)
    n.receive({"server_time": "2026-10-28T09:00:00+00:00", "items": []})
    assert n.state["since"] == "2026-10-28T09:00:00+00:00" and n.unread == 0 and tray.shown == []


def test_opening_the_list_marks_everything_read_and_a_choice_is_remembered(window, tmp_path, monkeypatch):
    n = make(window, tmp_path)
    n.receive(feed(note("a", "First"), note("b", "Second", screen="stock")))
    assert n.unread == 2
    dialog = NotificationsDialog(window, n)
    assert [dialog.list.item(i).text().split("\n")[0] for i in range(dialog.list.count())] == ["Second", "First"]
    assert dialog.empty.isHidden()
    opened = []
    n.open_screen.connect(opened.append)
    dialog._open(dialog.list.item(0))
    assert opened == ["stock"]
    n.mark_read()
    assert n.unread == 0
    dialog.popups.setChecked(False)
    assert ns.load_state(tmp_path / "n.json")["popups"] is False and ns.load_state(tmp_path / "n.json")["unread"] == 0
    assert NotificationsDialog(window, make(window, tmp_path)).popups.isChecked() is False  # survives a restart


def test_an_empty_list_says_what_to_expect(window, tmp_path):
    assert not NotificationsDialog(window, make(window, tmp_path)).empty.isHidden()


# ----------------------------------------------------------------- the main window
def main_window(qapp, monkeypatch, tmp_path, role=UserRole.OWNER):
    monkeypatch.setattr(Session, "_role", role)
    monkeypatch.setattr(ns, "state_path", lambda: tmp_path / "n.json")
    w = MainWindow()
    w._sync_timer.stop()
    return w


def test_the_bell_shows_how_many_are_unread(qapp, monkeypatch, tmp_path):
    w = main_window(qapp, monkeypatch, tmp_path)
    assert w.bell_btn.text() == "🔔  Notifications"
    w.notifier.receive(feed(note("a"), note("b")))
    assert w.bell_btn.text() == "🔔  Notifications  (2)"
    w.notifier.mark_read()
    assert w.bell_btn.text() == "🔔  Notifications"


def test_a_notification_opens_the_screen_it_is_about(qapp, monkeypatch, tmp_path):
    w = main_window(qapp, monkeypatch, tmp_path)
    monkeypatch.setattr(w, "_refresh_current", lambda: None)
    w.notifier.open_screen.emit("orders")
    assert w.content_stack.currentWidget() is w.orders_view
    w.notifier.open_screen.emit("stock")
    assert w.content_stack.currentWidget() is w.inventory_view
    w.notifier.open_screen.emit("restoration")
    assert w.content_stack.currentWidget() is w.restoration_view
    w.notifier.open_screen.emit("somewhere-new")  # an unknown screen is ignored
    assert w.content_stack.currentWidget() is w.restoration_view


def test_a_screen_the_user_does_not_have_is_not_opened(qapp, monkeypatch, tmp_path):
    w = main_window(qapp, monkeypatch, tmp_path, UserRole.SALES)  # sales has no Restoration
    monkeypatch.setattr(w, "_refresh_current", lambda: None)
    before = w.content_stack.currentWidget()
    w.notifier.open_screen.emit("restoration")
    assert w.content_stack.currentWidget() is before


def test_signing_out_stops_the_polling(qapp, monkeypatch, tmp_path, dialogs):
    import ui.login_window as login

    class StubLogin:
        def show(self):
            pass

    monkeypatch.setattr(login, "LoginWindow", StubLogin)
    w = main_window(qapp, monkeypatch, tmp_path)
    w.notifier._timer.start(60_000)
    w._on_session_expired()
    assert not w.notifier._timer.isActive()
