"""Passwords (Argon2id), opaque session tokens (stored as SHA-256), and at-rest encryption
of third-party OAuth tokens (Fernet / AES-128-CBC + HMAC)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings

_ph = PasswordHasher()  # argon2id with library defaults (RFC 9106 low-memory profile)
_DUMMY_HASH = _ph.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    try:
        return _ph.verify(stored or _DUMMY_HASH, password) and stored is not None
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class TokenCipher:
    def __init__(self, key: str | None):
        self._f = Fernet(key.encode()) if key else None

    @property
    def available(self) -> bool:
        return self._f is not None

    def encrypt(self, plaintext: str) -> str:
        if not self._f:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured; cannot store OAuth tokens.")
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str | None:
        if not self._f:
            return None
        try:
            return self._f.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return None


def get_cipher() -> TokenCipher:
    key = get_settings().token_encryption_key
    return TokenCipher(key.get_secret_value() if key else None)
