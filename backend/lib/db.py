"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

load_dotenv(Path(__file__).parent.parent / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000, tz_aware=True)
db = client[os.environ["DB_NAME"]]

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on.
INDEXES: dict[str, list[IndexModel]] = {
    "admins": [IndexModel([("id", ASCENDING)], name="admin_id", unique=True)],
    "sessions": [IndexModel([("token_hash", ASCENDING)], name="token", unique=True),
                 IndexModel([("expires_at", ASCENDING)], name="session_expiry", expireAfterSeconds=0)],
    "login_attempts": [IndexModel([("id", ASCENDING)], name="attempt_id", unique=True),
                       IndexModel([("expires_at", ASCENDING)], name="attempt_expiry", expireAfterSeconds=0)],
    "status_checks": [IndexModel([("timestamp", DESCENDING)], name="timestamp_desc")],
    "sites": [IndexModel([("key", ASCENDING)], name="site_key", unique=True)],
    "system_settings": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "topics": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("site_key", ASCENDING), ("run_date", DESCENDING)], name="site_run"),
        IndexModel([("status", ASCENDING)], name="status"),
        IndexModel([("fingerprint", ASCENDING)], name="fingerprint"),
    ],
    "articles": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("idempotency_key", ASCENDING)], name="idem", unique=True),
        IndexModel([("site_key", ASCENDING), ("stage", ASCENDING)], name="site_stage"),
        IndexModel([("scheduled_time", ASCENDING)], name="scheduled"),
    ],
    "prompts": [IndexModel([("key", ASCENDING)], name="prompt_key", unique=True)],
    "audit_logs": [IndexModel([("at", DESCENDING)], name="at_desc")],
    "published_posts": [
        IndexModel([("site_key", ASCENDING), ("fingerprint", ASCENDING)], name="site_fp"),
        IndexModel([("site_key", ASCENDING)], name="pp_site"),
    ],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception:
                raise RuntimeError(f"Required database index unavailable: {collection}.{model.document['name']}") from None
