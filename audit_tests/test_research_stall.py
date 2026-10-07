"""Stalled Deep Research recovers by itself; an editor's replacement is never undone (27 Sep 2026)."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib import browser_controller as bc  # noqa: E402
from lib.browser_actions import research_timed_out  # noqa: E402

NOW = datetime.now(timezone.utc)
STUCK = bc.Observation(snapshot="s", url="https://gemini.google.com/app/f63e", text="ಎಲ್ಲವನ್ನೂ ಒಟ್ಟಿಗೆ ತರುತ್ತಿದ್ದೇನೆ",
                       elements=[{"id": 1, "role": "button", "name": "Stop response"},
                                 {"id": 2, "role": "button", "name": "Thoughts"}])


def test_stalled_recopy_is_released_after_10_minutes_without_progress():
    job = {"kind": "research", "capture_existing": True, "created_at": NOW - timedelta(minutes=40)}
    assert "not progressing" in research_timed_out({**job, "progress_at": NOW - timedelta(minutes=11)}, STUCK)
    assert research_timed_out({**job, "progress_at": NOW - timedelta(minutes=5)}, STUCK) is None, "still writing"
    finished = bc.Observation(**{**STUCK.model_dump(), "elements": [{"id": 3, "role": "button", "name": "Share & Export"}]})
    assert research_timed_out({**job, "progress_at": NOW - timedelta(minutes=35)}, finished) is None


def test_replaced_run_never_holds_the_article():
    from lib import workflow as w
    current = {"id": "A", "stage": "selected", "site_key": "kannadiga"}
    fake_db = SimpleNamespace(articles=SimpleNamespace(find_one=AsyncMock(return_value=dict(current))))
    with patch.object(w, "db", fake_db), patch.object(w, "_update", AsyncMock()) as update, \
            patch.object(w, "audit", AsyncMock()) as audit:
        result = asyncio.run(w._ai_hold({"id": "A", "site_key": "kannadiga"}, "research",
                                        w.AIError("Replaced by a new Deep Research run", "browser")))
    assert result["stage"] == "selected" and not update.called and not audit.called


class _Articles:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, flt, projection=None):
        return {**self.doc, "dossier_meta": dict(self.doc.get("dossier_meta") or {})}

    async def update_one(self, flt, update):
        for key, value in update.get("$set", {}).items():
            self.doc[key] = value
        for key, value in update.get("$push", {}).items():
            self.doc.setdefault(key, []).append(value)


def _run(research_side_effects, meta):
    from lib import workflow as w
    articles = _Articles({"id": "A", "site_key": "kannadiga", "topic_snapshot": {"topic": "UP rain"}, "dossier_meta": meta})
    fake_db = SimpleNamespace(articles=articles, prompts=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    calls = []

    async def research(prompt, topic, report_only=False):
        effect = research_side_effects[len(calls)]
        calls.append(prompt)
        if isinstance(effect, Exception):
            raise effect
        articles.doc["dossier_meta"] = {**articles.doc["dossier_meta"], "report": effect}
        return effect, "gemini-browser"

    async def update(art_id, patch_, hist=None):
        articles.doc.update(patch_)
        return dict(articles.doc)
    with patch.object(w, "db", fake_db), patch.object(w, "_update", side_effect=update), patch.object(w, "audit", AsyncMock()), \
            patch.object(w, "_stopped_by_editor", AsyncMock(return_value=None)), \
            patch.object(w, "_ai_hold", AsyncMock(return_value={"stage": "held_review"})) as hold, \
            patch("lib.browser_bridge.enabled", AsyncMock(return_value=True)), \
            patch("lib.browser_bridge.consumed", AsyncMock()), \
            patch("lib.manual_ai.block_reason", AsyncMock(return_value=None)), \
            patch("lib.deep_research.research", side_effect=research):
        asyncio.run(w._run_report_research(dict(articles.doc), {"key": "kannadiga", "language": "kn"}))
    return calls, hold, articles.doc


def test_stalled_research_starts_one_fresh_run_automatically():
    from lib.ai import AIError
    from test_lanes_and_routes import KN_REPORT
    stall = AIError("Gemini's saved Deep Research is not progressing (the same step for 30 minutes), so its report "
                    "cannot be copied. It is researched again.", "browser")
    calls, hold, doc = _run([stall, KN_REPORT], {"report_mode": True, "prompt": "p", "status": "recopy"})
    assert len(calls) == 2 and not hold.called, "researched again once, automatically"
    assert doc["dossier_meta"]["auto_research_again"] is True
    assert any("researching again automatically" in h["note"] for h in doc["history"])
    calls, hold, doc = _run([stall, KN_REPORT], {"report_mode": True, "prompt": "p", "auto_research_again": True})
    assert len(calls) == 2 and not hold.called and doc["dossier_meta"]["auto_research_count"] == 2, "a second fresh run"
    calls, hold, _ = _run([stall], {"report_mode": True, "prompt": "p", "auto_research_again": True, "auto_research_count": 2})
    assert len(calls) == 1 and hold.called, "twice at most; then the owner decides"


def test_a_copy_of_a_conversation_without_a_finished_report_ends_with_a_clear_message():
    """Live case (28 Sep 2026): the saved conversation had no report; the copy would have waited 30 minutes."""
    from lib.workflow import STALLED_RESEARCH
    home = bc.Observation(snapshot="s", url="https://gemini.google.com/app", text="What can I help with?",
                          elements=[{"id": 1, "role": "button", "name": "Upload & tools"}])
    job = {"kind": "research", "capture_existing": True, "created_at": NOW - timedelta(minutes=20)}
    assert research_timed_out({**job, "progress_at": NOW - timedelta(minutes=2)}, home) is None, "give it a moment"
    reason = research_timed_out({**job, "progress_at": NOW - timedelta(minutes=6)}, home)
    assert "no finished report" in reason and not STALLED_RESEARCH.search(reason), "the owner decides, no new research"
    ready = bc.Observation(**{**home.model_dump(), "elements": [{"id": 3, "role": "button", "name": "Share & Export"}]})
    assert research_timed_out({**job, "progress_at": NOW - timedelta(minutes=6)}, ready) is None


def test_a_report_copy_replaces_the_articles_stuck_research_jobs():
    """Live case (28 Sep 2026): a job waiting for attention kept the Gemini lane; the copy failed at once twice."""
    from lib import browser_bridge as b
    jobs = SimpleNamespace(update_many=AsyncMock(), insert_one=AsyncMock())
    older = ["https://gemini.google.com/app/new", "https://gemini.google.com/app/old"]
    with patch.object(b, "db", SimpleNamespace(browser_jobs=jobs)), \
            patch.object(b, "_conversation_urls", AsyncMock(return_value=older)):
        job = asyncio.run(b.create_recopy_job("A", "p", "https://gemini.google.com/app/new", 42))
    query = jobs.update_many.await_args.args[0]
    assert set(query["status"]["$in"]) == {"queued", "running", "attention", "completed"}
    assert job["capture_candidates"] == older, "every conversation of the article, newest first, is searched for"
