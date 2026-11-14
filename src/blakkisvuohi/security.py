"""
Protection of personal data.

Layers, from the outside in:

* **Pseudonymous ids.** Telegram user and chat ids are never stored; an HMAC-SHA-256 under a secret
  key is. Without the key the values are useless (the previous version used an unsalted SHA-256,
  which can be brute forced because Telegram ids are small numbers).
* **Per-user data keys.** Everything about a user (nickname, body data, every drink) is encrypted
  with AES-256-GCM under a random key of that user. The data key is stored *wrapped* (encrypted)
  under a master key derived from SECRET_KEY, in a different database file than the data. Deleting
  a user's wrapped key therefore makes their data unrecoverable, also from any backup of the data
  file ("crypto-shredding").
* **Bound and padded.** A ciphertext is bound to its owner and purpose, so it cannot be moved
  between rows, and is padded to a fixed block size so that its length does not tell how many
  drinks a user has.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_SALT = b"blakkisvuohi/v5"
_VERSION = "v1"


class DecryptionError(Exception):
    """Ciphertext is malformed, was tampered with, or the key is wrong."""


def _derive(secret: bytes, purpose: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=f"blakkisvuohi/{purpose}".encode(),
    ).derive(secret)


def _seal(aead: AESGCM, data: bytes, aad: str) -> str:
    nonce = os.urandom(12)
    return (
        f"{_VERSION}."
        + base64.urlsafe_b64encode(nonce + aead.encrypt(nonce, data, aad.encode())).decode()
    )


def _open(aead: AESGCM, token: str, aad: str) -> bytes:
    try:
        version, _, payload = token.partition(".")
        if version != _VERSION:
            raise DecryptionError("unknown ciphertext version")
        raw = base64.urlsafe_b64decode(payload.encode())
        return aead.decrypt(raw[:12], raw[12:], aad.encode())
    except (InvalidTag, ValueError) as exc:
        raise DecryptionError("cannot decrypt value") from exc


class DataKey:
    """The encryption key of one user."""

    __slots__ = ("_aead", "_raw")

    def __init__(self, raw: bytes) -> None:
        if len(raw) != 32:
            raise ValueError("a data key is 32 bytes")
        self._raw = raw
        self._aead = AESGCM(raw)

    def __repr__(self) -> str:  # never let a key end up in a log
        return "DataKey(<hidden>)"

    def seal(self, value: Any, *, aad: str, pad_to: int = 256) -> str:
        """Encrypt a JSON serialisable value, padded (with JSON whitespace) to `pad_to` bytes."""
        data = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        if pad_to:
            data += b" " * (-len(data) % pad_to)
        return _seal(self._aead, data, aad)

    def open(self, token: str, *, aad: str) -> Any:
        try:
            return json.loads(_open(self._aead, token, aad))
        except ValueError as exc:  # not JSON: cannot happen for data that we sealed
            raise DecryptionError("cannot decode value") from exc


class Crypto:
    def __init__(self, secret_key: str) -> None:
        secret = secret_key.encode()
        self._pseudonym_key = _derive(secret, "pseudonym")
        self._wrap = AESGCM(_derive(secret, "key-wrap"))
        self._webhook_key = _derive(secret, "webhook-path")

    # -- pseudonymous identifiers -------------------------------------------------------------

    def _pseudonym(self, kind: str, value: int) -> str:
        # The kind prefix keeps user and group pseudonyms from ever colliding or being correlated.
        message = f"{kind}:{int(value)}".encode()
        return hmac.new(self._pseudonym_key, message, hashlib.sha256).hexdigest()

    def user_id(self, telegram_user_id: int) -> str:
        return self._pseudonym("user", telegram_user_id)

    def group_id(self, telegram_chat_id: int) -> str:
        return self._pseudonym("group", telegram_chat_id)

    def key_check(self) -> str:
        """Stored in the databases to detect a changed SECRET_KEY at startup."""
        return hmac.new(self._pseudonym_key, b"key-check", hashlib.sha256).hexdigest()

    def webhook_path(self) -> str:
        """Unguessable webhook path, so the bot token never appears in URLs or access logs."""
        return "/webhook/" + hmac.new(self._webhook_key, b"path", hashlib.sha256).hexdigest()[:48]

    # -- data keys ----------------------------------------------------------------------------

    @staticmethod
    def new_data_key() -> DataKey:
        return DataKey(os.urandom(32))

    def wrap(self, key: DataKey, user_id: str) -> str:
        return _seal(self._wrap, key._raw, f"{user_id}:key")  # noqa: SLF001

    def unwrap(self, token: str, user_id: str) -> DataKey:
        return DataKey(_open(self._wrap, token, f"{user_id}:key"))
