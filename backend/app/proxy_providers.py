"""Proxy provider plug-in — protocol, adapters, and factory.

DataForge supports multiple proxy sources beyond the static
``PROXY_LIST`` env var.  Each provider implements the
:class:`ProxyProvider` protocol so :class:`~app.proxy_manager.ProxyManager`
can delegate to it at init and on refresh.

Provider resolution (via :func:`create_provider`) follows the
``PROXY_PROVIDER_TYPE`` setting:

============  =========================================  ================
Type          Source                                     Config key
============  =========================================  ================
``static``    ``settings.PROXY_LIST`` env var (default)  *(none)*
``file``      Local JSON file (array of URL strings)     ``PROXY_PROVIDER_FILE``
``url``       HTTP endpoint returning JSON array         ``PROXY_PROVIDER_URL``
``brightdata`` HTTP endpoint (BrightData convention)     ``PROXY_PROVIDER_URL``
``oxylabs``   HTTP endpoint (Oxylabs convention)         ``PROXY_PROVIDER_URL``
``smartproxy`` HTTP endpoint (Smartproxy convention)    ``PROXY_PROVIDER_URL``
============  =========================================  ================

The ``brightdata`` / ``oxylabs`` / ``smartproxy`` types are aliases
for :class:`HttpUrlProvider` with preset auth-header formats.
Concrete HTTP client adapters for each provider SDK are future work;
the current stub accepts any URL returning a JSON array of proxy
strings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ProxyProvider:
    """Pluggable proxy source — protocol, not a formal ABC.

    Every provider must implement :meth:`fetch_proxies` (returning a
    list of proxy URL strings) and :meth:`refresh` (re-reading the
    source when the list may have changed).
    """

    def fetch_proxies(self) -> list[str]:
        """Return the current proxy list from this provider."""
        return []

    def refresh(self) -> list[str]:
        """Re-fetch the proxy list from the source and return it.

        May be a no-op for static providers.
        """
        return []


# ---------------------------------------------------------------------------
# Static list (default — mirrors PROXY_LIST env var)
# ---------------------------------------------------------------------------


class StaticListProvider(ProxyProvider):
    """Returns a fixed list supplied at construction time.

    This is the default provider when ``PROXY_PROVIDER_TYPE`` is
    ``"static"`` (or empty).  It wraps whatever the caller passes in,
    which is typically ``settings.PROXY_LIST.split(",")``.
    """

    def __init__(self, proxies: list[str]) -> None:
        self._proxies = list(proxies)

    def fetch_proxies(self) -> list[str]:
        return list(self._proxies)

    def refresh(self) -> list[str]:
        return list(self._proxies)


# ---------------------------------------------------------------------------
# JSON file
# ---------------------------------------------------------------------------


class JsonFileProvider(ProxyProvider):
    """Reads a proxy list from a JSON file on disk.

    The file must contain a JSON array of URL strings::

        ["http://1.2.3.4:8080", "socks5://5.6.7.8:1080"]

    ``refresh()`` re-reads the file so operator rotations take effect
    without restarting the process.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def fetch_proxies(self) -> list[str]:
        return self._read_file()

    def refresh(self) -> list[str]:
        return self._read_file()

    def _read_file(self) -> list[str]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Proxy provider file %s unreadable: %s", self._path, exc)
            return []
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Proxy provider file %s invalid JSON: %s", self._path, exc)
            return []
        if not isinstance(data, list):
            logger.warning("Proxy provider file %s: expected JSON array, got %s", self._path, type(data).__name__)
            return []
        proxies: list[str] = [str(p).strip() for p in data if str(p).strip()]
        logger.info("Loaded %d proxies from %s", len(proxies), self._path)
        return proxies


# ---------------------------------------------------------------------------
# HTTP URL (stub / future SDK)
# ---------------------------------------------------------------------------


class HttpUrlProvider(ProxyProvider):
    """Fetches proxy list from an HTTP endpoint returning a JSON array.

    This is the base for BrightData / Oxylabs / Smartproxy provider
    adapters.  The current implementation uses ``httpx`` (if available)
    to fetch the URL; on import failure it returns an empty list.

    The ``auth_header`` parameter allows providers that require
    authentication to pass a pre-formatted ``Authorization`` header value.
    """

    def __init__(self, url: str, *, auth_header: str = "") -> None:
        if not url:
            msg = "HttpUrlProvider requires a non-empty PROXY_PROVIDER_URL"
            raise ValueError(msg)
        self._url = url
        self._auth_header = auth_header

    def fetch_proxies(self) -> list[str]:
        return self._fetch_http()

    def refresh(self) -> list[str]:
        return self._fetch_http()

    def _fetch_http(self) -> list[str]:
        try:
            import httpx
        except ImportError:
            logger.debug("httpx not available; HttpUrlProvider cannot fetch proxies")
            return []

        # SSRF protection — reject internal/metadata URLs before any
        # network request is made.  The provider URL is operator-configured
        # but defense-in-depth applies regardless.
        try:
            from app.url_safety import validate_public_http_url

            validate_public_http_url(self._url)
        except ValueError as exc:
            logger.warning("Proxy provider URL blocked by SSRF defense: %s (%s)", self._url, exc)
            return []

        headers: dict[str, str] = {}
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        try:
            response = httpx.get(self._url, headers=headers, timeout=10.0)
            response.raise_for_status()
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("Proxy provider HTTP fetch from %s failed: %s", self._url, exc)
            return []

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Proxy provider HTTP response not valid JSON: %s", exc)
            return []

        if not isinstance(data, list):
            logger.warning("Proxy provider HTTP response: expected JSON array, got %s", type(data).__name__)
            return []

        proxies: list[str] = [str(p).strip() for p in data if str(p).strip()]
        logger.info("Loaded %d proxies from HTTP endpoint %s", len(proxies), self._url)
        return proxies


# ---------------------------------------------------------------------------
# Provider-specific HTTP aliases
# ---------------------------------------------------------------------------


class BrightDataProvider(HttpUrlProvider):
    """BrightData (Luminati) provider — same HTTP protocol, pre-set auth header format.

    The auth header is ``Bearer <api_key>``.  The URL defaults to
    BrightData's proxy list endpoint, but operators can override with
    ``PROXY_PROVIDER_URL``.
    """

    def __init__(self, url: str, *, api_key: str = "") -> None:
        auth_header = f"Bearer {api_key}" if api_key else ""
        super().__init__(url, auth_header=auth_header)


class OxylabsProvider(HttpUrlProvider):
    """Oxylabs provider — same HTTP protocol with token-based auth.

    The auth header is ``Token <api_key>``.
    """

    def __init__(self, url: str, *, api_key: str = "") -> None:
        auth_header = f"Token {api_key}" if api_key else ""
        super().__init__(url, auth_header=auth_header)


class SmartproxyProvider(HttpUrlProvider):
    """Smartproxy provider — same HTTP protocol with basic auth header.

    The auth header is ``Basic <base64(user:pass)>``.
    """

    def __init__(self, url: str, *, api_key: str = "") -> None:
        import base64

        auth_header = ""
        if api_key and ":" in api_key:
            encoded = base64.b64encode(api_key.encode()).decode()
            auth_header = f"Basic {encoded}"
        super().__init__(url, auth_header=auth_header)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDER_TYPE_MAP: dict[str, type[ProxyProvider]] = {
    "static": StaticListProvider,
    "file": JsonFileProvider,
    "url": HttpUrlProvider,
    "brightdata": BrightDataProvider,
    "oxylabs": OxylabsProvider,
    "smartproxy": SmartproxyProvider,
}


def create_provider() -> ProxyProvider:
    """Return the appropriate :class:`ProxyProvider` based on settings.

    Reads ``settings.PROXY_PROVIDER_TYPE`` and loads proxies from the
    configured source.  Falls back to :class:`StaticListProvider` if
    the type is unrecognised.
    """
    from app.config import settings

    ptype = (settings.PROXY_PROVIDER_TYPE or "static").strip().lower()

    if ptype == "static":
        proxies = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]
        return StaticListProvider(proxies)

    if ptype == "file":
        path = settings.PROXY_PROVIDER_FILE
        if not path:
            logger.warning("PROXY_PROVIDER_TYPE='file' but PROXY_PROVIDER_FILE is empty")
            return StaticListProvider([])
        return JsonFileProvider(path)

    if ptype in ("url", "brightdata", "oxylabs", "smartproxy"):
        url = settings.PROXY_PROVIDER_URL
        if not url:
            logger.warning("PROXY_PROVIDER_TYPE='%s' but PROXY_PROVIDER_URL is empty", ptype)
            return StaticListProvider([])

        if ptype == "brightdata":
            return BrightDataProvider(url, api_key=settings.CAPTCHA_API_KEY or "")
        if ptype == "oxylabs":
            return OxylabsProvider(url, api_key=settings.CAPTCHA_API_KEY or "")
        if ptype == "smartproxy":
            return SmartproxyProvider(url, api_key=settings.CAPTCHA_API_KEY or "")
        return HttpUrlProvider(url)

    logger.warning("Unknown PROXY_PROVIDER_TYPE=%r; falling back to static", ptype)
    proxies = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]
    return StaticListProvider(proxies)
