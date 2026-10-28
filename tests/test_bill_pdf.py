"""Printing a bill: the PDF is fetched and kept in a writable folder, and every failure says why."""

import pytest
import services.sales_service as sales_module
from services.api_client import APIClient, APIError
from services.sales_service import BillPdfError, SalesService
from ui.sales_history_screen import SalesHistoryScreen


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr(SalesService, "INVOICE_DIR", tmp_path / "VrikshaStudios" / "invoices")  # not the real folder
    return SalesService()


def serve(monkeypatch, result):
    def get_file(self, path, token):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(APIClient, "_get_file", get_file)


def test_the_pdf_is_saved_in_the_users_own_folder(svc, monkeypatch):
    serve(monkeypatch, b"%PDF-1.4 bill")
    path = svc.fetch_and_save_pdf("NTD-2026-00001")
    assert path.name == "NTD-2026-00001.pdf" and path.read_bytes() == b"%PDF-1.4 bill"
    assert path.is_absolute() and path.parent.name == "invoices"  # not relative to wherever the program started


def test_a_server_failure_is_explained_not_silent(svc, monkeypatch):
    serve(monkeypatch, APIError(500, '{"detail": "Could not draw the bill PDF: boom"}'))
    with pytest.raises(BillPdfError, match="Could not draw the bill PDF: boom"):
        svc.fetch_and_save_pdf("X-1")


def test_no_connection_and_not_a_pdf_are_explained(svc, monkeypatch):
    import requests

    serve(monkeypatch, requests.ConnectionError("down"))
    with pytest.raises(BillPdfError, match="could not be reached"):
        svc.fetch_and_save_pdf("X-1")
    serve(monkeypatch, b"<html>error page</html>")
    with pytest.raises(BillPdfError, match="not a PDF"):
        svc.fetch_and_save_pdf("X-1")


def test_an_unwritable_folder_is_explained(svc, tmp_path, monkeypatch):
    serve(monkeypatch, b"%PDF-1.4")
    blocker = tmp_path / "VrikshaStudios"
    blocker.write_text("a file where the folder should be")
    with pytest.raises(BillPdfError, match="could not be saved"):
        svc.fetch_and_save_pdf("X-1")


def test_open_falls_back_to_the_browser_when_no_pdf_program_is_set(tmp_path, monkeypatch):
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF")
    opened = []

    def nothing_registered(path):
        raise OSError("no association")

    monkeypatch.setattr(sales_module.os, "startfile", nothing_registered, raising=False)
    monkeypatch.setattr(sales_module.webbrowser, "open", lambda url: opened.append(url) or True)
    SalesService.open_pdf(pdf)
    assert opened and opened[0].startswith("file:///") and opened[0].endswith("b.pdf")
    monkeypatch.setattr(sales_module.webbrowser, "open", lambda url: False)
    with pytest.raises(BillPdfError, match="No program on this PC"):
        SalesService.open_pdf(pdf)


def test_bill_history_tells_the_user_why_a_reprint_failed(qapp, monkeypatch, dialogs):
    monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: (_ for _ in ()).throw(BillPdfError("The server could not make the PDF: boom")))
    s = SalesHistoryScreen()
    s._reprint_invoice({"invoice_number": "NTD-1"})
    kind, title, text = dialogs[-1]
    assert kind == "critical" and "NTD-1" in text and "boom" in text
