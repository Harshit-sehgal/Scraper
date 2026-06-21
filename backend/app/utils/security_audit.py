"""PII classification and data access auditing framework."""
import logging
import re
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PIIType(Enum):
    """Enumeration of PII data types."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    NAME = "name"
    ADDRESS = "address"
    IP_ADDRESS = "ip_address"
    PASSPORT = "passport"
    NONE = "none"


class PIIClassifier:
    """Classify data fields and values for PII detection."""
    
    # Common field name patterns that indicate PII
    PII_FIELD_PATTERNS = {
        PIIType.EMAIL: r"(email|mail|e_mail)",
        PIIType.PHONE: r"(phone|mobile|cell|telephone)",
        PIIType.SSN: r"(ssn|social.?security|tax.?id)",
        PIIType.CREDIT_CARD: r"(cc|card|credit|visa|mastercard)",
        PIIType.NAME: r"(name|first_name|last_name|fullname)",
        PIIType.ADDRESS: r"(address|street|city|zip|postal)",
        PIIType.IP_ADDRESS: r"(ip|ipv4|ipv6|host)",
        PIIType.PASSPORT: r"(passport|document|id)",
    }
    
    # Value patterns for PII detection
    VALUE_PATTERNS = {
        PIIType.EMAIL: r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        PIIType.PHONE: r"^(\+1)?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}$",
        PIIType.SSN: r"^\d{3}-\d{2}-\d{4}$",
        PIIType.CREDIT_CARD: r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}$",
        PIIType.IP_ADDRESS: r"^(\d{1,3}\.){3}\d{1,3}$",
    }
    
    @classmethod
    def classify_field_name(cls, field_name: str) -> PIIType:
        """Classify a field name as likely containing PII."""
        field_lower = field_name.lower()
        
        for pii_type, pattern in cls.PII_FIELD_PATTERNS.items():
            if re.search(pattern, field_lower):
                return pii_type
        
        return PIIType.NONE
    
    @classmethod
    def classify_value(cls, value: Any, field_name: str = "") -> PIIType:
        """Classify a value as likely containing PII."""
        if not isinstance(value, str):
            return PIIType.NONE
        
        # First check field name
        field_type = cls.classify_field_name(field_name)
        if field_type != PIIType.NONE:
            return field_type
        
        # Then check value patterns
        for pii_type, pattern in cls.VALUE_PATTERNS.items():
            if re.match(pattern, value):
                return pii_type
        
        return PIIType.NONE
    
    @classmethod
    def redact_pii(cls, value: str, pii_type: PIIType) -> str:
        """Redact PII value for logging/display."""
        if pii_type == PIIType.EMAIL:
            parts = value.split("@")
            if len(parts) == 2:
                return f"{parts[0][:2]}***@{parts[1]}"
            return "***@***"
        elif pii_type == PIIType.PHONE:
            return value[:3] + "***" + value[-4:] if len(value) >= 7 else "***"
        elif pii_type == PIIType.CREDIT_CARD:
            return "****-****-****-" + value[-4:]
        elif pii_type == PIIType.SSN:
            return "***-**-" + value[-4:]
        elif pii_type in (PIIType.NAME, PIIType.ADDRESS, PIIType.PASSPORT):
            return f"[{pii_type.value.upper()}]"
        else:
            return value


class DataAccessAuditor:
    """Audit log data access events with PII awareness."""
    
    @staticmethod
    def log_data_access(
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        data_classification: PIIType = PIIType.NONE,
        success: bool = True,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a data access event."""
        audit_entry = {
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "data_classification": data_classification.value,
            "success": success,
            "details": details or {},
        }
        
        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"DATA_ACCESS: {action} on {resource_type}/{resource_id} by {user_id} "
            f"(classification={data_classification.value})",
            extra={"audit": audit_entry},
        )
    
    @staticmethod
    def log_failed_login(username: str, reason: str) -> None:
        """Log a failed login attempt."""
        logger.warning(
            f"FAILED_LOGIN: {reason} for {username}",
            extra={"audit": {"event": "failed_login", "username": username, "reason": reason}},
        )
    
    @staticmethod
    def log_permission_denied(
        user_id: str, resource: str, permission: str
    ) -> None:
        """Log a permission denied event."""
        logger.warning(
            f"PERMISSION_DENIED: user {user_id} denied {permission} on {resource}",
            extra={
                "audit": {
                    "event": "permission_denied",
                    "user_id": user_id,
                    "resource": resource,
                    "permission": permission,
                }
            },
        )
