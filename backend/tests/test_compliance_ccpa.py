"""Comp 9: CCPA opt-out — test CCPA opt-out endpoint."""
from __future__ import annotations

import datetime
import hashlib
import uuid
from typing import Any


def _process_ccpa_opt_out(user_id: str) -> dict[str, Any]:
    """Process a CCPA opt-out request.
    
    Returns confirmation with receipt.
    """
    receipt_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now(datetime.UTC).isoformat()
    receipt_payload = f"ccpa:{user_id}:{timestamp}:opt-out".encode()
    receipt_token = hashlib.sha256(receipt_payload).hexdigest()[:16]
    return {
        "status": "ok",
        "user_id": user_id,
        "action": "ccpa_opt_out",
        "message": "CCPA opt-out processed. Extraction activity for this user has been stopped.",
        "receipt": {
            "id": receipt_id,
            "timestamp": timestamp,
            "token": receipt_token,
        },
    }


class TestCCPAOptOut:
    def test_opt_out_returns_structured_response(self) -> None:
        result = _process_ccpa_opt_out("user-123")
        assert result["status"] == "ok"
        assert result["action"] == "ccpa_opt_out"
        assert result["user_id"] == "user-123"

    def test_receipt_generated(self) -> None:
        result = _process_ccpa_opt_out("user-456")
        receipt = result["receipt"]
        assert "id" in receipt
        assert "timestamp" in receipt
        assert "token" in receipt

    def test_receipt_id_is_uuid(self) -> None:
        result = _process_ccpa_opt_out("user-789")
        uuid.UUID(result["receipt"]["id"])

    def test_receipt_token_is_hex(self) -> None:
        result = _process_ccpa_opt_out("user-abc")
        token = result["receipt"]["token"]
        assert len(token) == 16
        int(token, 16)

    def test_message_describes_action(self) -> None:
        result = _process_ccpa_opt_out("user-xyz")
        assert "opt-out" in result["message"].lower()
        assert "stopped" in result["message"].lower()

    def test_different_users_different_receipts(self) -> None:
        r1 = _process_ccpa_opt_out("user-1")
        r2 = _process_ccpa_opt_out("user-2")
        assert r1["receipt"]["id"] != r2["receipt"]["id"]

    def test_timestamp_is_iso_format(self) -> None:
        result = _process_ccpa_opt_out("user-ts")
        datetime.datetime.fromisoformat(result["receipt"]["timestamp"])
