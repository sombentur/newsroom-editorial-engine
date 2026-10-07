"""Bulk starts queue behind each other: strictly one article in production at a time."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_bulk_workflows_run_one_article_at_a_time():
    from routers import pipeline

    async def exercise():
        running = 0
        peak = 0
        completed = []

        async def worker(article_id):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            completed.append(article_id)
            running -= 1

        researched = {"dossier": {"summary": "ready"}, "validation": {"passed": True}}  # SEO onward: one at a time
        with (patch.object(pipeline, "_workflow_slots", asyncio.Semaphore(2)),
              patch.object(pipeline, "_article_or_404", new=AsyncMock(return_value=researched)),
              patch("lib.turn.wait_for_turn", new=AsyncMock(return_value=True)),
              patch.object(pipeline, "_run_pipeline_in_background", new=AsyncMock(side_effect=worker))):
            await asyncio.gather(*(pipeline._pipeline_in_background(str(i)) for i in range(6)))
        assert peak == 1
        assert len(completed) == 6

    asyncio.run(exercise())
