"""PDF export. Chromium (through Playwright) prints the stored HTML report.

Optional: install with `uv sync --extra pdf` and `uv run playwright install chromium`.
Without it, reports are still produced as HTML and the PDF is marked unavailable.
The page is printed with JavaScript disabled and every network request refused, so
report content cannot make the renderer fetch anything.
"""

import logging
import os

from markupsafe import escape

from app.core.config import get_settings

logger = logging.getLogger(__name__)

INSTALL_HINT = (
    "PDF export is not installed on this server. Run `uv sync --extra pdf` and "
    "`uv run playwright install chromium` in the backend folder, then restart the worker. "
    "The HTML report can be printed to PDF from the browser meanwhile."
)


def _sandbox() -> bool:
    """Use Chromium's own sandbox, which it refuses to start under the root account."""
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if is_root:
        logger.warning("PDF renderer runs as root, so Chromium's sandbox is off; run as a user")
    return not is_root


class PdfUnavailableError(Exception):
    """No PDF renderer is installed. The message is safe to show."""


async def render_pdf(html: str, footer_text: str) -> bytes:
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise PdfUnavailableError(INSTALL_HINT) from exc

    browser_path = get_settings().report_pdf_browser_path or None
    footer = (
        '<div style="width:100%;font-size:8px;color:#6b7280;padding:0 14mm;'
        'display:flex;justify-content:space-between">'
        f"<span>{escape(footer_text)}</span>"
        '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
        "</div>"
    )
    async with async_playwright() as p:
        sandbox = _sandbox()
        try:
            try:
                browser = await p.chromium.launch(
                    executable_path=browser_path, chromium_sandbox=sandbox
                )
            except PlaywrightError:
                if not sandbox:
                    raise
                # Some hosts (containers, locked-down kernels) cannot start the sandbox. The
                # page still has JavaScript and the network off, so print without it.
                logger.warning(
                    "Chromium's sandbox could not start; printing without it. Enable "
                    "unprivileged user namespaces on this host to restore it."
                )
                browser = await p.chromium.launch(
                    executable_path=browser_path, chromium_sandbox=False
                )
        except PlaywrightError as exc:
            logger.warning("PDF renderer could not start", extra={"error": str(exc)[:300]})
            raise PdfUnavailableError(INSTALL_HINT) from exc
        try:
            context = await browser.new_context(java_script_enabled=False, offline=True)
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(html, wait_until="load", timeout=60_000)
            return await page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer,
                margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
            )
        finally:
            await browser.close()
