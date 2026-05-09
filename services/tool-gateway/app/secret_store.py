"""Tool-gateway-local Fernet secret store.

Mirrors services/control-plane/app/services/secret_store.py — same key
derivation rules, so a secret encrypted on the control plane decrypts
here. If we ever extract a shared package, these two files merge.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


class FernetSecretStore:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as e:
            raise ValueError("ciphertext could not be decrypted with the configured key") from e


def _derive_dev_key(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


_singleton: FernetSecretStore | None = None


def get_secret_store() -> FernetSecretStore:
    global _singleton
    if _singleton is not None:
        return _singleton

    key = settings.platform_secrets_key.strip()
    if not key:
        logger.warning(
            "PLATFORM_SECRETS_KEY is not set; deriving a dev-only Fernet key "
            "from JWT_SECRET. Set PLATFORM_SECRETS_KEY in the environment."
        )
        key = _derive_dev_key("platform-secrets|" + settings.jwt_secret)

    _singleton = FernetSecretStore(key)
    return _singleton
