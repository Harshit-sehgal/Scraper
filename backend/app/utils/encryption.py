"""Encryption utilities for sensitive data at rest.

Provides authenticated encryption (AES-256-GCM) for auth profile
storage_state and other sensitive payloads. Keys are versioned and
loaded from environment variables — never committed.

Key rotation is supported through versioned env vars:

    DATAFORGE_ENCRYPTION_KEY_V1=<base64-key>
    DATAFORGE_ENCRYPTION_KEY_V2=<base64-key>   # new key for rotation
    DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION=v2

Old keys remain available for decryption; new encryptions use the
active key version.

Generate a key with: python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
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

# Single-key fallback (legacy, same as before)
_ENCRYPTION_KEY_ENV = "DATAFORGE_ENCRYPTION_KEY"
_ENCRYPTION_KEY_VERSION_ENV = "DATAFORGE_ENCRYPTION_KEY_VERSION"

# Multi-key rotation: versioned keys and active version selector
_ENCRYPTION_KEY_V_PREFIX = "DATAFORGE_ENCRYPTION_KEY_"
_ACTIVE_KEY_VERSION_ENV = "DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION"

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
# Key management — multi-version support
# ---------------------------------------------------------------------------


def _get_key(key_version: str = DEFAULT_KEY_VERSION) -> bytes | None:
    """Retrieve the encryption key for a given version.

    Resolution order:
    1. DATAFORGE_ENCRYPTION_KEY_V{version} (e.g., DATAFORGE_ENCRYPTION_KEY_V1)
    2. DATAFORGE_ENCRYPTION_KEY (legacy single key)
    3. Development/test: derive predictable key from version string

    In production, at least one key must be configured. In development/test,
    a predictable key is derived so tests can run without env configuration.
    """
    # Try versioned key: DATAFORGE_ENCRYPTION_KEY_V1, _V2, etc.
    versioned_env_name = f"{_ENCRYPTION_KEY_V_PREFIX}{key_version.upper()}"
    env_key = os.environ.get(versioned_env_name, "")
    if env_key:
        try:
            return base64.b64decode(env_key)
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to decode encryption key from %s: %s", versioned_env_name, exc)
            return None

    # Fall back to legacy single key
    env_key = os.environ.get(_ENCRYPTION_KEY_ENV, "")
    if env_key:
        try:
            return base64.b64decode(env_key)
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to decode encryption key from %s: %s", _ENCRYPTION_KEY_ENV, exc)
            return None

    # Development fallback: derive predictable key from version
    if os.environ.get("DATAFORGE_ENV", "development").lower() in {"development", "test"}:
        return _derive_test_key(key_version)
    return None


def _get_all_available_keys() -> dict[str, bytes]:
    """Discover all available encryption keys from the environment.

    Scans for DATAFORGE_ENCRYPTION_KEY_V1, _V2, etc. and falls back
    to the legacy DATAFORGE_ENCRYPTION_KEY (mapped to the version
    returned by _get_key_version()).

    Returns a dict of {version_string: key_bytes}.
    """
    keys: dict[str, bytes] = {}

    # Scan for versioned keys (V1, V2, V3, ...)
    for env_name, env_value in os.environ.items():
        if env_name.startswith(_ENCRYPTION_KEY_V_PREFIX) and env_value.strip():
            version_suffix = env_name[len(_ENCRYPTION_KEY_V_PREFIX) :].lower()
            if version_suffix:
                try:
                    key_bytes = base64.b64decode(env_value)
                    version = f"v{version_suffix}" if version_suffix.isdigit() else version_suffix
                    keys[version] = key_bytes
                except (ValueError, TypeError):
                    logger.debug("Skipping invalid key in %s", env_name)
                    continue

    # Legacy single key
    legacy_raw = os.environ.get(_ENCRYPTION_KEY_ENV, "")
    if legacy_raw:
        try:
            legacy_key = base64.b64decode(legacy_raw)
            # Only add if not already present under its version
            legacy_version = os.environ.get(_ENCRYPTION_KEY_VERSION_ENV, DEFAULT_KEY_VERSION)
            if legacy_version not in keys:
                keys[legacy_version] = legacy_key
        except (ValueError, TypeError):
            logger.debug("Skipping invalid legacy encryption key")

    # Development/test fallback: ensure at least one key exists
    if not keys:
        env = os.environ.get("DATAFORGE_ENV", "development").lower()
        if env in {"development", "test"}:
            test_key = _derive_test_key(DEFAULT_KEY_VERSION)
            keys[DEFAULT_KEY_VERSION] = test_key

    logger.debug("Available encryption keys: %s", list(keys.keys()))
    return keys


def _derive_test_key(version: str) -> bytes:
    """Derive a predictable 32-byte key from a version string for testing."""
    import hashlib

    return hashlib.sha256(f"test-key-{version}".encode()).digest()


def _get_key_version() -> str:
    """Return the active key version for NEW encryptions.

    Resolution order:
    1. DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION env var
    2. DATAFORGE_ENCRYPTION_KEY_VERSION env var (legacy)
    3. 'v1' (default)
    """
    active = os.environ.get(_ACTIVE_KEY_VERSION_ENV, "")
    if active:
        return active
    return os.environ.get(_ENCRYPTION_KEY_VERSION_ENV, DEFAULT_KEY_VERSION)


def list_available_key_versions() -> dict[str, bool]:
    """Return a dict of {version: is_active} for all configured keys.

    The active key version (used for new encryptions) is marked as
    ``is_active=True``. This is a diagnostic/management function.
    """
    active_version = _get_key_version()
    all_keys = _get_all_available_keys()
    return {v: (v == active_version) for v in all_keys}


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

    Uses the *active* key version for encryption.

    Raises:
        EncryptionError: If encryption fails (missing key, library error).
    """
    key_version = _get_key_version()
    key = _get_key(key_version)
    if key is None:
        # Try discovering any available key
        all_keys = _get_all_available_keys()
        if all_keys:
            # Use the first available key
            key_version = next(iter(all_keys))
            key = all_keys[key_version]
        else:
            # Last resort: dev-only fallback. Only derive a predictable
            # test key in development/test (matching ``_get_key``'s
            # policy at the top of this module). Any other env value
            # (staging, production, unknown) MUST fail closed — silently
            # encrypting auth-profile session secrets with a publicly-
            # known key in staging would be a plaintext-equivalent leak.
            env = os.environ.get("DATAFORGE_ENV", "development").lower()
            if env in {"development", "test"}:
                key = _derive_test_key(DEFAULT_KEY_VERSION)
                key_version = DEFAULT_KEY_VERSION
            else:
                env_var = f"{_ENCRYPTION_KEY_V_PREFIX}{key_version.upper()}"
                msg = (
                    f"Encryption key not configured (env={env!r}). "
                    f"Set {env_var} (or {env_var} / {_ENCRYPTION_KEY_ENV}) "
                    f"environment variable. Test-key fallback is only "
                    f"permitted in development/test."
                )
                raise EncryptionError(msg)

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

    Attempts to decrypt using the key version stored in the payload.
    If that key is not available or decryption fails, falls back to
    trying ALL available keys — supporting key rotation where data
    encrypted with old keys can still be decrypted.

    Args:
        encrypted_payload: The base64-encoded payload returned by :func:`encrypt`.

    Raises:
        DecryptionError: If decryption fails with all known keys.
    """
    try:
        import json

        payload_bytes = base64.b64decode(encrypted_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        msg = "Invalid encrypted payload format"
        raise DecryptionError(msg) from exc

    stored_key_version = payload.get("v", DEFAULT_KEY_VERSION)

    # Try the stored key version first
    key = _get_key(stored_key_version)
    if key is not None:
        try:
            ciphertext = base64.b64decode(payload["c"])
            nonce = base64.b64decode(payload["n"])
            tag = base64.b64decode(payload["t"])
            return _aes_gcm_decrypt(ciphertext, tag, nonce, key).decode("utf-8")
        except (KeyError, ValueError, DecryptionError) as exc:
            logger.debug("Decryption with version %s failed: %s", stored_key_version, exc)

    # Fall back to trying all available keys (key rotation support)
    all_keys = _get_all_available_keys()
    for version, fallback_key in all_keys.items():
        if version == stored_key_version:
            continue  # already tried above
        try:
            ciphertext = base64.b64decode(payload["c"])
            nonce = base64.b64decode(payload["n"])
            tag = base64.b64decode(payload["t"])
            result = _aes_gcm_decrypt(ciphertext, tag, nonce, fallback_key)
            logger.info("Decrypted payload with fallback key version %s (stored: %s)", version, stored_key_version)
            return result.decode("utf-8")
        except (KeyError, ValueError, DecryptionError):
            continue

    msg = f"Decryption failed — no available key for version {stored_key_version} and no fallback key succeeded"
    raise DecryptionError(msg)


def reencrypt_payload(encrypted_payload: str, target_key_version: str | None = None) -> str:
    """Decrypt and re-encrypt a payload, migrating it to the active key version.

    This is the key rotation migration function: it decrypts using
    whatever key was used originally (including fallback keys), then
    re-encrypts using the *active* key version (or *target_key_version*
    if specified).

    Args:
        encrypted_payload: Existing encrypted payload to migrate.
        target_key_version: Target version for re-encryption. Defaults to
            the active key version from environment.

    Returns:
        Newly encrypted payload string.

    Raises:
        DecryptionError: If the input cannot be decrypted.
        EncryptionError: If re-encryption fails.
    """
    plaintext = decrypt(encrypted_payload)

    # Temporarily override the active key version for re-encryption
    original_active_value = os.environ.get(_ACTIVE_KEY_VERSION_ENV)
    if target_key_version:
        os.environ[_ACTIVE_KEY_VERSION_ENV] = target_key_version

    try:
        return encrypt(plaintext)
    finally:
        if target_key_version:
            if original_active_value:
                os.environ[_ACTIVE_KEY_VERSION_ENV] = original_active_value
            else:
                os.environ.pop(_ACTIVE_KEY_VERSION_ENV, None)


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
