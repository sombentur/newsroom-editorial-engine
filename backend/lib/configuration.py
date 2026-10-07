"""Startup checks report setting names only, never their values."""
import os
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from lib.runtime import ConfigurationError, RuntimeSafety


def validate_environment():
    RuntimeSafety.from_env()
    from lib.manual_ai import enabled
    enabled()
    for name in ("MONGO_URL", "DB_NAME", "APP_URL", "SESSION_SECRET", "WP_CREDENTIAL_ENCRYPTION_KEY"):
        if not os.environ.get(name, "").strip():
            raise ConfigurationError(f"{name} is required. Run Setup Local.cmd or configure backend/.env locally.")
    if not os.environ["MONGO_URL"].startswith(("mongodb://", "mongodb+srv://")):
        raise ConfigurationError("MONGO_URL must be a MongoDB connection string.")
    if len(os.environ["SESSION_SECRET"]) < 32:
        raise ConfigurationError("SESSION_SECRET must contain at least 32 characters.")
    try:
        Fernet(os.environ["WP_CREDENTIAL_ENCRYPTION_KEY"].encode())
    except (ValueError, TypeError):
        raise ConfigurationError("WP_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key.") from None
    origin = urlsplit(os.environ["APP_URL"])
    if (origin.scheme not in {"http", "https"} or not origin.hostname or origin.username or origin.password
            or origin.path not in {"", "/"} or origin.query or origin.fragment
            or (origin.scheme == "http" and origin.hostname not in {"127.0.0.1", "localhost", "::1"})):
        raise ConfigurationError("APP_URL must be an HTTPS origin or a local loopback HTTP origin.")
