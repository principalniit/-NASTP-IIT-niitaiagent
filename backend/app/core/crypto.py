"""Encryption for stored credentials (integration secrets).

Fernet (AES-128-CBC with HMAC-SHA256) keyed from INTEGRATIONS_ENCRYPTION_KEYS. The keys
live only in the server environment; the database holds ciphertext. Without a key,
secrets cannot be stored at all.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings
from app.core.errors import ConflictError


class EncryptionUnavailableError(ConflictError):
    def __init__(self) -> None:
        super().__init__(
            "Credentials cannot be stored until the server operator sets "
            "INTEGRATIONS_ENCRYPTION_KEYS.",
            code="encryption_key_missing",
        )


def _cipher() -> MultiFernet:
    keys = get_settings().encryption_keys
    if not keys:
        raise EncryptionUnavailableError()
    return MultiFernet([Fernet(k) for k in keys])


def available() -> bool:
    return bool(get_settings().encryption_keys)


def encrypt(plaintext: str) -> bytes:
    return _cipher().encrypt(plaintext.encode())


def decrypt(token: bytes) -> str:
    try:
        return _cipher().decrypt(token).decode()
    except InvalidToken as exc:
        raise ValueError("The stored secret cannot be decrypted with the configured keys") from exc


def rotate(token: bytes) -> bytes:
    """Re-encrypt with the first (newest) key."""
    return _cipher().rotate(token)
