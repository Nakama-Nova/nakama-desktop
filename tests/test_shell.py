"""The window's shell: top bar, connection chip, account menu, Go to, folding sidebar."""

import time

from PyQt6.QtWidgets import QPushButton

from services import api_client
from ui.components.goto_dialog import GoToDialog
from ui.components.navbar import connection_text
from ui.main_window import MainWindow


def window(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    return w


def test_connection_text_tells_the_counter_nothing_is_lost():
    assert connection_text(True, 0) == "Online"
    assert connection_text(True, 2) == "Online, sending 2 bills"
    assert connection_text(False, 1) == "Offline, 1 bill waiting to send"
    assert connection_text(False, 3) == "Offline, 3 bills waiting to send"
    assert connection_text(False, 0) == "Offline, bills are kept on this PC"


def test_the_chip_follows_the_server_state(qapp, monkeypatch):
    w = window(qapp)
    monkeypatch.setattr(api_client, "_down_until", time.monotonic() + 60)
    w._refresh_connection()
    assert w.navbar.conn_lbl.text().endswith("bills are kept on this PC") or "waiting to send" in w.navbar.conn_lbl.text()
    monkeypatch.setattr(api_client, "_down_until", 0.0)
    w._refresh_connection()
    assert "Online" in w.navbar.conn_lbl.text()
    w.close()


def test_the_account_menu_holds_password_and_sign_out(qapp):
    w = window(qapp)
    assert w.role_badge.text() == "Owner"
    assert [a.text() for a in w.navbar.account_menu.actions() if a.text()] == ["Settings", "Change my password", "Sign out"]
    w.close()


def test_go_to_filters_and_picks_a_screen(qapp):
    entries = [("Home", 0), ("Stock", 2), ("Wages", 11)]
    d = GoToDialog(entries)
    assert d.list.count() == 3
    d.search.setText("wag")
    assert [d.list.item(i).text() for i in range(d.list.count())] == ["Wages"]
    d._pick(d.list.item(0))
    assert d.chosen == 11
    d.search.setText("zzz")
    assert d.list.count() == 0 and not d.empty.isHidden()


def test_a_section_folds_and_reopens_when_you_go_to_one_of_its_pages(qapp):
    w = window(qapp)
    w.resize(1500, 900)  # wide enough for the full sidebar; a narrow window shows icons only
    w.show()
    stock_btn = w._nav_mapping[2]
    assert stock_btn.isVisible()
    w._toggle_group("Stock and buying")
    assert not stock_btn.isVisible()
    w._switch_page(2, refresh=False)  # opening a page in a folded section unfolds it
    assert stock_btn.isVisible()
    w.close()


def test_the_page_headings_are_buttons_in_sentence_case(qapp):
    w = window(qapp)
    names = [b.property("section") for b in w.nav_scroll.widget().findChildren(QPushButton) if b.property("section")]
    assert names[0] == "Selling" and "Stock and buying" in names
    assert all(n == n[0].upper() + n[1:].lower() for n in names)
    w.close()
