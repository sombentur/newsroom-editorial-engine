"""Owner rule: one article at a time until it is published (or rejected); everything else waits its turn."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def _matches(doc, flt):
    for key, cond in flt.items():
        if key == "$or":
            if not any(_matches(doc, c) for c in cond):
                return False
        elif isinstance(cond, dict) and "$exists" in cond:
            if (key in doc) != cond["$exists"]:
                return False
        elif doc.get(key) != cond:
            return False
    return True


class Collection:
    def __init__(self, *docs):
        self.docs = [dict(d) for d in docs]

    async def find_one(self, flt, projection=None):
        return next((dict(d) for d in self.docs if _matches(d, flt)), None)

    async def update_one(self, flt, update):
        for d in self.docs:
            if _matches(d, flt):
                d.update(update.get("$set", {}))
                for k in update.get("$unset", {}):
                    d.pop(k, None)
                for k, v in update.get("$push", {}).items():
                    d.setdefault(k, []).append(v)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


def fake_db(*articles, ahead=False):
    return SimpleNamespace(system_settings=Collection({"id": "system", "research_ahead": ahead}), articles=Collection(*articles))


def test_one_article_holds_the_turn_until_wordpress_has_it():
    from lib import turn
    db = fake_db({"id": "a", "stage": "writing_article"}, {"id": "b", "stage": "research_validated"})

    async def run():
        with patch.object(turn, "db", db):
            assert await turn.take_turn("a") is None, "free: a takes the turn"
            assert (await turn.take_turn("b"))["id"] == "a", "b waits"
            db.articles.docs[0]["stage"] = "held_review"
            assert (await turn.take_turn("b"))["id"] == "a", "held for review still holds the turn"
            db.articles.docs[0]["stage"] = "scheduled"
            assert await turn.take_turn("b") is None, "WordPress has a: b's turn"
            assert (await turn.current_article())["id"] == "b"
            db.articles.docs[1]["stage"] = "rejected"
            assert await turn.current_article() is None, "rejected releases the turn"
    asyncio.run(run())


def test_editor_action_on_another_article_waits_and_is_marked_queued():
    from lib import turn
    db = fake_db({"id": "a", "stage": "writing_article"}, {"id": "b", "stage": "research_validated"})

    async def run():
        with patch.object(turn, "db", db), patch.object(turn, "TURN_POLL_SECONDS", 0.01):
            await turn.take_turn("a")
            waiting = asyncio.create_task(turn.wait_for_turn("b"))
            await asyncio.sleep(0.05)
            assert not waiting.done(), "b does not start while a is in progress"
            assert db.articles.docs[1]["turn_wait"]["behind"] == "a"
            assert "Queued" in db.articles.docs[1]["history"][-1]["note"]
            db.articles.docs[0]["stage"] = "published"
            assert await asyncio.wait_for(waiting, 1) is True, "b starts once a is published"
            assert "turn_wait" not in db.articles.docs[1]
    asyncio.run(run())


def test_scheduler_starts_nothing_else_while_the_current_article_waits_for_the_editor():
    from lib import scheduler
    held = {"id": "a", "site_key": "kannadiga", "stage": "held_review", "held_reason": "AI SEO assets error"}
    site = {"key": "kannadiga", "paused": False}
    with (patch.object(scheduler, "current_article", AsyncMock(return_value=held)),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "_next_work", AsyncMock()) as next_work,
          patch.object(scheduler, "_create_next_article", AsyncMock()) as create,
          patch.object(scheduler, "_start", AsyncMock()) as start):
        asyncio.run(scheduler._advance_sequence([site, {"key": "human"}], {}))
    assert not next_work.called and not create.called and not start.called
    working = {**held, "stage": "writing_article", "held_reason": None}
    with (patch.object(scheduler, "current_article", AsyncMock(return_value=working)),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "_start", AsyncMock()) as start):
        asyncio.run(scheduler._advance_sequence([site], {}))
    assert start.call_args.args[1]["id"] == "a", "the current article continues"


def test_chrome_takes_jobs_only_for_the_current_article():
    from lib import browser_bridge
    request = SimpleNamespace(headers={"x-bridge-version": "0.4.22"}, json=AsyncMock(return_value={"lane": "image"}))
    settings = SimpleNamespace(find_one=AsyncMock(return_value={"global_paused": False}))
    jobs = SimpleNamespace(find_one_and_update=AsyncMock(return_value=None))
    with (patch.object(browser_bridge, "db", SimpleNamespace(system_settings=settings, browser_jobs=jobs)),
          patch("lib.turn.current_article", AsyncMock(return_value={"id": "a"})),
          patch("lib.turn.next_article", AsyncMock(return_value=None))):
        asyncio.run(browser_bridge.claim(request))
    assert jobs.find_one_and_update.call_args.args[0]["article_id"] == {"$in": ["browser-connection-test", "a"]}


# ── Research ahead (owner rule, 27 Sep 2026): the next article's research starts once the current one is on its
# thumbnail; one article at most; it takes the turn next. ──
ON_THUMBNAIL = {"stage": "generating_image", "article": {"headline": "x"}, "quality_gate": {"passed": True}}


def test_next_article_researches_ahead_once_the_current_one_is_on_its_thumbnail():
    from lib import turn
    db = fake_db({"id": "a", "stage": "writing_article"}, {"id": "b", "stage": "selected"}, {"id": "c", "stage": "selected"},
                 ahead=True)

    async def run():
        with patch.object(turn, "db", db):
            await turn.take_turn("a")
            assert not await turn.claim_next("b"), "a is still on research or SEO: b waits"
            db.articles.docs[0].update(ON_THUMBNAIL)
            assert await turn.claim_next("b"), "a is on its thumbnail: b researches ahead"
            assert "Next in line: its research starts now" in db.articles.docs[1]["history"][-1]["note"]
            assert not await turn.claim_next("c"), "one article ahead at most"
            db.articles.docs[0]["stage"] = "scheduled"
            assert (await turn.take_turn("c"))["id"] == "b", "the article researched ahead goes next"
            assert await turn.take_turn("b") is None and await turn.next_article() is None
            assert (await turn.current_article())["id"] == "b"
    asyncio.run(run())


def test_stopping_the_next_article_releases_its_place():
    from lib import turn
    db = fake_db({"id": "a", **ON_THUMBNAIL}, {"id": "b", "stage": "researching"}, ahead=True)

    async def run():
        with patch.object(turn, "db", db):
            await turn.take_turn("a")
            assert await turn.claim_next("b")
            db.articles.docs[1].update(stage="held_review", held_reason="Stopped by editor.")
            assert await turn.next_article() is None
    asyncio.run(run())


def test_editor_started_research_waits_then_runs_ahead():
    from lib import turn
    db = fake_db({"id": "a", "stage": "writing_article"}, {"id": "b", "stage": "researching"}, ahead=True)

    async def run():
        with patch.object(turn, "db", db), patch.object(turn, "TURN_POLL_SECONDS", 0.01):
            await turn.take_turn("a")
            waiting = asyncio.create_task(turn.wait_for_research("b"))
            await asyncio.sleep(0.05)
            assert not waiting.done() and "Queued behind" in db.articles.docs[1]["history"][-1]["note"]
            db.articles.docs[0].update(ON_THUMBNAIL)
            assert await asyncio.wait_for(waiting, 1) == "ahead"
    asyncio.run(run())


def test_scheduler_starts_the_next_research_while_the_current_article_is_on_its_thumbnail():
    from lib import scheduler
    queued = {"id": "b", "site_key": "human", "stage": "selected"}
    sites = [{"key": "kannadiga"}, {"key": "human"}]
    database = SimpleNamespace(articles=SimpleNamespace(find_one=AsyncMock(return_value=dict(queued))))

    async def run(current):
        scheduler._ai_tasks.pop(scheduler.AHEAD, None)
        research, claim = AsyncMock(), AsyncMock(return_value=True)
        with (patch.object(scheduler, "db", database),
              patch.object(scheduler, "current_article", AsyncMock(return_value=current)),
              patch.object(scheduler, "next_article", AsyncMock(return_value=None)),
              patch.object(scheduler, "claim_next", claim),
              patch.object(scheduler, "is_connected", return_value=True),
              patch.object(scheduler, "run_research_stage", new=research)):
            await scheduler._research_ahead(sites, {"research_ahead": True})
            if task := scheduler._ai_tasks.get(scheduler.AHEAD):
                await task
        return research, claim

    research, claim = asyncio.run(run({"id": "a", "site_key": "kannadiga", "stage": "writing_article"}))
    assert not claim.await_count and not research.await_count, "nothing starts while the current article is on SEO"
    research, claim = asyncio.run(run({"id": "a", "site_key": "kannadiga", **ON_THUMBNAIL}))
    claim.assert_awaited_once_with("b")
    assert research.await_args.args[0]["id"] == "b", "the queued article (other site first) researches ahead"


def test_the_article_researched_ahead_takes_the_turn_next():
    from lib import scheduler
    ahead = {"id": "b", "site_key": "human", "stage": "research_validated"}
    with (patch.object(scheduler, "_research_ahead", AsyncMock()),
          patch.object(scheduler, "current_article", AsyncMock(return_value=None)),
          patch.object(scheduler, "next_article", AsyncMock(return_value=ahead)),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "_next_work", AsyncMock()) as next_work,
          patch.object(scheduler, "_start", AsyncMock()) as start):
        asyncio.run(scheduler._advance_sequence([{"key": "kannadiga"}, {"key": "human"}], {"last_sequence_site": "human"}))
    assert start.await_args.args[1]["id"] == "b" and start.await_args.args[2] is scheduler._complete_article
    assert not next_work.called, "no other article is considered first"


def test_chrome_takes_gemini_jobs_for_the_article_researching_ahead():
    from lib import browser_bridge
    request = SimpleNamespace(headers={"x-bridge-version": "0.4.26"}, json=AsyncMock(return_value={"lane": "research"}))
    settings = SimpleNamespace(find_one=AsyncMock(return_value={"global_paused": False}))
    jobs = SimpleNamespace(find_one_and_update=AsyncMock(return_value=None))
    with (patch.object(browser_bridge, "db", SimpleNamespace(system_settings=settings, browser_jobs=jobs)),
          patch("lib.turn.current_article", AsyncMock(return_value={"id": "a"})),
          patch("lib.turn.next_article", AsyncMock(return_value={"id": "b"}))):
        asyncio.run(browser_bridge.claim(request))
    rule = jobs.find_one_and_update.call_args.args[0]["$and"][0]["$or"]
    assert {"article_id": {"$in": ["browser-connection-test", "a"]}} in rule
    assert {"article_id": "b", "kind": "research"} in rule, "only research (Gemini) jobs of the next article"


def test_editor_started_workflow_researches_ahead_then_waits_for_its_turn():
    from routers import pipeline as p
    calls = []
    art = {"id": "b", "site_key": "human", "stage": "researching"}

    async def stages(art_id, research_only=False):
        calls.append("research only" if research_only else "rest")

    async def turn_wait(art_id):
        calls.append("turn")
        return True

    with (patch.object(p, "_article_or_404", AsyncMock(side_effect=[dict(art), {**art, "stage": "research_validated"}])),
          patch.object(p, "_run_pipeline_in_background", AsyncMock(side_effect=stages)),
          patch("lib.turn.wait_for_research", AsyncMock(return_value="ahead")),
          patch("lib.turn.wait_for_turn", AsyncMock(side_effect=turn_wait))):
        asyncio.run(p._pipeline_in_background("b"))
    assert calls == ["research only", "turn", "rest"]


# ── Owner rule (28 Sep 2026): by default the next article starts only once the current one is scheduled ──
def test_by_default_the_next_article_waits_until_the_current_one_is_scheduled():
    from lib import turn
    db = fake_db({"id": "a", **ON_THUMBNAIL}, {"id": "b", "stage": "selected"})

    async def run():
        with patch.object(turn, "db", db), patch.object(turn, "TURN_POLL_SECONDS", 0.01):
            await turn.take_turn("a")
            assert not await turn.claim_next("b"), "no research ahead"
            waiting = asyncio.create_task(turn.wait_for_research("b"))
            await asyncio.sleep(0.05)
            assert not waiting.done() and "scheduled for publishing" in db.articles.docs[1]["history"][-1]["note"]
            db.articles.docs[0]["stage"] = "scheduled"
            assert await asyncio.wait_for(waiting, 1) == "turn", "it starts once the current article is scheduled"
    asyncio.run(run())


def test_scheduler_prepares_nothing_early_unless_research_ahead_is_on():
    from lib import scheduler
    scheduler._ai_tasks.pop(scheduler.AHEAD, None)
    with (patch.object(scheduler, "current_article", AsyncMock(return_value={"id": "a", "site_key": "kannadiga", **ON_THUMBNAIL})),
          patch.object(scheduler, "next_article", AsyncMock(return_value=None)),
          patch.object(scheduler, "claim_next", AsyncMock(return_value=True)) as claim,
          patch.object(scheduler, "_create_next_article", AsyncMock()) as create):
        asyncio.run(scheduler._research_ahead([{"key": "kannadiga"}, {"key": "human"}], {}))
    assert not claim.called and not create.called, "no article is created or researched early"


def test_an_article_waiting_only_for_editorial_sign_off_lets_the_next_one_start():
    """Owner rule (28 Sep 2026): high-risk articles wait for approval while production moves on."""
    from lib import turn
    held = {"id": "a", "stage": "held_review", "held_reason": "High-risk subject requires human editorial sign-off: scam"}
    db = fake_db(dict(held), {"id": "b", "stage": "selected"})
    db.system_settings.docs[0]["current_article"] = "a"

    async def run():
        with patch.object(turn, "db", db):
            assert await turn.current_article() is None, "the turn is released"
            assert await turn.take_turn("b") is None, "the next article takes it"
    asyncio.run(run())
    assert "next article has started" in db.articles.docs[0]["history"][-1]["note"]
    assert db.system_settings.docs[0]["current_article"] == "b"
    other = fake_db({"id": "a", "stage": "held_review", "held_reason": "featured image failed (browser): x"})
    other.system_settings.docs[0]["current_article"] = "a"

    async def technical():
        with patch.object(turn, "db", other):
            return await turn.current_article()
    assert asyncio.run(technical())["id"] == "a", "other holds still keep the turn"
    assert not turn.awaiting_sign_off({**held, "approval": {"by": "owner"}}), "approved: no longer waiting"
