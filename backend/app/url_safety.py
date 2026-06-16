import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpcore
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Allowed outbound HTTP(S) ports. Restricts SSRF probes to the standard
# web service ports; an attacker cannot use the proxy to reach internal
# services listening on SSH, Redis, Memcached, Postgres, etc.
_ALLOWED_HTTP_PORTS: frozenset[int] = frozenset({80, 443, 8080, 8443})


# ── Injectable DNS resolver ───────────────────────────────────────────
# Allow tests to inject a fake resolver so they never depend on real DNS.
# The resolver signature is ``(host: str) -> list[str]`` returning
# IP-address strings.  Production uses the default (``socket.getaddrinfo``).
def _default_resolver(hostname: str) -> list[str]:
    """Default DNS resolver — delegates to :func:`socket.getaddrinfo`."""
    addrs = socket.getaddrinfo(hostname, None)
    return [str(addr[4][0]) for addr in addrs]


_resolver: Callable[[str], list[str]] | None = None
"""Injectable resolver override.  ``None`` means use :func:`_default_resolver`."""


def set_dns_resolver(resolver: Callable[[str], list[str]] | None) -> None:
    """Override the DNS resolver used by URL safety checks.

    Parameters
    ----------
    resolver : callable or None
        A callable ``(host: str) -> list[str]`` that returns resolved IP
        addresses for the given hostname.  Pass ``None`` to reset to the
        default (``socket.getaddrinfo``).

    Tests should call this (via ``monkeypatch``) to inject a fake resolver
    that never hits real DNS, enabling deterministic, offline URL-safety
    assertions.

    """
    global _resolver
    _resolver = resolver


def _get_resolver() -> Callable[[str], list[str]]:
    """Return the active resolver — override if set, else default."""
    return _resolver if _resolver is not None else _default_resolver


def is_safe_ip(ip_str: str) -> bool:
    """Return True if the IP address is a public, routable IP address.

    Rejects loopback, private, link-local, multicast, reserved, etc.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check standard unsafe ranges plus non-globally-routable ranges.
        # `is_global` rejects documentation, benchmark, and IETF-assigned
        # blocks that the other predicates do not always cover.
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or not ip.is_global
        )
    except ValueError:
        return False


def _is_smoke_allowed_internal_host(hostname: str | None) -> bool:
    if not hostname or not settings.SMOKE_TEST_MODE:
        return False

    host = hostname.strip("[]").lower()
    for raw_entry in settings.ALLOWED_INTERNAL_HOSTS.split(","):
        entry = raw_entry.strip().lower()
        if not entry:
            continue
        if entry.strip("[]") == host:
            return True
        parsed = urlparse(f"http://{entry}")
        if parsed.hostname and parsed.hostname.strip("[]").lower() == host:
            return True
    return False


def _normalize_ip_literal(hostname: str) -> str | None:
    """Recognise non-canonical IPv4 literal forms and return the canonical dotted-decimal string.

    ``ipaddress.ip_address`` only accepts canonical decimal/dotted forms,
    so a hostname like ``0x7f.0.0.1`` (hex), ``0177.0.0.1`` (octal), or
    ``2130706433`` (single decimal) would fall through to DNS resolution
    and bypass our IP-literal safety check. This helper uses
    :func:`socket.inet_aton` (which accepts all of these forms) to
    normalise the literal, and returns the canonical dotted-decimal
    string the rest of the safety checks can validate.

    Returns ``None`` if the input is not an IPv4 literal in any form.
    IPv6 is handled by :mod:`ipaddress` directly in the caller.
    """
    candidate = hostname.strip("[]")
    # Reject anything that has DNS-illegal characters before we hand it
    # to inet_aton (which silently accepts some weird inputs).
    if not candidate or any(c.isspace() or ord(c) < 32 for c in candidate):
        return None
    # Single-decimal form (e.g. "2130706433") is sometimes accepted by
    # inet_aton but is not a valid hostname; reject it explicitly.
    if "." not in candidate:
        return None
    try:
        packed = socket.inet_aton(candidate)
    except OSError:
        return None
    return socket.inet_ntoa(packed)


def validate_public_http_url(url: str) -> None:
    """Raise ValueError if the URL resolves to or points to a private / internal network target.

    Allows configured internal hosts via settings.ALLOWED_INTERNAL_HOSTS (e.g. 'nginx' for compose tests).
    """
    if not url:
        msg = "URL cannot be empty"
        _record_ssrf_reject("empty_url")
        raise ValueError(msg)

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = f"URL scheme '{parsed.scheme}' is not supported. Only http and https are allowed."
        _record_ssrf_reject("bad_scheme")
        raise ValueError(msg)

    hostname = parsed.hostname
    if not hostname:
        msg = f"URL '{url}' does not contain a valid hostname."
        _record_ssrf_reject("no_hostname")
        raise ValueError(msg)

    # Port allowlist: restrict outbound HTTP requests to well-known web
    # service ports. Prevents an attacker from probing internal services
    # listening on non-HTTP ports (SSH, Redis, Memcached, etc.). The
    # allowlist is bypassed in smoke-test mode (where integration
    # endpoints may bind to ephemeral ports).
    if parsed.port is not None and not settings.SMOKE_TEST_MODE and parsed.port not in _ALLOWED_HTTP_PORTS:
        msg = f"URL port '{parsed.port}' is not in the allowed list."
        _record_ssrf_reject("disallowed_port")
        raise ValueError(msg)

    # Lowercase for safe comparison
    hostname_lower = hostname.lower()

    # 1. Allowlist override check (for local integration / Docker smoke test)
    if _is_smoke_allowed_internal_host(hostname_lower):
        return

    # 2. Reject explicit loopback / internal names
    if hostname_lower in ("localhost", "host.docker.internal", "[::1]", "::1", "0.0.0.0", "127.0.0.1"):  # nosec B104
        msg = f"URL hostname '{hostname}' is a restricted local loopback target."
        _record_ssrf_reject("loopback_name")
        raise ValueError(msg)

    # 3. Reject cloud metadata endpoints specifically (check BEFORE generic internal TLDs
    #    so metadata.google.internal gets a specific error message)
    if hostname_lower in ("169.254.169.254", "metadata.google.internal", "instance-data"):
        msg = f"URL hostname '{hostname}' is a restricted cloud metadata endpoint."
        _record_ssrf_reject("cloud_metadata")
        raise ValueError(msg)

    # 4. Reject direct IP literals without depending on DNS.
    #    Handle canonical IPv4/IPv6 via ipaddress, then non-canonical
    #    IPv4 forms (hex / octal / mixed) via _normalize_ip_literal.
    ip_literal = None
    try:
        ip_literal = ipaddress.ip_address(hostname_lower.strip("[]"))
    except ValueError:
        normalized = _normalize_ip_literal(hostname_lower)
        if normalized is not None:
            ip_literal = ipaddress.ip_address(normalized)
    if ip_literal is not None:
        if not is_safe_ip(str(ip_literal)):
            msg = f"URL hostname '{hostname}' resolves to restricted IP {ip_literal} — rejected for security (SSRF protection)."
            _record_ssrf_reject("restricted_ip_literal")
            raise ValueError(
                msg,
            )
        return

    # 5. Reject internal TLDs (misconfiguration / SSRF trick)
    internal_tlds = (".local", ".internal", ".lan", ".corp")
    for tld in internal_tlds:
        if hostname_lower.endswith(tld):
            msg = f"URL hostname '{hostname}' uses internal TLD '{tld}' which is restricted for security."
            _record_ssrf_reject("internal_tld")
            raise ValueError(msg)

    # 6. Reject admin denylisted domains (P1-COMPLIANCE-001).  Consulted
    #    AFTER the SSRF / internal-TLD checks so a denylisted domain is
    #    still rejected for the right reason if it also happens to be
    #    loopback/internal.  Best-effort: a broken denylist subsystem
    #    must NEVER turn a safe URL into a 5xx; we log and proceed.
    try:
        from app.admin_denylist import validate_against_denylist

        validate_against_denylist(url)
    except ImportError:
        logger.debug("Admin denylist module not available; skipping denylist check")
    except ValueError:
        _record_ssrf_reject("admin_denylisted")
        raise
    except Exception as e:
        logger.debug("Admin denylist check failed (non-fatal): %s", e)

    # Design note: DNS-based SSRF protection is handled by the transport
    # layer which resolves DNS asynchronously via loop.getaddrinfo().
    # We intentionally do NOT resolve DNS here to avoid blocking the
    # event loop when this function is called from async request handlers.


def _record_ssrf_reject(reason: str) -> None:
    """Record an SSRF reject with a structured reason for Prometheus export.

    Lazy-imported so this module's import surface stays small for
    tests that do not need the metrics collector.
    """
    try:
        from app.metrics_collector import record_ssrf_reject

        record_ssrf_reject(reason)
    except Exception:
        logger.debug("Failed to record SSRF reject reason: %s", reason)


# ───────────────────────────────────────────────────────────────────────
# SSRF-safe transport layer
#
# Why a custom transport instead of editing httpx internals:
#   * httpx does NOT publicly accept a ``network_backend`` parameter in
#     ``AsyncHTTPTransport.__init__`` or ``HTTPTransport.__init__``.
#   * The only public seam for network behaviour is
#     ``httpcore.NetworkBackend`` / ``httpcore.AsyncNetworkBackend``
#     (public abstract base classes).
#   * The default concrete backends ``httpcore.AnyIOBackend`` and
#     ``httpcore.SyncBackend`` are PUBLIC symbols in modern httpcore.
#     Earlier versions exposed them only via
#     ``httpcore._backends.auto.AutoBackend`` and
#     ``httpcore._backends.sync.SyncBackend`` (private aliases).
#
# Implementation strategy:
#   1. Subclass the PUBLIC ``httpcore.AsyncNetworkBackend`` /
#      ``httpcore.NetworkBackend`` and validate every TCP target IP
#      before delegating to the wrapped backend.
#   2. Use the PUBLIC ``httpcore.AnyIOBackend`` / ``httpcore.SyncBackend``
#      as the wrapped backend (not the underscored aliases).
#   3. Inject the safe backend into httpx's connection pool via the
#      ``_pool._network_backend`` attribute. This is a private httpx
#      attribute, so we also:
#        - Pin httpx/httpcore versions in the lock file.
#        - Add a startup self-check that asserts the swap is in place.
#        - Provide a fallback wrapper transport (no monkey-patching)
#          that validates at the request layer for defense-in-depth.
# ───────────────────────────────────────────────────────────────────────


class SafeAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    """Public httpcore async backend that validates destination IPs.

    Subclasses ``httpcore.AsyncNetworkBackend`` (public abstract base).
    """

    def __init__(self, backend: httpcore.AsyncNetworkBackend) -> None:
        self._backend = backend

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        import asyncio

        if _is_smoke_allowed_internal_host(host):
            return await self._backend.connect_tcp(
                host,
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        safe_ip: str | None = None
        for _family, _type, _proto, _canonname, sockaddr in infos:
            ip = str(sockaddr[0])
            if not is_safe_ip(ip):
                msg = f"Rejected connection to unsafe IP address: {ip}"
                raise ValueError(msg)
            if safe_ip is None:
                safe_ip = ip
        if safe_ip is None:
            msg = f"No usable addresses resolved for host: {host}"
            raise ValueError(msg)

        # Pin the connection to the validated IP to close the DNS-rebinding
        # window between this check and the underlying connect. For HTTPS,
        # the URL host is still used for SNI / cert verification by httpx
        # when it wraps this stream in TLS — only the TCP socket target is
        # pinned.
        return await self._backend.connect_tcp(
            safe_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,  # noqa: ARG002, RUF100
        timeout: float | None = None,  # noqa: ARG002, ASYNC109, RUF100
        socket_options: Any = None,  # noqa: ARG002, RUF100
    ) -> httpcore.AsyncNetworkStream:
        msg = "UNIX socket connections are disabled for security reasons."
        raise ValueError(msg)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class SafeNetworkBackend(httpcore.NetworkBackend):
    """Public httpcore sync backend that validates destination IPs."""

    def __init__(self, backend: httpcore.NetworkBackend) -> None:
        self._backend = backend

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        if _is_smoke_allowed_internal_host(host):
            return self._backend.connect_tcp(
                host,
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )

        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        safe_ip: str | None = None
        for _family, _type, _proto, _canonname, sockaddr in infos:
            ip = str(sockaddr[0])
            if not is_safe_ip(ip):
                msg = f"Rejected connection to unsafe IP address: {ip}"
                raise ValueError(msg)
            if safe_ip is None:
                safe_ip = ip
        if safe_ip is None:
            msg = f"No usable addresses resolved for host: {host}"
            raise ValueError(msg)

        # Pin to validated IP — see SafeAsyncNetworkBackend for rationale.
        return self._backend.connect_tcp(
            safe_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,  # noqa: ARG002, RUF100
        timeout: float | None = None,  # noqa: ARG002, RUF100
        socket_options: Any = None,  # noqa: ARG002, RUF100
    ) -> httpcore.NetworkStream:
        msg = "UNIX socket connections are disabled for security reasons."
        raise ValueError(msg)

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


def _default_async_backend() -> httpcore.AsyncNetworkBackend:
    """Return the public async network backend used by httpx by default.

    Prefer the public ``httpcore.AnyIOBackend``; fall back to the
    historical private alias if the public symbol is unavailable in an
    older httpcore. The fallback is logged so a vendor upgrade is
    noticed.
    """
    if hasattr(httpcore, "AnyIOBackend"):
        return httpcore.AnyIOBackend()
    logger.warning(
        "httpcore.AnyIOBackend unavailable; falling back to private _backends.auto.AutoBackend. "
        "Upgrade httpcore to a version that exposes AnyIOBackend publicly.",
    )
    from httpcore._backends.auto import AutoBackend

    return AutoBackend()


def _default_sync_backend() -> httpcore.NetworkBackend:
    """Return the public sync network backend used by httpx by default."""
    if hasattr(httpcore, "SyncBackend"):
        return httpcore.SyncBackend()
    logger.warning(
        "httpcore.SyncBackend unavailable; falling back to private _backends.sync.SyncBackend. "
        "Upgrade httpcore to a version that exposes SyncBackend publicly.",
    )
    from httpcore._backends.sync import SyncBackend

    return SyncBackend()


# ───────────────────────────────────────────────────────────────────────
# Public-API transport wrapper (PRIMARY SSRF enforcement)
#
# This is the **PRIMARY** SSRF enforcement layer. It uses ONLY public
# httpx transport APIs (``httpx.AsyncBaseTransport.handle_async_request``
# and ``httpx.BaseTransport.handle_request``) and depends on no private
# internals. It validates the destination IP at the transport layer —
# before the inner transport is invoked — so a transport-internals
# regression in httpx/httpcore does NOT bypass SSRF protection.
#
# The inner transport is the ``SafeAsyncHTTPTransport`` /
# ``SafeHTTPTransport`` (which monkey-patches ``_pool._network_backend``
# for defense-in-depth). This belt-and-braces layout means:
#
#   1. PRIMARY:   URL→IP validation at ``handle_async_request`` time
#                (public httpx extension point, no private attrs).
#   2. SECONDARY: ``SafeAsyncNetworkBackend.connect_tcp`` re-validates
#                the resolved IP at TCP connect time (defends against
#                DNS rebinding between the public check and the connect).
#   3. FALLBACK:  if httpx internals change, the public-API layer still
#                enforces; if the public-API layer is somehow skipped,
#                the network backend still enforces.
# ───────────────────────────────────────────────────────────────────────


class _UrlValidatingAsyncTransport(httpx.AsyncBaseTransport):
    """Async httpx transport wrapper — PRIMARY SSRF enforcement.

    Subclasses the PUBLIC ``httpx.AsyncBaseTransport`` (no private
    internals touched). Resolves the host, validates every resolved IP
    against :func:`is_safe_ip`, and only then delegates to the inner
    transport. The inner transport (``SafeAsyncHTTPTransport``) provides
    a second layer of validation at TCP connect time.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = urlparse(str(request.url)).hostname
        if host and not _is_smoke_allowed_internal_host(host):
            try:
                # We deliberately do NOT call validate_public_http_url here
                # because that raises ValueError on smoke-test allowlist
                # bypass; we want a transport-layer hard fail.
                infos = await asyncio.get_event_loop().getaddrinfo(host, None)
                for _family, _type, _proto, _canonname, sockaddr in infos:
                    if not is_safe_ip(str(sockaddr[0])):
                        msg = f"Transport rejected unsafe destination IP for host {host}"
                        raise ValueError(msg)
            except (socket.gaierror, OSError) as e:
                if settings.ENV.lower() in ("production", "staging") and not settings.SMOKE_TEST_MODE:
                    msg = f"Transport rejected unresolvable host {host} in production: {e}"
                    raise ValueError(msg) from e
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


class _UrlValidatingSyncTransport(httpx.BaseTransport):
    """Sync httpx transport wrapper — PRIMARY SSRF enforcement.

    Same strategy as :class:`_UrlValidatingAsyncTransport`, for the
    sync path.
    """

    def __init__(self, inner: httpx.BaseTransport | None = None) -> None:
        self._inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = urlparse(str(request.url)).hostname
        if host and not _is_smoke_allowed_internal_host(host):
            try:
                infos = socket.getaddrinfo(host, None)
                for _family, _type, _proto, _canonname, sockaddr in infos:
                    if not is_safe_ip(str(sockaddr[0])):
                        msg = f"Transport rejected unsafe destination IP for host {host}"
                        raise ValueError(msg)
            except (socket.gaierror, OSError) as e:
                if settings.ENV.lower() in ("production", "staging") and not settings.SMOKE_TEST_MODE:
                    msg = f"Transport rejected unresolvable host {host} in production: {e}"
                    raise ValueError(msg) from e
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


# ───────────────────────────────────────────────────────────────────────
# Public SSRF-safe transport factory and self-check
# ───────────────────────────────────────────────────────────────────────


class SafeAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """Subclass of the public ``httpx.AsyncHTTPTransport``.

    Injects ``SafeAsyncNetworkBackend`` (a public httpcore
    ``AsyncNetworkBackend`` subclass) into the underlying
    connection pool. The pool attribute name (``_pool._network_backend``)
    is private; the injection is guarded by
    :func:`verify_ssrf_self_check` which runs at startup and raises
    loudly if the attribute is missing.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        default_backend = _default_async_backend()
        self._pool._network_backend = SafeAsyncNetworkBackend(default_backend)
        # Mark the pool so the self-check can confirm the injection.
        self._pool._ssrf_safe = True  # type: ignore[attr-defined]


class SafeHTTPTransport(httpx.HTTPTransport):
    """Subclass of the public ``httpx.HTTPTransport``.

    Same injection strategy as :class:`SafeAsyncHTTPTransport`, for
    the sync path.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        default_backend = _default_sync_backend()
        self._pool._network_backend = SafeNetworkBackend(default_backend)
        self._pool._ssrf_safe = True  # type: ignore[attr-defined]


_TRANSPORT_KEYS = (
    "verify",
    "cert",
    "trust_env",
    "http1",
    "http2",
    "limits",
    "proxy",
    "uds",
    "local_address",
    "retries",
    "socket_options",
)


def get_safe_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Create an AsyncClient with transport-layer SSRF protection.

    The client is wired with two stacked SSRF enforcement layers:

    1. **PRIMARY** — :class:`_UrlValidatingAsyncTransport` resolves the
       host, validates every resolved IP against the public-safe-IP
       predicate, and only then delegates to the inner transport. This
       layer uses ONLY public httpx APIs and is independent of
       ``_pool._network_backend``.
    2. **SECONDARY** — :class:`SafeAsyncHTTPTransport` swaps
       ``_pool._network_backend`` for :class:`SafeAsyncNetworkBackend`,
       which re-validates the resolved IP at TCP connect time. This
       layer defends against DNS rebinding between the public check and
       the actual connect, and is verified by
       :func:`verify_ssrf_self_check` at startup.
    """
    if "transport" not in kwargs:
        transport_kwargs = {k: kwargs.pop(k) for k in _TRANSPORT_KEYS if k in kwargs}
        inner = SafeAsyncHTTPTransport(**transport_kwargs)
        kwargs["transport"] = _UrlValidatingAsyncTransport(inner)
    return httpx.AsyncClient(**kwargs)


def get_safe_client(**kwargs: Any) -> httpx.Client:
    """Create a sync Client with transport-layer SSRF protection.

    Same two-layer enforcement as :func:`get_safe_async_client`, for the
    sync path.
    """
    if "transport" not in kwargs:
        transport_kwargs = {k: kwargs.pop(k) for k in _TRANSPORT_KEYS if k in kwargs}
        inner = SafeHTTPTransport(**transport_kwargs)
        kwargs["transport"] = _UrlValidatingSyncTransport(inner)
    return httpx.Client(**kwargs)


# ───────────────────────────────────────────────────────────────────────
# Startup self-check
# ───────────────────────────────────────────────────────────────────────


def verify_ssrf_self_check() -> dict[str, Any]:
    """Confirm that the SSRF-safe transport factory still enforces the
    safety path against the currently-installed ``httpx`` / ``httpcore``
    versions.

    Returns a dict with ``ok`` (bool) and diagnostic fields. Logs a
    ``WARNING`` (not an exception) if the check fails; the caller can
    choose to escalate based on environment.

    The check is intentionally non-fatal at module import time so that
    tests, dry-runs, and offline development environments don't break
    when the network layer changes upstream. The recommended caller is
    the FastAPI lifespan handler, which can promote the warning to a
    hard fail in production.
    """
    diag: dict[str, Any] = {
        "ok": True,
        "httpx_version": getattr(httpx, "__version__", "unknown"),
        "httpcore_version": getattr(httpcore, "__version__", "unknown"),
        "has_anyio_backend": hasattr(httpcore, "AnyIOBackend"),
        "has_sync_backend": hasattr(httpcore, "SyncBackend"),
        "public_transport_present": False,
        "pool_attr_present": False,
        "marker_present": False,
    }

    try:
        # PRIMARY layer: the public-API transport wrapper. This must
        # always be the outer transport of the safe client.
        from app.url_safety import _UrlValidatingAsyncTransport as _PublicT

        if not issubclass(_PublicT, httpx.AsyncBaseTransport):
            diag["ok"] = False
            diag["reason"] = (
                "Public-API transport wrapper is not a subclass of httpx.AsyncBaseTransport; the primary SSRF layer is missing."
            )
            return diag
        diag["public_transport_present"] = True

        # SECONDARY layer: the private-injection transport that swaps
        # ``_pool._network_backend`` for the safe backend. This is
        # defense-in-depth and is verified separately.
        transport = SafeAsyncHTTPTransport()
        pool = getattr(transport, "_pool", None)
        if pool is None:
            diag["ok"] = False
            diag["reason"] = "httpx transport has no _pool attribute"
            return diag
        diag["pool_attr_present"] = True

        # Confirm the network backend was actually swapped.
        backend = getattr(pool, "_network_backend", None)
        if not isinstance(backend, SafeAsyncNetworkBackend):
            diag["ok"] = False
            diag["reason"] = (
                "Pool's _network_backend is not a SafeAsyncNetworkBackend "
                f"({type(backend).__name__}). httpx/httpcore internals may "
                "have changed; re-pin the supported versions in pyproject.toml."
            )
            return diag

        diag["marker_present"] = bool(getattr(pool, "_ssrf_safe", False))
        if not diag["marker_present"]:
            diag["ok"] = False
            diag["reason"] = "Pool marker _ssrf_safe missing; the self-injection is incomplete."
            return diag

        # Final wiring assertion: get_safe_async_client() must use the
        # public-API wrapper as the OUTER transport.
        import inspect

        from app.url_safety import get_safe_async_client as _factory

        src = inspect.getsource(_factory)
        if "_UrlValidatingAsyncTransport" not in src or "SafeAsyncHTTPTransport" not in src:
            diag["ok"] = False
            diag["reason"] = (
                "get_safe_async_client is no longer stacking the public-API "
                "transport wrapper on top of the private-injection transport."
            )
            return diag

        return diag
    except Exception as e:
        diag["ok"] = False
        diag["reason"] = f"Self-check raised: {e}"
        return diag
