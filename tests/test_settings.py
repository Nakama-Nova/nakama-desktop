"""This computer's settings: the file, the server address, the dialog, and what each one changes."""

import json

import pytest
from PyQt6.QtWidgets import QMessageBox

from services import app_settings
from ui.settings_dialog import SettingsDialog
from conftest import create_bill


# ------------------------------------------------------------------ the settings file
def test_defaults_when_there_is_no_file():
    assert app_settings.load() == app_settings.DEFAULTS
    assert app_settings.get("default_payment") == "cash"


def test_a_saved_setting_is_kept():
    app_settings.set_value("open_bill_pdf", False)
    app_settings.set_value("default_payment", "none")
    assert app_settings.get("open_bill_pdf") is False and app_settings.get("default_payment") == "none"
    assert json.loads(app_settings.settings_path().read_text())["auto_updates"] is True  # the rest is kept too


def test_wrong_or_unknown_values_are_ignored():
    app_settings.save({"default_payment": "bitcoin", "open_bill_pdf": "yes", "colour": "red"})
    assert app_settings.load() == app_settings.DEFAULTS
    assert "colour" not in json.loads(app_settings.settings_path().read_text())


def test_a_damaged_file_never_breaks_the_program():
    path = app_settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert app_settings.load() == app_settings.DEFAULTS
    path.write_text(json.dumps(["a list"]), encoding="utf-8")
    assert app_settings.load() == app_settings.DEFAULTS
    path.write_text(json.dumps({"open_bill_pdf": False, "default_payment": 7}), encoding="utf-8")
    assert app_settings.load()["open_bill_pdf"] is False and app_settings.load()["default_payment"] == "cash"


# ------------------------------------------------------------------ server address
@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://api.example.com", "https://api.example.com"),
        ("  https://api.example.com/  ", "https://api.example.com"),
        ("http://192.168.1.20:8000", "http://192.168.1.20:8000"),
        ("api.example.com", None),
        ("ftp://api.example.com", None),
        ("https://", None),
        ("https://has space.com", None),
        ("", None),
    ],
)
def test_the_address_must_be_http_or_https(text, expected):
    assert app_settings.clean_server_address(text) == expected


def test_writing_the_address_keeps_the_other_lines(tmp_path):
    app_settings.env_path().write_text("OTHER=1\nAPI_BASE_URL=http://old:8000\nMORE=2\n", encoding="utf-8")
    app_settings.write_server_address("https://api.example.com/")
    lines = app_settings.env_path().read_text().splitlines()
    assert lines == ["OTHER=1", "API_BASE_URL=https://api.example.com", "MORE=2"]
    assert app_settings.read_server_address() == "https://api.example.com"


def test_writing_the_address_creates_the_file_when_there_is_none():
    assert not app_settings.env_path().exists()
    app_settings.write_server_address("https://api.example.com")
    assert app_settings.env_path().read_text().strip() == "API_BASE_URL=https://api.example.com"


def test_a_bad_address_is_refused_before_anything_is_written():
    with pytest.raises(ValueError):
        app_settings.write_server_address("not an address")
    assert not app_settings.env_path().exists()


def test_plain_http_to_another_machine_is_flagged_but_this_machine_is_not():
    assert app_settings.is_unencrypted_remote("http://192.168.1.20:8000")
    assert app_settings.is_unencrypted_remote("http://api.example.com")
    assert not app_settings.is_unencrypted_remote("https://api.example.com")
    assert not app_settings.is_unencrypted_remote("http://127.0.0.1:8000")
    assert not app_settings.is_unencrypted_remote("http://localhost:8000")


# ------------------------------------------------------------------ the dialog
class FakeNotifier:
    def __init__(self, on=True):
        self.state = {"popups": on}
        self.calls = []

    def set_popups(self, on):
        self.calls.append(on)
        self.state["popups"] = on


class FakeUpdater:
    def __init__(self):
        self.auto, self.checked = [], 0

    def set_automatic(self, on):
        self.auto.append(on)

    def check(self, manual=False):
        self.checked += 1


def quiet(monkeypatch):
    shown = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, _n=name, **k: shown.append((_n, a[2]))))
    return shown


def test_the_dialog_starts_from_the_saved_settings(qapp):
    app_settings.save({"default_payment": "none", "open_bill_pdf": False})
    d = SettingsDialog(notifier=FakeNotifier(on=False), updater=FakeUpdater())
    assert d.payment.currentData() == "none" and not d.open_pdf.isChecked() and not d.popups.isChecked()


def test_saving_keeps_every_choice_and_tells_the_notifier_and_updater(qapp, monkeypatch):
    quiet(monkeypatch)
    n, u = FakeNotifier(), FakeUpdater()
    d = SettingsDialog(notifier=n, updater=u)
    d.payment.setCurrentIndex(d.payment.findData("none"))
    d.open_pdf.setChecked(False)
    d.popups.setChecked(False)
    d.auto_updates.setEnabled(True)  # a development copy has it greyed out; an installed one does not
    d.auto_updates.setChecked(False)
    d._save()
    saved = app_settings.load()
    assert saved["default_payment"] == "none" and saved["open_bill_pdf"] is False and saved["auto_updates"] is False
    assert n.calls == [False] and u.auto == [False]


def test_an_unchanged_server_address_does_not_ask_for_a_restart(qapp, monkeypatch):
    shown = quiet(monkeypatch)
    from services.api_client import BASE_URL

    d = SettingsDialog(notifier=FakeNotifier(), updater=FakeUpdater())
    d.server.setText(BASE_URL)
    d._save()
    assert not d.restart_needed and not shown and not app_settings.env_path().exists()


def test_a_new_server_address_is_written_and_a_restart_is_asked_for(qapp, monkeypatch):
    shown = quiet(monkeypatch)
    d = SettingsDialog(notifier=FakeNotifier(), updater=FakeUpdater())
    d.server.setText("https://api.example.com/")
    d._save()
    assert d.restart_needed and app_settings.read_server_address() == "https://api.example.com"
    assert shown and "starts" in shown[-1][1]


def test_a_bad_address_stops_the_save_and_says_why(qapp, monkeypatch):
    shown = quiet(monkeypatch)
    d = SettingsDialog(notifier=FakeNotifier(), updater=FakeUpdater())
    d.payment.setCurrentIndex(d.payment.findData("none"))
    d.server.setText("api.example.com")
    d._save()
    assert shown and "http://" in shown[-1][1]
    assert app_settings.get("default_payment") == "cash"  # nothing was kept


def test_the_note_under_the_address_follows_what_is_typed(qapp):
    d = SettingsDialog()
    d.server.setText("api.example.com")
    assert "must start with" in d.server_note.text()
    d.server.setText("http://192.168.1.20:8000")
    assert "not encrypted" in d.server_note.text()
    d.server.setText("https://api.example.com")
    assert "restart" in d.server_note.text()


def test_test_connection_reports_both_outcomes(qapp, monkeypatch):
    shown = quiet(monkeypatch)
    from services.api_client import APIClient

    d = SettingsDialog()
    d.server.setText("https://api.example.com")
    monkeypatch.setattr(APIClient, "health_check", lambda self: True)
    d._test_connection()
    assert shown[-1][0] == "information" and "Connected" in shown[-1][1]
    monkeypatch.setattr(APIClient, "health_check", lambda self: False)
    d._test_connection()
    assert shown[-1][0] == "warning" and "Could not reach" in shown[-1][1]
    assert d.test_btn.isEnabled() and d.test_btn.text() == "Test connection"


def test_check_now_asks_the_updater(qapp):
    u = FakeUpdater()
    d = SettingsDialog(notifier=FakeNotifier(), updater=u)
    d.check_btn.click()
    assert u.checked == 1


# ------------------------------------------------------------------ what the settings change
def test_new_bill_starts_as_the_chosen_payment(qapp):
    from ui.sales_screen import CartItem, SalesScreen

    app_settings.set_value("default_payment", "none")
    s = SalesScreen()
    assert s.pay_pick.currentText() == "Not paid yet"
    s.pay_pick.setCurrentIndex(0)
    s._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    s.clear_btn.click()
    assert s.pay_pick.currentText() == "Not paid yet"  # Clear goes back to the chosen start

    app_settings.set_value("default_payment", "cash")
    s.apply_settings()
    assert s.pay_pick.currentText() == "Cash"  # an empty bill follows a new setting at once


def test_a_bill_in_progress_keeps_its_payment_when_settings_change(qapp):
    from ui.sales_screen import CartItem, SalesScreen

    s = SalesScreen()
    s._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    s.pay_pick.setCurrentIndex(s.pay_pick.findText("UPI"))
    app_settings.set_value("default_payment", "none")
    s.apply_settings()
    assert s.pay_pick.currentText() == "UPI"


@pytest.mark.parametrize("open_it", [True, False])
def test_the_bill_pdf_opens_only_when_the_setting_says_so(qapp, monkeypatch, open_it):
    from services.customer_service import CustomerService
    from services.sales_service import SalesService
    from ui.sales_screen import CartItem, SalesScreen

    app_settings.set_value("open_bill_pdf", open_it)
    s = SalesScreen()
    s._cart = [CartItem("a", "Lamp", 100, 0, 1)]
    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    opened = []
    monkeypatch.setattr(SalesService, "is_online", lambda self: True)
    monkeypatch.setattr(CustomerService, "ensure_customer", lambda self, n, p: "cust-1")
    monkeypatch.setattr(SalesService, "create_sale", lambda self, items, **k: {"invoice_number": "INV-1"})
    monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: "bill.pdf")
    monkeypatch.setattr(SalesService, "open_pdf", staticmethod(lambda path: opened.append(path)))
    monkeypatch.setattr("ui.sales_screen.QMessageBox.information", lambda *a, **k: None)
    create_bill(s)
    assert opened == (["bill.pdf"] if open_it else [])


def test_the_updater_stays_quiet_when_background_checks_are_off(qapp, monkeypatch):
    from ui import updater as updater_module
    from ui.updater import UpdateBanner, Updater

    monkeypatch.setattr(updater_module, "is_release_build", lambda: True)
    from PyQt6.QtWidgets import QWidget

    win = QWidget()
    u = Updater(win, UpdateBanner())

    app_settings.set_value("auto_updates", False)
    u.start()
    assert not u._timer.isActive()

    u.set_automatic(True)  # turned on in Settings: starts now, without a restart
    assert u._timer.isActive()
    u.set_automatic(False)
    assert not u._timer.isActive()


def test_the_updater_does_nothing_in_a_development_copy(qapp, monkeypatch):
    from PyQt6.QtWidgets import QWidget

    from ui.updater import UpdateBanner, Updater

    u = Updater(QWidget(), UpdateBanner())
    u.set_automatic(True)
    assert not u._timer.isActive()  # a development copy never checks


def test_the_account_menu_and_ctrl_comma_open_settings_and_a_save_updates_new_bill(qapp, monkeypatch):
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    opened = []
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: opened.append(self) or 1)
    app_settings.set_value("default_payment", "none")
    w._open_settings()
    assert len(opened) == 1 and w.sales_view.pay_pick.currentText() == "Not paid yet"  # a save reached New Bill
    assert [a.text() for a in w.navbar.account_menu.actions() if a.text()][0] == "Settings"
    w.close()
