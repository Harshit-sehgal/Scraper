"""Invoice generation for billing.

Generates invoices for billing purposes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum


class InvoiceStatus(Enum):
    """Invoice status."""

    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


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
        if due_days < 0:
            msg = "due_days must be non-negative"
            raise ValueError(msg)
        now = datetime.now(UTC)
        invoice = Invoice(
            user_id=user_id,
            items=items,
            created_at=now,
            due_date=now + timedelta(days=due_days),
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

