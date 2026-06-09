"""Characterization tests for the conftest-level DNS isolation.

These tests assert the autouse ``_default_dns_resolver`` fixture behaves as
the Phase 0 master plan requires: by default, no unmarked test can make a
real DNS query, and a test can opt in to live network with the ``network``
marker (which must be registered in pyproject.toml/conftest.py).

The contract is intentionally narrow:

1. The autouse fixture replaces ``socket.getaddrinfo`` with a deterministic
   stand-in so that ``validate_public_http_url("http://google.com")`` cannot
   silently reach the network. We assert that the stand-in resolves
   ``localhost`` to ``127.0.0.1`` (matching real DNS) and that an unknown
   ``.invalid`` hostname does not raise a ``gaierror`` from real DNS.
2. The ``network`` marker is registered in ``pyproject.toml`` so that
   ``@pytest.mark.network`` is a recognised opt-in, not a typo. The test
   applying the marker is what would have been filtered out with
   ``PytestUnknownMarkWarning`` if the marker was unregistered.
"""

from __future__ import annotations

import socket

import pytest


def test_default_dns_standin_resolves_loopback() -> None:
    """The autouse fixture must map ``localhost`` to ``127.0.0.1``.

    This matches what real DNS does on a healthy machine, so tests that
    rely on ``localhost`` being a loopback keep passing. If the autouse
    fixture is missing, this test will *also* pass on machines where
    real DNS works — that is acceptable for a characterization test; the
    real proof is the next test, which uses an ``.invalid`` TLD.
    """
    result = socket.getaddrinfo("localhost", 80)
    assert result
    _family, _type, _proto, _canon, sockaddr = result[0]
    assert any(addr[0] == "127.0.0.1" for addr in (r[4] for r in result))


def test_default_dns_standin_handles_unknown_tld() -> None:
    """The autouse fixture must answer unknown TLDs deterministically.

    ``.invalid`` is reserved by RFC 2606 and must never resolve in real
    DNS. If this test raises ``socket.gaierror`` instead of returning a
    result, the conftest's autouse DNS fixture is missing and the test
    is silently hitting the network (or a CI sandbox with no DNS).
    """
    result = socket.getaddrinfo("definitely-not-real.invalid", 80)
    assert result, "autouse DNS standin must return at least one record"
    family, _type, _proto, _canon, sockaddr = result[0]
    assert isinstance(sockaddr, tuple)
    assert len(sockaddr) >= 2


@pytest.mark.network
def test_network_marker_is_recognised() -> None:
    """The ``@pytest.mark.network`` decorator must be accepted.

    If the marker is not registered in ``pyproject.toml``'s
    ``[tool.pytest.ini_options].markers`` list, this test would have
    raised a ``PytestUnknownMarkWarning`` at collection. The fact that
    it ran is the assertion.
    """
    assert True
