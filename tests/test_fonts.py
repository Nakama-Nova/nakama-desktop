"""The brand fonts ship inside the app and load."""

from ui.fonts import FONT_DIR, FONT_FILES, load_brand_fonts


def test_font_files_and_their_licences_are_in_the_repo():
    for name in FONT_FILES:
        assert (FONT_DIR / name).stat().st_size > 100_000
    assert (FONT_DIR / "OFL-Inter.txt").read_text(encoding="utf-8").startswith("Copyright")
    assert (FONT_DIR / "OFL-CormorantGaramond.txt").exists()


def test_both_families_register(qapp):
    families = load_brand_fonts()
    assert "Cormorant Garamond" in families and "Inter" in families


def test_text_colours_read_at_wcag_aa_on_every_surface():
    from ui.theme import Colors

    def lum(h):
        c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    surfaces = [Colors.BG, Colors.CARD_BG, Colors.TABLE_HEADER_BG, Colors.SIDEBAR_BG]
    for name in ("TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED", "SUCCESS", "DANGER", "ORANGE"):
        for surface in surfaces:
            assert ratio(getattr(Colors, name), surface) >= 4.5, (name, surface)
