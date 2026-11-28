"""The dark theme: a palette applied before the screens are built, readable, reversible, chosen in Settings."""

import pytest
from PyQt6.QtWidgets import QMessageBox, QPushButton, QTableWidget, QWidget

from services import app_settings
from ui import theme
from ui.theme import DARK_PALETTE, LIGHT_PALETTE, ROLES, Colors, Theme, apply_theme, ink, native_dark_palette, soft


@pytest.fixture(autouse=True)
def back_to_light():
    """Every test starts and ends in the light theme, as the rest of the suite expects."""
    apply_theme("light")
    yield
    apply_theme("light")


def luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_dark_palette_only_names_colours_that_exist():
    assert set(DARK_PALETTE) <= set(LIGHT_PALETTE)  # a typo would silently do nothing


def test_applying_dark_changes_the_page_and_light_restores_it_exactly():
    apply_theme("dark")
    assert Colors.DARK_MODE and Colors.BG == "#1B130C" and Colors.CARD_BG == "#261B12"
    apply_theme("light")
    assert not Colors.DARK_MODE
    assert {k: getattr(Colors, k) for k in LIGHT_PALETTE} == LIGHT_PALETTE


def test_the_roles_and_button_styles_follow_the_theme():
    light_primary = Theme.btn("primary")
    apply_theme("dark")
    assert ROLES["primary"][0] == "#D9A441" and ROLES["primary"][1] == Colors.BRAND_DARK  # gold, with dark text
    assert Theme.btn("primary") != light_primary  # the cached light style was dropped
    apply_theme("light")
    assert Theme.btn("primary") == light_primary


@pytest.mark.parametrize(
    "text,ground",
    [
        ("TEXT_PRIMARY", "BG"),
        ("TEXT_PRIMARY", "CARD_BG"),
        ("TEXT_SECONDARY", "CARD_BG"),
        ("TEXT_MUTED", "CARD_BG"),
        ("SIDEBAR_TEXT", "SIDEBAR_BG"),
        ("SIDEBAR_ACTIVE_TEXT", "SIDEBAR_ACTIVE"),
        ("SIDEBAR_HEADING", "SIDEBAR_BG"),
        ("GREEN", "CARD_BG"),
        ("ORANGE", "CARD_BG"),
        ("RED", "CARD_BG"),
        ("BRAND_BROWN", "SIDEBAR_BG"),  # the brand name in the sidebar
    ],
)
def test_dark_text_is_readable_on_its_ground(text, ground):
    apply_theme("dark")
    assert contrast(getattr(Colors, text), getattr(Colors, ground)) >= 4.5, (text, ground)


def test_the_gold_primary_button_is_readable():
    apply_theme("dark")
    base, on_base = ROLES["primary"]
    assert contrast(base, on_base) >= 7


def test_soft_and_ink_suit_the_surface():
    light_chip = soft("#2B7149")
    apply_theme("dark")
    dark_chip = soft("#2B7149")
    assert luminance(light_chip) > 0.6 and luminance(dark_chip) < 0.1  # pale on a light page, deep on a dark one
    assert contrast(ink("#2B7149"), dark_chip) >= 4.5


def test_the_native_palette_matches_so_message_boxes_and_menus_are_dark(qapp):
    from PyQt6.QtGui import QPalette

    apply_theme("dark")
    p = native_dark_palette()
    assert p.color(QPalette.ColorRole.Window).name() == "#1b130c"
    assert p.color(QPalette.ColorRole.Text).name() == "#f4e9d6"


def test_a_widget_in_a_table_cell_no_longer_paints_the_page_colour(qapp):
    t = QTableWidget(1, 1)
    box = QWidget()
    t.setCellWidget(0, 0, box)
    assert "QWidget { background: transparent; }" in box.styleSheet()
    t.setCellWidget(0, 0, box)  # putting it in again does not stack the rule
    assert box.styleSheet().count("background: transparent") == 1


def test_a_cell_widget_keeps_the_look_it_brings(qapp):
    t = QTableWidget(1, 1)
    button = QPushButton("x")
    button.setStyleSheet("QPushButton { background: #FF0000; }")
    t.setCellWidget(0, 0, button)
    assert button.styleSheet().endswith("QPushButton { background: #FF0000; }")  # its own rule comes last, so it wins


def test_pills_are_deep_tints_on_a_dark_page(qapp):
    from PyQt6.QtWidgets import QTableWidgetItem

    from ui.components.pills import STOCK_TONES, PillDelegate

    def pill_pixel():
        t = QTableWidget(1, 1)
        t.setItemDelegateForColumn(0, PillDelegate(STOCK_TONES, t))
        t.setItem(0, 0, QTableWidgetItem("In stock"))
        t.resize(300, 120)
        t.show()
        image = t.viewport().grab().toImage()
        rect = t.visualItemRect(t.item(0, 0))
        colour = image.pixelColor(t.columnViewportPosition(0) + t.columnWidth(0) // 2, rect.center().y() - 9).name()
        t.close()
        return colour

    light = pill_pixel()
    apply_theme("dark")
    dark = pill_pixel()
    assert luminance(light) > 0.7 and luminance(dark) < 0.1


# ------------------------------------------------------------------ the setting
def test_theme_is_a_saved_choice_of_light_or_dark():
    assert app_settings.get("theme") == "light"
    app_settings.set_value("theme", "dark")
    assert app_settings.get("theme") == "dark"
    app_settings.save({"theme": "neon"})
    assert app_settings.get("theme") == "dark"  # an unknown look is ignored


def test_settings_offers_it_and_asks_for_a_restart_when_it_changes(qapp, monkeypatch):
    from ui.settings_dialog import SettingsDialog

    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a[2])))
    d = SettingsDialog()
    assert [d.theme.itemText(i) for i in range(d.theme.count())] == ["Light", "Dark", "Heritage glass"]
    assert d.theme.currentData() == "light"
    d.theme.setCurrentIndex(d.theme.findData("dark"))
    d._save()
    assert app_settings.get("theme") == "dark" and d.restart_needed
    assert shown and "look" in shown[-1] and "next time" in shown[-1]


def test_an_unchanged_look_does_not_ask_for_a_restart(qapp, monkeypatch):
    from ui.settings_dialog import SettingsDialog

    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: shown.append(a[2])))
    d = SettingsDialog()
    d._save()
    assert not d.restart_needed and not shown


def test_the_sign_in_brand_panel_stays_cream_in_the_dark_theme(qapp):
    from ui.login_window import LoginWindow

    apply_theme("dark")
    w = LoginWindow()
    sheet = w.findChild(QWidget, "brandPanel").styleSheet()
    assert "#FBF6EC" in sheet and "#F1E2C3" in sheet  # the logo and painted carvings are made for cream
    w.close()


def test_the_sidebar_logo_gets_a_light_plate_only_in_the_dark_theme(qapp):
    from ui.main_window import MainWindow

    light = MainWindow()
    light._sync_timer.stop()
    light._conn_timer.stop()
    assert "FBF6EC" not in light.logo_lbl.styleSheet()
    light.close()
    apply_theme("dark")
    dark = MainWindow()
    dark._sync_timer.stop()
    dark._conn_timer.stop()
    assert "#FBF6EC" in dark.logo_lbl.styleSheet()
    dark.close()


def test_theme_module_leaves_no_state_between_runs():
    assert theme.Colors.DARK_MODE is False  # the fixture put it back
