"""A small local website for crawler tests, served from a background thread."""

import hashlib
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def html(title: str, body: str, head: str = "") -> bytes:
    return (
        f"<!doctype html><html lang='en'><head><title>{title}</title>"
        f"<meta name='description' content='{title} description'>{head}</head>"
        f"<body>{body}</body></html>"
    ).encode()


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0


@dataclass
class RequestRecord:
    path: str
    user_agent: str
    at: float
    headers: dict[str, str]


class FixtureSite:
    def __init__(self) -> None:
        self.routes: dict[str, Response] = {}
        self.requests: list[RequestRecord] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FixtureSite":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def page(self, path: str, title: str, body: str, head: str = "", **headers: str) -> None:
        self.routes[path] = Response(
            200, html(title, body, head), {"Content-Type": "text/html; charset=utf-8", **headers}
        )

    def paths(self) -> list[str]:
        return [r.path for r in self.requests]

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        site = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                site.requests.append(
                    RequestRecord(
                        self.path,
                        self.headers.get("User-Agent", ""),
                        time.monotonic(),
                        dict(self.headers),
                    )
                )
                response = site.routes.get(self.path)
                if response is None:
                    response = Response(
                        404, html("Not found", "<p>Missing</p>"), {"Content-Type": "text/html"}
                    )
                if response.delay:
                    time.sleep(response.delay)
                etag = None
                if response.status == 200 and response.body:
                    etag = '"' + hashlib.sha256(response.body).hexdigest()[:16] + '"'
                    if self.headers.get("If-None-Match") == etag:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.end_headers()
                        return
                self.send_response(response.status)
                for key, value in response.headers.items():
                    self.send_header(key, value)
                if etag:
                    self.send_header("ETag", etag)
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                self.wfile.write(response.body)

        return Handler


def build_standard_site(site: FixtureSite) -> None:
    b = site.base
    site.routes["/robots.txt"] = Response(
        200,
        f"User-agent: *\nDisallow: /private/\nSitemap: {b}/sitemap.xml\n".encode(),
        {"Content-Type": "text/plain"},
    )
    site.routes["/sitemap.xml"] = Response(
        200,
        (
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{b}/</loc></url><url><loc>{b}/about</loc></url>"
            f"<url><loc>{b}/orphan</loc></url><url><loc>{b}/admissions</loc></url>"
            "</urlset>"
        ).encode(),
        {"Content-Type": "application/xml"},
    )
    shared = (
        "<p>We are a technology institute offering programmes in computing and engineering.</p>"
    )
    site.page(
        "/",
        "Home",
        "<h1>Home</h1><p>Welcome</p>"
        "<a href='/about'>About us</a> <a href='/admissions'>Admissions</a>"
        "<a href='/old-page'>Old</a> <a href='/missing'>Missing</a> <a href='/error'>Error</a>"
        "<a href='/private/secret'>Private</a> <a href='/file.pdf'>PDF</a>"
        "<a href='https://external.example.com/'>External</a> <a href='/wp-admin/x'>Admin</a>"
        "<a href='/deep/1'>Deep</a> <a href='/about#team'>Team</a> <a href='/redirect-out'>Out</a>"
        "<img src='/logo.png'>",
        head="<link rel='canonical' href='/'>",
    )
    site.page(
        "/about",
        "About",
        f"<h1>About</h1>{shared}<a href='/'>Home</a><a href='/about-copy'>Copy</a>",
    )
    site.page(
        "/about-copy",
        "About copy",
        f"<h1>About</h1>{shared}<a href='/'>Home</a><a href='/about-copy'>Copy</a>",
    )
    site.page(
        "/admissions",
        "Admissions",
        "<h1>Admissions</h1><p>Apply now</p><a href='/about'>About</a>",
        head="<meta name='robots' content='noindex'>",
    )
    site.routes["/old-page"] = Response(301, b"", {"Location": "/new-page"})
    site.page("/new-page", "New page", "<h1>New</h1><p>Moved here</p>")
    site.routes["/redirect-out"] = Response(
        302, b"", {"Location": f"http://127.0.0.2:{site.port}/"}
    )
    site.routes["/error"] = Response(500, b"oops", {"Content-Type": "text/plain"})
    site.routes["/file.pdf"] = Response(200, b"%PDF-1.4 fake", {"Content-Type": "application/pdf"})
    site.page("/private/secret", "Secret", "<p>Should never be fetched</p>")
    site.page("/wp-admin/x", "Admin", "<p>Excluded</p>")
    site.page("/orphan", "Orphan", "<h1>Orphan</h1><p>Only in the sitemap</p>")
    for i in range(1, 8):
        site.page(f"/deep/{i}", f"Deep {i}", f"<p>Level {i}</p><a href='/deep/{i + 1}'>Next</a>")
