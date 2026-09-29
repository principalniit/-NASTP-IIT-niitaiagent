import pytest

from app.core.urls import UnsafeURLError, normalise_site_url


@pytest.mark.parametrize(
    ("raw", "expected_url", "expected_host"),
    [
        ("niit.edu.pk", "https://niit.edu.pk/", "niit.edu.pk"),
        ("HTTPS://NIIT.edu.PK/Admissions", "https://niit.edu.pk/Admissions", "niit.edu.pk"),
        ("https://example.org:443/a#frag", "https://example.org/a", "example.org"),
        ("http://example.org:8080/", "http://example.org:8080/", "example.org"),
        ("https://example.org/?q=1", "https://example.org/?q=1", "example.org"),
        ("https://bücher.example/", "https://xn--bcher-kva.example/", "xn--bcher-kva.example"),
        ("https://8.8.8.8/", "https://8.8.8.8/", "8.8.8.8"),
    ],
)
def test_normalises_valid_urls(raw: str, expected_url: str, expected_host: str) -> None:
    assert normalise_site_url(raw) == (expected_url, expected_host)


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://example.org/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pass@example.org/",
        "http://localhost/",
        "http://LOCALHOST./",
        "http://foo.localhost/",
        "http://metadata.google.internal/",
        "http://printer.local/",
        "http://intranet/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://172.16.1.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://224.0.0.1/",
        "https://example.org:99999/",
        "https://",
    ],
)
def test_rejects_unsafe_urls(raw: str) -> None:
    with pytest.raises(UnsafeURLError):
        normalise_site_url(raw)
