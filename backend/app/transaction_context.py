from contextvars import ContextVar
from typing import Any, Dict, Optional

# Canonical transaction context for the semantic substrate
# Maps state_object_id -> staging_dict
active_transaction: ContextVar[Optional[Dict[str, Any]]] = ContextVar("active_transaction", default=None)


def get_active_transaction() -> Optional[Dict[str, Any]]:
    return active_transaction.get()


def is_in_transaction() -> bool:
    return active_transaction.get() is not None
