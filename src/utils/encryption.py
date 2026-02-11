import logging
import os
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Manages encryption/decryption of API keys using Fernet symmetric encryption."""

    def __init__(self, master_key: str = None):
        """
        Initialize with a master key from environment.
        Accepts either a valid Fernet key (base64-encoded 32 bytes) or
        an arbitrary passphrase (derived via SHA-256).
        """
        raw_key = master_key or os.getenv('ENCRYPTION_MASTER_KEY', '')
        if not raw_key:
            raise ValueError(
                "ENCRYPTION_MASTER_KEY not set. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        # Try using the key directly as a valid Fernet key
        try:
            key_bytes = raw_key.encode() if isinstance(raw_key, str) else raw_key
            self._fernet = Fernet(key_bytes)
        except (ValueError, Exception):
            # Derive a valid Fernet key from the passphrase via SHA-256
            derived = hashlib.sha256(raw_key.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(derived)
            self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string, return base64-encoded ciphertext."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string back to plaintext."""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("Decryption failed - invalid key or corrupted data")

    @staticmethod
    def mask_key(key: str, visible_prefix: int = 3, visible_suffix: int = 6) -> str:
        """Mask an API key for display: 'sk-...xyz123'"""
        if not key or len(key) < (visible_prefix + visible_suffix + 3):
            return '***'
        return key[:visible_prefix] + '...' + key[-visible_suffix:]
