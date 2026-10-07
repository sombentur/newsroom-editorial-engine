"""An interrupted WordPress create is adopted only when the post is provably this article's."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def _client(rows):
    from lib.wordpress import WordPressClient
    wp = WordPressClient.__new__(WordPressClient)
    wp.api = "https://example.org/wp-json/wp/v2"
    wp._call = AsyncMock(return_value=rows)
    return wp


BODY = {"slug": "ilo-convention-193", "title": "ILO Convention 193", "author": 1, "featured_media": 2734}
OURS = {"id": 2735, "slug": "ilo-convention-193", "title": {"raw": "ILO Convention 193"}, "author": 1,
        "featured_media": 2734, "status": "future", "link": "https://example.org/?p=2735"}


def test_own_interrupted_post_is_adopted():
    assert asyncio.run(_client([OURS]).find_own_post(BODY))["id"] == 2735


def test_other_posts_are_never_adopted():
    for other in ({**OURS, "title": {"raw": "Another story"}}, {**OURS, "author": 7}, {**OURS, "featured_media": 99}):
        assert asyncio.run(_client([other]).find_own_post(BODY)) is None


def test_scheduled_post_already_live_is_recorded_as_published():
    from unittest.mock import patch
    from lib import workflow as w

    class FakeWP:
        base, api = "https://example.org", "https://example.org/wp-json/wp/v2"

        def __init__(self, site):
            pass

        async def _call(self, method, url, **kw):
            return {"id": 1}

        async def find_media_by_slug(self, slug):
            return {"id": 2734}

        async def resolve_term(self, kind, name):
            return 5

        async def save_post(self, body, existing_id=None):
            return {"id": 2735, "status": "future", "link": "https://example.org/?p=2735"}

        async def write_seo(self, post_id, article, canonical):
            return False

        async def set_primary_category(self, post_id, term_id):
            return True

        async def read_post(self, post_id):  # the scheduled time came: WordPress published it
            return {"id": 2735, "status": "publish", "link": "https://example.org/ilo-convention-193/"}

        async def verify_public(self, url):
            return {"status_code": 200, "public_page_ok": True}

    saved = {}

    async def update(art_id, patch_, hist=None):
        saved.update(patch_)
        return dict(saved)
    art = {"id": "A", "site_key": "human", "image": {"data_uri": "data:image/webp;base64,AA=="}}
    article = {"headline": "ILO Convention 193", "slug": "ilo-convention-193", "content_html": "<p>x</p>"}
    with patch("lib.wordpress.WordPressClient", FakeWP), patch.object(w, "_update", side_effect=update), \
            patch.object(w, "audit", AsyncMock()), patch.object(w, "db") as db:
        db.articles.update_one = AsyncMock()
        asyncio.run(w._wp_write_live(art, {"key": "human"}, article, "future", "2026-09-27T08:07:00Z"))
    assert saved["stage"] == "verified" and saved["wp"]["status"] == "publish"
    assert saved["wp"]["public_url"] == "https://example.org/ilo-convention-193/"
