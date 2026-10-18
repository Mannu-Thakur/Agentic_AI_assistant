"""Outbound-network guardrails for tools that accept a user-controlled URL.

The application is a public service.  A URL supplied to an MCP or web-fetch
tool must never become a request to the host, container metadata service, a
private VPC address, or another internal service.  This module deliberately
does not follow redirects; callers must validate each destination themselves.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit


class UnsafeOutboundUrl(ValueError):
    """Raised when a URL is not safe for a server-side outbound request."""


_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "host.docker.internal",
    "gateway.docker.internal",
    "kubernetes.default.svc",
}


def _normalise_url(value: str, *, allow_http: bool) -> SplitResult:
    value = (value or "").strip()
    if not value:
        raise UnsafeOutboundUrl("A remote URL is required.")
    if "://" not in value:
        value = ("http://" if allow_http else "https://") + value

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeOutboundUrl("Only http and https URLs are supported.")
    if parsed.scheme == "http" and not allow_http:
        raise UnsafeOutboundUrl("HTTPS is required for remote MCP servers outside development.")
    if not parsed.hostname:
        raise UnsafeOutboundUrl("The remote URL must include a hostname.")
    if parsed.username or parsed.password:
        raise UnsafeOutboundUrl("Credentials embedded in a remote URL are not allowed.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeOutboundUrl("The remote URL contains an invalid port.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeOutboundUrl("The remote URL contains an invalid port.")
    return parsed


def _assert_public_hostname(hostname: str) -> None:
    host = hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTNAMES or host.endswith((".local", ".internal", ".localhost", ".test")):
        raise UnsafeOutboundUrl("Requests to local or internal hostnames are blocked.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise UnsafeOutboundUrl("Requests to private, loopback, link-local, or reserved IP addresses are blocked.")


def normalise_outbound_url(value: str, *, allow_http: bool) -> str:
    """Validate URL syntax and literal-IP safety, then return its canonical form."""
    parsed = _normalise_url(value, allow_http=allow_http)
    _assert_public_hostname(parsed.hostname or "")
    # Fragments are never transmitted and only add ambiguity to audit records.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


async def assert_public_dns_resolution(value: str, *, allow_http: bool) -> str:
    """Validate a URL and ensure every DNS answer is globally routable.

    DNS is intentionally resolved immediately before a request.  This narrows
    DNS-rebinding risk: every new MCP request re-checks the current destination.
    """
    canonical = normalise_outbound_url(value, allow_http=allow_http)
    parsed = urlsplit(canonical)
    host = parsed.hostname or ""
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeOutboundUrl("The remote hostname could not be resolved.") from exc

    addresses = {item[4][0] for item in infos}
    if not addresses:
        raise UnsafeOutboundUrl("The remote hostname did not resolve to an address.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:  # getaddrinfo should always return an IP literal
            raise UnsafeOutboundUrl("The remote hostname resolved to an invalid address.") from exc
        if not ip.is_global:
            raise UnsafeOutboundUrl("The remote hostname resolves to a private or reserved address.")
    return canonical


class PublicAddressNetworkBackend:
    """Resolve and pin a checked public IP for each new outbound TCP socket.

    A separate URL preflight is insufficient: an HTTP client's own DNS lookup
    could receive a different answer (DNS rebinding) after preflight. This
    httpcore-compatible backend connects to a validated numeric address while
    httpcore retains the original hostname for TLS SNI and certificate checks.
    """

    def __init__(self, backend: Any = None):
        if backend is None:
            from httpcore._backends.auto import AutoBackend

            backend = AutoBackend()
        self._backend = backend

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise UnsafeOutboundUrl("The remote hostname could not be resolved.") from exc

        addresses: list[str] = []
        for info in infos:
            candidate = info[4][0]
            try:
                ip = ipaddress.ip_address(candidate)
            except ValueError as exc:
                raise UnsafeOutboundUrl("The remote hostname resolved to an invalid address.") from exc
            if not ip.is_global:
                raise UnsafeOutboundUrl("The remote hostname resolves to a private or reserved address.")
            if str(ip) not in addresses:
                addresses.append(str(ip))

        if not addresses:
            raise UnsafeOutboundUrl("The remote hostname did not resolve to an address.")

        # Pass a numeric literal to the socket backend. The OS therefore cannot
        # perform a second, attacker-controlled hostname lookup for this socket.
        return await self._backend.connect_tcp(
            host=addresses[0],
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> Any:
        raise UnsafeOutboundUrl("Unix domain sockets are not allowed for remote MCP requests.")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)
