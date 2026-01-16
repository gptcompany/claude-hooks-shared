#!/usr/bin/env python3
"""
Enterprise Secrets Loader - SOPS+age integration
Zero-friction, zero-leak secret management

Usage:
    from secrets_loader import load_secrets
    load_secrets()  # Instead of load_dotenv()

    api_key = os.getenv("API_KEY")  # Works exactly the same

The loader:
1. Tries to load from .env.enc (SOPS encrypted) first
2. Falls back to .env (plaintext) for dev environments
3. Supports audit logging for compliance
"""

import logging
import os
import subprocess
from pathlib import Path

# Audit logger setup
_audit_logger = None


def _get_audit_logger():
    """Get or create audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = logging.getLogger("secrets_audit")
        _audit_logger.setLevel(logging.INFO)
        # Only add handler if none exists
        if not _audit_logger.handlers:
            log_dir = Path("/var/log")
            if log_dir.exists() and os.access(log_dir, os.W_OK):
                handler = logging.FileHandler("/var/log/secrets_audit.log")
            else:
                # Fallback to user-writable location
                log_path = Path.home() / ".local/share/secrets_audit.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                handler = logging.FileHandler(log_path)
            handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            _audit_logger.addHandler(handler)
    return _audit_logger


class SecretsLoader:
    """Load secrets from SOPS-encrypted .env files."""

    def __init__(self, env_file: str = ".env.enc", audit: bool = True):
        self.env_file = Path(env_file)
        self._loaded = False
        self._audit = audit

    @staticmethod
    def _is_sops_available() -> bool:
        """Check if sops CLI is available."""
        try:
            subprocess.run(
                ["sops", "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _log_audit(self, action: str, file_path: str, success: bool):
        """Log audit event."""
        if not self._audit:
            return
        try:
            logger = _get_audit_logger()
            status = "SUCCESS" if success else "FAILED"
            user = os.getenv("USER", "unknown")
            cwd = os.getcwd()
            logger.info(f"{action} | {status} | file={file_path} | user={user} | cwd={cwd}")
        except Exception:
            pass  # Don't fail on audit logging errors

    def load(self) -> bool:
        """
        Load secrets from encrypted file into os.environ.
        Falls back to plaintext .env if .env.enc not found.

        Returns:
            bool: True if secrets were loaded successfully
        """
        if self._loaded:
            return True

        # Determine file paths
        enc_file = self.env_file
        if not str(enc_file).endswith(".enc"):
            enc_file = Path(str(self.env_file) + ".enc")

        plaintext_file = Path(str(enc_file).replace(".enc", ""))
        if str(plaintext_file) == str(enc_file):
            plaintext_file = Path(".env")

        # Try encrypted file first
        if enc_file.exists() and self._is_sops_available():
            success = self._load_encrypted(enc_file)
            if success:
                return True

        # Fallback to plaintext .env
        if plaintext_file.exists():
            return self._load_plaintext(plaintext_file)

        # Try current directory .env as last resort
        if Path(".env").exists():
            return self._load_plaintext(Path(".env"))

        return False

    def _load_encrypted(self, path: Path) -> bool:
        """Decrypt and load secrets."""
        try:
            result = subprocess.run(
                ["sops", "-d", "--input-type", "dotenv", "--output-type", "dotenv", str(path)],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            self._parse_dotenv(result.stdout)
            self._loaded = True
            self._log_audit("LOAD_ENCRYPTED", str(path), True)
            return True
        except subprocess.CalledProcessError as e:
            self._log_audit("LOAD_ENCRYPTED", str(path), False)
            # Log error details for debugging
            import sys

            print(f"SOPS decrypt failed: {e.stderr}", file=sys.stderr)
            return False
        except subprocess.TimeoutExpired:
            self._log_audit("LOAD_ENCRYPTED", str(path), False)
            return False

    def _load_plaintext(self, path: Path) -> bool:
        """Load plaintext .env file."""
        try:
            with open(path) as f:
                self._parse_dotenv(f.read())
            self._loaded = True
            self._log_audit("LOAD_PLAINTEXT", str(path), True)
            return True
        except OSError:
            self._log_audit("LOAD_PLAINTEXT", str(path), False)
            return False

    def _parse_dotenv(self, content: str) -> None:
        """Parse dotenv format and set env vars."""
        for line in content.strip().split("\n"):
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Skip export prefix
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                os.environ[key] = value


# Module-level singleton
_loader = None


def load_secrets(env_file: str = ".env.enc", audit: bool = True) -> bool:
    """
    Load secrets - drop-in replacement for load_dotenv().

    Args:
        env_file: Path to encrypted .env file (default: .env.enc)
        audit: Enable audit logging (default: True)

    Returns:
        bool: True if secrets were loaded successfully

    Usage:
        from secrets_loader import load_secrets
        load_secrets()  # Instead of load_dotenv()

        api_key = os.getenv("API_KEY")  # Works exactly the same
    """
    global _loader
    _loader = SecretsLoader(env_file, audit=audit)
    return _loader.load()


def get_secret(key: str, default: str = None) -> str:
    """
    Get a secret value from environment.

    Args:
        key: Environment variable name
        default: Default value if not found

    Returns:
        Secret value or default
    """
    return os.getenv(key, default)


# Convenience: auto-load on import if .env.enc exists
# Uncomment the line below to enable auto-loading
# load_secrets()
