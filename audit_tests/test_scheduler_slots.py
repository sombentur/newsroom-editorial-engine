"""The automatic schedule must not lose a ready article at the day boundary."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

SITE = {
    "key": "kannadiga", "timezone": "Asia/Kolkata", "daily_quota": 5,
    "publish_times": ["07:30", "10:30", "13:30", "17:00", "20:30"],
    "auto_publish": True,
}


def _slot(day, hour, minute):
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+05:30").astimezone(timezone.utc).isoformat()


def test_sixth_ready_article_moves_to_next_day():
    from lib import scheduler
    articles = [
        {"id": str(i), "stage": "scheduled", "scheduled_time": _slot("2026-09-24", h, m)}
        for i, (h, m) in enumerate([(7, 30), (10, 30), (13, 30), (17, 0), (20, 30)])
    ]
    now = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
    assert scheduler.next_publish_slot(SITE, articles, now).isoformat() == _slot("2026-09-25", 7, 30)


def test_already_published_post_consumes_daily_quota_even_without_scheduled_time():
    from lib import scheduler
    articles = [{"id": str(i), "stage": "verified", "wp": {
        "status": "publish", "verified_at": _slot("2026-09-24", h, m),
    }} for i, (h, m) in enumerate([(7, 30), (10, 30), (13, 30), (17, 0), (20, 30)])]
    now = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
    assert scheduler.next_publish_slot(SITE, articles, now).isoformat() == _slot("2026-09-25", 7, 30)


def test_past_slots_are_not_reused_to_cram_posts_into_the_day():
    from lib import scheduler
    now = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)
    assert scheduler.next_publish_slot(SITE, [], now).isoformat() == _slot("2026-09-25", 7, 30)


def test_ready_low_risk_article_is_scheduled_before_more_research():
    from lib import scheduler
    articles = [
        {"id": "research", "site_key": "kannadiga", "stage": "researching",
         "created_at": datetime(2026, 9, 24, tzinfo=timezone.utc)},
        {"id": "ready", "site_key": "kannadiga", "stage": "image_ready",
         "created_at": datetime(2026, 9, 24, tzinfo=timezone.utc),
         "review_flags": [], "validation": {"passed": True},
         "quality_gate": {"passed": True}, "image": {"status": "generated"}},
    ]
    database = Mock()
    database.articles.find.return_value.sort.return_value.to_list = AsyncMock(return_value=articles)
    with (patch.object(scheduler, "db", database),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "system_block_reason", new=AsyncMock(return_value=None)),
          patch.object(scheduler, "wordpress_write", new_callable=AsyncMock) as write,
          patch.object(scheduler, "run_research_stage", new_callable=AsyncMock) as research):
        asyncio.run(scheduler._publish_ready(SITE, {"mode": "auto"}))
    assert write.await_args.args[:3] == (articles[1], SITE, "future")
    assert write.await_args.args[3]
    research.assert_not_awaited()


def test_due_wordpress_post_becomes_verified_only_after_readback_and_public_check():
    from lib import scheduler
    article = {"id": "scheduled", "stage": "scheduled",
               "scheduled_time": "2026-01-01T00:00:00+00:00",
               "wp": {"post_id": 42, "status": "future", "verification": {"creation_response_ok": True}}}
    database = Mock()
    database.articles.update_one = AsyncMock()
    client = Mock(base="https://example.com")
    client.read_post = AsyncMock(return_value={"id": 42, "status": "publish", "link": "https://example.com/post"})
    client.verify_public = AsyncMock(return_value={"public_page_ok": True})
    with (patch.object(scheduler, "db", database),
          patch.object(scheduler, "audit", new_callable=AsyncMock),
          patch("lib.wordpress.WordPressClient", return_value=client)):
        asyncio.run(scheduler._reconcile_due_posts(SITE, [article], {"mode": "auto"}))
    patch_data = database.articles.update_one.await_args.args[1]["$set"]
    assert patch_data["stage"] == "verified"
    assert patch_data["wp"]["status"] == "publish"


def test_missed_wordpress_cron_reuses_the_scheduled_post_after_grace_period():
    from lib import scheduler
    article = {"id": "scheduled", "stage": "scheduled",
               "scheduled_time": "2026-01-01T00:00:00+00:00", "wp": {"post_id": 42, "status": "future"}}
    client = Mock(base="https://example.com")
    client.read_post = AsyncMock(return_value={"id": 42, "status": "future"})
    with (patch("lib.wordpress.WordPressClient", return_value=client),
          patch.object(scheduler, "wordpress_write", new_callable=AsyncMock) as write):
        asyncio.run(scheduler._reconcile_due_posts(SITE, [article], {"mode": "auto"}))
    assert write.await_args.args == (article, SITE, "publish", article["scheduled_time"])


def test_only_source_list_mismatch_gets_one_automatic_citation_reformat():
    from lib import scheduler
    article = {"stage": "held_review", "held_reason": "Research needs review: Some claim links are missing from the source list",
               "validation": {"failed_reasons": ["claim_urls_match_sources"]},
               "dossier": {"publication_ready": True},
               "dossier_meta": {"interaction_id": "saved", "report": "saved report"}}
    assert scheduler._citation_reformat_candidate(article)
    article["validation"]["failed_reasons"].append("publication_ready")
    assert not scheduler._citation_reformat_candidate(article)
    article["validation"]["failed_reasons"] = ["claim_urls_match_sources"]
    article["dossier_meta"]["citation_reformat_attempted"] = True
    assert not scheduler._citation_reformat_candidate(article)


def test_provider_backed_source_recheck_is_one_time_and_preserves_other_holds():
    from lib import scheduler
    article = {"stage": "held_review", "held_reason": "Research needs review: Some claim links are missing from the source list",
               "validation": {"failed_reasons": ["claim_urls_match_sources"]},
               "dossier": {"publication_ready": True},
               "dossier_meta": {"citations_included": True,
                                "report": "Report\nPROVIDER CITATION LINKS\n- Source: https://source.example"}}
    assert scheduler._citation_source_recheck_candidate(article)
    article["validation"]["failed_reasons"].append("publication_ready")
    assert not scheduler._citation_source_recheck_candidate(article)
    article["validation"]["failed_reasons"] = ["claim_urls_match_sources"]
    article["dossier_meta"]["citation_source_recheck_attempted"] = True
    assert not scheduler._citation_source_recheck_candidate(article)


def test_deep_research_report_preserves_provider_citation_urls():
    from lib.deep_research import report_text
    result = {"steps": [{"type": "model_output", "content": [{"type": "text",
        "text": "Finding [cite: 1]", "annotations": [
            {"type": "url_citation", "start_index": 8, "end_index": 17,
             "url": "https://source.example/report"},
        ]}]}]}
    report = report_text(result)
    assert "Finding [cite: 1]" in report
    assert "https://source.example/report" in report
    assert report.count("https://source.example/report") == 1


def test_long_research_does_not_block_a_newly_ready_article():
    """Publishing runs every tick for each site, independent of the (long) AI sequence."""
    from lib import scheduler
    research_article = {"id": "research", "stage": "researching", "created_at": datetime.now(timezone.utc)}
    ready_article = {"id": "ready", "stage": "image_ready", "created_at": datetime.now(timezone.utc)}
    database = Mock()
    database.articles.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[research_article, ready_article])
    release = asyncio.Event()

    async def exercise():
        scheduler._ai_tasks[scheduler.SEQUENCE] = asyncio.create_task(release.wait())
        await scheduler._publish_ready(SITE, {"mode": "auto"})
        release.set()
        await scheduler._ai_tasks.pop(scheduler.SEQUENCE)

    with (patch.object(scheduler, "db", database),
          patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "wordpress_write", new_callable=AsyncMock) as write):
        asyncio.run(exercise())
    assert write.await_args.args[:3] == (ready_article, SITE, "future")


def _ready(**extra):
    return {"id": "ready", "site_key": "kannadiga", "stage": "image_ready", "created_at": datetime(2026, 9, 27, tzinfo=timezone.utc),
            "review_flags": [], "validation": {"passed": True}, "quality_gate": {"passed": True},
            "image": {"status": "generated"}, **extra}


def _handed_to_wordpress(articles):
    from lib import scheduler
    database = Mock()
    database.articles.find.return_value.sort.return_value.to_list = AsyncMock(return_value=articles)
    with (patch.object(scheduler, "db", database), patch.object(scheduler, "is_connected", return_value=True),
          patch.object(scheduler, "_reconcile_due_posts", new=AsyncMock()),
          patch.object(scheduler, "wordpress_write", new_callable=AsyncMock) as write):
        asyncio.run(scheduler._publish_ready(SITE, {"mode": "auto"}))
    return write.await_args.args[2:]


def test_an_already_booked_article_keeps_its_slot():
    from lib import scheduler
    booked = scheduler.next_publish_slot(SITE, [], datetime.now(timezone.utc)).isoformat()
    article = _ready(scheduled_time=booked, wp={"post_id": 2987, "status": "future", "simulated": False})
    assert _handed_to_wordpress([article]) == ("future", booked), "its own booking must not push it to a later slot"


def test_a_slot_taken_by_another_article_is_not_reused():
    from lib import scheduler
    now = datetime.now(timezone.utc)
    booked = scheduler.next_publish_slot(SITE, [], now).isoformat()
    other = {"id": "other", "stage": "scheduled", "scheduled_time": booked}
    status, slot = _handed_to_wordpress([other, _ready(scheduled_time=booked)])
    assert status == "future" and slot == scheduler.next_publish_slot(SITE, [other], now).isoformat() != booked


def test_a_live_post_is_never_moved_back_to_scheduled():
    assert _handed_to_wordpress([_ready(wp={"post_id": 2735, "status": "publish", "simulated": False})]) == ("publish",)
