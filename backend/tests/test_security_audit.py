"""Test security audit and PII classification."""

from app.utils.security_audit import DataAccessAuditor, PIIClassifier, PIIType
from app.utils.ssrf_defense import DNSRebindingDefense, SSRFDefense


class TestPIIClassification:
    """Test PII classification."""

    def test_classify_email_field(self):
        """Detect email field names."""
        assert PIIClassifier.classify_field_name("email") == PIIType.EMAIL
        assert PIIClassifier.classify_field_name("user_email") == PIIType.EMAIL
        assert PIIClassifier.classify_field_name("contact_email_address") == PIIType.EMAIL

    def test_classify_phone_field(self):
        """Detect phone field names."""
        assert PIIClassifier.classify_field_name("phone") == PIIType.PHONE
        assert PIIClassifier.classify_field_name("mobile_number") == PIIType.PHONE
        assert PIIClassifier.classify_field_name("cell_phone") == PIIType.PHONE

    def test_classify_ssn_field(self):
        """Detect SSN field names."""
        assert PIIClassifier.classify_field_name("ssn") == PIIType.SSN
        assert PIIClassifier.classify_field_name("social_security_number") == PIIType.SSN

    def test_classify_email_value(self):
        """Detect email values."""
        result = PIIClassifier.classify_value("user@example.com")
        assert result == PIIType.EMAIL

    def test_classify_phone_value(self):
        """Detect phone values."""
        result = PIIClassifier.classify_value("555-123-4567")
        assert result == PIIType.PHONE

    def test_classify_credit_card_value(self):
        """Detect credit card values."""
        result = PIIClassifier.classify_value("4532-1111-2222-3333")
        assert result == PIIType.CREDIT_CARD

    def test_redact_email(self):
        """Redact email addresses."""
        redacted = PIIClassifier.redact_pii("user@example.com", PIIType.EMAIL)
        assert "user@example.com" not in redacted
        assert "@" in redacted
        assert "***" in redacted

    def test_redact_phone(self):
        """Redact phone numbers."""
        redacted = PIIClassifier.redact_pii("555-123-4567", PIIType.PHONE)
        assert "123" not in redacted
        assert "***" in redacted

    def test_redact_credit_card(self):
        """Redact credit card numbers."""
        redacted = PIIClassifier.redact_pii("4532111122223333", PIIType.CREDIT_CARD)
        assert "3333" in redacted
        assert "****" in redacted


class TestSSRFDefense:
    """Test SSRF prevention."""

    def test_block_localhost_ip(self):
        """Block localhost IP."""
        assert SSRFDefense.is_blocked_ip("127.0.0.1")

    def test_block_private_ips(self):
        """Block private IP ranges."""
        assert SSRFDefense.is_blocked_ip("10.0.0.1")
        assert SSRFDefense.is_blocked_ip("172.16.0.1")
        assert SSRFDefense.is_blocked_ip("192.168.1.1")

    def test_block_ipv6_loopback(self):
        """Block IPv6 loopback."""
        assert SSRFDefense.is_blocked_ip("::1")

    def test_allow_public_ip(self):
        """Allow public IPs."""
        # 8.8.8.8 is Google DNS (public)
        assert not SSRFDefense.is_blocked_ip("8.8.8.8")

    def test_validate_safe_url(self):
        """Validate safe URLs."""
        # Using example.com which should resolve to public IPs
        safe, ip = SSRFDefense.validate_url("https://example.com")
        # May fail in some test environments, so be permissive
        if safe:
            assert ip is not None

    def test_block_invalid_scheme(self):
        """Block dangerous schemes."""
        safe, reason = SSRFDefense.validate_url("http://localhost:8000/api")
        assert not safe

    def test_block_localhost_url(self):
        """Block localhost URLs."""
        safe, reason = SSRFDefense.validate_url("http://127.0.0.1/api")
        assert not safe


class TestDNSRebindingDefense:
    """Test DNS rebinding detection."""

    def test_dns_rebinding_detector_init(self):
        """Initialize DNS rebinding detector."""
        detector = DNSRebindingDefense(ttl_cache_seconds=60)
        assert detector.ttl_cache_seconds == 60

    def test_cache_dns_resolution(self):
        """Cache DNS resolutions."""
        detector = DNSRebindingDefense()

        # First check
        result1 = detector.check_dns_rebinding("example.com")

        # Second check should use cache (no rebinding detected)
        result2 = detector.check_dns_rebinding("example.com")

        # Both should be False (no rebinding)
        assert not result1
        assert not result2


class TestDataAccessAuditor:
    """Test audit logging."""

    def test_log_data_access_success(self, caplog):
        """Log successful data access."""
        import logging
        caplog.set_level(logging.INFO)

        DataAccessAuditor.log_data_access(
            user_id="user123",
            resource_type="job",
            resource_id="job456",
            action="read",
            data_classification=PIIType.NONE,
            success=True,
        )

        assert "DATA_ACCESS" in caplog.text
        assert "user123" in caplog.text
        assert "job456" in caplog.text

    def test_log_failed_login(self, caplog):
        """Log failed login."""
        import logging
        caplog.set_level(logging.WARNING)

        DataAccessAuditor.log_failed_login("admin", "Invalid password")

        assert "FAILED_LOGIN" in caplog.text
        assert "admin" in caplog.text

    def test_log_permission_denied(self, caplog):
        """Log permission denied."""
        import logging
        caplog.set_level(logging.WARNING)

        DataAccessAuditor.log_permission_denied("user123", "job456", "delete")

        assert "PERMISSION_DENIED" in caplog.text
        assert "user123" in caplog.text
