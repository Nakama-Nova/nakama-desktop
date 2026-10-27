"""Stock screens: full product form, stock changes, materials, purchases, access by role."""

import pytest
from PyQt6.QtWidgets import QPushButton

from services.api_client import APIClient, APIError
from services.enums import UserRole
from services.inventory_service import InventoryService
from services.session import Session
from services.stock_service import StockService
from ui.inventory_window import InventoryWindow
from ui.item_form import ItemDialog
from ui.main_window import MainWindow
from ui.materials_screen import MaterialsScreen
from ui.purchases_screen import NewPurchaseDialog
from ui.stock_dialogs import AdjustStockDialog

ITEMS = [
    {"id": "i1", "name": "Teak Armchair", "sku": "CH-1", "selling_price": "18500", "current_stock": 2, "min_stock": 5, "unit": "pcs"},
    {"id": "i2", "name": "Study Table", "sku": "TB-2", "selling_price": "14200", "current_stock": 9, "min_stock": 5, "unit": "pcs"},
]
MATERIALS = [{"id": "m1", "name": "Teak plank", "unit": "cft", "current_price": "900", "stock": "12.5"}]


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: ITEMS)
    monkeypatch.setattr(StockService, "rows", lambda self, kind: [])
    monkeypatch.setattr(StockService, "materials", lambda self: MATERIALS)
    monkeypatch.setattr(
        StockService, "adjust_material", lambda self, mid, change, notes: calls.append(("material", mid, change, notes))
    )
    monkeypatch.setattr(
        StockService, "adjust_item", lambda self, iid, qty, notes: calls.append(("item", iid, qty, notes))
    )
    return calls


def row_buttons(table, row, col):
    return [b.text() for b in table.cellWidget(row, col).findChildren(QPushButton)]


def test_owner_sees_the_stock_tools_and_can_search_by_code(qapp, fake):
    w = InventoryWindow()
    w.refresh_data()
    assert w.table.rowCount() == 2
    assert w.table.item(0, w.COL_STATUS).text() == "⚠️ Low"  # 2 left, warn at 5
    assert w.table.item(1, w.COL_STATUS).text() == "✅ OK"
    assert row_buttons(w.table, 0, w.COL_ACTIONS) == ["✏️ Edit", "± Stock", "🕘", "🖼️", "🗑️"]
    w.search_input.setText("tb-2")  # by code, any case
    assert w.table.rowCount() == 1 and w.table.item(0, w.COL_NAME).text() == "Study Table"


@pytest.mark.parametrize("role", [UserRole.SALES, UserRole.ACHARI, UserRole.WORKER])
def test_other_staff_only_read_stock(qapp, fake, monkeypatch, role):
    monkeypatch.setattr(Session, "_role", role)
    w = InventoryWindow()
    w.refresh_data()
    assert w.table.rowCount() == 2
    assert w.table.columnCount() == 5  # no actions column
    assert w.add_btn.isHidden() and w.categories_btn.isHidden() and w.brands_btn.isHidden()


def test_product_form_collects_everything_the_website_needs(qapp):
    cats = [{"id": "c1", "name": "Chairs"}]
    d = ItemDialog(None, None, cats, [])
    d.name.setText("Carved Chair")
    d.sku.setText("CH-9")
    d.category.setCurrentIndex(1)
    d.stock.setValue(4)
    d.selling.setValue(9500)
    d.gst.setCurrentIndex(0)
    d.published.setChecked(True)
    d.slug.setText("carved-chair")
    d.dim["l"].setValue(450)
    d.dim["h"].setValue(900)
    d.lead_days.setValue(14)
    data = d.get_data()
    assert data["category_id"] == "c1" and data["current_stock"] == 4 and data["gst_percent"] == 0
    assert data["is_published"] and data["slug"] == "carved-chair" and data["lead_time_days"] == 14
    assert data["dimensions_mm"] == {"l": 450, "h": 900}  # only the sizes that were entered
    assert data["description"] is None and data["hsn_code"] is None


def test_editing_never_overwrites_stock(qapp):
    existing = {"name": "Chair", "sku": "C", "current_stock": 7, "gst_percent": "18.00", "category_id": "c1"}
    d = ItemDialog(None, existing, [{"id": "c1", "name": "Chairs"}], [])
    data = d.get_data()
    assert "current_stock" not in data  # stock changes only through Adjust stock
    assert data["gst_percent"] == 18 and data["category_id"] == "c1"
    assert not d.stock.isEnabled()


def test_adjust_stock_sign_and_required_reason(qapp):
    d = AdjustStockDialog(None, "Chair", "pcs", 5)
    d.qty.setValue(3)
    d.reason.setText("damaged")
    assert d.change() == 3 and d.notes() == "damaged"
    d.remove_radio.setChecked(True)
    assert d.change() == -3


def test_stock_button_sends_the_signed_change_with_the_reason(qapp, fake, monkeypatch):
    w = InventoryWindow()
    w.refresh_data()

    class Auto(AdjustStockDialog):
        def exec(self):
            self.qty.setValue(2)
            self.remove_radio.setChecked(True)
            self.reason.setText("found broken")
            return 1

    monkeypatch.setattr("ui.inventory_window.AdjustStockDialog", Auto)
    w.table.cellWidget(0, w.COL_ACTIONS).findChildren(QPushButton)[1].click()
    assert fake == [("item", "i1", -2, "found broken")]


def test_materials_screen_lists_and_adjusts(qapp, fake, monkeypatch):
    s = MaterialsScreen()
    s.refresh_data()
    assert s.table.item(0, 0).text() == "Teak plank" and s.table.item(0, 3).text() == "12.5"
    assert "🗑️" in row_buttons(s.table, 0, s.COL_ACTIONS)

    class Auto(AdjustStockDialog):
        def exec(self):
            self.qty.setValue(1.5)
            self.reason.setText("opening count")
            return 1

    monkeypatch.setattr("ui.materials_screen.AdjustStockDialog", Auto)
    s.table.cellWidget(0, s.COL_ACTIONS).findChildren(QPushButton)[0].click()
    assert fake == [("material", "m1", 1.5, "opening count")]


def test_only_the_owner_can_delete_a_material(qapp, fake, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.MANAGER)
    s = MaterialsScreen()
    s.refresh_data()
    assert "🗑️" not in row_buttons(s.table, 0, s.COL_ACTIONS)


def test_new_purchase_builds_lines_and_total(qapp):
    d = NewPurchaseDialog(None, [{"id": "s1", "name": "Teak Traders"}], MATERIALS, ITEMS)
    d.supplier.setCurrentIndex(1)
    d.invoice.setText("TT-77")
    d.what.setCurrentIndex(0)  # the material
    d.qty.setValue(10)
    d.price.setValue(900)
    d.gst.setCurrentIndex(0)
    d._add_line()
    d.what.setCurrentIndex(1)  # a finished product
    d.qty.setValue(2)
    d.price.setValue(1000)
    d._add_line()
    assert d.total.text() == "Total ₹11,000.00"
    data = d.get_data()
    assert data["supplier_id"] == "s1" and data["invoice_number"] == "TT-77"
    assert data["items"][0] == {"raw_material_id": "m1", "quantity": 10.0, "unit_price": 900.0, "gst_percent": 0}
    assert data["items"][1]["item_id"] == "i1"
    d._remove(1)
    assert len(d.get_data()["items"]) == 1 and d.total.text() == "Total ₹9,000.00"


@pytest.mark.parametrize(
    "role,sees",
    [(UserRole.OWNER, True), (UserRole.MANAGER, True), (UserRole.SALES, False), (UserRole.ACHARI, False), (UserRole.WORKER, False)],
)
def test_materials_and_purchases_menu_by_role(qapp, monkeypatch, role, sees):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    labels = [label for _, label, _ in w._get_allowed_nav_items()]
    assert ("Materials" in labels) is sees and ("Purchases" in labels) is sees


def test_server_reasons_are_shown_in_plain_words():
    e = APIError(409, '{"detail": "Supplier is on past purchases; it cannot be deleted"}')
    assert str(e) == "Supplier is on past purchases; it cannot be deleted (409)"
    assert "Some files" in str(APIError(409, '{"detail": {"message": "Some files did not upload", "missing": []}}'))
    assert str(APIError(500, "boom")) == "boom (500)"


def test_every_item_is_loaded_not_just_the_first_page(monkeypatch):
    pages = {0: [{"id": i} for i in range(100)], 100: [{"id": i} for i in range(100, 130)]}
    api = APIClient("http://x")
    monkeypatch.setattr(api, "_get", lambda path, token, params=None, quiet=False: pages[params["offset"]])
    assert len(api.get_items("t")) == 130


def test_photo_upload_sends_the_content_type_the_server_checks(monkeypatch, tmp_path):
    sent = {}

    class Resp:
        status_code = 201

        @staticmethod
        def json():
            return {"id": "a1"}

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        sent["file"] = files["file"]
        return Resp()

    monkeypatch.setattr("services.api_client._http.post", fake_post)
    photo = tmp_path / "front.PNG"
    photo.write_bytes(b"x")
    APIClient("http://x")._upload("/items/i1/assets", "t", str(photo))
    assert sent["file"][0] == "front.PNG" and sent["file"][2] == "image/png"
    model = tmp_path / "chair.glb"
    model.write_bytes(b"x")
    APIClient("http://x")._upload("/items/i1/assets", "t", str(model))
    assert sent["file"][2] == "model/gltf-binary"
