"""SSRF protection: connection-time address checks, pinning and redirect handling."""

import ipaddress
from collections.abc import Iterable

import httpcore
import pytest

from app.modules.crawler.fetcher import Fetcher
from app.modules.crawler.url_safety import (
    BlockedDestinationError,
    GuardedNetworkBackend,
    SafetyPolicy,
    resolve_checked,
)

POLICY = SafetyPolicy()


def fake_resolver(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str, port: int) -> list[str]:
        return mapping[host]

    return resolve


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.8",
        "172.16.5.4",
        "192.168.0.1",
        "169.254.169.254",
        "100.64.1.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd12::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "224.0.0.1",
        "255.255.255.255",
        "198.18.0.1",
    ],
)
async def test_non_public_resolutions_are_blocked(address: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await resolve_checked(
            "evil.example", 80, POLICY, fake_resolver({"evil.example": [address]})
        )


async def test_any_private_record_blocks_the_host() -> None:
    resolver = fake_resolver({"mixed.example": ["93.184.216.34", "10.0.0.1"]})
    with pytest.raises(BlockedDestinationError):
        await resolve_checked("mixed.example", 443, POLICY, resolver)


async def test_ip_literals_and_ports_are_checked() -> None:
    with pytest.raises(BlockedDestinationError):
        await resolve_checked("127.0.0.1", 80, POLICY)
    with pytest.raises(BlockedDestinationError):
        await resolve_checked("[::1]", 80, POLICY)
    with pytest.raises(BlockedDestinationError):
        await resolve_checked("93.184.216.34", 22, POLICY)
    assert await resolve_checked("93.184.216.34", 443, POLICY) == "93.184.216.34"


async def test_allowlisted_private_network() -> None:
    policy = SafetyPolicy(allowed_private_networks=(ipaddress.ip_network("10.1.0.0/16"),))
    resolver = fake_resolver({"staging.local.example": ["10.1.2.3"]})
    assert await resolve_checked("staging.local.example", 80, policy, resolver) == "10.1.2.3"
    with pytest.raises(BlockedDestinationError):
        await resolve_checked("x.example", 80, policy, fake_resolver({"x.example": ["10.2.0.1"]}))


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(  # type: ignore[override]
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109
        local_address: str | None = None,
        socket_options: Iterable[object] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected.append((host, port))
        raise httpcore.ConnectError("recorded, not connected")


async def test_connection_is_pinned_to_the_checked_address() -> None:
    """DNS rebinding: a second, private answer must never be used for the socket."""
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])

    async def rebinding_resolver(host: str, port: int) -> list[str]:
        return next(answers)

    inner = RecordingBackend()
    backend = GuardedNetworkBackend(POLICY, rebinding_resolver, inner)
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("rebind.example", 80)
    assert inner.connected == [("93.184.216.34", 80)]
    with pytest.raises(BlockedDestinationError):
        await backend.connect_tcp("rebind.example", 80)
    assert len(inner.connected) == 1


async def test_fetcher_uses_the_guarded_backend() -> None:
    """Fails if an httpx upgrade stops the guarded pool from being used."""
    fetcher = Fetcher(
        user_agent="test",
        timeout_seconds=2,
        max_bytes=1000,
        max_redirects=3,
        policy=POLICY,
        resolver=fake_resolver({"internal.example": ["10.0.0.5"]}),
    )
    try:
        result = await fetcher.fetch("http://internal.example/", in_scope=lambda _: True)
        assert result.outcome == "blocked_destination"
        metadata = await fetcher.fetch("http://169.254.169.254/latest/", in_scope=lambda _: True)
        assert metadata.outcome == "blocked_destination"
    finally:
        await fetcher.aclose()


async def test_environment_proxies_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    fetcher = Fetcher(
        user_agent="test",
        timeout_seconds=2,
        max_bytes=1000,
        max_redirects=3,
        policy=POLICY,
        resolver=fake_resolver({"internal.example": ["10.0.0.5"]}),
    )
    try:
        assert fetcher.client._mounts == {}
        result = await fetcher.fetch("http://internal.example/", in_scope=lambda _: True)
        assert result.outcome == "blocked_destination"
    finally:
        await fetcher.aclose()
