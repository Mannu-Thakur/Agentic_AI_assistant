import socket

import pytest

from app.tools.network_safety import PublicAddressNetworkBackend, UnsafeOutboundUrl


@pytest.mark.anyio
async def test_outbound_socket_uses_the_validated_numeric_address(monkeypatch):
    class RecordingBackend:
        connected_host = None

        async def connect_tcp(self, **kwargs):
            self.connected_host = kwargs["host"]
            return "connected"

        async def sleep(self, _seconds):
            return None

    records = [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
    ]
    monkeypatch.setattr("app.tools.network_safety.socket.getaddrinfo", lambda *_args, **_kwargs: records)
    backend = RecordingBackend()
    pinned = PublicAddressNetworkBackend(backend)

    result = await pinned.connect_tcp("mcp.example", 443, timeout=1.0)

    assert result == "connected"
    assert backend.connected_host == "8.8.8.8"


@pytest.mark.anyio
async def test_outbound_socket_rejects_a_private_dns_answer_before_connect(monkeypatch):
    class RecordingBackend:
        connected = False

        async def connect_tcp(self, **_kwargs):
            self.connected = True
            return "connected"

        async def sleep(self, _seconds):
            return None

    records = [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
    ]
    monkeypatch.setattr("app.tools.network_safety.socket.getaddrinfo", lambda *_args, **_kwargs: records)
    backend = RecordingBackend()
    pinned = PublicAddressNetworkBackend(backend)

    with pytest.raises(UnsafeOutboundUrl, match="private or reserved"):
        await pinned.connect_tcp("mcp.example", 443)

    assert backend.connected is False


@pytest.mark.anyio
async def test_remote_mcp_http_transport_uses_dns_pinning_backend():
    from app.tools.mcp_client import McpHttpClient

    client = McpHttpClient("https://mcp.example/")
    await client._ensure_client()
    try:
        transport = client._client._transport
        assert isinstance(transport._pool._network_backend, PublicAddressNetworkBackend)
    finally:
        await client.close()
