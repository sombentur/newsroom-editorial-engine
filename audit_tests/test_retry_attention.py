"""Retry runs the step again: a job waiting for attention is replaced, not re-joined (live case, 28 Sep 2026)."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_retry_replaces_a_job_waiting_for_attention():
    from routers import pipeline as p
    held = {"id": "A", "site_key": "kannadiga", "stage": "held_review", "dossier": None,
            "held_reason": "research failed (browser): Deep Research task indicates 'You stopped this task'"}
    jobs = SimpleNamespace(update_many=AsyncMock())
    articles = SimpleNamespace(update_one=AsyncMock())

    async def run():
        with (patch.object(p, "db", SimpleNamespace(browser_jobs=jobs, articles=articles)),
              patch.object(p, "_article_or_404", AsyncMock(return_value=held)),
              patch.object(p, "_site_or_404", AsyncMock(return_value={"key": "kannadiga"})),
              patch.object(p, "_pipeline_in_background", AsyncMock()),
              patch.object(p, "audit", AsyncMock())):
            await p.retry_article("A")
            await asyncio.sleep(0)
    asyncio.run(run())
    query, update = jobs.update_many.await_args.args
    assert query == {"article_id": "A", "status": "attention"} and update["$set"]["status"] == "cancelled"
    assert articles.update_one.await_args.args[1]["$set"]["stage"] == "researching"
    assert "dossier_meta.auto_research_count" in articles.update_one.await_args.args[1]["$unset"], \
        "a run the owner starts is a first run again"


def test_retry_of_the_thumbnail_starts_the_fresh_chat_count_again():
    from routers import pipeline as p
    held = {"id": "A", "site_key": "human", "stage": "held_review", "dossier": {"summary": "s"}, "validation": {"passed": True},
            "article": {"thumbnail_design": {"style": "x"}}, "image": None,
            "held_reason": "featured image failed (browser): ChatGPT's image generation failed (it showed \"Image generation failed\")."}
    jobs = SimpleNamespace(update_many=AsyncMock())
    articles = SimpleNamespace(update_one=AsyncMock())

    async def run():
        with (patch.object(p, "db", SimpleNamespace(browser_jobs=jobs, articles=articles)),
              patch.object(p, "_article_or_404", AsyncMock(return_value=held)),
              patch.object(p, "_site_or_404", AsyncMock(return_value={"key": "human"})),
              patch.object(p, "_pipeline_in_background", AsyncMock()),
              patch.object(p, "audit", AsyncMock())):
            await p.retry_article("A")
            await asyncio.sleep(0)
    asyncio.run(run())
    update = articles.update_one.await_args.args[1]
    assert update["$set"]["stage"] == "generating_image" and "image_fresh_runs" in update["$unset"]
