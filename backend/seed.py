"""Idempotent configuration initialization; never seeds articles or activity.

The two sites are placeholders: give them their real names, domains and WordPress details in the
Setup Wizard after the first start (nothing here needs editing).
"""
import asyncio
from lib.db import db, ensure_indexes
from lib.prompts import ARTICLE_PROMPT, IMAGE_PROMPT, RESEARCH_PROMPT
from lib.thumbnail_prompts import HUMAN_IMAGE_PROMPT, KANNADIGA_IMAGE_PROMPT
from lib.util import new_id, now_utc

SITES = [
    {
        "key": "kannadiga", "name": "Kannada Edition", "domain": "",
        "language": "kn", "audience": "Kannada readers in Karnataka and Kannadigas worldwide",
        "timezone": "Asia/Kolkata", "publish_times": [f"{h:02d}:00" for h in range(6, 24)],
        "daily_quota": 18, "word_count_min": 600, "word_count_max": 1100,
        "default_category": "Karnataka", "categories": ["Karnataka", "Politics", "Technology", "Cinema", "Jobs", "Regional", "Culture"],
        "author": "editorial-kn", "seo_plugin": "rankmath",
        "brand_style": "authoritative Kannada regional broadsheet", "tone": "clear, respectful, contemporary Kannada",
        "alert_channel": "", "auto_publish": False, "paused": False,
        "wp_base_url": "", "wp_username": "",
        "connected": False, "connection_test": None,
    },
    {
        "key": "human", "name": "English Edition", "domain": "",
        "language": "en", "audience": "English readers focused on the human consequences of policy, economy, tech, and AI",
        "timezone": "America/New_York", "publish_times": [f"{h:02d}:00" for h in range(6, 24)],
        "daily_quota": 18, "word_count_min": 700, "word_count_max": 1300,
        "default_category": "Economy", "categories": ["Economy", "Employment", "Technology", "Healthcare", "Immigration", "Labor", "Inequality"],
        "author": "editorial-en", "seo_plugin": "yoast",
        "brand_style": "serious global human-impact analysis", "tone": "empathetic, evidence-driven",
        "alert_channel": "", "auto_publish": False, "paused": False,
        "wp_base_url": "", "wp_username": "",
        "connected": False, "connection_test": None,
    },
]

PROMPTS = [
    {"key": "image_human", "name": "Human — Documentary Thumbnail", "template": HUMAN_IMAGE_PROMPT},
    {"key": "image_kannadiga", "name": "Kannadiga — Kannada Thumbnail", "template": KANNADIGA_IMAGE_PROMPT},
    {"key": "research", "name": "Source-Grounded Research Dossier", "template": RESEARCH_PROMPT},
    {"key": "article", "name": "Source-Grounded Article", "template": ARTICLE_PROMPT},
    {"key": "image", "name": "Featured Thumbnail", "template": IMAGE_PROMPT},
]


async def seed():
    for site in SITES:
        await db.sites.update_one({"key": site["key"]}, {"$setOnInsert": {
            **site, "credential_revision": new_id(), "created_at": now_utc(), "updated_at": now_utc()
        }}, upsert=True)
    for prompt in PROMPTS:
        await db.prompts.update_one({"key": prompt["key"]}, {"$setOnInsert": {
            "id": new_id(), **prompt, "version": 1, "versions": [], "updated_at": now_utc()
        }}, upsert=True)
    await db.system_settings.update_one({"id": "system"}, {"$setOnInsert": {
        "mode": "review", "scheduler_enabled": False, "repair_lock": True,
        "global_paused": True, "killswitch": False, "updated_at": now_utc()
    }}, upsert=True)

async def main():
    await ensure_indexes()
    await seed()

if __name__ == "__main__":
    asyncio.run(main())
