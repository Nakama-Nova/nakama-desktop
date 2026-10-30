"""The Bootstrap-style look: theme roles, components, brand images and empty states."""

import pathlib

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from ui.assets import carving_path, load_image, logo_path
from ui.components.bootstrap import Alert, Badge, Button, Card, Grid12
from ui.components.carvings import SETS, CarvingRow, attach_empty_state
from ui.theme import BUTTON_SIZES, ROLES, Colors, Theme

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _settle():
    for _ in range(5):
        QCoreApplication.processEvents()


def test_brand_colours_are_mapped_onto_bootstrap_roles():
    assert Colors.PRIMARY == Colors.BRAND_BROWN == "#5A2A06"
    assert Colors.SECONDARY == Colors.BRAND_GOLD == "#BF830B"
    assert Colors.LIGHT == "#FBF6EC"
    assert set(ROLES) >= {"primary", "secondary", "success", "danger", "warning", "info", "light", "dark"}


@pytest.mark.parametrize("role", list(ROLES))
@pytest.mark.parametrize("size", list(BUTTON_SIZES))
@pytest.mark.parametrize("outline", [False, True])
def test_every_button_variant_has_a_style_sheet(role, size, outline):
    css = Theme.btn(role, size, outline)
    assert "QPushButton:hover" in css and "QPushButton:disabled" in css


def test_legacy_helpers_still_work_and_unknown_roles_are_refused():
    for css in (Theme.btn_primary(), Theme.btn_secondary(), Theme.btn_danger(), Theme.btn_table_action(),
                Theme.btn_quick_action("#2F7D4F"), Theme.btn_quick_action("success")):
        assert "QPushButton" in css
    assert Colors.BRAND_BROWN.lower() in Theme.btn_primary().lower()
    with pytest.raises(ValueError):
        Theme.btn("nope")


def test_badge_alert_card_and_button_build(qapp):
    assert Badge("New", "success").text() == "New"
    assert Alert("Saved", "success").text() == "Saved"
    card = Card("Totals")
    assert card.header.text() == "Totals" and card.body is not None
    assert Button("Go", "danger", "lg", outline=True).text() == "Go"


def test_grid12_changes_its_spans_with_the_width(qapp):
    grid = Grid12()
    cards = [Card() for _ in range(4)]
    for c in cards:
        grid.add(c, lg=3, md=6, sm=12)

    def columns():
        return [grid._grid.getItemPosition(grid._grid.indexOf(c)) for c in cards]

    grid.show()
    grid.resize(1200, 100)
    _settle()
    assert grid.mode() == "lg" and {pos[0] for pos in columns()} == {0}  # four across
    grid.resize(800, 100)
    _settle()
    assert grid.mode() == "md" and {pos[0] for pos in columns()} == {0, 1}  # two by two
    grid.resize(500, 100)
    _settle()
    assert grid.mode() == "sm" and [pos[0] for pos in columns()] == [0, 1, 2, 3]  # stacked
    grid.close()


def test_logo_and_every_carving_ship_with_transparency():
    assert logo_path().exists() and logo_path(short=True).exists()
    for side, god in SETS.values():
        for name in (side, god):
            image = load_image(carving_path(name))
            assert not image.isNull(), name
            assert image.hasAlphaChannel(), name


def test_the_pair_faces_inward_around_the_god(qapp):
    row = CarvingRow("temple")
    row.resize(600, 300)
    left, god, right = row.layout_boxes()
    assert left[0] == right[0] and (left[1], right[1]) == (False, True)  # same carving, right one mirrored
    assert left[2].right() < god[2].left() < god[2].right() < right[2].left()
    assert god[2].height() > left[2].height()  # the god stands tallest


def test_the_pair_shrinks_to_fit_a_narrow_row(qapp):
    row = CarvingRow("temple")
    row.resize(200, 400)
    boxes = row.layout_boxes()
    assert boxes[0][2].left() >= -0.5 and boxes[2][2].right() <= 200.5


def test_empty_state_shows_over_an_empty_table_only(qapp):
    table = QTableWidget(0, 2)
    table.resize(600, 500)
    watcher = attach_empty_state(table, "No orders yet", "Orders appear here.")
    assert watcher.state is None  # nothing is built until the table is shown
    table.show()
    _settle()
    state = watcher.state
    assert state.isVisible() and state.title_lbl.text() == "No orders yet"

    table.setRowCount(1)
    table.setItem(0, 0, QTableWidgetItem("x"))
    _settle()
    assert not state.isVisible()

    table.setRowCount(0)
    _settle()
    assert state.isVisible()
    table.close()


def test_a_table_that_always_has_rows_never_builds_an_empty_state(qapp):
    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem("x"))
    watcher = attach_empty_state(table, "None", "")
    table.show()
    _settle()
    assert watcher.state is None
    table.close()


def test_main_window_has_a_navbar_with_the_page_title(qapp):
    from ui.main_window import MainWindow

    w = MainWindow()
    w._sync_timer.stop()
    assert w.navbar.title_lbl.text() == "Home"
    w._switch_page(15, refresh=False)
    assert w.navbar.title_lbl.text() == "Orders"
    assert not w.logo_lbl.pixmap().isNull()  # the logo is in the sidebar header
    assert w.role_badge.text() == "Owner"
    assert hasattr(w.orders_view.table, "viewport")
    w.close()


def test_login_window_uses_the_logo_and_stays_usable_on_a_small_screen(qapp):
    from ui.login_window import LoginWindow

    w = LoginWindow()
    assert not w.logo_lbl.pixmap().isNull()
    for size in ((1366, 700), (1920, 1040)):
        w.resize(*size)
        w.show()
        _settle()
        assert w.button.isVisible() and w.username.isVisible()
        assert w.carvings.height() >= 100
    w.close()


def test_new_screens_text_never_mentions_gst():
    from ui.main_window import EMPTY_STATES

    for title, hint, _ in EMPTY_STATES.values():
        assert "gst" not in (title + hint).lower()
    for path in (ROOT / "ui" / "login_window.py", ROOT / "ui" / "components" / "carvings.py"):
        assert "gst" not in path.read_text(encoding="utf-8").lower()


def test_the_installer_build_packs_the_images():
    assert "assets/images;assets/images" in (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
