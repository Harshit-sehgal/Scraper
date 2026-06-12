"""Encryption utilities for sensitive data at rest.

Provides authenticated encryption (AES-256-GCM) for auth profile
storage_state and other sensitive payloads. Keys are versioned and
loaded from environment variables — never committed.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Primary encryption key from environment. Must be a base64-encoded 32-byte key.
# Generate with: python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
_ENCRYPTION_KEY_ENV = "DATAFORGE_ENCRYPTION_KEY"
_ENCRYPTION_KEY_VERSION_ENV = "DATAFORGE_ENCRYPTION_KEY_VERSION"

# Default key version for new encryptions
DEFAULT_KEY_VERSION = "v1"

# GCM nonce size (12 bytes is standard / recommended by NIST)
_GCM_NONCE_SIZE = 12
# GCM tag size (16 bytes = 128 bits)
_GCM_TAG_SIZE = 16


class EncryptionError(Exception):
    """Raised when encryption operation fails."""


class DecryptionError(Exception):
    """Raised when decryption operation fails."""


class EncryptedPayload(NamedTuple):
    """Structured representation of an encrypted payload."""

    ciphertext_b64: str
    nonce_b64: str
    tag_b64: str
    key_version: str


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


def _get_key(key_version: str = DEFAULT_KEY_VERSION) -> bytes | None:
    """Retrieve the encryption key for a given version.

    In production, the key must be set via the ``DATAFORGE_ENCRYPTION_KEY``
    environment variable. In development/test, a predictable key is derived
    from the version string so tests can run without env configuration.
    """
    env_key = os.environ.get(_ENCRYPTION_KEY_ENV, "")
    if env_key:
        try:
            return base64.b64decode(env_key)
        except Exception as exc:
            logger.warning("Failed to decode encryption key from env: %s", exc)
            return None
    # Development fallback: derive predictable key from version
    # This is NOT secure — only for tests / local dev.
    if os.environ.get("DATAFORGE_ENV", "development").lower() in {"development", "test"}:
        return _derive_test_key(key_version)
    return None


def _derive_test_key(version: str) -> bytes:
    """Derive a predictable 32-byte key from a version string for testing."""
    import hashlib

    return hashlib.sha256(f"test-key-{version}".encode()).digest()


def _get_key_version() -> str:
    return os.environ.get(_ENCRYPTION_KEY_VERSION_ENV, DEFAULT_KEY_VERSION)


# ---------------------------------------------------------------------------
# Low-level AES-GCM
# ---------------------------------------------------------------------------


def _aes_gcm_encrypt(plaintext: bytes, key: bytes) -> tuple[bytes, bytes, bytes]:
    """Encrypt plaintext with AES-256-GCM.

    Returns ``(ciphertext, tag, nonce)``.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import-untyped]
    except ImportError as exc:
        msg = "cryptography library required for encryption. Install: pip install cryptography"
        raise EncryptionError(
            msg,
        ) from exc

    if len(key) not in (16, 24, 32):
        msg = f"Invalid key length: {len(key)} bytes (expected 16, 24, or 32)"
        raise EncryptionError(msg)

    nonce = secrets.token_bytes(_GCM_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    # AESGCM.encrypt returns ciphertext + tag appended
    ciphertext = ciphertext_with_tag[:-_GCM_TAG_SIZE]
    tag = ciphertext_with_tag[-_GCM_TAG_SIZE:]
    return ciphertext, tag, nonce


def _aes_gcm_decrypt(ciphertext: bytes, tag: bytes, nonce: bytes, key: bytes) -> bytes:
    """Decrypt AES-256-GCM ciphertext.

    Raises ``DecryptionError`` on failure.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import-untyped]
    except ImportError as exc:
        msg = "cryptography library required for decryption. Install: pip install cryptography"
        raise DecryptionError(
            msg,
        ) from exc

    if len(key) not in (16, 24, 32):
        msg = f"Invalid key length: {len(key)} bytes"
        raise DecryptionError(msg)

    aesgcm = AESGCM(key)
    ciphertext_with_tag = ciphertext + tag
    try:
        return aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    except Exception as exc:
        msg = "Decryption failed — invalid key, corrupted data, or tampering"
        raise DecryptionError(msg) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string and return a JSON-serializable payload.

    The returned string is a base64-encoded JSON object containing the
    ciphertext, nonce, tag, and key version. This format is self-contained
    and versioned for future key rotation.

    Raises:
        EncryptionError: If encryption fails (missing key, library error).
    """
    key = _get_key()
    if key is None:
        env = os.environ.get("DATAFORGE_ENV", "development").lower()
        if env == "production":
            msg = f"Encryption key not configured. Set {_ENCRYPTION_KEY_ENV} environment variable."
            raise EncryptionError(
                msg,
            )
        # In dev/test, derive a test key
        key = _derive_test_key(DEFAULT_KEY_VERSION)

    key_version = _get_key_version()
    ciphertext, tag, nonce = _aes_gcm_encrypt(plaintext.encode("utf-8"), key)

    payload = {
        "v": key_version,
        "c": base64.b64encode(ciphertext).decode("ascii"),
        "n": base64.b64encode(nonce).decode("ascii"),
        "t": base64.b64encode(tag).decode("ascii"),
    }
    import json

    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def decrypt(encrypted_payload: str) -> str:
    """Decrypt an encrypted payload back to the original plaintext string.

    Args:
        encrypted_payload: The base64-encoded payload returned by :func:`encrypt`.

    Raises:
        DecryptionError: If decryption fails.
    """
    try:
        import json

        payload_bytes = base64.b64decode(encrypted_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        msg = "Invalid encrypted payload format"
        raise DecryptionError(msg) from exc

    key_version = payload.get("v", DEFAULT_KEY_VERSION)
    key = _get_key(key_version)
    if key is None:
        msg = f"Encryption key not available for version {key_version}"
        raise DecryptionError(msg)

    try:
        ciphertext = base64.b64decode(payload["c"])
        nonce = base64.b64decode(payload["n"])
        tag = base64.b64decode(payload["t"])
    except (KeyError, ValueError) as exc:
        msg = "Malformed encrypted payload"
        raise DecryptionError(msg) from exc

    plaintext = _aes_gcm_decrypt(ciphertext, tag, nonce, key)
    return plaintext.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Heuristic check whether a string appears to be an encrypted payload.

    This is a best-effort check for validation purposes — it does not
    guarantee the payload is valid or decryptable.
    """
    if not value or not isinstance(value, str):
        return False
    try:
        import json

        payload_bytes = base64.b64decode(value)
        payload = json.loads(payload_bytes.decode("utf-8"))
        return all(k in payload for k in ("v", "c", "n", "t"))
    except Exception:
        return False
