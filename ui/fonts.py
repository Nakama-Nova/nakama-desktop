"""
ui/fonts.py

The brand fonts ship inside the app (assets/fonts, SIL Open Font License) so the
design looks right on any PC: Cormorant Garamond for headings and Inter for text.
If a file cannot be loaded the app falls back to Georgia / Segoe UI.
"""

from pathlib import Path

from PyQt6.QtGui import QFontDatabase

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_FILES = ("CormorantGaramond.ttf", "Inter.ttf")


def load_brand_fonts() -> list[str]:
    """Register the bundled fonts; returns the family names that loaded."""
    families: list[str] = []
    for name in FONT_FILES:
        font_id = QFontDatabase.addApplicationFont(str(FONT_DIR / name))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families
