"""
ui/item_form.py

The full product form: basics, pricing, and what the website shows. Used to add
and to edit a product. Stock is set only when adding; afterwards it changes
through "Adjust stock" so every change is in the stock ledger.
"""

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services import pricing
from ui.theme import Colors, Theme

GST_CHOICES = [0, 5, 12, 18, 28]  # what the server accepts


def _label(text: str) -> QLabel:
    return QLabel(text, styleSheet=Theme.label())


class ItemDialog(QDialog):
    def __init__(self, parent=None, item=None, categories=None, brands=None, default_type=None):
        super().__init__(parent)
        self._editing = item is not None
        self.setWindowTitle("Edit product" if item else "Add product")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        item = item or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ---- Basics
        basics = QWidget()
        f = QFormLayout(basics)
        f.setSpacing(10)
        self.name = self._line(item.get("name"), "e.g. Carved Teak Armchair")
        self.item_type = QComboBox()
        self.item_type.addItem("Furniture", "furniture")
        self.item_type.addItem("Sculpture (temple carving)", "sculpture")
        start = item.get("item_type") or default_type or "furniture"
        self.item_type.setCurrentIndex(max(0, self.item_type.findData(start)))
        self.item_type.setStyleSheet(Theme.input_style())
        # The code is made by the server from the type (FUR-0001, SCU-0001) and never changes
        self.sku = self._line(item.get("sku"), "")
        if self._editing:
            self.sku.setReadOnly(True)
            self.sku.setToolTip("A product's code never changes")
        else:
            self.sku.setPlaceholderText("Given automatically when you save")
            self.sku.setEnabled(False)
        self.description = QPlainTextEdit(item.get("description") or "")
        self.description.setFixedHeight(70)
        self.description.setStyleSheet(Theme.input_style())
        self.category = self._combo(categories, item.get("category_id"))
        self.brand = self._combo(brands, item.get("brand_id"))
        self.unit = self._line(item.get("unit") or "pcs", "pcs")
        self.min_stock = QSpinBox()
        self.min_stock.setRange(0, 100000)
        self.min_stock.setValue(int(item.get("min_stock", 5) or 0))
        self.min_stock.setStyleSheet(Theme.input_style())
        for label, w in [
            ("Name *", self.name),
            ("Type", self.item_type),
            ("Code (SKU)", self.sku),
            ("Description", self.description),
            ("Category", self.category),
            ("Brand", self.brand),
            ("Unit", self.unit),
            ("Warn me below", self.min_stock),
        ]:
            f.addRow(_label(label), w)
        self.stock = QSpinBox()
        self.stock.setRange(0, 1000000)
        self.stock.setStyleSheet(Theme.input_style())
        if self._editing:
            self.stock.setValue(int(item.get("current_stock", 0) or 0))
            self.stock.setEnabled(False)
            self.stock.setToolTip("Use Adjust stock to change it, so it is recorded")
            f.addRow(_label("In stock"), self.stock)
        else:
            f.addRow(_label("Starting stock"), self.stock)
        tabs.addTab(basics, "Basics")

        # ---- Pricing: cost + profit % + GST = what the customer pays
        pricing_tab = QWidget()
        p = QFormLayout(pricing_tab)
        p.setSpacing(10)
        self.purchase = self._money(item.get("purchase_price"))
        self.production = self._money(item.get("production_cost"))
        self.cost_lbl = QLabel("")
        self.cost_lbl.setStyleSheet(f"font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        self.by_profit = QCheckBox("Work the selling price out from cost and profit %")
        self._net_saved = float(item.get("selling_price") or 0)  # the stored price (before GST)
        self.by_profit.setChecked(item.get("profit_percent") is not None or not item)
        self.profit = QDoubleSpinBox()
        self.profit.setRange(0, 1000)
        self.profit.setDecimals(2)
        self.profit.setSuffix(" %")
        self.profit.setStyleSheet(Theme.input_style())
        known = item.get("profit_percent")
        if known is None:
            known = pricing.profit_percent_of(
                pricing.cost_of(item.get("purchase_price"), item.get("production_cost")), self._net_saved
            )
        self.profit.setValue(float(known or 0))
        self.gst = QComboBox()
        for g in GST_CHOICES:
            self.gst.addItem(f"{g}%", g)
        gst_now = int(float(item.get("gst_percent") or 0))
        self.gst.setCurrentIndex(GST_CHOICES.index(gst_now) if gst_now in GST_CHOICES else 0)
        self.gst.setStyleSheet(Theme.input_style())
        self.net_lbl = QLabel("")
        self.net_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self.selling = self._money(pricing.with_gst(self._net_saved, gst_now))  # what the customer pays
        self._gross_typed = False
        self.hsn = self._line(item.get("hsn_code"), "optional")
        note = QLabel(
            "Selling price = (buying price + making cost) plus the profit %, then plus GST. "
            "GST is kept at 0% until the shop is registered; bills show no tax."
        )
        note.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        note.setWordWrap(True)
        for label, w in [
            ("Buying price", self.purchase),
            ("Making cost", self.production),
            ("Cost", self.cost_lbl),
            ("", self.by_profit),
            ("Profit %", self.profit),
            ("GST", self.gst),
            ("Price before GST", self.net_lbl),
            ("Selling price (with GST)", self.selling),
            ("HSN code", self.hsn),
        ]:
            p.addRow(_label(label), w)
        p.addRow(note)
        for spin in (self.purchase, self.production, self.profit):
            spin.valueChanged.connect(lambda _v: self._reprice())
        self.gst.currentIndexChanged.connect(lambda _i: self._reprice())
        self.by_profit.toggled.connect(lambda _c: self._reprice())
        self.selling.valueChanged.connect(self._gross_edited)
        self._reprice()
        tabs.addTab(pricing_tab, "Pricing")

        # ---- Website
        web = QWidget()
        w = QFormLayout(web)
        w.setSpacing(10)
        self.published = QCheckBox("Show this product on the website")
        self.published.setChecked(bool(item.get("is_published")))
        self.slug = self._line(item.get("slug"), "web address, made from the name if empty")
        self.wood = self._line(item.get("wood_type"), "e.g. Teak")
        self.short_desc = self._line(item.get("short_desc"), "one line for the shop page")
        self.made_to_order = QCheckBox("Made to order")
        self.made_to_order.setChecked(bool(item.get("made_to_order")))
        self.lead_days = QSpinBox()
        self.lead_days.setRange(0, 365)
        self.lead_days.setSpecialValueText("not set")
        self.lead_days.setSuffix(" days")
        self.lead_days.setValue(int(item.get("lead_time_days") or 0))
        self.lead_days.setStyleSheet(Theme.input_style())
        dims = item.get("dimensions_mm") or {}
        self.dim = {}
        dim_row = QHBoxLayout()
        for key, name in (("l", "L"), ("w", "W"), ("h", "H")):
            s = QSpinBox()
            s.setRange(0, 10000)
            s.setSpecialValueText("-")
            s.setSuffix(f" {name}")
            s.setValue(int(dims.get(key) or 0))
            s.setStyleSheet(Theme.input_style())
            self.dim[key] = s
            dim_row.addWidget(s)
        dim_box = QWidget()
        dim_box.setLayout(dim_row)
        dim_row.setContentsMargins(0, 0, 0, 0)
        self.furniture = QCheckBox("Furniture (shows in the 3D Lab)")
        self.furniture.setChecked(bool(item.get("is_furniture")))
        w.addRow(self.published)
        for label, wid in [
            ("Web address", self.slug),
            ("Wood", self.wood),
            ("Short line", self.short_desc),
            ("Size (mm)", dim_box),
            ("Lead time", self.lead_days),
        ]:
            w.addRow(_label(label), wid)
        w.addRow(self.made_to_order)
        w.addRow(self.furniture)
        tabs.addTab(web, "Website")
        self.item_type.currentIndexChanged.connect(self._type_changed)
        self._type_changed()

        # ---- Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(Theme.btn_secondary())
        cancel.clicked.connect(self.reject)
        save = QPushButton("💾 Save")
        save.setStyleSheet(Theme.btn_primary())
        save.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(save)
        root.addLayout(btns)

    # ---- small builders
    @staticmethod
    def _line(value, placeholder=""):
        e = QLineEdit(value or "")
        e.setPlaceholderText(placeholder)
        e.setStyleSheet(Theme.input_style())
        return e

    @staticmethod
    def _money(value):
        s = QDoubleSpinBox()
        s.setRange(0, 10_000_000)
        s.setDecimals(2)
        s.setPrefix("₹")
        s.setValue(float(value or 0))
        s.setStyleSheet(Theme.input_style())
        return s

    def _reprice(self):
        """Keep Cost, Price before GST and Selling price (with GST) in step with what was typed."""
        gst = self.gst.currentData()
        cost = pricing.cost_of(self.purchase.value(), self.production.value())
        self.cost_lbl.setText(f"₹{cost:,.2f}")
        auto = self.by_profit.isChecked()
        self.profit.setEnabled(auto)
        self.selling.setReadOnly(auto)
        self.selling.setButtonSymbols(
            QDoubleSpinBox.ButtonSymbols.NoButtons if auto else QDoubleSpinBox.ButtonSymbols.UpDownArrows
        )
        if auto:
            self._net_saved = pricing.price_from_cost(cost, self.profit.value())
        elif self._gross_typed:
            self._net_saved = pricing.net_from_gross(self.selling.value(), gst)
        # else: an existing hand-typed price that was not touched keeps its stored value
        tax = pricing.with_gst(self._net_saved, gst) - self._net_saved
        self.net_lbl.setText(f"₹{self._net_saved:,.2f}" + (f"   (GST {gst}%: ₹{tax:,.2f})" if gst else ""))
        if auto or self._gross_typed or self.selling.value() == 0:
            self.selling.blockSignals(True)
            self.selling.setValue(pricing.with_gst(self._net_saved, gst))
            self.selling.blockSignals(False)
        if not auto:
            shown = pricing.profit_percent_of(cost, self._net_saved)
            self.profit.blockSignals(True)
            self.profit.setValue(shown or 0)
            self.profit.blockSignals(False)

    def _gross_edited(self, _value):
        """The owner typed the selling price: it becomes the price (the price before GST is worked back from it)."""
        if self.by_profit.isChecked():
            return
        self._gross_typed = True
        self._reprice()

    def _type_changed(self, _i=0):
        """Only furniture has parts for the 3D Lab."""
        sculpture = self.item_type.currentData() == "sculpture"
        if sculpture:
            self.furniture.setChecked(False)
        self.furniture.setEnabled(not sculpture)
        self.furniture.setToolTip("Only furniture has parts for the 3D Lab" if sculpture else "")

    @staticmethod
    def _combo(rows, current):
        c = QComboBox()
        c.addItem("(none)", None)
        for r in rows or []:
            c.addItem(r["name"], r["id"])
        if current:
            i = c.findData(str(current))
            if i >= 0:
                c.setCurrentIndex(i)
        c.setStyleSheet(Theme.input_style())
        return c

    # ---- result
    def get_data(self) -> dict:
        dims = {k: s.value() for k, s in self.dim.items() if s.value() > 0}
        data = {
            "name": self.name.text().strip(),
            "item_type": self.item_type.currentData(),
            "description": self.description.toPlainText().strip() or None,
            "category_id": self.category.currentData(),
            "brand_id": self.brand.currentData(),
            "unit": self.unit.text().strip() or "pcs",
            "min_stock": self.min_stock.value(),
            "selling_price": self._net_saved,  # before GST: bills add the GST on top
            "profit_percent": self.profit.value() if self.by_profit.isChecked() else None,
            "purchase_price": self.purchase.value(),
            "production_cost": self.production.value(),
            "gst_percent": self.gst.currentData(),
            "hsn_code": self.hsn.text().strip() or None,
            "is_published": self.published.isChecked(),
            "slug": self.slug.text().strip() or None,
            "wood_type": self.wood.text().strip() or None,
            "short_desc": self.short_desc.text().strip() or None,
            "made_to_order": self.made_to_order.isChecked(),
            "lead_time_days": self.lead_days.value() or None,
            "dimensions_mm": dims or None,
            "is_furniture": self.furniture.isChecked(),
        }
        if not self._editing:
            data["current_stock"] = self.stock.value()
        return data
