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


class CrossTenantContaminationError(Exception):
    """Raised when a result set spans multiple org_ids AND ``strict=True``.

    Hard-block mode is opted-in by callers that own per-user data
    boundaries. Admin / operator all-access queries still use
    ``strict=False`` so they can legitimately span multiple org_ids.
    """


def guard_cross_tenant(
    rows: list[dict[str, Any]],
    *,
    context: str = "",
    strict: bool = False,
) -> set[str]:
    """Inspect ``rows`` for ``org_id`` field and alert on contamination.

    In the default ``strict=False`` mode this is telemetry-only — the
    function logs a ``CRITICAL``-level message and increments a
    process-wide counter so operators can investigate. Production
    traffic must not be blocked by a guardian that may fire during
    legitimate admin/operator all-access queries.

    With ``strict=True``, this raises
    :class:`CrossTenantContaminationError` on contamination, which
    callers should wrap in a 500 response. Use ``strict=True`` for
    any non-admin endpoint that owns per-user data boundaries.
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
            "CROSS-TENANT GUARD%s: query returned rows from %d distinct "
            "org_ids (%s)%s. This may indicate a missing WHERE clause. "
            "investigate immediately.",
            " (STRICT)" if strict else "",
            len(org_ids),
            ", ".join(sorted(org_ids)),
            f" [context={context}]" if context else "",
        )
        try:
            from app.metrics_collector import record_cross_tenant_guard_alert

            record_cross_tenant_guard_alert()
        except Exception as exc:
            logger.debug("Failed to record cross-tenant guard metric: %s", exc)

        if strict:
            msg = f"Cross-tenant contamination detected ({context or 'unknown'}): {len(org_ids)} distinct org_ids in result set"
            raise CrossTenantContaminationError(msg)

    return org_ids
