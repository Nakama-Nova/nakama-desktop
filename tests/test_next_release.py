"""Known-buyer note, quick-add chips, the top bar's person, and the settings that back them."""

from PyQt6.QtWidgets import QLabel, QPushButton

from services import app_settings
from services.sales_service import SalesService
from ui.icons import avatar_pixmap, initials
from ui.sales_screen import CartItem, SalesScreen

ITEMS = [
    {"id": "i1", "name": "Ganesha temple panel, teak, 4 ft", "selling_price": 1000, "gst_percent": 12, "current_stock": 5},
    {"id": "i2", "name": "Brass lamp stand, 5 ft", "selling_price": 100, "gst_percent": 12, "current_stock": 9},
    {"id": "i3", "name": "Pooja mandap", "selling_price": 500, "gst_percent": 12, "current_stock": 2},
]


def _wait(condition, seconds=3.0):
    """Let the event loop run until the condition holds (the buyer lookup answers from a worker thread)."""
    import time

    from PyQt6.QtCore import QCoreApplication

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False



def screen_with_items(qapp):
    s = SalesScreen()
    s._apply_items(ITEMS)
    return s


# ------------------------------------------------------------------ known buyer
def test_a_found_buyer_is_a_line_under_the_fields_not_a_pop_up(qapp, monkeypatch):
    s = screen_with_items(qapp)
    s.phone_input.setText("98450 12345")
    monkeypatch.setattr(s._customer_service, "search_by_phone", lambda p: {"id": "c1", "name": "Lakshmi Interiors"})
    monkeypatch.setattr("ui.sales_screen.run_async", lambda fn, ok, err: None)  # the count is tested below
    boxes = []
    monkeypatch.setattr("ui.sales_screen.QMessageBox.information", lambda *a, **k: boxes.append(a))
    s._handle_customer_lookup()
    assert _wait(lambda: s.customer_input.text() == "Lakshmi Interiors")
    assert s.buyer_note.text() == "Lakshmi Interiors is already a buyer." and not boxes


def test_the_note_gains_the_number_of_earlier_bills(qapp):
    s = screen_with_items(qapp)
    s.phone_input.setText("98450 12345")
    sales = [{"order_status": "completed"}, {"order_status": "completed"}, {"order_status": "cancelled"}]
    s._show_history("Lakshmi Interiors", "98450 12345", sales)
    assert s.buyer_note.text() == "Lakshmi Interiors is already a buyer, with 2 earlier bills."
    s._show_history("Lakshmi Interiors", "98450 12345", [{"order_status": "completed"}])
    assert "1 earlier bill." in s.buyer_note.text()
    s._show_history("Lakshmi Interiors", "98450 12345", [])
    assert "no earlier bills" in s.buyer_note.text()


def test_a_late_answer_for_a_different_buyer_is_ignored(qapp):
    s = screen_with_items(qapp)
    s.phone_input.setText("11111")
    s._show_history("Someone else", "99999", [{"order_status": "completed"}])
    assert s.buyer_note.isHidden()


def test_an_unknown_number_says_a_new_buyer_will_be_saved(qapp, monkeypatch):
    s = screen_with_items(qapp)
    s.phone_input.setText("98450 12345")
    monkeypatch.setattr(s._customer_service, "search_by_phone", lambda p: None)
    s._handle_customer_lookup()
    assert _wait(lambda: "saved as a new buyer" in s.buyer_note.text())


def test_clearing_the_bill_clears_the_note(qapp):
    s = screen_with_items(qapp)
    s._note("Someone is already a buyer.", "good")
    s.clear_btn.click()
    assert s.buyer_note.isHidden()


# ------------------------------------------------------------------ quick-add chips
def chips(s):
    return [b.toolTip() for b in s.recent_row.findChildren(QPushButton)]


def test_no_chips_until_something_has_been_sold_here(qapp):
    s = screen_with_items(qapp)
    assert s.recent_row.isHidden()


def test_an_added_item_becomes_a_chip_newest_first_and_is_not_repeated(qapp):
    s = screen_with_items(qapp)
    s._add_item(ITEMS[0])
    s._add_item(ITEMS[1])
    s._add_item(ITEMS[0])  # again: moves to the front, no duplicate
    assert not s.recent_row.isHidden()
    assert chips(s) == ["Add Ganesha temple panel, teak, 4 ft", "Add Brass lamp stand, 5 ft"]
    assert app_settings.get("recent_items") == ["i1", "i2"]


def test_a_chip_adds_that_product_to_the_bill(qapp):
    s = screen_with_items(qapp)
    s._add_item(ITEMS[1])
    s._cart.clear()
    s._refresh_table()
    s.recent_row.findChildren(QPushButton)[0].click()
    assert [c.name for c in s._cart] == ["Brass lamp stand, 5 ft"]


def test_only_the_last_five_are_kept(qapp):
    many = [{"id": f"x{n}", "name": f"Item {n}", "selling_price": 1, "gst_percent": 0, "current_stock": 9} for n in range(8)]
    s = SalesScreen()
    s._apply_items(many)
    for item in many:
        s._add_item(item)
    assert app_settings.get("recent_items") == ["x7", "x6", "x5", "x4", "x3"]
    assert len(chips(s)) == 5


def test_a_product_that_no_longer_exists_is_just_left_out(qapp):
    app_settings.set_value("recent_items", ["gone", "i2"])
    s = screen_with_items(qapp)
    assert chips(s) == ["Add Brass lamp stand, 5 ft"]


def test_recent_items_must_be_a_list_of_text():
    app_settings.save({"recent_items": [1, 2]})
    assert app_settings.get("recent_items") == []
    app_settings.save({"recent_items": ["a", "b"]})
    assert app_settings.get("recent_items") == ["a", "b"]


# ------------------------------------------------------------------ the person in the top bar
def test_initials():
    assert initials("Chaithanya M") == "CM"
    assert initials("Meena") == "ME"
    assert initials("  anil  kumar  rao ") == "AK"
    assert initials("") == "?" and initials(None) == "?"
    assert initials("k.s_mani") == "KS"


def test_the_avatar_is_a_round_coloured_badge(qapp):
    px = avatar_pixmap("CM", "#5A2A06", "#FFF3DC", 28, 1.0).toImage()
    assert px.pixelColor(14, 3).name() == "#5a2a06" or px.pixelColor(14, 6).name() == "#5a2a06"  # teak inside the circle
    assert px.pixelColor(0, 0).alpha() == 0  # the corner is outside the circle


def test_the_top_bar_shows_the_name_once_the_server_says_it(qapp):
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    assert w.role_badge.text() == "Owner"  # just the role until the name is known (and when offline)
    w.navbar.set_person("Chaithanya M")
    assert w.role_badge.text() == "Chaithanya  ·  Owner" and not w.role_badge.icon().isNull()
    assert w.role_badge.toolTip() == "Chaithanya M, Owner"
    w.navbar.set_person("")  # an empty answer changes nothing
    assert w.role_badge.text() == "Chaithanya  ·  Owner"
    w.close()


# ------------------------------------------------------------------ extra roles shown and kept
ROLES = [("Accountant", "accountant"), ("Manager", "manager")]
PLACES = [{"id": "p1", "name": "Shop"}, {"id": "p2", "name": "Carving unit"}]
USER = {"id": "u1", "username": "meena", "full_name": "Meena"}


def test_the_service_returns_current_extra_roles(monkeypatch):
    from services.iam_service import IamService

    svc = IamService()
    monkeypatch.setattr(svc._api, "_get", lambda path, token, **k: {"user_id": "u1", "roles": [{"role_key": "accountant", "plant_unit_id": None}]})
    assert svc.user_roles("u1") == [{"role_key": "accountant", "plant_unit_id": None}]


def test_the_service_says_not_known_for_an_old_or_unreachable_server(monkeypatch):
    import requests

    from services.api_client import APIError
    from services.iam_service import IamService

    svc = IamService()

    def old(path, token, **k):
        raise APIError(404, "Not Found")

    monkeypatch.setattr(svc._api, "_get", old)
    assert svc.user_roles("u1") is None

    def down(path, token, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(svc._api, "_get", down)
    assert svc.user_roles("u1") is None


def test_the_dialog_starts_with_the_roles_the_person_already_has(qapp):
    from ui.staff_screen import ExtraRolesDialog

    d = ExtraRolesDialog(None, USER, ROLES, PLACES, current=[
        {"role_key": "accountant", "plant_unit_id": None},
        {"role_key": "manager", "plant_unit_id": "p2"},
    ])
    assert d.assignments() == [
        {"role_key": "accountant", "plant_unit_id": None},
        {"role_key": "manager", "plant_unit_id": "p2"},
    ]
    assert "extra roles they have now" in d.findChildren(QLabel)[0].text()


def test_saving_without_touching_anything_keeps_the_roles(qapp):
    from ui.staff_screen import ExtraRolesDialog

    held = [{"role_key": "manager", "plant_unit_id": "p1"}]
    assert ExtraRolesDialog(None, USER, ROLES, PLACES, current=held).assignments() == held


def test_removing_a_row_removes_that_role_only(qapp):
    from ui.staff_screen import ExtraRolesDialog

    d = ExtraRolesDialog(None, USER, ROLES, PLACES, current=[
        {"role_key": "accountant", "plant_unit_id": None},
        {"role_key": "manager", "plant_unit_id": None},
    ])
    d._rows[0][0].parentWidget()  # rows exist
    from PyQt6.QtWidgets import QPushButton

    drop = [b for b in d.findChildren(QPushButton) if b.text() == ""][0]  # the first row's remove button
    drop.click()
    assert [a["role_key"] for a in d.assignments()] == ["manager"]


def test_a_role_or_place_the_lists_do_not_name_is_kept_not_dropped(qapp):
    from ui.staff_screen import ExtraRolesDialog

    held = [{"role_key": "night_watch", "plant_unit_id": "p9"}]
    assert ExtraRolesDialog(None, USER, ROLES, PLACES, current=held).assignments() == held


def test_when_the_server_cannot_say_the_dialog_starts_empty_and_warns(qapp):
    from PyQt6.QtWidgets import QLabel

    from ui.staff_screen import ExtraRolesDialog

    d = ExtraRolesDialog(None, USER, ROLES, PLACES, current=None)
    assert d.assignments() == []
    assert "cannot show the extra roles" in d.findChildren(QLabel)[0].text() and "replaces" in d.findChildren(QLabel)[0].text()
