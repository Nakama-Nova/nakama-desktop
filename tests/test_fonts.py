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
