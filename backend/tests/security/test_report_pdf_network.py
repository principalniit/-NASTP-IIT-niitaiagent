"""The PDF renderer never fetches anything, whatever the report HTML asks for."""

import os

import pytest

from app.core.config import get_settings
from app.modules.reports.pdf import PdfUnavailableError, render_pdf
from tests.fixtures.site import FixtureSite


async def test_pdf_rendering_makes_no_network_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(), "report_pdf_browser_path", os.environ.get("TEST_PDF_BROWSER_PATH", "")
    )
    with FixtureSite() as site:
        site.page("/track.png", "x", "x")
        html = (
            "<html><head>"
            f"<link rel='stylesheet' href='{site.base}/style.css'>"
            f"<script src='{site.base}/app.js'></script>"
            "</head><body><h1>Report</h1>"
            f"<img src='{site.base}/track.png'>"
            f"<iframe src='{site.base}/frame'></iframe>"
            f"<script>fetch('{site.base}/beacon')</script>"
            "</body></html>"
        )
        try:
            pdf = await render_pdf(html, "Footer <b>text</b>")
        except PdfUnavailableError:
            pytest.skip("No Chromium for PDF rendering here (set TEST_PDF_BROWSER_PATH)")
        assert pdf.startswith(b"%PDF")
        assert site.requests == []
