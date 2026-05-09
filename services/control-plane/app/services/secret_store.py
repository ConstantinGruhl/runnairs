"""Symmetric secret storage.

`SecretStore` is the interface; `FernetSecretStore` is the prototype's
Fernet-backed implementation. To swap in HashiCorp Vault, AWS KMS, or
another backend, implement the same two-method interface and bind it
in get_secret_store().
"""
from __future__ import annotations

import base64
import hashlib
import logging
from abc import ABC, abstractmethod

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


class SecretStore(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> bytes: ...

    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> str: ...


class FernetSecretStore(SecretStore):
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            raise ValueError("ciphertext could not be decrypted with the configured key") from e


def _derive_dev_key(seed: str) -> str:
    """Derive a stable 32-byte url-safe Fernet key from a seed string.

    Used only when PLATFORM_SECRETS_KEY is unset. Loud warning logged.
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


_singleton: SecretStore | None = None


def get_secret_store() -> SecretStore:
    global _singleton
    if _singleton is not None:
        return _singleton

    key = settings.platform_secrets_key.strip()
    if not key:
        logger.warning(
            "PLATFORM_SECRETS_KEY is not set; deriving a dev-only Fernet key "
            "from JWT_SECRET. Set PLATFORM_SECRETS_KEY for any non-trivial use."
        )
        key = _derive_dev_key("platform-secrets|" + settings.jwt_secret)

    _singleton = FernetSecretStore(key)
    return _singleton
