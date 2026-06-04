"""Invariant Firewall — mutation guards for the semantic field.

Every mutation to the world state should pass through these guards,
which verify field invariants before and after each operation.
If invariants are violated, the mutation is rejected and auto-rolled-back
from a pre-mutation snapshot.
"""

import functools
import logging
from collections.abc import Callable

from app.field_validator import validate_world_state

logger = logging.getLogger(__name__)

# Sentinel attribute name to prevent re-entrant invariant checks during
# rollback
_ROLLBACK_GUARD_ATTR = "_invariant_rollback_active"


def requires_invariants(mutation_fn: Callable):
    """Decorator that enforces field invariants around a mutation.

    Checks invariants before and after the mutation and rejects
    the mutation if any invariants are violated. On violation,
    auto-rolls back to the pre-mutation state from a snapshot.

    Uses a rollback-in-progress guard attribute on the instance
    to prevent re-entrant invariant checking during restoration.
    """

    @functools.wraps(mutation_fn)
    def wrapper(*args, **kwargs):
        ws = _find_world_state(args, kwargs)

        # Skip invariant checks during rollback restoration
        if ws is not None and getattr(ws, _ROLLBACK_GUARD_ATTR, False):
            return mutation_fn(*args, **kwargs)

        snapshot: dict | None = None

        # Save snapshot for potential rollback
        if ws is not None:
            try:
                snapshot = ws.to_dict()
            except Exception as snapshot_err:
                snapshot = None
                logger.warning("Could not take snapshot before %s — rollback unavailable", mutation_fn.__name__)
                try:
                    ws.record_degradation(
                        subsystem="invariant_firewall",
                        severity="warning",
                        cause=f"Snapshot failed before {mutation_fn.__name__}: {snapshot_err}",
                    )
                except Exception:
                    pass  # nosec B110

            # Check pre-conditions
            pre_issues = validate_world_state(ws)
            if pre_issues:
                logger.warning("Pre-condition violation in %s: %s", mutation_fn.__name__, pre_issues[:3])

        # Execute mutation
        result = mutation_fn(*args, **kwargs)

        # Check post-conditions
        if ws is not None:
            post_issues = validate_world_state(ws)
            if post_issues:
                logger.error("Post-condition violation in %s: %s — rolling back", mutation_fn.__name__, post_issues[:3])
                if snapshot is not None:
                    try:
                        setattr(ws, _ROLLBACK_GUARD_ATTR, True)
                        ws.clear()
                        # Unwrap to avoid re-entering the decorator
                        original = getattr(ws.from_dict, "__wrapped__", ws.from_dict)
                        original(ws, snapshot)
                        logger.warning("Rolled back %s — %d issue(s) prevented", mutation_fn.__name__, len(post_issues))
                    except Exception as rollback_err:
                        logger.critical("ROLLBACK FAILED for %s: %s — state may be corrupt!", mutation_fn.__name__, rollback_err)
                        try:
                            ws.record_degradation(
                                subsystem="invariant_firewall",
                                severity="critical",
                                cause=f"Rollback failed for {mutation_fn.__name__}: {rollback_err}. State may be corrupt!",
                            )
                        except Exception:
                            pass  # nosec B110
                    finally:
                        setattr(ws, _ROLLBACK_GUARD_ATTR, False)
                else:
                    logger.critical("Cannot rollback %s — no snapshot available. State may be corrupt!", mutation_fn.__name__)
                    try:
                        ws.record_degradation(
                            subsystem="invariant_firewall",
                            severity="critical",
                            cause=f"Cannot rollback {mutation_fn.__name__} — no snapshot available. State may be corrupt!",
                        )
                    except Exception:
                        pass  # nosec B110
                msg = (
                    f"Invariant violation in {mutation_fn.__name__}: "
                    f"{post_issues[0]}{' (+' + str(len(post_issues) - 1) + ' more)' if len(post_issues) > 1 else ''}"
                )
                raise RuntimeError(
                    msg,
                )

        return result

    return wrapper


def _find_world_state(args, kwargs):
    """Find the world state object in args or kwargs."""
    from app.semantic_world_state import SemanticWorldState

    for arg in args:
        if isinstance(arg, SemanticWorldState):
            return arg
    for val in kwargs.values():
        if isinstance(val, SemanticWorldState):
            return val
    # Check for ws or self parameter
    if "ws" in kwargs:
        return kwargs["ws"]
    if "self" in kwargs:
        candidate = kwargs["self"]
        if hasattr(candidate, "field_regions"):
            return candidate
    return None
