"""Designs screen, finishing projects (bought pieces), project costs and expenses on a project."""

import pytest
from PyQt6.QtWidgets import QDialog, QInputDialog, QMessageBox

from services.designs_service import DesignsService
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.restoration_service import RestorationService, stages, status_word
from services.session import Session
from services.stock_service import StockService
from ui.designs_screen import DesignDialog, DesignsScreen, PickProductDialog, ProductFromDesignDialog
from ui.expenses_screen import ExpenseDialog
from ui.main_window import MainWindow
from ui.restoration_screen import ProjectDialog, RestorationScreen

D1 = {"id": "d1", "sku": "DES-0001", "name": "Hoysala Madhanika", "description": "Lady with the mirror", "status": "ready", "restoration_id": "r1", "restoration_title": "Madhanika, Halebidu", "product_count": 2, "created_at": "2026-10-28T10:00:00Z", "updated_at": "2026-10-28T10:00:00Z"}
D2 = {**D1, "id": "d2", "sku": "DES-0002", "name": "Garuda", "status": "draft", "restoration_id": None, "restoration_title": None, "product_count": 0}
DETAIL = {
    **D1,
    "restoration": {"id": "r1", "title": "Madhanika, Halebidu", "temple_name": "Hoysaleswara", "kind": "temple", "status": "review"},
    "products": [
        {"id": "i1", "sku": "SCU-0001", "name": "Madhanika, large", "item_type": "sculpture", "selling_price": "48000", "current_stock": 1},
        {"id": "i2", "sku": "SCU-0002", "name": "Madhanika, small", "item_type": "sculpture", "selling_price": "18000", "current_stock": 0},
    ],
    "files": [{"id": "f1", "kind": "glb", "size_bytes": 5242880, "created_at": "2026-10-28T11:00:00Z", "label": None, "content_type": "x", "scan_id": None}],
}
ITEMS = [
    {"id": "i1", "sku": "SCU-0001", "name": "Madhanika, large", "item_type": "sculpture"},
    {"id": "i3", "sku": "SCU-0003", "name": "Nandi", "item_type": "sculpture"},
    {"id": "i4", "sku": "FUR-0001", "name": "Armchair", "item_type": "furniture"},
]


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def listing(self, status=None, search=None, item_id=None):
        calls.append(("list", status, search))
        rows = [D1, D2]
        return [r for r in rows if (not status or r["status"] == status) and (not search or search.lower() in (r["sku"] + r["name"]).lower())]

    monkeypatch.setattr(DesignsService, "designs", listing)
    monkeypatch.setattr(DesignsService, "design", lambda self, i: DETAIL)
    monkeypatch.setattr(DesignsService, "create", lambda self, d: calls.append(("create", d)) or {"name": d["name"], "sku": "DES-0003"})
    monkeypatch.setattr(DesignsService, "update", lambda self, i, d: calls.append(("update", i, d)))
    monkeypatch.setattr(DesignsService, "link", lambda self, d, i: calls.append(("link", d, i)))
    monkeypatch.setattr(DesignsService, "unlink", lambda self, d, i: calls.append(("unlink", d, i)) or True)
    monkeypatch.setattr(DesignsService, "create_product", lambda self, d, data: calls.append(("make", d, data)) or {"name": data["name"], "sku": "SCU-0004"})
    monkeypatch.setattr(RestorationService, "projects", lambda self, status=None: [{"id": "r1", "title": "Madhanika, Halebidu", "kind": "temple"}])
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: ITEMS)
    return calls


def select(screen, row):
    screen.table.selectRow(row)
    screen._selected()


# ------------------------------------------------------------------ the screen
def test_lists_designs_with_their_codes_and_source(qapp, fake):
    s = DesignsScreen()
    s.refresh_data()
    assert s.table.rowCount() == 2
    assert [s.table.item(r, s.COL_SKU).text() for r in range(2)] == ["DES-0001", "DES-0002"]
    assert s.table.item(0, s.COL_FROM).text() == "Madhanika, Halebidu" and s.table.item(0, s.COL_PRODUCTS).text() == "2"
    assert s.table.item(1, s.COL_STATUS).text() == "Draft"


def test_filters_and_search_reach_the_server(qapp, fake):
    s = DesignsScreen()
    s.status_filter.setCurrentIndex(s.status_filter.findData("draft"))
    assert fake[-1] == ("list", "draft", "")
    s.status_filter.setCurrentIndex(0)
    s.search.setText("garuda")
    s._search_timer.stop()
    s.refresh_data()
    assert fake[-1] == ("list", None, "garuda") and s.table.rowCount() == 1


def test_a_design_shows_its_products_and_the_restorations_files(qapp, fake):
    s = DesignsScreen()
    s.refresh_data()
    select(s, 0)
    assert s.heading.text() == "DES-0001  ·  Hoysala Madhanika"
    assert "Lady with the mirror" in s.notes.text() and "Taken from: Madhanika, Halebidu" in s.notes.text()
    assert [s.products.item(r, 0).text() for r in range(2)] == ["SCU-0001", "SCU-0002"]
    assert s.products.item(0, s.PCOL_PRICE).text() == "₹48,000.00" and s.products.item(0, s.PCOL_TYPE).text() == "Sculpture"
    assert s.files.rowCount() == 1 and s.files.item(0, 0).text() == "3D model (.glb)" and not s.files.isHidden()


def test_a_design_with_no_restoration_hides_the_files(qapp, fake, monkeypatch):
    monkeypatch.setattr(DesignsService, "design", lambda self, i: {**DETAIL, "restoration": None, "files": [], "restoration_id": None})
    s = DesignsScreen()
    s.refresh_data()
    select(s, 0)
    assert s.files.isHidden() and s.files_title.isHidden()


def test_creating_a_design_asks_for_a_name_and_can_start_from_a_restoration(qapp, fake, dialogs, monkeypatch):
    d = DesignDialog(None, [{"id": "r1", "title": "Madhanika", "kind": "temple"}])
    d._check()
    assert d.result() == 0 and dialogs[-1][0] == "warning"
    d.name.setText("Nandi")
    d.source.setCurrentIndex(d.source.findData("r1"))
    assert d.get_data() == {"name": "Nandi", "description": None, "restoration_id": "r1"}
    s = DesignsScreen()
    monkeypatch.setattr(DesignDialog, "exec", lambda self: (self.name.setText("Garuda"), QDialog.DialogCode.Accepted)[-1])
    s.new_btn.click()
    assert next(c for c in fake if c[0] == "create")[1]["name"] == "Garuda"
    assert dialogs[-1][0] == "information" and "DES-0003" in dialogs[-1][2]


def test_linking_a_product_offers_only_ones_not_already_linked(qapp, fake, monkeypatch):
    s = DesignsScreen()
    s.refresh_data()
    select(s, 0)
    seen = []
    monkeypatch.setattr(PickProductDialog, "exec", lambda self: (seen.append([self.pick.itemData(i) for i in range(self.pick.count())]), self.pick.setCurrentIndex(0), QDialog.DialogCode.Accepted)[-1])
    s.link_btn.click()
    assert seen == [["i3", "i4"]]  # i1 is already on the design; sculptures come first
    assert next(c for c in fake if c[0] == "link") == ("link", "d1", "i3")


def test_the_product_picker_narrows_by_code_or_name(qapp):
    d = PickProductDialog(None, ITEMS)
    d.search.setText("nandi")
    assert [d.pick.itemData(i) for i in range(d.pick.count())] == ["i3"]
    d.search.setText("fur-")
    assert d.item_id() == "i4"


def test_unlinking_asks_first(qapp, fake, monkeypatch):
    s = DesignsScreen()
    s.refresh_data()
    select(s, 0)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    s.products.cellWidget(1, s.PCOL_ACTION).click()
    assert not [c for c in fake if c[0] == "unlink"]
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    s.products.cellWidget(1, s.PCOL_ACTION).click()
    assert next(c for c in fake if c[0] == "unlink") == ("unlink", "d1", "i2")


def test_building_a_product_out_of_a_design(qapp, fake, dialogs, monkeypatch):
    s = DesignsScreen()
    s.refresh_data()
    select(s, 0)
    monkeypatch.setattr(ProductFromDesignDialog, "exec", lambda self: (self.name.setText("Madhanika, medium"), self.price.setValue(30000), self.wood.setText("Teak"), QDialog.DialogCode.Accepted)[-1])
    s.make_btn.click()
    sent = next(c for c in fake if c[0] == "make")
    assert sent[1] == "d1" and sent[2] == {"name": "Madhanika, medium", "selling_price": 30000.0, "wood_type": "Teak"}
    assert dialogs[-1][0] == "information" and "SCU-0004" in dialogs[-1][2] and "DES-0001" in dialogs[-1][2]
    blank = ProductFromDesignDialog(None, D1)
    assert blank.name.text() == "Hoysala Madhanika"  # starts from the design's name
    blank.name.setText("")
    blank._check()
    assert blank.result() == 0


def test_changing_the_design_status_sends_only_that(qapp, fake):
    s = DesignsScreen()
    s.refresh_data()
    select(s, 0)
    s.status.setCurrentIndex(s.status.findData("retired"))
    s._status_chosen()
    assert next(c for c in fake if c[0] == "update") == ("update", "d1", {"status": "retired"})


@pytest.mark.parametrize(
    "role,sees",
    [(UserRole.OWNER, True), (UserRole.ARTISAN, True), (UserRole.MANAGER, False), (UserRole.SALES, False), (UserRole.ACHARI, False), (UserRole.WORKER, False)],
)
def test_only_the_owner_and_artisans_see_designs(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    assert ("Designs" in [label for _, label, _ in w._get_allowed_nav_items()]) is sees


# --------------------------------------------------- bought pieces: finishing and painting
def test_stages_follow_the_kind_of_project():
    assert [v for _, v in stages("temple")] == ["planned", "capturing", "processing", "review", "carving", "restored", "on_hold", "cancelled"]
    assert [v for _, v in stages("finishing")] == ["planned", "finishing", "painting", "restored", "on_hold", "cancelled"]
    assert status_word("planned", "finishing") == "Bought" and status_word("restored", "finishing") == "Ready to sell"
    assert status_word("restored", "temple") == "Restored" and status_word("painting", "finishing") == "Painting"


def test_the_project_form_switches_between_temple_and_finishing(qapp, dialogs):
    d = ProjectDialog(None, [], None, ITEMS[:2], [{"id": "s1", "name": "Ramu Artisan"}])
    assert not d.temple.isHidden() and d.item.isHidden()
    d.kind.setCurrentIndex(d.kind.findData("finishing"))
    assert d.temple.isHidden() and not d.item.isHidden() and not d.supplier.isHidden()
    d.title.setText("Finish Ganesha")
    d._check()
    assert d.result() == 0 and "choose the piece" in dialogs[-1][2]  # a finishing project needs its piece
    d.item.setCurrentIndex(d.item.findData("i1"))
    d.supplier.setCurrentIndex(d.supplier.findData("s1"))
    assert d.get_data() == {"kind": "finishing", "title": "Finish Ganesha", "piece": None, "condition_notes": None, "lead_artisan_id": None, "item_id": "i1", "supplier_id": "s1"}
    d.kind.setCurrentIndex(d.kind.findData("temple"))
    d.temple.setText("Temple")
    assert d.get_data()["kind"] == "temple" and "item_id" not in d.get_data() and d.get_data()["temple_name"] == "Temple"


def test_an_existing_project_cannot_change_kind(qapp):
    d = ProjectDialog(None, [], {"kind": "finishing", "title": "F", "item_id": "i1", "supplier_id": None}, ITEMS[:2], [])
    assert not d.kind.isEnabled() and d.kind.currentData() == "finishing" and d.item.currentData() == "i1"


FINISH = {"id": "r2", "kind": "finishing", "title": "Finish Ganesha", "temple_name": None, "location": None, "piece": "Ganesha", "condition_notes": "Rough chisel marks", "status": "painting", "lead_artisan_id": None, "lead_artisan_name": None, "item_id": "i1", "item_sku": "SCU-0001", "item_name": "Bought Ganesha", "supplier_id": "s1", "supplier_name": "Ramu Artisan", "scan_count": 0, "file_count": 0}
TEMPLE = {**FINISH, "id": "r1", "kind": "temple", "title": "Madhanika", "temple_name": "Hoysaleswara", "item_id": None, "item_sku": None, "item_name": None, "supplier_id": None, "supplier_name": None, "status": "review"}


@pytest.fixture
def projects(monkeypatch):
    calls = []
    monkeypatch.setattr(RestorationService, "projects", lambda self, status=None: [TEMPLE, FINISH])
    monkeypatch.setattr(RestorationService, "project", lambda self, rid: {**(FINISH if rid == "r2" else TEMPLE), "scans": [], "files": [], "designs": [{"id": "d1", "sku": "DES-0001", "name": "Ganesha design", "status": "draft"}] if rid == "r2" else []})
    monkeypatch.setattr(RestorationService, "cost", lambda self, rid: {"item_id": "i1", "item_sku": "SCU-0001", "item_name": "Bought Ganesha", "purchase_price": "3000.00", "labour": "750.00", "expenses": "400.00", "total": "4150.00", "selling_price": "9000.00", "profit_if_sold": "4850.00"})
    monkeypatch.setattr(DesignsService, "create", lambda self, d: calls.append(("design", d)) or {"name": d["name"], "sku": "DES-0007"})
    return calls


def row_of(screen, title):
    return next(r for r in range(screen.table.rowCount()) if screen.table.item(r, 0).text() == title)


def test_a_finishing_project_shows_its_piece_and_its_own_stages(qapp, projects):
    s = RestorationScreen()
    s.refresh_data()
    r = row_of(s, "Finish Ganesha")
    assert s.table.item(r, s.COL_TEMPLE).text() == "SCU-0001  Bought Ganesha"  # the piece, where a temple would be
    assert s.table.item(r, s.COL_STATUS).text() == "Painting"
    s.table.selectRow(r)
    s._selected()
    assert "Bought Ganesha (SCU-0001)" in s.heading.text() and "bought from Ramu Artisan" in s.heading.text()
    assert [s.status.itemData(i) for i in range(s.status.count())] == ["planned", "finishing", "painting", "restored", "on_hold", "cancelled"]
    assert s.status.currentData() == "painting" and "DES-0001 Ganesha design" in s.designs_label.text()
    t = row_of(s, "Madhanika")
    s.table.selectRow(t)
    s._selected()
    assert "carving" in [s.status.itemData(i) for i in range(s.status.count())] and "painting" not in [s.status.itemData(i) for i in range(s.status.count())]
    assert "No design made" in s.designs_label.text()


def test_the_cost_button_is_the_owners_and_shows_the_breakdown(qapp, projects, dialogs, monkeypatch):
    s = RestorationScreen()
    s.refresh_data()
    s.table.selectRow(row_of(s, "Finish Ganesha"))
    s._selected()
    assert not s.cost_btn.isHidden()
    s.cost_btn.click()
    kind, title, text = dialogs[-1]
    assert kind == "information" and "Bought Ganesha" in title
    assert "₹3,000.00" in text and "₹750.00" in text and "₹400.00" in text and "₹4,150.00" in text and "profit ₹4,850.00" in text
    monkeypatch.setattr(Session, "_role", UserRole.ARTISAN)
    assert RestorationScreen().cost_btn.isHidden()  # money: not for artisans


def test_making_a_design_from_a_restoration(qapp, projects, dialogs, monkeypatch):
    s = RestorationScreen()
    s.refresh_data()
    s.table.selectRow(row_of(s, "Madhanika"))
    s._selected()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Madhanika pattern", True)))
    s.design_btn.click()
    sent = next(c for c in projects if c[0] == "design")[1]
    assert sent["name"] == "Madhanika pattern" and sent["restoration_id"] == "r1"
    assert dialogs[-1][0] == "information" and "DES-0007" in dialogs[-1][2]


def test_adding_a_finishing_project_offers_sculptures_and_suppliers(qapp, projects, monkeypatch):
    monkeypatch.setattr(RestorationService, "team", lambda self: [])
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: ITEMS)
    monkeypatch.setattr(StockService, "rows", lambda self, kind: [{"id": "s1", "name": "Ramu Artisan"}] if kind == "suppliers" else [])
    made = []
    monkeypatch.setattr(RestorationService, "create", lambda self, d: made.append(d) or {})
    seen = {}

    def fill(self):
        seen["items"] = [self.item.itemData(i) for i in range(1, self.item.count())]
        seen["suppliers"] = [self.supplier.itemData(i) for i in range(1, self.supplier.count())]
        self.kind.setCurrentIndex(self.kind.findData("finishing"))
        self.title.setText("Finish Nandi")
        self.item.setCurrentIndex(self.item.findData("i3"))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ProjectDialog, "exec", fill)
    s = RestorationScreen()
    s.refresh_data()
    s.new_btn.click()
    assert seen["items"] == ["i1", "i3"]  # only sculptures, never the armchair
    assert seen["suppliers"] == ["s1"]
    assert made[0]["kind"] == "finishing" and made[0]["item_id"] == "i3"


# --------------------------------------------------------------- expenses on a project
def test_only_the_owner_gets_the_project_choice_on_an_expense(qapp):
    plain = ExpenseDialog(None)
    assert plain.project is None and "restoration_id" not in plain.get_data()
    owner = ExpenseDialog(None, None, (), projects=[{"id": "r2", "title": "Finish Ganesha"}])
    owner.category.setCurrentText("Paint")
    owner.amount.setValue(400)
    assert owner.get_data()["restoration_id"] is None  # "Not for a project" by default
    owner.project.setCurrentIndex(owner.project.findData("r2"))
    assert owner.get_data()["restoration_id"] == "r2"
    editing = ExpenseDialog(None, {"spent_on": "2026-10-21", "category": "Paint", "amount": "400", "method": "cash", "restoration_id": "r2"}, (), projects=[{"id": "r2", "title": "Finish Ganesha"}])
    assert editing.project.currentData() == "r2"
