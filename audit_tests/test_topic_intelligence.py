"""Topic Intelligence (owner rules, 28 Sep 2026): each site's sources and brief, fresh fitting news only, an AI editor
scoring against the brief, and 70+ topics moving to the Editorial Workbench up to the daily quota."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_each_site_reads_its_own_sources():
    from lib.editorial_briefs import FEEDS, source_urls
    kn, en = source_urls("kannadiga"), source_urls("human")
    assert kn[:len(FEEDS["kannadiga"])] == FEEDS["kannadiga"] and "https://www.prajavani.net/stories.rss" in kn
    assert all("hl=en-IN" in u and "when%3A2d" in u for u in kn[len(FEEDS["kannadiga"]):])
    assert en and all("hl=en-US" in u and "when%3A2d" in u for u in en)


def test_kinds_of_story_each_site_never_covers():
    from lib.editorial_briefs import excluded
    assert excluded("human", "Karnataka government announces a new scheme")
    assert excluded("human", "How to write a resume that beats AI filters")
    assert excluded("human", "10 tips to save money on groceries")
    assert not excluded("human", "Indiana workers lose overtime pay as state law changes")
    assert excluded("kannadiga", "ಬಿಗ್\u200b\u200bಬಾಸ್ ಮನೆಗೆ ಮೂವರು ಹೊಸ ಸ್ಪರ್ಧಿಗಳ ಎಂಟ್ರಿ")  # live TV9 title
    assert excluded("kannadiga", "Silk Board junction traffic crawls again")
    assert not excluded("kannadiga", "ಕಲಬುರಗಿ ರೈತರಿಗೆ ಸಾಲ ನೋಟಿಸ್")


def test_discovery_keeps_only_fresh_fitting_news_and_never_scores_70_without_the_ai_editor():
    from lib import discovery
    fresh = format_datetime(datetime.now(timezone.utc))
    stale = format_datetime(datetime.now(timezone.utc) - timedelta(days=5))

    async def fetch(url, limit=8, client=None):
        if "news.google.com" in url:
            return [{"topic": "Kalaburagi farmers get loan notices after crop loss", "link": "https://e.org/a", "publisher": "The Hindu", "pub": fresh},
                    {"topic": "Kalaburagi farmers get loan notices after heavy crop loss", "link": "https://e.org/b", "publisher": "TOI", "pub": fresh},
                    {"topic": "Fertilizer story from last week", "link": "https://e.org/c", "publisher": "X", "pub": stale}]
        return [{"topic": "ಬಿಗ್ ಬಾಸ್ ಮನೆಗೆ ಹೊಸ ಸ್ಪರ್ಧಿ", "link": "https://e.org/d", "publisher": "TV9 Kannada", "pub": fresh},
                {"topic": "ತುಮಕೂರು: ನಾಲ್ಕು ತಿಂಗಳು ಕಳೆದರೂ ಬಾರದ ಪಠ್ಯಪುಸ್ತಕ", "link": "https://e.org/e", "publisher": "Prajavani", "pub": ""}]

    with (patch.object(discovery, "_fetch_rss", side_effect=fetch),
          patch("lib.safety.discovery_block_reason", AsyncMock(return_value=None)),
          patch.object(discovery, "_rank_with_gemini", AsyncMock(return_value=False))):
        found = asyncio.run(discovery.discover({"key": "kannadiga", "language": "kn", "daily_quota": 18}, [], "2026-09-28"))
    assert {c["topic"] for c in found} == {"Kalaburagi farmers get loan notices after crop loss",
                                           "ತುಮಕೂರು: ನಾಲ್ಕು ತಿಂಗಳು ಕಳೆದರೂ ಬಾರದ ಪಠ್ಯಪುಸ್ತಕ"}, "stale, excluded and repeated stories dropped"
    assert all(c["score"] <= discovery.HEURISTIC_CAP for c in found), "without the AI editor nothing reaches 70"


def test_a_failing_source_is_skipped_but_all_failing_is_an_error():
    from lib import discovery
    from lib.editorial_briefs import FEEDS

    async def flaky(url, limit=8, client=None):
        if "news.google.com" in url:
            raise discovery.DiscoveryError("down")
        return [{"topic": "ಕಲಬುರಗಿ ರೈತರ ಸಂಕಷ್ಟ", "link": "https://e.org", "publisher": "Prajavani", "pub": ""}]

    with patch.object(discovery, "_fetch_rss", side_effect=flaky):
        assert len(asyncio.run(discovery._gather("kannadiga"))) == len(FEEDS["kannadiga"])
    with patch.object(discovery, "_fetch_rss", side_effect=discovery.DiscoveryError("down")):
        with pytest.raises(discovery.DiscoveryError):
            asyncio.run(discovery._gather("human"))


def test_ai_editor_scores_against_the_brief_and_writes_the_angle():
    from lib import discovery
    cands = [{"topic": "Tech firm cuts 10,000 jobs after record profit", "status": "candidate", "score": 50,
              "similarity": 0.0, "risk_flags": [], "category": "News", "score_breakdown": {}}]
    ranking = {"rankings": [{"index": 0, "score": 88, "category": "Corporate & HR", "reason": "Exposes the profit paradox",
                             "angle": "The Record Profit Paradox: Why Wall Street Rewards CEOs for Destroying 10,000 Families",
                             "safe": True}]}
    calls = []

    def call(site, topics, covered, model):
        calls.append((topics, covered, model))
        return ranking

    with (patch.object(discovery, "_gemini_rank_call", side_effect=call),
          patch("lib.runtime.RuntimeSafety.from_env", return_value=SimpleNamespace(dry_run=False))):
        assert asyncio.run(discovery._rank_with_gemini({"key": "human", "name": "English Edition"}, cands, ["An old covered story"]))
    assert cands[0]["score"] == 88 and cands[0]["ai_ranked"] and cands[0]["angle"].startswith("The Record Profit Paradox")
    assert calls[0][1] == ["An old covered story"], "the editor is told what was already covered"
    en = discovery._rank_instructions({"key": "human", "name": "English Edition"})
    assert "hidden corporate reality" in en and "already_covered" in en and "Corporate & HR" in en
    kn = discovery._rank_instructions({"key": "kannadiga", "name": "Kannada Edition"})
    assert "Common citizen first" in kn and "in Kannada" in kn


def _site():
    return {"key": "kannadiga", "timezone": "Asia/Kolkata", "daily_quota": 18}


def test_topics_scoring_70_move_to_the_workbench_up_to_the_daily_quota():
    from lib import scheduler
    today = datetime.now(ZoneInfo("Asia/Kolkata"))
    articles = [{"stage": "verified", "created_at": today}] * 16 + [{"stage": "rejected", "created_at": today}]
    strong = [{"_id": i, "id": f"t{i}", "topic": f"Topic {i}", "score": 90 - i} for i in range(2)]
    database = Mock()
    database.articles.find.return_value.to_list = AsyncMock(return_value=articles)
    database.topics.find.return_value.sort.return_value.to_list = AsyncMock(return_value=strong)
    database.topics.update_one = AsyncMock()
    made = []

    async def create(topic, actor="system"):
        made.append(topic["id"])
        return {"id": "a-" + topic["id"], "topic_id": topic["id"], "stage": "selected"}

    with (patch.object(scheduler, "db", database), patch.object(scheduler, "create_job", AsyncMock(side_effect=create)),
          patch.object(scheduler, "audit", AsyncMock())):
        created = asyncio.run(scheduler._auto_queue(_site()))
    query = database.topics.find.call_args.args[0]
    assert query["score"] == {"$gte": 70} and query["ai_ranked"] is True and query["run_date"] == today.date().isoformat()
    assert database.topics.find.return_value.sort.return_value.to_list.await_args.args[0] == 2, "2 of today's 18 left"
    assert made == ["t0", "t1"] and len(created) == 2


def test_a_full_day_queues_nothing_more():
    from lib import scheduler
    today = datetime.now(ZoneInfo("Asia/Kolkata"))
    database = Mock()
    database.articles.find.return_value.to_list = AsyncMock(return_value=[{"stage": "scheduled", "created_at": today}] * 18)
    with patch.object(scheduler, "db", database), patch.object(scheduler, "create_job", AsyncMock()) as create:
        assert asyncio.run(scheduler._auto_queue(_site())) == []
    assert not create.called and not database.topics.find.called


def test_topics_the_ai_editor_skipped_get_one_more_pass():
    """Live case (28 Sep 2026): the editor scored only 20 of 98 the Kannada site topics in one answer."""
    from lib import discovery
    cands = [{"topic": f"Topic {i}", "status": "candidate", "score": 50, "similarity": 0.0, "risk_flags": [],
              "category": "News", "score_breakdown": {}} for i in range(14)]
    calls = []

    def call(site, topics, covered, model):
        calls.append(list(topics))
        return {"rankings": [{"index": i, "score": 75, "angle": "", "category": "Economy", "reason": "fit", "safe": True}
                             for i in range(len(topics) if len(calls) > 1 else 2)]}

    with (patch.object(discovery, "_gemini_rank_call", side_effect=call),
          patch("lib.runtime.RuntimeSafety.from_env", return_value=SimpleNamespace(dry_run=False))):
        assert asyncio.run(discovery._rank_with_gemini({"key": "human", "name": "English Edition"}, cands))
    assert len(calls) == 2 and calls[1] == [f"Topic {i}" for i in range(2, 14)], "the skipped twelve, once more"
    assert all(c["ai_ranked"] for c in cands)


def test_a_failing_model_moves_on_to_the_next_one():
    from lib import discovery
    used = []

    def call(site, topics, covered, model):
        used.append(model)
        if len(used) == 1:
            raise RuntimeError("404 model not found")
        return {"rankings": [{"index": 0, "score": 80, "angle": "", "category": "Economy", "reason": "fit", "safe": True}]}

    cands = [{"topic": "Topic", "status": "candidate", "score": 50, "similarity": 0.0, "risk_flags": [],
              "category": "News", "score_breakdown": {}}]
    with (patch.object(discovery, "_gemini_rank_call", side_effect=call),
          patch("lib.runtime.RuntimeSafety.from_env", return_value=SimpleNamespace(dry_run=False))):
        assert asyncio.run(discovery._rank_with_gemini({"key": "human", "name": "English Edition"}, cands))
    assert len(used) == 2 and cands[0]["score"] == 80
    assert "Be strict" in discovery._rank_instructions({"key": "kannadiga", "name": "Kannada Edition"})
