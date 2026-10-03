"""SSRF protection for every outbound crawler connection.

The crawler must never become a way to reach the platform's own network. Protection is
applied at connection time, inside the HTTP client's network backend:

1. The hostname is resolved.
2. Every resolved address is checked. If any is not public (and not explicitly allowed),
   the connection is refused. Checking all records defeats mixed public/private answers.
3. The socket is opened to the exact address that was checked, so a second DNS answer
   (DNS rebinding) can never be substituted between the check and the connection.

TLS still verifies the certificate against the original hostname, because the TLS layer
receives the hostname separately from the socket address. Redirects are followed by the
fetcher one hop at a time, so each hop passes through this check again.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

import httpcore
import httpx

from app.core.config import get_settings
from app.core.urls import is_public_ip

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
Resolver = Callable[[str, int], Awaitable[list[str]]]


class BlockedDestinationError(Exception):
    """Raised when a connection would reach a forbidden address or port."""


@dataclass(frozen=True)
class SafetyPolicy:
    allowed_ports: frozenset[int] = frozenset({80, 443})
    allowed_private_networks: tuple[IPNetwork, ...] = field(default_factory=tuple)

    @classmethod
    def from_settings(cls, extra_ports: Iterable[int] = ()) -> "SafetyPolicy":
        return cls(
            allowed_ports=frozenset({80, 443, *extra_ports}),
            allowed_private_networks=tuple(get_settings().crawler_private_networks),
        )

    def is_allowed_ip(self, ip: IPAddress) -> bool:
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if any(ip in net for net in self.allowed_private_networks):
            return True
        return is_public_ip(ip)


async def system_resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]  # drop IPv6 zone identifiers
        if address not in addresses:
            addresses.append(address)
    return addresses


async def resolve_checked(
    host: str, port: int, policy: SafetyPolicy, resolver: Resolver = system_resolve
) -> str:
    """Return one address for host that is safe to connect to, or raise."""
    return (await resolve_all_checked(host, port, policy, resolver))[0]


def _ipv4_first(addresses: list[str]) -> list[str]:
    """IPv4 before IPv6, keeping the resolver's order within each family.

    Browsers fall back between families (Happy Eyeballs); a crawler that tried only the
    first answer failed on networks with broken IPv6 while the site worked in a browser.
    """
    return sorted(addresses, key=lambda a: ipaddress.ip_address(a).version)


async def resolve_all_checked(
    host: str, port: int, policy: SafetyPolicy, resolver: Resolver = system_resolve
) -> list[str]:
    """Every address for host, IPv4 first, when all of them are safe; otherwise raise."""
    if port not in policy.allowed_ports:
        raise BlockedDestinationError(f"Port {port} is not allowed")
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not policy.is_allowed_ip(literal):
            raise BlockedDestinationError("Destination address is not public")
        return [literal.compressed]
    try:
        addresses = await resolver(host, port)
    except OSError as exc:
        raise httpcore.ConnectError(f"Could not resolve {host}") from exc
    if not addresses:
        raise httpcore.ConnectError(f"Could not resolve {host}")
    for address in addresses:
        if not policy.is_allowed_ip(ipaddress.ip_address(address)):
            raise BlockedDestinationError("Destination resolves to a non-public address")
    return _ipv4_first(addresses)


# How long to wait for one address before trying the next one of the same host.
FALLBACK_TIMEOUT = 5.0


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        policy: SafetyPolicy,
        resolver: Resolver = system_resolve,
        inner: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._policy = policy
        self._resolver = resolver
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        # Every address was checked above, from one resolution: the socket only ever
        # goes to one of them, so a second (rebinding) answer is never used.
        addresses = await resolve_all_checked(host, port, self._policy, self._resolver)
        for index, address in enumerate(addresses):
            last = index == len(addresses) - 1
            attempt = timeout if last or timeout is None else min(timeout, FALLBACK_TIMEOUT)
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=attempt,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError):
                if last:
                    raise
        raise httpcore.ConnectError(f"Could not connect to {host}")  # pragma: no cover

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore interface
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise BlockedDestinationError("Unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class GuardedTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose every connection goes through GuardedNetworkBackend.

    Environment proxies are ignored on purpose: a proxy would make the connection
    address differ from the checked one.
    """

    def __init__(
        self,
        policy: SafetyPolicy,
        resolver: Resolver = system_resolve,
        max_connections: int = 10,
        inner_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        super().__init__(trust_env=False, retries=0)
        self.network_backend = GuardedNetworkBackend(policy, resolver, inner_backend)
        # Replaces the pool built by the parent class. Pinned httpx version range in
        # pyproject.toml; tests/security/test_ssrf.py fails if this hook stops working.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=self.network_backend,
        )
