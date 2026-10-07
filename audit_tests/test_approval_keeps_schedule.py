"""Approving a post already scheduled or live on WordPress records the approval only (27 Sep 2026)."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

READY = {"id": "A", "site_key": "kannadiga", "article": {"headline": "t"}, "quality_gate": {"passed": True},
         "image": {"status": "generated"}}


def _approve(art):
    from routers import pipeline
    articles = SimpleNamespace(find_one=AsyncMock(return_value=dict(art)), update_one=AsyncMock())
    with patch.object(pipeline, "db", SimpleNamespace(articles=articles)), patch.object(pipeline, "audit", new=AsyncMock()):
        asyncio.run(pipeline.approve_article(art["id"], SimpleNamespace(state=SimpleNamespace(admin="owner"))))
    return articles.update_one.await_args.args[1]


def test_approving_a_scheduled_post_keeps_it_scheduled():
    update = _approve({**READY, "stage": "scheduled", "scheduled_time": "2026-09-27T15:00:00+00:00",
                       "wp": {"post_id": 2987, "status": "future"}})
    assert "stage" not in update["$set"], "no second WordPress hand-off (it booked a new slot)"
    assert update["$set"]["approval"]["by"] == "owner"
    assert "stays scheduled" in update["$push"]["history"]["note"]


def test_approving_a_finished_article_hands_it_to_the_publishing_workflow():
    assert _approve({**READY, "stage": "held_review"})["$set"]["stage"] == "image_ready"
