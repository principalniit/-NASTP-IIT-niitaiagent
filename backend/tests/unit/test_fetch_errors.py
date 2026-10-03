"""Failed requests are described in plain words in crawl notes and page errors."""

import ssl

import httpx

from app.modules.crawler.fetcher import describe_error


def _wrapped(cause: BaseException) -> httpx.ConnectError:
    try:
        try:
            raise cause
        except BaseException as inner:
            raise httpx.ConnectError("connect failed") from inner
    except httpx.ConnectError as exc:
        return exc


def test_certificate_problems_are_named() -> None:
    error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    error.verify_message = "unable to get local issuer certificate"
    text = describe_error(_wrapped(error))
    assert "security certificate could not be verified" in text
    assert "full certificate chain" in text


def test_dns_refused_and_reset_are_named() -> None:
    assert "could not be found (DNS)" in describe_error(_wrapped(OSError("Could not resolve x")))
    assert "refused the connection" in describe_error(_wrapped(ConnectionRefusedError()))
    assert "closed the connection" in describe_error(_wrapped(ConnectionResetError()))
    assert describe_error(httpx.ConnectError("nope")) == "Could not connect to the server"
