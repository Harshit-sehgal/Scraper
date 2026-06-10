"""Invoice generation and usage alerts for billing.

Generates invoices and sends usage alerts for billing purposes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class InvoiceStatus(Enum):
    """Invoice status."""

    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class AlertType(Enum):
    """Usage alert types."""

    QUOTA_WARNING = "quota_warning"
    QUOTA_EXCEEDED = "quota_exceeded"
    UNUSUAL_ACTIVITY = "unusual_activity"
    BILLING_ISSUE = "billing_issue"


@dataclass
class InvoiceItem:
    """Single invoice item."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    quantity: int = 0
    unit_price: float = 0.0
    total: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class Invoice:
    """Invoice data."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    status: InvoiceStatus = InvoiceStatus.DRAFT
    items: list[InvoiceItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    currency: str = "USD"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    due_date: datetime | None = None
    paid_at: datetime | None = None
    metadata: dict = field(default_factory=dict)

    def calculate_totals(self) -> None:
        """Calculate invoice totals."""
        self.subtotal = sum(item.total for item in self.items)
        self.tax = self.subtotal * 0.1  # 10% tax
        self.total = self.subtotal + self.tax


@dataclass
class UsageAlert:
    """Usage alert data."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    alert_type: AlertType = AlertType.QUOTA_WARNING
    message: str = ""
    threshold: float = 0.0
    current_usage: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False


class InvoiceGenerator:
    """Generates invoices for users."""

    def __init__(self):
        self._invoices: dict[str, list[Invoice]] = {}

    def generate_invoice(
        self,
        user_id: str,
        items: list[InvoiceItem],
        due_days: int = 30,
    ) -> Invoice:
        """Generate a new invoice."""
        invoice = Invoice(
            user_id=user_id,
            items=items,
            due_date=datetime.now(UTC).replace(
                day=datetime.now(UTC).day + due_days,
            ),
        )
        invoice.calculate_totals()

        if user_id not in self._invoices:
            self._invoices[user_id] = []
        self._invoices[user_id].append(invoice)

        return invoice

    def get_invoices(self, user_id: str) -> list[Invoice]:
        """Get all invoices for a user."""
        return self._invoices.get(user_id, [])

    def get_pending_invoices(self, user_id: str) -> list[Invoice]:
        """Get pending invoices for a user."""
        return [inv for inv in self._invoices.get(user_id, []) if inv.status == InvoiceStatus.PENDING]

    def mark_paid(self, invoice_id: str) -> Invoice | None:
        """Mark an invoice as paid."""
        for invoices in self._invoices.values():
            for invoice in invoices:
                if invoice.id == invoice_id:
                    invoice.status = InvoiceStatus.PAID
                    invoice.paid_at = datetime.now(UTC)
                    return invoice
        return None

    def create_usage_invoice(
        self,
        user_id: str,
        usage_data: dict,
        rates: dict,
    ) -> Invoice:
        """Create invoice from usage data."""
        items = []
        for usage_type, quantity in usage_data.items():
            if usage_type in rates:
                rate = rates[usage_type]
                item = InvoiceItem(
                    description=f"{usage_type} usage",
                    quantity=quantity,
                    unit_price=rate,
                    total=quantity * rate,
                )
                items.append(item)

        return self.generate_invoice(user_id, items)


class UsageAlertManager:
    """Manages usage alerts for users."""

    def __init__(self):
        self._alerts: dict[str, list[UsageAlert]] = {}
        self._thresholds: dict[str, dict] = {}

    def set_threshold(
        self,
        usage_type: str,
        warning_threshold: float = 0.8,
        critical_threshold: float = 1.0,
    ) -> None:
        """Set alert thresholds for a usage type."""
        self._thresholds[usage_type] = {
            "warning": warning_threshold,
            "critical": critical_threshold,
        }

    def check_usage(
        self,
        user_id: str,
        usage_type: str,
        current_usage: float,
        limit: float,
    ) -> UsageAlert | None:
        """Check if usage exceeds thresholds and create alert."""
        if limit <= 0:
            return None

        usage_ratio = current_usage / limit
        thresholds = self._thresholds.get(usage_type, {"warning": 0.8, "critical": 1.0})

        alert_type = None
        message = ""

        if usage_ratio >= thresholds["critical"]:
            alert_type = AlertType.QUOTA_EXCEEDED
            message = f"Usage limit exceeded for {usage_type}: {current_usage}/{limit}"
        elif usage_ratio >= thresholds["warning"]:
            alert_type = AlertType.QUOTA_WARNING
            message = f"Usage warning for {usage_type}: {current_usage}/{limit} ({usage_ratio:.0%})"

        if alert_type:
            return self.create_alert(user_id, alert_type, message, limit, current_usage)
        return None

    def create_alert(
        self,
        user_id: str,
        alert_type: AlertType,
        message: str,
        threshold: float,
        current_usage: float,
    ) -> UsageAlert:
        """Create a new usage alert."""
        alert = UsageAlert(
            user_id=user_id,
            alert_type=alert_type,
            message=message,
            threshold=threshold,
            current_usage=current_usage,
        )

        if user_id not in self._alerts:
            self._alerts[user_id] = []
        self._alerts[user_id].append(alert)

        return alert

    def get_alerts(self, user_id: str) -> list[UsageAlert]:
        """Get all alerts for a user."""
        return self._alerts.get(user_id, [])

    def get_unacknowledged_alerts(self, user_id: str) -> list[UsageAlert]:
        """Get unacknowledged alerts for a user."""
        return [alert for alert in self._alerts.get(user_id, []) if not alert.acknowledged]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alerts in self._alerts.values():
            for alert in alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    return True
        return False


# Global instances
invoice_generator = InvoiceGenerator()
usage_alert_manager = UsageAlertManager()


def get_invoice_generator() -> InvoiceGenerator:
    """Get the global invoice generator."""
    return invoice_generator


def get_usage_alert_manager() -> UsageAlertManager:
    """Get the global usage alert manager."""
    return usage_alert_manager
