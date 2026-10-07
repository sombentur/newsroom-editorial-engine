"""WordPress secrets: encrypted at rest, decrypted only by the server-side client."""
import os
import re
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken


class CredentialError(ValueError):
    pass


def _cipher() -> Fernet:
    key = os.environ.get("WP_CREDENTIAL_ENCRYPTION_KEY")
    if not key:
        raise CredentialError("WP_CREDENTIAL_ENCRYPTION_KEY must be configured on the server. No key was generated and no credential was changed.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise CredentialError("WordPress credential encryption key is unavailable or invalid.") from None


def normalize_password(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    if value and (set(value) <= set("•●*.xX") or any(c in value for c in "•●")):
        raise CredentialError("Enter an actual Application Password, not a masked placeholder.")
    return value


def encrypt_password(value: str) -> str:
    return _cipher().encrypt(normalize_password(value).encode()).decode()


def decrypt_password(site: dict) -> str:
    token = site.get("wp_password_ciphertext")
    if not token:
        raise CredentialError("Application Password is not configured.")
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        raise CredentialError("Stored Application Password cannot be decrypted. Restore the encryption key or replace the password.") from None


def normalize_base_url(value: str, domain: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "https" and parsed.hostname
                 and parsed.hostname.lower() in {domain.lower().removeprefix("www."), "www." + domain.lower().removeprefix("www.")}
                 and parsed.port in (None, 443) and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and not any(segment in {"wp-admin", "wp-login.php", "wp-json"} for segment in parsed.path.split("/")))
    except ValueError:
        valid = False
    if not valid:
        raise CredentialError(f"Save this website's HTTPS base URL (https://{domain}), not another website or a wp-admin, wp-login or wp-json URL.")
    return value


def missing_credentials(site: dict) -> list[str]:
    return [label for key, label in (("wp_base_url", "WordPress Base URL"), ("wp_username", "WordPress Username"),
                                    ("wp_password_ciphertext", "Application Password")) if not site.get(key)]


def is_connected(site: dict) -> bool:
    try:
        normalize_base_url(site.get("wp_base_url", ""), site.get("domain", ""))
    except CredentialError:
        return False
    test = site.get("connection_test") or {}
    return bool(not missing_credentials(site) and site.get("connected") and test.get("passed")
                and test.get("authenticated") is True and test.get("simulated") is False
                and site.get("credential_revision") and site.get("connection_revision") == site.get("credential_revision"))


def connection_reason(site: dict) -> str:
    try:
        normalize_base_url(site.get("wp_base_url", ""), site.get("domain", ""))
    except CredentialError as exc:
        return str(exc)
    missing = missing_credentials(site)
    if missing:
        return "Missing saved settings: " + ", ".join(missing) + ". Save Connection, then Test Connection."
    return (site.get("connection_test") or {}).get("message") or "Saved credentials have not passed a live authentication test."
