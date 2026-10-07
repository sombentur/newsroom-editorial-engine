"""Leftover work-tab text is kept in full in the article's history before the box is cleared (27 Sep 2026)."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_saved_work_tab_text_goes_to_the_article_history():
    from lib import browser_bridge as b
    articles = SimpleNamespace(find_one=AsyncMock(return_value={"stage": "writing_article"}), update_one=AsyncMock())
    jobs = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))
    job = {"id": "J", "kind": "seo", "status": "running", "article_id": "A"}
    with patch.object(b, "db", SimpleNamespace(articles=articles, browser_jobs=jobs)), \
            patch.object(b, "job_status", AsyncMock(return_value=job)):
        asyncio.run(b.progress("J", b.Progress(message="Saved the text", saved_text="[Ask anything] my old draft")))
    note = articles.update_one.call_args.args[1]["$push"]["history"]["note"]
    assert "ChatGPT work tab was saved here" in note and note.endswith("[Ask anything] my old draft")
