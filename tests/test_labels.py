"""Stickers: the codes scan, the logo does not break the QR, the sheet maths fits the page."""

import pytest

from services import qr_service
from services.label_layouts import BY_KEY, FORMATS
from ui import label_render

ITEM = {"name": "Ganesha panel, teak", "sku": "VS-00123", "selling_price": 8000, "gst_percent": 18}


def test_payload_round_trip():
    assert qr_service.qr_payload("VS-00123") == "VS:VS-00123"
    assert qr_service.sku_from_payload("VS:VS-00123") == "VS-00123"
    assert qr_service.sku_from_payload("VS-00123") == "VS-00123"


def test_logo_hides_a_small_part_of_the_qr():
    assert (qr_service.LOGO_FRACTION + 2 / 25) ** 2 < 0.15  # plate area on the smallest QR, far under the 30 % H can repair


@pytest.mark.parametrize("fmt", FORMATS, ids=lambda f: f.key)
def test_labels_fit_their_page(fmt):
    pw, ph = fmt.page
    for slot in range(fmt.per_page):
        x, y = fmt.origin(slot)
        assert x >= 0 and y >= 0 and x + fmt.w <= pw + 0.01 and y + fmt.h <= ph + 0.01


@pytest.mark.parametrize("key", [f.key for f in FORMATS])
def test_codes_scan_with_logo(qapp, key):
    zxingcpp = pytest.importorskip("zxingcpp")
    np = pytest.importorskip("numpy")
    from PyQt6.QtGui import QImage

    img = label_render.label_image(BY_KEY[key], ITEM, dpi=400).convertToFormat(QImage.Format.Format_Grayscale8)
    arr = np.frombuffer(img.constBits().asstring(img.sizeInBytes()), np.uint8).reshape(img.height(), img.bytesPerLine())[:, : img.width()]
    found = {r.format.name: r.text for r in zxingcpp.read_barcodes(arr)}
    assert found.get("QRCode") == "VS:VS-00123"
    if key in ("label_60x40", "thermal_80", "hang_tag", "sheet_21", "a4_grid"):  # wide enough for the bar code
        assert found.get("Code128") == "VS-00123"


def test_pdf_pages(qapp, tmp_path):
    sheet = tmp_path / "s.pdf"
    label_render.save_pdf(str(sheet), BY_KEY["sheet_21"], [ITEM] * 22, start=3)  # 22 labels from place 3: two pages
    assert sheet.read_bytes().startswith(b"%PDF")
    roll = tmp_path / "r.pdf"
    label_render.save_pdf(str(roll), BY_KEY["label_50x25"], [ITEM] * 3)
    assert roll.read_bytes().startswith(b"%PDF")


def test_dialog_counts_and_skips_products_without_a_code(qapp):
    from ui.label_print_dialog import LabelPrintDialog, expand

    items = [dict(ITEM, current_stock=3), {"name": "No code", "selling_price": 1}]
    assert len(expand(items, 2, False)) == 2 and len(expand(items, 2, True)) == 6
    d = LabelPrintDialog(None, items)
    d.format.setCurrentIndex(d.format.findData("sheet_21"))
    d.copies.setValue(4)
    assert len(d.labels()) == 4 and "1 sheet" in d.count.text()
    assert d.start.maximum() == 21 and d.pdf_btn.isEnabled()


def test_a_code_with_letters_code_128_cannot_hold_still_gets_a_qr_label(qapp):
    assert qr_service.barcode_bars("VS-ö1") == "" and qr_service.barcode_bars("VS-00123") != ""
    img = label_render.label_image(BY_KEY["label_60x40"], {**ITEM, "sku": "VS-ö1"}, dpi=300)  # no bar code, no crash
    assert not img.isNull()
