"""Tests for the encryption module."""

import pytest
from app.utils.encryption import DecryptionError, EncryptionError, decrypt, encrypt, is_encrypted


class TestEncryptDecrypt:
    """Tests for basic encryption and decryption."""

    def test_roundtrip(self):
        plaintext = "sensitive-data-123!@#"
        encrypted = encrypt(plaintext)
        assert is_encrypted(encrypted)
        decrypted = decrypt(encrypted)
        assert decrypted == plaintext

    def test_empty_string(self):
        encrypted = encrypt("")
        assert is_encrypted(encrypted)
        assert decrypt(encrypted) == ""

    def test_unicode(self):
        plaintext = "日本語テスト 🚀 émojis"
        encrypted = encrypt(plaintext)
        assert decrypt(encrypted) == plaintext

    def test_large_payload(self):
        plaintext = "x" * 10000
        encrypted = encrypt(plaintext)
        assert decrypt(encrypted) == plaintext

    def test_different_payloads_produce_different_ciphertexts(self):
        encrypted1 = encrypt("test")
        encrypted2 = encrypt("test")
        # Due to random nonce, same plaintext should produce different ciphertexts
        assert encrypted1 != encrypted2

    def test_corrupted_payload_fails(self):
        encrypted = encrypt("test")
        corrupted = encrypted[:-5] + "XXXXX"
        with pytest.raises(DecryptionError):
            decrypt(corrupted)

    def test_is_encrypted_false_for_plaintext(self):
        assert is_encrypted("not-encrypted") is False
        assert is_encrypted("") is False
        assert is_encrypted(None) is False  # type: ignore[arg-type]

    def test_is_encrypted_false_for_base64_json_without_required_keys(self):
        import base64
        import json

        bad_payload = base64.b64encode(json.dumps({"foo": "bar"}).encode()).decode()
        assert is_encrypted(bad_payload) is False


class TestEncryptionKeyFallbackPolicy:
    """Bug S-003: ``encrypt()`` previously only refused to derive the
    public test key when ``DATAFORGE_ENV == "production"``. Every other
    env value (staging, unknown, the default ``development``-as-fallback
    when unset) silently encrypted auth-profile session secrets with a
    publicly-known key. The fix aligns ``encrypt()``'s last-resort
    branch with ``_get_key``'s policy: the test key is only permitted
    in ``{development, test}``; any other env without a configured key
    must fail closed.
    """

    _KEY_ENVS = (
        "DATAFORGE_ENCRYPTION_KEY",
        "DATAFORGE_ENCRYPTION_KEY_V1",
        "DATAFORGE_ENCRYPTION_KEY_V2",
        "DATAFORGE_ENCRYPTION_KEY_V3",
    )

    def _no_key_envs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in self._KEY_ENVS:
            monkeypatch.delenv(var, raising=False)

    def test_dev_env_uses_test_key_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_key_envs(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "development")
        # Must not raise; round-trip works with the derived test key.
        encrypted = encrypt("dev-secret")
        assert decrypt(encrypted) == "dev-secret"

    def test_test_env_uses_test_key_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_key_envs(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "test")
        encrypted = encrypt("test-secret")
        assert decrypt(encrypted) == "test-secret"

    def test_staging_env_fails_closed_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_key_envs(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "staging")
        with pytest.raises(EncryptionError):
            encrypt("staging-secret")

    def test_production_env_fails_closed_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_key_envs(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "production")
        with pytest.raises(EncryptionError):
            encrypt("prod-secret")

    def test_unknown_env_fails_closed_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_key_envs(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "some-unknown-env")
        with pytest.raises(EncryptionError):
            encrypt("unknown-env-secret")
