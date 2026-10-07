"""Browser queue unblocking, parallel lanes, and the Chrome-vs-API generation routes."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

NOW = datetime.now(timezone.utc)


# ── queue unblocking ─────────────────────────────────────────────────────
def test_stale_attention_release_only_when_nothing_can_be_lost():
    from lib.browser_bridge import _stale_attention_reason
    old = NOW - timedelta(minutes=30)
    unsent = {"status": "attention", "article_id": "a", "updated_at": old,
              "last_observation": {"send_attempted": False}, "activity": [{"action": "fill_prompt"}]}
    assert "nothing had been sent" in _stale_attention_reason(unsent)
    sent = {**unsent, "activity": [{"action": "submit"}]}
    assert _stale_attention_reason(sent) is None, "a sent prompt may hold a report: owner decides"
    assert _stale_attention_reason({**unsent, "updated_at": NOW - timedelta(minutes=5)}) is None, "too recent"
    test_job = {**sent, "article_id": "browser-connection-test"}
    assert "Connection test released" in _stale_attention_reason(test_job)
    assert _stale_attention_reason({**unsent, "status": "running"}) is None


def test_old_prompt_job_is_replaced_not_reused():
    from lib import browser_bridge as b
    old = {"id": "old", "status": "queued", "prompt": "old dossier prompt"}
    jobs = SimpleNamespace(find_one=AsyncMock(side_effect=[old, {"result": "article"}]),
                           update_one=AsyncMock(), insert_one=AsyncMock())

    async def run():
        with patch.object(b, "db", SimpleNamespace(browser_jobs=jobs, articles=SimpleNamespace(find_one=AsyncMock(return_value=None)))), \
                patch.object(b, "job_status", AsyncMock(return_value={"status": "completed"})):
            return await b.run_job("research", "art", "new article prompt", 3600)

    assert asyncio.run(run()) == "article"
    cancelled = jobs.update_one.await_args_list[0].args
    assert cancelled[0] == {"id": "old", "status": "queued"} and cancelled[1]["$set"]["status"] == "cancelled"
    assert jobs.insert_one.await_args.args[0]["prompt"] == "new article prompt"


def test_claim_only_offers_awaited_jobs_for_the_requested_lane():
    from lib import browser_bridge as b
    captured = {}

    async def find_one_and_update(query, *_a, **_k):
        captured.update(query)
        return None

    database = SimpleNamespace(system_settings=SimpleNamespace(find_one=AsyncMock(return_value={"global_paused": False})),
                               browser_jobs=SimpleNamespace(find_one_and_update=find_one_and_update))
    request = SimpleNamespace(headers={"x-bridge-version": "0.4.0"}, json=AsyncMock(return_value={"lane": "image"}))
    with (patch.object(b, "db", database), patch.dict(b._awaiting, {"waiting-job": 1}, clear=True),
          patch("lib.turn.current_article", AsyncMock(return_value={"id": "turn-holder"})),
          patch("lib.turn.next_article", AsyncMock(return_value=None))):
        assert asyncio.run(b.claim(request)) == {"job": None}
    assert {"id": {"$in": ["waiting-job"]}} in captured["$or"]
    assert captured["kind"] == {"$in": ["image", "seo"]}
    assert "capture_existing" not in captured
    assert captured["article_id"] == {"$in": ["browser-connection-test", "turn-holder"]}, "only the current article's jobs"


# ── strictly sequential production, alternating sites ────────────────────
def test_sites_alternate_kannadiga_first():
    from lib.scheduler import _site_order
    kn, hu = {"key": "kannadiga"}, {"key": "human"}
    assert [s["key"] for s in _site_order([hu, kn], None)] == ["kannadiga", "human"]
    assert [s["key"] for s in _site_order([hu, kn], "kannadiga")] == ["human", "kannadiga"]
    assert [s["key"] for s in _site_order([hu, kn], "human")] == ["kannadiga", "human"]


def _sequence_db(articles_by_site):
    database = Mock()
    def find(query, *_a):
        cursor = Mock()
        rows = [a for a in articles_by_site.get(query.get("site_key"), []) if a["stage"] != "rejected"]
        cursor.sort.return_value.to_list = AsyncMock(return_value=rows)
        return cursor
    database.articles.find.side_effect = find
    database.system_settings.update_one = AsyncMock()
    return database


def test_one_article_at_a_time_and_next_site_takes_its_turn():
    from lib import scheduler
    kn_article = {"id": "K1", "stage": "researching", "created_at": NOW}
    hu_article = {"id": "H1", "stage": "selected", "created_at": NOW}
    database = _sequence_db({"kannadiga": [kn_article], "human": [hu_article]})
    sites = [{"key": "kannadiga"}, {"key": "human"}]
    gate = asyncio.Event()
    started = []

    async def complete(article, site):
        started.append(article["id"])
        await gate.wait()

    async def exercise():
        await scheduler._advance_sequence(sites, {"last_sequence_site": "kannadiga"})
        await asyncio.sleep(0)
        await scheduler._advance_sequence(sites, {"last_sequence_site": "human"})  # still busy: no second start
        await asyncio.sleep(0)
        running = dict(scheduler._task_article)
        gate.set()
        await scheduler._ai_tasks[scheduler.SEQUENCE]
        return running

    with (patch.object(scheduler, "db", database),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "_complete_article", new=complete),
          patch.object(scheduler, "current_article", AsyncMock(return_value=None)),
          patch.object(scheduler, "next_article", AsyncMock(return_value=None)),
          patch.object(scheduler, "take_turn", AsyncMock(return_value=None)),
          patch("routers.pipeline._research_tasks", {})):
        running = asyncio.run(exercise())
    assert started == ["H1"], "Human's turn after Kannadiga; only one article runs"
    assert running == {scheduler.SEQUENCE: "H1"}
    database.system_settings.update_one.assert_awaited_once()


def test_article_waiting_for_wordpress_holds_the_sequence():
    from lib import scheduler
    database = _sequence_db({"human": [{"id": "H1", "stage": "image_ready", "created_at": NOW}],
                             "kannadiga": [{"id": "K2", "stage": "selected", "created_at": NOW}]})
    with (patch.object(scheduler, "db", database),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "_start", new=AsyncMock()) as start,
          patch.object(scheduler, "current_article", AsyncMock(return_value=None)),
          patch.object(scheduler, "next_article", AsyncMock(return_value=None)),
          patch.object(scheduler, "take_turn", AsyncMock(return_value=None)) as take_turn,
          patch("routers.pipeline._research_tasks", {})):
        asyncio.run(scheduler._advance_sequence([{"key": "kannadiga"}, {"key": "human"}], {"last_sequence_site": "kannadiga"}))
    start.assert_not_awaited()


def test_complete_article_runs_stages_in_order_until_ready():
    from lib import scheduler
    state = {"id": "A", "stage": "selected"}
    order = []

    async def research(a, site):
        order.append("research"); state.update(stage="research_validated", dossier={"x": 1}, validation={"passed": True})

    async def seo(a, site):
        order.append("article"); state.update(stage="article_validated", article={"h": 1})

    async def image(a, site):
        order.append("image"); state.update(stage="image_ready", image={"i": 1})

    database = Mock()
    database.articles.find_one = AsyncMock(side_effect=lambda *_a, **_k: dict(state))
    database.system_settings.find_one = AsyncMock(return_value={})  # automatic research on (the default)
    with (patch.object(scheduler, "db", database),
          patch.object(scheduler, "system_block_reason", new=AsyncMock(return_value=None)),
          patch.object(scheduler, "run_research_stage", new=research),
          patch.object(scheduler, "run_article_stage", new=seo),
          patch.object(scheduler, "run_image_stage", new=image)):
        asyncio.run(scheduler._complete_article({"id": "A"}, {"key": "kannadiga"}))
    assert order == ["research", "article", "image"]


# ── Chrome Bridge vs API route ───────────────────────────────────────────
KN_REPORT = "# ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ: ರೈತರ ಸಂಕಷ್ಟದ ವರದಿ\n\n" + "\n\n".join(
    f"## ವಿಭಾಗ {i}\n\n" + "ರಾಯಚೂರಿನಲ್ಲಿ ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ ಬಯಲಾಗಿದೆ ಮತ್ತು ರೈತರು ಸಾಲದಲ್ಲಿದ್ದಾರೆ. " * 8 for i in range(5)
) + "\n\n## ಮೂಲಗಳು\n1. https://www.prajavani.net/a\n2. https://www.thehindu.com/b\n"
SEO_JSON = ('{"seo_title":"ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ ಬಯಲು","meta_description":"ರಾಯಚೂರಿನಲ್ಲಿ ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ ಬಯಲಾಗಿದ್ದು ರೈತರು ಸಂಕಷ್ಟದಲ್ಲಿದ್ದಾರೆ; ಸಂಪೂರ್ಣ ವರದಿ ಇಲ್ಲಿದೆ ಓದಿ.",'
            '"focus_keyword":"ಫೇಕ್ ಸೀಡ್ಸ್","slug":"fake-seeds-scam","category":"ಕೃಷಿ","tags":["ರೈತರು"],'
            '"thumbnail_headlines":["ಫೇಕ್ ಸೀಡ್ಸ್","ದಂಧೆ ಬಯಲು","ರೈತರ ಸಂಕಷ್ಟ"],"thumbnail_design":{"story_type":"investigative '
            'fake-seed scam","emotion":"farmer distress","left":{"title":"THE FARMER","shows":["farmer in a cotton field",'
            '"failed seedlings","loan papers","worried family"],"colors":["dusty gold"]},"right":{"title":"THE RACKET",'
            '"shows":["unmarked seed packets","warehouse","generic dealer silhouette","agriculture officers"],'
            '"colors":["deep red"]},"center":["cracked seed packet","magnifying glass","scales of justice"]}}')
SITE = {"key": "kannadiga", "name": "Kannada Edition", "language": "kn", "audience": "Karnataka"}


def _workflow_patches(w, stored):
    async def update(art_id, patch, hist=None):
        stored.update(patch)
        return dict(stored)
    return [patch.object(w, "_update", side_effect=update), patch.object(w, "audit", new=AsyncMock()),
            patch.object(w, "_stopped_by_editor", new=AsyncMock(return_value=None))]


def test_api_route_research_uses_deep_research_api_report_as_article():
    from lib import workflow as w
    stored = {"id": "A", "site_key": "kannadiga", "topic_snapshot": {"topic": "Fake seeds"}, "dossier_meta": {}}
    after = {**stored, "dossier_meta": {"report_mode": True, "prompt": "p", "report": KN_REPORT}}
    database = SimpleNamespace(articles=SimpleNamespace(find_one=AsyncMock(side_effect=[stored, after]), update_one=AsyncMock()),
                               prompts=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    research = AsyncMock(return_value=(KN_REPORT, "deep-research-preview"))
    ps = _workflow_patches(w, stored)
    with patch.object(w, "db", database), ps[0], ps[1], ps[2], \
            patch("lib.browser_bridge.enabled", new=AsyncMock(return_value=False)), \
            patch("lib.manual_ai.block_reason", new=AsyncMock(return_value=None)), \
            patch("lib.deep_research.research", new=research):
        result = asyncio.run(w._run_report_research(dict(stored), SITE))
    assert research.await_args.kwargs == {"report_only": True}
    assert result["stage"] == "research_validated" and result["dossier"]["report_mode"]


def test_api_route_seo_uses_gemini_and_chrome_route_uses_chatgpt():
    from lib import workflow as w
    for chrome in (False, True):
        stored = {"id": "A", "site_key": "kannadiga", "dossier_meta": {"report": KN_REPORT}, "review_flags": []}
        seo_api, run_job = AsyncMock(return_value=SEO_JSON), AsyncMock(return_value=SEO_JSON)
        ps = _workflow_patches(w, stored)
        with ps[0], ps[1], ps[2], patch.object(w, "_seo_via_api", new=seo_api), \
                patch("lib.browser_bridge.enabled", new=AsyncMock(return_value=chrome)), \
                patch("lib.browser_bridge.run_job", new=run_job), patch("lib.browser_bridge.consumed", new=AsyncMock()):
            result = asyncio.run(w._run_report_article(dict(stored), SITE))
        assert (run_job.await_count, seo_api.await_count) == ((1, 0) if chrome else (0, 1))
        assert result["article"]["slug"] == "fake-seeds-scam"
        prompt = result["article"]["thumbnail_prompt"]
        assert prompt.startswith("🎯 BLOG THUMBNAIL GENERATION PROMPT — 16:9") and "farmer in a cotton field" in prompt
        assert '"ದಂಧೆ ಬಯಲು" must be the strongest and largest visual text.' in prompt
        assert result["article"]["headline"] == "ಫೇಕ್ ಸೀಡ್ಸ್: ದಂಧೆ ಬಯಲು, ರೈತರ ಸಂಕಷ್ಟ", "the post title matches the thumbnail"
        assert result["article"]["report_title"] == "ಫೇಕ್ ಸೀಡ್ಸ್ ದಂಧೆ: ರೈತರ ಸಂಕಷ್ಟದ ವರದಿ"


def test_unusable_seo_answer_is_asked_once_more_before_holding():
    from lib import workflow as w
    # Live case: a letter of another script inside a Kannada thumbnail line (it would also enter the post title).
    bad = SEO_JSON.replace('"ರೈತರ ಸಂಕಷ್ಟ"]', '"ರೈತರ ಸಂಕಷ\u0a9f"]')
    for answers, held in (([bad, SEO_JSON], False), ([bad, bad], True)):
        stored = {"id": "A", "site_key": "kannadiga", "dossier_meta": {"report": KN_REPORT}, "review_flags": []}
        run_job = AsyncMock(side_effect=answers)
        ps = _workflow_patches(w, stored)
        with ps[0], ps[1], ps[2], patch("lib.browser_bridge.enabled", new=AsyncMock(return_value=True)), \
                patch("lib.browser_bridge.run_job", new=run_job), patch("lib.browser_bridge.consumed", new=AsyncMock()):
            result = asyncio.run(w._run_report_article(dict(stored), SITE))
        assert run_job.await_count == 2 and "another script" in run_job.await_args.args[2]
        if held:
            assert result["stage"] == "held_review" and "another script" in result["held_reason"]
        else:
            assert result["article"]["headline"] == "ಫೇಕ್ ಸೀಡ್ಸ್: ದಂಧೆ ಬಯಲು, ರೈತರ ಸಂಕಷ್ಟ"


def test_the_fresh_run_after_15_minutes_is_marked_so_it_may_finish():
    from lib import browser_bridge as b
    jobs = SimpleNamespace(find_one=AsyncMock(side_effect=[None, {"result": "report"}]), insert_one=AsyncMock())
    articles = SimpleNamespace(find_one=AsyncMock(return_value={"dossier_meta": {"auto_research_again": True}}))

    async def run():
        with patch.object(b, "db", SimpleNamespace(browser_jobs=jobs, articles=articles)), \
                patch.object(b, "job_status", AsyncMock(return_value={"status": "completed"})):
            return await b.run_job("research", "art", "prompt", 3600)

    assert asyncio.run(run()) == "report"
    assert jobs.insert_one.await_args.args[0]["rerun"] is True


def test_workbench_queue_runs_in_the_order_the_app_takes_articles():
    from datetime import datetime, timezone
    from routers.pipeline import _queue_order
    at = lambda m: datetime(2026, 9, 28, 1, m, tzinfo=timezone.utc)  # noqa: E731
    waiting = [{"id": "cur", "site_key": "kannadiga", "created_at": at(0)},
               {"id": "k1", "site_key": "kannadiga", "created_at": at(1)}, {"id": "k2", "site_key": "kannadiga", "created_at": at(2)},
               {"id": "k3", "site_key": "kannadiga", "created_at": at(3)}, {"id": "h1", "site_key": "human", "created_at": at(4)}]
    assert _queue_order(waiting, {"id": "cur", "site_key": "kannadiga"}, None, "kannadiga") == ["h1", "k1", "k2", "k3"], \
        "the other site first, then in turn, oldest first"
    assert _queue_order(waiting[1:4], None, None, "human") == ["k1", "k2", "k3"]
