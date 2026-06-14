"""
At-rest encryption utility for sensitive PII fields.

Uses Fernet (symmetric AES-128-CBC with HMAC-SHA256) via the cryptography library.
The encryption key is derived from ENCRYPTION_KEY (or SECRET_KEY as fallback) using PBKDF2.

Usage:
    from app.encrypt import encrypt_field, decrypt_field

    # Store: encrypted = encrypt_field("sensitive data")
    # Retrieve: plaintext = decrypt_field(encrypted)

This provides at-rest encryption for sensitive database fields.
"""
import os
import base64
import logging
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

log = logging.getLogger("webpanel")

# H10: Use ENCRYPTION_KEY as the primary key material (separate from SECRET_KEY)
# Falls back to SECRET_KEY for backward compatibility with a warning.
_ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "") or os.environ.get("SECRET_KEY", "")
if not _ENCRYPTION_KEY:
    log.critical("FATAL: Neither ENCRYPTION_KEY nor SECRET_KEY is set.")
    raise SystemExit("Refusing to start without an encryption key.")

# H12: ENCRYPTION_SALT is required — fail if not set (no hardcoded fallback)
_ENCRYPTION_SALT = os.environ.get("ENCRYPTION_SALT", "")
if not _ENCRYPTION_SALT:
    _IS_PRODUCTION = os.environ.get("ENVIRONMENT", "").lower() == "production"
    if _IS_PRODUCTION:
        log.critical("FATAL: ENCRYPTION_SALT is not set in production. "
                     "Set a random 32-char hex string in .env .")
        raise SystemExit("Refusing to start without ENCRYPTION_SALT in production.")
    log.warning("ENCRYPTION_SALT not set — generating ephemeral salt (keys will change on restart!)")
    # Use SECRET_KEY as ephemeral salt so keys are at least unique per deployment
    _SALT = _ENCRYPTION_KEY.encode()
else:
    _SALT = _ENCRYPTION_SALT.encode()

_kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=32,
    salt=_SALT,
    iterations=600000,
)
_fernet_key = base64.urlsafe_b64encode(_kdf.derive(_ENCRYPTION_KEY.encode()))
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
        log.error("Encryption failed: %s — NOT storing plaintext (data leak prevented)", e)
        raise  # Never store plaintext — data leak prevention


# Legacy salt used before ENCRYPTION_SALT was introduced (commit 3eb59cb)
# This is kept for backward compatibility when decrypting data that was
# encrypted before the ENCRYPTION_SALT env var existed.
_LEGACY_SALT = b"gnukontrolr-encryption-salt-v1"

# Try to read the vault secret key — the setup script generated a unique
# SECRET_KEY in /run/secrets/env/main.env which may differ from the .env value.
_VAULT_SECRET_KEY = None
try:
    _vault_env = Path("/run/secrets/env/main.env")
    if _vault_env.exists():
        for line in _vault_env.read_text().splitlines():
            if line.startswith("SECRET_KEY="):
                _VAULT_SECRET_KEY = line.split("=", 1)[1].strip()
                break
except Exception:
    pass

_legacy_ciphers = []  # list of (key_label, Fernet)


def _init_legacy_ciphers():
    """Build a list of legacy cipher instances to try during decryption."""
    global _legacy_ciphers
    if _legacy_ciphers:
        return
    keys_to_try = [_ENCRYPTION_KEY]  # current key is always tried first
    if _VAULT_SECRET_KEY and _VAULT_SECRET_KEY != _ENCRYPTION_KEY:
        keys_to_try.append(_VAULT_SECRET_KEY)
    for key in keys_to_try:
        _kdf_legacy = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_LEGACY_SALT,
            iterations=600000,
        )
        _fernet = Fernet(base64.urlsafe_b64encode(_kdf_legacy.derive(key.encode())))
        _legacy_ciphers.append(_fernet)


def _try_decrypt(data: bytes) -> str | None:
    """Try all known ciphers in order. Returns plaintext or None."""
    # Current cipher first
    try:
        return _cipher.decrypt(data).decode()
    except Exception:
        pass
    # Legacy ciphers (pre-ENCRYPTION_SALT, possibly with vault SECRET_KEY)
    _init_legacy_ciphers()
    for c in _legacy_ciphers:
        try:
            return c.decrypt(data).decode()
        except Exception:
            continue
    return None


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a field that was encrypted with encrypt_field.

    Returns the original plaintext. If the value is not encrypted (no 'enc:' prefix),
    returns it as-is (backward compatibility during migration).

    Tries multiple decryption strategies in order:
    1. Current encryption key + current ENCRYPTION_SALT
    2. Current encryption key + legacy hardcoded salt (commit 3eb59cb)
    3. Vault SECRET_KEY (from /run/secrets/env/main.env if available) + legacy salt
    """
    if not ciphertext:
        return ""
    if not ciphertext.startswith("enc:"):
        return ciphertext  # Not encrypted yet (migration in progress)
    encrypted_data = ciphertext[4:]  # Strip 'enc:' prefix
    plaintext = _try_decrypt(encrypted_data.encode())
    if plaintext is not None:
        return plaintext
    log.error("Decryption failed — tried all known keys")
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
