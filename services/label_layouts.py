"""
services/label_layouts.py

The sticker formats, in millimetres. A "roll" format prints one label per page, the page
being the label (thermal label and receipt printers). A "sheet" format puts many labels
on an A4 page. Sheet sizes follow the common label-sheet layouts; do one test print on
plain paper and hold it against a sheet before using a new layout.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LabelFormat:
    key: str
    title: str
    w: float  # one label, mm
    h: float
    cols: int = 1  # 1 x 1 = a roll: one label per page
    rows: int = 1
    left: float = 0  # sheet margins and the distance from one label to the next
    top: float = 0
    pitch_x: float = 0
    pitch_y: float = 0
    price: bool = True  # False for catalogue and shelf cards

    @property
    def per_page(self) -> int:
        return self.cols * self.rows

    @property
    def is_sheet(self) -> bool:
        return self.per_page > 1

    @property
    def page(self) -> tuple[float, float]:
        return (210.0, 297.0) if self.is_sheet else (self.w, self.h)

    def origin(self, slot: int) -> tuple[float, float]:
        """Top-left corner, in mm, of label number `slot` (0-based) on its page."""
        r, c = divmod(slot, self.cols)
        return self.left + c * self.pitch_x, self.top + r * self.pitch_y


FORMATS = [
    LabelFormat("label_50x25", "Small label 50 x 25 mm (thermal label printer)", 50, 25),
    LabelFormat("label_60x40", "Label 60 x 40 mm (thermal label printer)", 60, 40),
    LabelFormat("thermal_58", "Receipt roll 58 mm wide", 58, 40),
    LabelFormat("thermal_80", "Receipt roll 80 mm wide", 80, 45),
    LabelFormat("hang_tag", "Hang tag 50 x 90 mm", 50, 90),
    LabelFormat("sheet_21", "A4 sticker sheet, 21 labels (63.5 x 38.1 mm)", 63.5, 38.1, 3, 7, 7.2, 15.15, 66.0, 38.1),
    LabelFormat("sheet_24", "A4 sticker sheet, 24 labels (63.5 x 33.9 mm)", 63.5, 33.9, 3, 8, 7.2, 13.0, 66.0, 33.9),
    LabelFormat("sheet_65", "A4 sticker sheet, 65 labels (38.1 x 21.2 mm)", 38.1, 21.2, 5, 13, 4.7, 10.7, 40.6, 21.2),
    LabelFormat("a4_grid", "A4 grid, 12 cards (no price, for catalogues and shelves)", 63.0, 70.0, 3, 4, 10.5, 8.5, 63.0, 70.0, price=False),
]
BY_KEY = {f.key: f for f in FORMATS}
