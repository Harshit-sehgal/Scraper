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


class TestPerUserEncryptionSaltPolicy:
    """F-ENC-001: per-user encryption previously fell back to a source-visible
    literal default salt ``"default-salt-change-in-prod"`` whenever
    ``DATAFORGE_ENCRYPTION_SALT`` was unset. The result was that any reader
    who knew ``user_id`` could reproduce the per-user derived AES key and
    decrypt AuthProfile ciphertext — a plaintext-equivalent leak in any
    non-dev env where the operator forgot to set the salt.

    Fix: the per-user branch rejects unset ``DATAFORGE_ENCRYPTION_SALT`` in
    any env other than ``{development, test}``; the salt is permitted (any
    value) in dev/test so local contributors don't have to set it.
    """

    _SALT_ENV = "DATAFORGE_ENCRYPTION_SALT"

    def _no_salt_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(self._SALT_ENV, raising=False)

    def test_staging_env_fails_closed_without_salt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_salt_env(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "staging")
        with pytest.raises(EncryptionError):
            encrypt("user-payload", user_id="user-abc")

    def test_production_env_fails_closed_without_salt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._no_salt_env(monkeypatch)
        monkeypatch.setenv("DATAFORGE_ENV", "production")
        with pytest.raises(EncryptionError):
            encrypt("user-payload", user_id="user-abc")

    def test_dev_env_uses_per_user_key_when_salt_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # In dev, we accept dev-mode encryption but the per-user path
        # should still succeed when an explicit salt is set.
        monkeypatch.setenv("DATAFORGE_ENV", "development")
        monkeypatch.setenv(self._SALT_ENV, "dev-salt-value")
        encrypted = encrypt("dev-payload", user_id="user-xyz")
        # Round-trip requires the same user_id at decrypt; the per-user
        # marker in the payload forbids decrypt without it.
        assert decrypt(encrypted, user_id="user-xyz") == "dev-payload"

    def test_per_user_decrypt_without_user_id_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_ENV", "development")
        monkeypatch.setenv(self._SALT_ENV, "dev-salt-value")
        encrypted = encrypt("user-secret", user_id="user-123")
        with pytest.raises(DecryptionError):
            decrypt(encrypted)  # missing user_id

    def test_per_user_decrypt_with_wrong_user_id_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATAFORGE_ENV", "development")
        monkeypatch.setenv(self._SALT_ENV, "dev-salt-value")
        encrypted = encrypt("user-secret", user_id="user-123")
        with pytest.raises(DecryptionError):
            decrypt(encrypted, user_id="user-456")
