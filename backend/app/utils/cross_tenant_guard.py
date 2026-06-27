"""Cross-tenant query guardian — alert on multi-org_id result sets.

In a properly isolated system, a single API request should only ever
return rows belonging to one ``org_id``.  If a result set contains
rows from multiple organisations, it likely means a ``WHERE org_id =
$1`` clause was omitted — a serious data-leak bug.

This module provides :func:`guard_cross_tenant` which inspects a list
of result rows and fires a ``CRITICAL``-level log + Prometheus counter
when multiple distinct ``org_id`` values appear in the same set.

The guard is deliberately NOT a hard ``raise`` — production traffic
must not be blocked by a guardian that may fire during legitimate
admin/operator all-access queries.  Instead, it emits telemetry so
operators can investigate.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Track the total number of cross-tenant contamination events seen
# in this process.  Surface in /metrics for alerting.
_cross_tenant_alerts: int = 0


def get_cross_tenant_alert_count() -> int:
    """Return the number of cross-tenant contamination events seen."""
    return _cross_tenant_alerts


def reset_cross_tenant_alert_count() -> None:
    """Reset the alert counter.  Test helper."""
    global _cross_tenant_alerts
    _cross_tenant_alerts = 0


def guard_cross_tenant(rows: list[dict[str, Any]], *, context: str = "") -> set[str]:
    """Inspect ``rows`` for ``org_id`` field and alert on contamination.

    Returns the set of distinct ``org_id`` values.  If more than one
    distinct ``org_id`` is found, logs a ``CRITICAL`` alert and
    increments the process-wide counter.

    Args:
        rows: The result set from a database query.
        context: An optional label (e.g. the endpoint or query type)
            included in the alert message for operational triage.

    Returns:
        The set of distinct ``org_id`` values found.
    """
    global _cross_tenant_alerts

    org_ids: set[str] = set()
    for row in rows:
        org_id = row.get("org_id")
        if org_id:
            org_ids.add(str(org_id))

    if len(org_ids) > 1:
        _cross_tenant_alerts += 1
        logger.critical(
            "CROSS-TENANT GUARD: query returned rows from %d distinct "
            "org_ids (%s)%s. This may indicate a missing WHERE clause. "
            "investigate immediately.",
            len(org_ids),
            ", ".join(sorted(org_ids)),
            f" [context={context}]" if context else "",
        )
        try:
            from app.metrics_collector import record_cross_tenant_guard_alert

            record_cross_tenant_guard_alert(context=context or "unknown")
        except Exception as exc:
            logger.debug("Failed to record cross-tenant guard metric: %s", exc)

    return org_ids
