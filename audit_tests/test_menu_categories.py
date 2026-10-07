"""Owner rule (29 Sep 2026): every post sits under one of its site's header-menu categories (the Kannada site one, the English site one or
two); the topic category stays as a secondary; existing categories are never removed."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib import menu_categories as m  # noqa: E402


def ids(chosen):
    return [c["id"] for c in chosen[0]]


def test_chatgpts_pick_is_validated_against_the_menu():
    assert ids(m.choose("human", ["Immigration", "United States", "Economy"])) == [1355, 97], "at most two on the English site"
    assert ids(m.choose("human", ["Work and Labor"])) == [1331], "English variants are understood"
    assert ids(m.choose("kannadiga", ["ಕರ್ನಾಟಕ", "ಭಾರತ"])) == [182], "exactly one on the Kannada site"
    assert ids(m.choose("kannadiga", "Karnataka")) == [182]
    assert m.choose("human", ["Sports"], {"headline": "Union workers win a wage deal"})[1] == "keyword rules"
    assert m.choose("unknown", ["Economy"]) == ([], "no menu configured")


def test_keyword_rules_and_site_default_when_chatgpt_gives_no_valid_pick():
    assert ids(m.choose("human", None, {"headline": "Layoffs hit warehouse workers", "category": "Labor"})) == [1331]
    assert ids(m.choose("human", None, {"headline": "AI claim denials", "category": "Healthcare"})) == [1336]
    assert ids(m.choose("human", None, {"headline": "New software award"})) == [35], "whole words: no 'war' in software"
    assert ids(m.choose("kannadiga", None, {"headline": "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಮಳೆ", "category": "ಹವಾಮಾನ"})) == [182]
    assert ids(m.choose("kannadiga", None, {"headline": "ಹೊಸ ಸುದ್ದಿ"})) == [18], "the Kannada site default"


def test_seo_prompt_lists_the_sites_menu_and_parse_keeps_the_pick():
    from lib import report_article as r
    for key, name in (("human", "- Work & Labor: jobs"), ("kannadiga", "- ಹೂಡಿಕೆ: Stock market")):
        prompt = r.seo_prompt({"content_html": "<p>x</p>", "headline": "H"},
                              {"key": key, "name": "Site", "language": "kn" if key == "kannadiga" else "en"})
        assert '"menu_categories"' in prompt and "MENU CATEGORIES" in prompt and name in prompt
    assert "menu_categories" in r.SEO_FIELDS


class FakeWP:
    base, api = "https://example.org", "https://example.org/wp-json/wp/v2"

    def __init__(self, current=None, terms=None):
        self.current, self.terms, self.created, self.primary = current, terms or {}, [], []

    async def resolve_term(self, kind, name, parent=None):
        if name not in self.terms:
            self.created.append((name, parent))
            self.terms[name] = 5000 + len(self.created)
        return self.terms[name]

    async def read_post(self, post_id):
        return {"id": post_id, "categories": self.current or []}


def cats(article, current=None, existing=None, site="human", terms=None):
    from lib import workflow as w
    wp = FakeWP(current, terms)
    result = asyncio.run(w._post_categories(wp, {"site_key": site, "topic_snapshot": {}}, article, existing))
    return result, wp


def test_new_post_gets_menu_categories_first_and_a_new_topic_category_under_the_main_one():
    (got, primary, menu), wp = cats({"category": "Retirement", "menu_categories": [{"id": 1336, "name": "Economy"}]})
    assert got == [1336, 5001] and primary == 1336 and wp.created == [("Retirement", 1336)]
    (got, primary, _), _ = cats({"category": "Economy", "menu_categories": [{"id": 1336, "name": "Economy"}]},
                                terms={"Economy": 1336})
    assert got == [1336] and primary == 1336, "a topic named like the menu category is the menu category"


def test_existing_post_keeps_its_categories_and_its_own_menu_category():
    article = {"category": "Labor", "menu_categories": [{"id": 1331, "name": "Work & Labor"}]}
    (got, primary, _), _ = cats(article, current=[97, 1415], existing=2977, terms={"Labor": 1415})
    assert got == [97, 1415] and primary is None, "already under United States: left as it is, primary untouched"
    (got, primary, _), _ = cats(article, current=[1415, 1], existing=2977, terms={"Labor": 1415})
    assert got == [1331, 1415, 1] and primary == 1331, "no menu category yet: added, nothing removed"


def test_resolve_term_matches_escaped_names_and_creates_categories_under_a_parent():
    from lib.wordpress import WordPressClient
    client = WordPressClient.__new__(WordPressClient)
    client.api = "https://example.org/wp-json/wp/v2"
    calls = []

    async def fake_call(method, url, **kw):
        calls.append((method, kw.get("json")))
        return [{"id": 1331, "name": "Work &amp; Labor"}] if method == "GET" else {"id": 9}
    client._call = fake_call
    assert asyncio.run(client.resolve_term("categories", "Work & Labor", parent=97)) == 1331 and len(calls) == 1
    assert asyncio.run(client.resolve_term("categories", "Retirement", parent=1336)) == 9
    assert calls[-1] == ("POST", {"name": "Retirement", "parent": 1336})
    assert asyncio.run(client.resolve_term("tags", "401k", parent=1336)) == 9 and calls[-1] == ("POST", {"name": "401k"})
