from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from argon2.low_level import hash_secret_raw, Type

from backend.core.config import settings

ARGON2_TYPE = Type.ID


class SecureStorage:
    """AES-256-GCM encryption / decryption for user data at rest.

    The master key is derived via Argon2id from a user password and is never
    persisted to disk.  Only the salt (and Argon2 parameters) are stored.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("Master key must be 32 bytes (256 bits)")
        self._key = master_key

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    @classmethod
    def derive_key(cls, password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
        """Derive a 256-bit key from *password* via Argon2id.

        Returns ``(key, salt)``.  If *salt* is ``None`` a fresh random salt
        is generated.
        """
        if salt is None:
            salt = os.urandom(settings.ARGON2_SALT_BYTES)

        key = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=settings.ARGON2_ITERATIONS,
            memory_cost=settings.ARGON2_MEMORY_KB,
            parallelism=settings.ARGON2_PARALLELISM,
            hash_len=32,
            type=ARGON2_TYPE,
        )
        return key, salt

    def encrypt(self, plaintext: str | bytes) -> bytes:
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        nonce = os.urandom(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, blob: bytes) -> bytes:
        if len(blob) < 28:
            raise ValueError("Ciphertext too short (need nonce + tag + data)")
        nonce, ciphertext = blob[:12], blob[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def encrypt_file(self, source_path: Path, dest_path: Path) -> Path:
        plaintext = source_path.read_bytes()
        dest_path.write_bytes(self.encrypt(plaintext))
        return dest_path

    def decrypt_file(self, source_path: Path) -> bytes:
        return self.decrypt(source_path.read_bytes())

    def encrypt_json(self, data: dict | list) -> bytes:
        return self.encrypt(json.dumps(data, ensure_ascii=False))

    def decrypt_json(self, blob: bytes) -> dict | list:
        return json.loads(self.decrypt(blob).decode("utf-8"))


# ------------------------------------------------------------------
# Storage singleton helper
# ------------------------------------------------------------------
class VaultStore:
    """Manages the encrypted file vault on disk.

    Every file is stored as a named encrypted envelope whose filename is
    the SHA-256 hash of the original path (to avoid leaking metadata).
    """

    vault_dir: Path = settings.SECURE_VAULT_DIR

    def __init__(self, storage: SecureStorage):
        self._storage = storage
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _path_hash(original_path: str) -> str:
        import hashlib
        return hashlib.sha256(original_path.encode()).hexdigest()

    def store(self, original_path: str, content: bytes) -> Path:
        envelope = self.vault_dir / self._path_hash(original_path)
        envelope.write_bytes(self._storage.encrypt(content))
        return envelope

    def retrieve(self, original_path: str) -> bytes:
        envelope = self.vault_dir / self._path_hash(original_path)
        if not envelope.exists():
            raise FileNotFoundError(f"No vault entry for {original_path}")
        return self._storage.decrypt(envelope.read_bytes())
