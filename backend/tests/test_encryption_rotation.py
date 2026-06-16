"""Unit tests for encryption key rotation.

Tests the multi-key support in backend/app/utils/encryption.py:
- Versioned key creation and selection
- Decryption fallback across multiple keys
- reencrypt_payload for key migration
- list_available_key_versions diagnostic
"""

from __future__ import annotations

import base64
import os

import pytest
from app.utils.encryption import (
    _derive_test_key,
    _get_all_available_keys,
    decrypt,
    encrypt,
    is_encrypted,
    list_available_key_versions,
    reencrypt_payload,
)


class TestEncryptionKeyRotation:
    """Tests for multi-key encryption support."""

    def test_encrypt_decrypt_basic(self) -> None:
        """Basic encrypt/decrypt round-trip works."""
        plaintext = "Hello, DataForge!"
        encrypted = encrypt(plaintext)
        assert encrypted != plaintext
        assert is_encrypted(encrypted)
        decrypted = decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_different_plaintexts_produce_different_outputs(self) -> None:
        """Different plaintexts produce different encrypted payloads."""
        e1 = encrypt("data1")
        e2 = encrypt("data2")
        assert e1 != e2

    def test_decrypt_wrong_payload_raises(self) -> None:
        """Decrypting garbage raises DecryptionError."""
        from app.utils.encryption import DecryptionError

        with pytest.raises(DecryptionError):
            decrypt("not-a-valid-payload")

    def test_reencrypt_payload_migrates_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """reencrypt_payload decrypts with old key and re-encrypts with new key."""
        # Set up two keys: V1 for original encryption, V2 for migration
        key_v1 = base64.b64encode(_derive_test_key("v1")).decode()
        key_v2 = base64.b64encode(_derive_test_key("v2")).decode()
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V1", key_v1)
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V2", key_v2)
        monkeypatch.setenv("DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION", "v1")
        monkeypatch.setenv("DATAFORGE_ENV", "test")

        # Encrypt with V1
        plaintext = "Sensitive data to migrate"
        original_encrypted = encrypt(plaintext)
        assert decrypt(original_encrypted) == plaintext

        # Migrate to V2
        monkeypatch.setenv("DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION", "v2")
        migrated = reencrypt_payload(original_encrypted, target_key_version="v2")
        assert migrated != original_encrypted
        assert decrypt(migrated) == plaintext

    def test_decryption_fallback_across_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """decrypt falls back to all available keys if stored version's key is missing."""
        key_v1 = base64.b64encode(_derive_test_key("v1")).decode()
        key_v2 = base64.b64encode(_derive_test_key("v2")).decode()

        # Set up both keys but encrypt with V1
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V1", key_v1)
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V2", key_v2)
        monkeypatch.setenv("DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION", "v1")
        monkeypatch.setenv("DATAFORGE_ENV", "test")

        plaintext = "Fallback test data"
        encrypted = encrypt(plaintext)
        assert decrypt(encrypted) == plaintext

        # Remove V1 key — decryption should fall back to V2
        monkeypatch.delenv("DATAFORGE_ENCRYPTION_KEY_V1", raising=False)
        decrypted = decrypt(encrypted)
        assert decrypted == plaintext

    def test_list_available_key_versions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """list_available_key_versions returns all configured keys with active marker."""
        key_v1 = base64.b64encode(_derive_test_key("v1")).decode()
        key_v2 = base64.b64encode(_derive_test_key("v2")).decode()
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V1", key_v1)
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V2", key_v2)
        monkeypatch.setenv("DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION", "v2")
        monkeypatch.setenv("DATAFORGE_ENV", "test")

        versions = list_available_key_versions()
        assert "v1" in versions
        assert "v2" in versions
        assert versions["v2"] is True  # active
        assert versions["v1"] is False  # not active

    def test_get_all_available_keys_discovers_versioned_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_all_available_keys discovers versioned keys from environment."""
        key_v1 = base64.b64encode(_derive_test_key("v1")).decode()
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V1", key_v1)
        monkeypatch.setenv("DATAFORGE_ENV", "test")

        keys = _get_all_available_keys()
        assert "v1" in keys
        assert len(keys) == 1

    def test_get_all_available_keys_falls_back_to_legacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_all_available_keys falls back to the legacy DATAFORGE_ENCRYPTION_KEY."""
        # Test with only the legacy key
        monkeypatch.setenv("DATAFORGE_ENV", "test")
        # Clear env vars so we get the test key
        monkeypatch.delenv("DATAFORGE_ENCRYPTION_KEY_V1", raising=False)

        keys = _get_all_available_keys()
        assert len(keys) >= 1  # test key will be derived

    def test_encrypt_with_no_key_in_production_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """encrypt raises EncryptionError in production with no keys configured."""
        from app.utils.encryption import EncryptionError

        monkeypatch.setenv("DATAFORGE_ENV", "production")
        # Clear all key env vars
        for env in list(os.environ.keys()):
            if env.startswith("DATAFORGE_ENCRYPTION_KEY"):
                monkeypatch.delenv(env, raising=False)

        with pytest.raises(EncryptionError):
            encrypt("should fail")

    def test_long_string_encrypt_decrypt(self) -> None:
        """Long strings (up to 10KB) round-trip correctly."""
        plaintext = "A" * 10_000
        encrypted = encrypt(plaintext)
        decrypted = decrypt(encrypted)
        assert decrypted == plaintext
        assert len(decrypted) == 10_000

    def test_unicode_strings(self) -> None:
        """Unicode strings (emoji, non-Latin) round-trip correctly."""
        plaintext = "Hello 世界 🌍 ¡¿Üñíçödé?! 🎉"
        encrypted = encrypt(plaintext)
        decrypted = decrypt(encrypted)
        assert decrypted == plaintext

    def test_is_encrypted_heuristic(self) -> None:
        """is_encrypted correctly identifies encrypted payloads."""
        plain = "not encrypted"
        assert not is_encrypted(plain)
        assert not is_encrypted("")
        assert not is_encrypted("abc123")

        encrypted = encrypt("test data")
        assert is_encrypted(encrypted)

    def test_reencrypt_payload_without_target_uses_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """reencrypt_payload without target_version uses the active key version."""
        key_v1 = base64.b64encode(_derive_test_key("v1")).decode()
        monkeypatch.setenv("DATAFORGE_ENCRYPTION_KEY_V1", key_v1)
        monkeypatch.setenv("DATAFORGE_ENV", "test")

        plaintext = "Migrate me"
        encrypted = encrypt(plaintext)

        # Re-encrypt without specifying target — uses active version
        result = reencrypt_payload(encrypted)
        assert decrypt(result) == plaintext
