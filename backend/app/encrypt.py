"""
At-rest encryption utility for sensitive PII fields.

Uses Fernet (symmetric AES-128-CBC with HMAC-SHA256) via the cryptography library.
The encryption key is derived from SECRET_KEY using PBKDF2.

Usage:
    from app.encrypt import encrypt_field, decrypt_field
    
    # Store: encrypted = encrypt_field("sensitive data")
    # Retrieve: plaintext = decrypt_field(encrypted)
    
This provides at-rest encryption for sensitive database fields.
"""
import os
import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

log = logging.getLogger("webpanel")

# Derive encryption key from SECRET_KEY
_SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-use-32-char-secret")
_SALT = b"gnukontrolr-encryption-salt-v1"

_kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=_SALT,
    iterations=600000,
)
_fernet_key = base64.urlsafe_b64encode(_kdf.derive(_SECRET_KEY.encode()))
_cipher = Fernet(_fernet_key)


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string field for at-rest storage.
    
    Returns base64-encoded ciphertext prefixed with 'enc:' to distinguish
    from unencrypted values during migration.
    """
    if not plaintext:
        return ""
    try:
        encrypted = _cipher.encrypt(plaintext.encode())
        return "enc:" + encrypted.decode()
    except Exception as e:
        log.error("Encryption failed: %s", e)
        return plaintext  # Fallback: store plaintext (should not happen in production)


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a field that was encrypted with encrypt_field.
    
    Returns the original plaintext. If the value is not encrypted (no 'enc:' prefix),
    returns it as-is (backward compatibility during migration).
    """
    if not ciphertext:
        return ""
    if not ciphertext.startswith("enc:"):
        return ciphertext  # Not encrypted yet (migration in progress)
    try:
        encrypted_data = ciphertext[4:]  # Strip 'enc:' prefix
        decrypted = _cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()
    except Exception as e:
        log.error("Decryption failed: %s", e)
        return "[decryption error]"


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted."""
    return value.startswith("enc:") if value else False


def encrypt_dict(data: dict, fields: list[str]) -> dict:
    """Encrypt specified fields in a dictionary (for serialization)."""
    result = dict(data)
    for field in fields:
        if field in result and isinstance(result[field], str):
            result[field] = encrypt_field(result[field])
    return result


def decrypt_dict(data: dict, fields: list[str]) -> dict:
    """Decrypt specified fields in a dictionary."""
    result = dict(data)
    for field in fields:
        if field in result and isinstance(result[field], str):
            result[field] = decrypt_field(result[field])
    return result
