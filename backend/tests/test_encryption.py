"""Tests for the encryption module."""

import pytest
from app.utils.encryption import DecryptionError, decrypt, encrypt, is_encrypted


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
