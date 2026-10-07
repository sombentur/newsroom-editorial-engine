"""Small shared helpers: UTC time, doc cleaning, credential redaction, audit trail."""

import uuid
from datetime import datetime, timezone
from typing import Any

from lib.db import db
from lib.redaction import redact


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def clean(doc: dict | None) -> dict | None:
    """Strip Mongo's _id so a document is JSON-serialisable."""
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


def clean_all(docs: list[dict]) -> list[dict]:
    for d in docs:
        d.pop("_id", None)
    return docs


SECRET_FIELDS = {"wp_app_password", "wp_password_ciphertext", "gemini_api_key", "image_api_key", "openai_api_key"}


def redact_site(site: dict) -> dict:
    """Return a site doc safe for the browser — secrets replaced by has_* booleans."""
    site = clean(dict(site))
    from lib.wp_credentials import is_connected, connection_reason
    site["has_wp_password"] = bool(site.get("wp_password_ciphertext"))
    site["connected"] = is_connected(site)
    site["connection_reason"] = connection_reason(site)
    site.pop("credential_revision", None)
    site.pop("connection_revision", None)
    for f in SECRET_FIELDS:
        site.pop(f, None)
    return site


async def audit(
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    site_key: str | None = None,
    actor: str = "system",
    detail: Any = None,
) -> None:
    await db.audit_logs.insert_one(
        {
            "id": new_id(),
            "at": now_utc(),
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "site_key": site_key,
            "detail": redact(detail),
        }
    )
