"""Test security audit and PII classification."""

from app.utils.security_audit import DataAccessAuditor, PIIClassifier, PIIType


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
