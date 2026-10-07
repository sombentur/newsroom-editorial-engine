"""Publish now (Broadcast Schedule, 27 Sep 2026): never two WordPress posts for one article; a scheduled post goes
live at once and frees its slot; live or rejected articles are refused."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_wordpress_writes_for_one_article_never_overlap_and_a_live_post_stays_live():
    from lib import workflow as w
    saved = {"id": "A", "stage": "image_ready", "wp": None}
    running, seen = [], []

    async def inner(art, site, status, when=None):
        running.append(1)
        assert len(running) == 1, "one WordPress write per article at a time"
        seen.append((status, (art.get("wp") or {}).get("post_id")))
        await asyncio.sleep(0.01)
        saved["wp"] = {"post_id": 2990, "status": status}
        running.pop()
        return dict(saved)

    database = SimpleNamespace(articles=SimpleNamespace(find_one=AsyncMock(side_effect=lambda *_a, **_k: dict(saved))))

    async def run():
        w._WP_WRITES.pop("A", None)
        with patch.object(w, "db", database), patch.object(w, "_wordpress_write", new=inner):
            # The scheduler's hand-off and the editor's Publish now arrive together.
            await asyncio.gather(w.wordpress_write({"id": "A"}, {}, "future", "2026-09-28T02:00:00+00:00"),
                                 w.wordpress_write({"id": "A"}, {}, "publish"))
            await w.wordpress_write({"id": "A"}, {}, "future", "2026-09-28T02:00:00+00:00")
        w._WP_WRITES.pop("A", None)
    asyncio.run(run())
    assert seen == [("future", None), ("publish", 2990)], "the second write updates the post the first one created"


def test_publishing_a_scheduled_post_now_moves_its_date_and_frees_its_slot():
    from lib import workflow as w
    bodies, saved = [], {}

    class FakeWP:
        base, api = "https://example.org", "https://example.org/wp-json/wp/v2"

        def __init__(self, site):
            pass

        async def _call(self, method, url, **kw):
            return {"id": 1}

        async def resolve_term(self, kind, name):
            return 5

        async def save_post(self, body, existing_id=None):
            bodies.append((body, existing_id))
            return {"id": 2987, "status": "publish", "link": "https://example.org/up-rain/"}

        async def write_seo(self, post_id, article, canonical):
            return False

        async def set_primary_category(self, post_id, term_id):
            return True

        async def read_post(self, post_id):
            return {"id": 2987, "status": "publish", "link": "https://example.org/up-rain/"}

        async def verify_public(self, url):
            return {"status_code": 200, "public_page_ok": True}

    async def update(art_id, patch_, hist=None):
        saved.update(patch_)
        return dict(saved)
    art = {"id": "A", "site_key": "kannadiga", "image": {"data_uri": "data:image/webp;base64,AA=="},
           "scheduled_time": "2099-01-01T02:00:00+00:00",
           "wp": {"simulated": False, "post_id": 2987, "status": "future", "featured_media_id": 2986}}
    article = {"headline": "t", "slug": "up-rain", "content_html": "<p>x</p>"}
    with patch("lib.wordpress.WordPressClient", FakeWP), patch.object(w, "_update", side_effect=update), \
            patch.object(w, "audit", AsyncMock()), patch.object(w, "db") as db:
        db.articles.update_one = AsyncMock()
        asyncio.run(w._wp_write_live(art, {"key": "kannadiga"}, article, "publish", None))
    body, existing = bodies[0]
    assert existing == 2987 and body["status"] == "publish", "the same post goes live"
    assert datetime.fromisoformat(body["date"]) <= datetime.now(timezone.utc), "its future date moves to now"
    assert saved["stage"] == "verified" and saved["scheduled_time"] is None, "its booked slot is free again"


def test_publish_now_refuses_live_and_rejected_articles():
    from fastapi import HTTPException
    from routers import pipeline as p
    for art in ({"id": "A", "stage": "verified", "wp": {"status": "publish"}}, {"id": "A", "stage": "rejected"}):
        with patch.object(p, "_article_or_404", AsyncMock(return_value=art)):
            try:
                asyncio.run(p.publish_article("A"))
            except HTTPException as exc:
                assert exc.status_code == 409
            else:
                raise AssertionError("must refuse " + art["stage"])
