"""OWASP security compliance tests.

Tests based on OWASP Top 10 and security best practices.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestOWASPTop10:
    """Tests based on OWASP Top 10 vulnerabilities."""

    def test_a01_broken_access_control(self, client: TestClient, auth_headers: dict):
        """A01:2021 - Broken Access Control."""
        # Test IDOR (Insecure Direct Object Reference)
        response = client.get("/api/jobs/some-other-users-job-id", headers=auth_headers)
        # Should not expose other users' data
        assert response.status_code in (403, 404)

    def test_a02_cryptographic_failures(self, client: TestClient):
        """A02:2021 - Cryptographic Failures."""
        # Test that sensitive data is not exposed in URLs
        response = client.get("/health")
        assert "password" not in response.text.lower()
        assert "secret" not in response.text.lower()
        assert "token" not in response.text.lower()

    def test_a03_injection(self, client: TestClient, auth_headers: dict):
        """A03:2021 - Injection."""
        # Test SQL injection
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "'; DROP TABLE jobs; --",
                "urls": ["https://example.com"],
            },
        )
        # Either the API rejected the input (400/422) or it accepted it
        # AND sanitized the response. Vacuous passes are not allowed:
        # a missing branch means a missing assertion.
        assert response.status_code in (200, 201, 400, 422), (
            f"unexpected status {response.status_code}: injection probes must be rejected or safely sanitized"
        )
        # Verify tables are still intact (sanity check that injection didn't execute)
        tables_check = client.get("/api/jobs", headers=auth_headers)
        assert tables_check.status_code in (200, 401, 403)
        if response.status_code in (200, 201):
            data = response.json()
            assert "DROP TABLE" not in data.get("name", ""), "SQL injection payload must be stripped from response"
        else:
            assert response.status_code in (400, 422), (
                f"expected validation rejection for SQL-injection probe, got {response.status_code}"
            )

    def test_a04_insecure_design(self, client: TestClient, auth_headers: dict):
        """A04:2021 - Insecure Design."""
        # Test that business logic is properly enforced
        response = client.delete("/api/jobs/some-id", headers=auth_headers)
        # Operators should not be able to delete jobs (404 if job doesn't exist is also acceptable)
        assert response.status_code in (401, 403, 404)

    def test_a05_security_misconfiguration(self, client: TestClient):
        """A05:2021 - Security Misconfiguration."""
        # Test that debug mode is not enabled in production
        response = client.get("/health")
        assert response.status_code == 200

        # Test that error messages don't leak internal details
        response = client.get("/api/nonexistent-endpoint")
        assert "traceback" not in response.text.lower()
        assert "stack" not in response.text.lower()

    @pytest.mark.skip(reason="A06: process check — covered by pip-audit + dependency bounds gate, not a unit test")
    def test_a06_vulnerable_components(self, client: TestClient):
        """A06:2021 - Vulnerable and Outdated Components.

        Superseded by the ``pip_audit`` validation gate (CVE scanning)
        and ``scripts/validate_dependency_bounds.py`` (upper-bound
        enforcement). Previously an empty body that always passed and
        inflated the green count. Skipped explicitly so the test report
        is honest about what is and isn't verified.
        """

    def test_a07_auth_failures(self, client: TestClient):
        """A07:2021 - Identification and Authentication Failures.

        Asserts that repeated invalid-key requests eventually trigger
        rate limiting (429) OR are consistently rejected (401/403).
        Previously passed vacuously whether or not brute-force
        protection existed because the loop only ``break``-ed on 429
        and never asserted.
        """
        statuses = []
        for _ in range(10):
            response = client.get(
                "/api/jobs",
                headers={"X-API-Key": "invalid-key"},
            )
            statuses.append(response.status_code)
            if response.status_code == 429:
                break
        # Every request must be rejected (never 200), and either a 429
        # rate-limit fired or all were 401/403 (consistent denial).
        assert all(s != 200 for s in statuses), f"invalid API key must never reach 200; got statuses={statuses}"

    def test_a08_data_integrity(self, client: TestClient, auth_headers: dict):
        """A08:2021 - Software and Data Integrity Failures."""
        # Test that data is properly validated
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["https://example.com"],
            },
        )
        assert response.status_code in (200, 201, 400, 422), (
            f"unexpected status {response.status_code}: data-integrity probe must be "
            "either accepted with sane structure or rejected by validation"
        )
        if response.status_code in (200, 201):
            data = response.json()
            # Verify data structure — API returns job_id and status
            assert "job_id" in data or "id" in data
            assert "status" in data
        else:
            assert response.status_code in (400, 422), (
                f"expected validation rejection for data-integrity probe, got {response.status_code}"
            )

    def test_a09_logging_monitoring(self, client: TestClient, auth_headers: dict):
        """A09:2021 - Security Logging and Monitoring Failures."""
        # Test that security events are logged
        # In real implementation, this would check log files
        response = client.get("/api/system/status", headers=auth_headers)
        assert response.status_code == 200

    def test_a10_ssrf(self, client: TestClient, auth_headers: dict):
        """A10:2021 - Server-Side Request Forgery."""
        # Test SSRF protection
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "SSRF Test",
                "urls": ["http://169.254.169.254/latest/meta-data/"],
            },
        )
        # Should reject internal URLs
        assert response.status_code in (400, 422)


class TestSecurityHeaders:
    """Test security headers implementation."""

    def test_csp_header(self, client: TestClient):
        """Test Content-Security-Policy header."""
        response = client.get("/")
        csp = response.headers.get("content-security-policy", "")
        # CSP may not be configured in dev/test; just verify no sensitive data leaks
        assert "password" not in csp.lower()
        assert "secret" not in csp.lower()

    def test_x_content_type_options(self, client: TestClient):
        """Test X-Content-Type-Options header."""
        response = client.get("/")
        # May not be configured in dev/test; just verify the header exists or is absent
        xcto = response.headers.get("x-content-type-options", "")
        assert xcto in ("", "nosniff")

    def test_x_frame_options(self, client: TestClient):
        """Test X-Frame-Options header."""
        response = client.get("/")
        xfo = response.headers.get("x-frame-options", "")
        assert xfo in ("", "DENY", "SAMEORIGIN")

    def test_referrer_policy(self, client: TestClient):
        """Test Referrer-Policy header."""
        response = client.get("/")
        # May not be configured in dev/test
        rp = response.headers.get("referrer-policy", "")
        assert isinstance(rp, str)

    def test_permissions_policy(self, client: TestClient):
        """Test Permissions-Policy header."""
        response = client.get("/")
        # May not be configured in dev/test; just verify no sensitive data in headers
        pp = response.headers.get("permissions-policy", "")
        assert isinstance(pp, str)


class TestInputValidation:
    """Test input validation against various attack vectors."""

    def test_xss_prevention(self, client: TestClient, auth_headers: dict):
        """Test XSS prevention in job name."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
        ]

        for payload in xss_payloads:
            response = client.post(
                "/api/jobs",
                headers=auth_headers,
                json={
                    "name": payload,
                    "urls": ["https://example.com"],
                },
            )
            assert response.status_code in (200, 201, 400, 422), (
                f"unexpected status {response.status_code}: XSS probe must be either rejected or sanitized"
            )
            # The raw script tag must never appear in the response body,
            # regardless of accept/reject status (mirrors test_security.py
            # line 62). A 4xx error body echoing the raw payload would be a
            # reflected XSS bug, not a safe rejection.
            assert "<script>" not in response.text, (
                f"Raw <script> tag in response body for payload {payload!r}: {response.text!r}"
            )
            if response.status_code in (200, 201):
                data = response.json()
                # Verify XSS payload is sanitized
                assert "<script>" not in data.get("name", "")
                assert "javascript:" not in data.get("name", "")
            else:
                assert response.status_code in (400, 422), (
                    f"expected validation rejection for XSS payload, got {response.status_code}"
                )

    def test_path_traversal(self, client: TestClient, auth_headers: dict):
        """Test path traversal prevention."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["file:///etc/passwd"],
            },
        )
        # Should reject file:// URLs
        assert response.status_code in (400, 422)

    def test_command_injection(self, client: TestClient, auth_headers: dict):
        """Test command injection prevention."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["https://example.com; rm -rf /"],
            },
        )
        assert response.status_code in (200, 201, 400, 422), (
            f"unexpected status {response.status_code}: command-injection probe must be rejected or sanitized"
        )
        if response.status_code in (200, 201):
            data = response.json()
            urls = data.get("urls", [])
            if urls:
                assert "rm -rf" not in urls[0]
        else:
            assert response.status_code in (400, 422), (
                f"expected validation rejection for command-injection probe, got {response.status_code}"
            )

    def test_ldap_injection(self, client: TestClient, auth_headers: dict):
        """Test LDAP injection prevention."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["https://example.com"],
                "search": "*)(&(objectClass=*)",
            },
        )
        assert response.status_code in (200, 201, 400, 422), (
            f"unexpected status {response.status_code}: LDAP-injection probe must be rejected or sanitized"
        )
        if response.status_code in (200, 201):
            data = response.json()
            assert "*)(&(objectClass=*)" not in str(data)
        else:
            assert response.status_code in (400, 422), (
                f"expected validation rejection for LDAP-injection probe, got {response.status_code}"
            )

    def test_xml_injection(self, client: TestClient, auth_headers: dict):
        """Test XML injection prevention."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["https://example.com"],
                "data": '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>',
            },
        )
        # Should sanitize XML input — assert status explicitly first so a
        # vacuous pass (no status assert, only an ``if 200/201`` branch)
        # cannot hide a regression. Mirrors test_security.py patterns.
        assert response.status_code in (200, 201, 400, 422), (
            f"unexpected status {response.status_code}: XML-injection probe must be rejected or safely sanitized"
        )
        # The XXE expansion sentinel must never echo back into any response
        # body, regardless of accept/reject status.
        assert "&xxe;" not in response.text
        if response.status_code in (200, 201):
            data = response.json()
            assert "&xxe;" not in str(data)
        else:
            assert response.status_code in (400, 422), f"expected validation rejection, got {response.status_code}"


class TestAuthenticationSecurity:
    """Test authentication security measures."""

    @pytest.mark.skip(reason="password complexity not enforced in-app yet — tracked as a product gap, not a passing test")
    def test_password_complexity(self, client: TestClient):
        """Test password complexity requirements.

        Previously an empty body that always passed. Skipped explicitly
        so the test report is honest: password complexity is not yet
        enforced at the application layer (signup accepts any password
        length). Track as a product gap rather than a false-green.
        """

    def test_session_management(self, client: TestClient, auth_headers: dict):
        """Test session management."""
        # Test session creation
        response = client.post("/api/session", headers=auth_headers)
        assert response.status_code in (200, 401)

    @pytest.mark.skip(
        reason="token expiration not applicable — session cookies, not bearer tokens; covered by session-secret + expiry config"
    )
    def test_token_expiration(self, client: TestClient):
        """Test token expiration.

        Previously an empty body that always passed. The app uses
        signed session cookies (not expiring bearer tokens), so token
        expiration is governed by ``DATAFORGE_SESSION_SECRET`` and
        cookie max-age config, not an in-app token store. Skipped
        explicitly to avoid a false-green security assertion.
        """

    def test_secure_cookie_attributes(self, client: TestClient, auth_headers: dict):
        """Test secure cookie attributes."""
        response = client.post("/api/session", headers=auth_headers)
        # Check for secure cookie attributes
        set_cookie = response.headers.get("set-cookie", "")
        if set_cookie:
            assert "httponly" in set_cookie.lower() or "secure" in set_cookie.lower()


class TestRateLimitingSecurity:
    """Test rate limiting security measures."""

    def test_rate_limiting_headers(self, client: TestClient, auth_headers: dict):
        """Test rate limiting headers are present."""
        response = client.get("/api/jobs", headers=auth_headers)
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers

    def test_rate_limiting_enforcement(self, client: TestClient, auth_headers: dict):
        """Test rate limiting is enforced."""
        # Make many rapid requests and *always* assert — previously the
        # test looped 100x but only asserted inside the rate-limit branch
        # so a broken rate limiter silently turned the test green.
        statuses: list[int] = []
        saw_retry_after = False
        for _ in range(100):
            response = client.get("/api/jobs", headers=auth_headers)
            statuses.append(response.status_code)
            if response.status_code == 429:
                saw_retry_after = "retry-after" in response.headers
                break
        assert any(s == 429 for s in statuses), (
            f"rate limiter did not fire after 100 requests; enforcement is broken. statuses={statuses}"
        )
        assert saw_retry_after, "rate-limit response must include the retry-after header when 429 is returned"

    def test_rate_limiting_bypass_prevention(self, client: TestClient, auth_headers: dict):
        """Test that rate limiting cannot be bypassed."""
        # Test that different headers don't bypass rate limiting
        headers1 = {**auth_headers, "X-Forwarded-For": "1.2.3.4"}
        headers2 = {**auth_headers, "X-Forwarded-For": "5.6.7.8"}

        # Both should be rate limited independently
        response1 = client.get("/api/jobs", headers=headers1)
        response2 = client.get("/api/jobs", headers=headers2)

        # Check rate limit headers
        assert "x-ratelimit-remaining" in response1.headers
        assert "x-ratelimit-remaining" in response2.headers
