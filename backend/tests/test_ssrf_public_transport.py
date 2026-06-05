"""Public-API SSRF transport wrapper tests.

These tests assert the **primary** SSRF enforcement layer is the public
``httpx.AsyncBaseTransport`` / ``httpx.BaseTransport`` wrapper, NOT the
private-injection transport. They:

1. Confirm the safe factories stack the public wrapper on top of the
   private-injection transport.
2. Confirm the public wrapper blocks a request to a private IP at the
   transport layer (no monkey-patch, no ``_pool`` access required).
3. Confirm the public wrapper blocks the request even if the inner
   transport is a vanilla ``httpx.AsyncHTTPTransport`` (i.e. the
   public-API layer is the primary enforcement on its own).
4. Confirm the public wrapper survives a corrupted inner transport
   (``_pool._network_backend`` swapped to a hostile backend) — proving
   the public-API layer does not depend on the inner layer.
"""

from __future__ import annotations

import inspect
from typing import Any

import httpx
import pytest
from app.url_safety import (
    _UrlValidatingAsyncTransport,
    _UrlValidatingSyncTransport,
    get_safe_async_client,
    get_safe_client,
)


class _HostileInnerAsyncTransport(httpx.AsyncBaseTransport):
    """Inner transport that, if reached, would happily connect to a private IP.

    This proves the OUTER ``_UrlValidatingAsyncTransport`` blocks the
    request before this inner transport is invoked.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:  # noqa: ARG002
        self.calls.append(str(request.url))
        msg = "Hostile inner transport must never be reached for a private IP."
        raise AssertionError(msg)

    async def aclose(self) -> None:
        pass


class _HostileInnerSyncTransport(httpx.BaseTransport):
    """Sync variant of ``_HostileInnerAsyncTransport``."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # noqa: ARG002
        self.calls.append(str(request.url))
        msg = "Hostile inner sync transport must never be reached for a private IP."
        raise AssertionError(msg)

    def close(self) -> None:
        pass


def test_public_wrapper_subclasses_public_base_classes() -> None:
    """The primary SSRF layer must use ONLY public httpx APIs."""
    assert issubclass(_UrlValidatingAsyncTransport, httpx.AsyncBaseTransport)
    assert issubclass(_UrlValidatingSyncTransport, httpx.BaseTransport)
    # The primary path must NOT inherit from any class that depends on
    # private httpx internals.
    assert httpx.AsyncBaseTransport in _UrlValidatingAsyncTransport.__mro__
    assert httpx.BaseTransport in _UrlValidatingSyncTransport.__mro__


def test_safe_async_client_uses_public_wrapper_outermost() -> None:
    """``get_safe_async_client`` must stack the public wrapper on top.

    The OUTER transport of the returned client is the public-API
    wrapper; the inner transport is the private-injection transport.
    The wrapper is what an attacker can probe first, so it must be the
    layer that actually enforces the SSRF check.
    """

    async def _probe() -> None:
        async with get_safe_async_client() as client:
            assert isinstance(client._transport, _UrlValidatingAsyncTransport)
            inner = client._transport._inner
            assert inner is not None
            assert not isinstance(inner, _UrlValidatingAsyncTransport)

    import asyncio

    asyncio.run(_probe())


def test_safe_client_uses_public_wrapper_outermost() -> None:
    """Sync variant of the primary-outer assertion."""
    with get_safe_client() as client:
        assert isinstance(client._transport, _UrlValidatingSyncTransport)
        inner = client._transport._inner
        assert inner is not None
        assert not isinstance(inner, _UrlValidatingSyncTransport)


@pytest.mark.asyncio
async def test_public_wrapper_blocks_private_ip_even_with_vanilla_inner() -> None:
    """Primary layer blocks private-IP requests even when the inner
    transport is a vanilla (unprotected) ``AsyncHTTPTransport``.

    The inner transport is wired with a hostile spy that would happily
    connect to a private IP — proving the public wrapper, not the
    inner, is the actual enforcement.
    """
    hostile = _HostileInnerAsyncTransport()
    transport = _UrlValidatingAsyncTransport(hostile)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises((ValueError, httpx.ConnectError, httpx.RequestError)):
            await client.get("http://127.0.0.1:9999/")
    assert hostile.calls == [], "Public-API wrapper must short-circuit the request before the inner transport."


def test_public_wrapper_blocks_private_ip_sync() -> None:
    """Sync variant of the primary-outer assertion."""
    hostile = _HostileInnerSyncTransport()
    transport = _UrlValidatingSyncTransport(hostile)
    with httpx.Client(transport=transport) as client:
        with pytest.raises((ValueError, httpx.ConnectError, httpx.RequestError)):
            client.get("http://127.0.0.1:9999/")
    assert hostile.calls == [], "Public-API wrapper must short-circuit the request before the inner sync transport."


@pytest.mark.asyncio
async def test_public_wrapper_survives_hostile_backend_injection() -> None:
    """Primary layer survives a hostile ``_pool._network_backend``.

    If the inner transport's connection pool has been replaced with a
    backend that would happily connect to a private IP, the
    public-API layer must STILL block the request at the request
    layer. This is the property that makes the public wrapper the
    PRIMARY layer (independent of httpx internals).
    """

    class _HostilePool:
        _network_backend = object()
        _ssrf_safe = False  # marker deliberately wrong

        async def aclose(self) -> None:  # required by AsyncHTTPTransport
            return None

    class _HostileAsyncTransport(httpx.AsyncHTTPTransport):
        def __init__(self) -> None:
            super().__init__()
            # Simulate a hostile (or upstream-broken) pool mutation.
            self._pool = _HostilePool()  # type: ignore[assignment]

    transport = _UrlValidatingAsyncTransport(_HostileAsyncTransport())
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises((ValueError, httpx.ConnectError, httpx.RequestError)):
            await client.get("http://127.0.0.1:9999/")


def test_safe_factories_source_uses_public_wrapper() -> None:
    """Both factories must reference both transport layers by name in source.

    Acts as a regression guard: if someone replaces the factory body
    with a single ``httpx.AsyncHTTPTransport`` (or ``SafeAsyncHTTPTransport``
    only), the source no longer stacks the public-API wrapper on top
    of the private-injection transport, and this assertion fires.
    """
    for fn in (get_safe_async_client, get_safe_client):
        src: str = inspect.getsource(fn)
        assert "_UrlValidating" in src, f"{fn.__name__} does not reference the public-API wrapper"
        assert "SafeAsyncHTTPTransport" in src or "SafeHTTPTransport" in src, (
            f"{fn.__name__} does not reference the private-injection transport"
        )


def test_public_wrapper_does_not_touch_private_pool_attrs() -> None:
    """The primary layer must NOT mutate ``_pool`` or other private attrs.

    The whole point of the public-API wrapper is that it does not depend
    on httpx internals. This assertion checks the source for the
    forbidden attributes.
    """
    for cls in (_UrlValidatingAsyncTransport, _UrlValidatingSyncTransport):
        src: str = inspect.getsource(cls)
        for forbidden in ("_pool", "_network_backend", "httpcore._backends", "httpcore._network"):
            assert forbidden not in src, (
                f"{cls.__name__} references forbidden private attribute {forbidden!r}; "
                "the public-API layer must be private-attr-free."
            )


def test_verify_ssrf_self_check_acknowledges_public_layer() -> None:
    """The startup self-check must verify the public-API layer is present.

    If the public-API wrapper is removed in a future refactor, the
    self-check should still report ``ok=False`` rather than silently
    accepting the regression.
    """
    from app.url_safety import verify_ssrf_self_check

    diag: dict[str, Any] = verify_ssrf_self_check()
    assert diag.get("ok") is True
    assert diag.get("public_transport_present") is True, diag
    assert diag.get("pool_attr_present") is True, diag
    assert diag.get("marker_present") is True, diag
