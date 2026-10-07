"""Owner request (28 Sep 2026): Gemini Deep Research in another Google account (gemini.google.com/u/N/app)."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_the_chosen_account_is_stored_as_its_u_number_only():
    from fastapi import HTTPException
    from lib import browser_bridge as b
    saved = {}
    configs = SimpleNamespace(update_one=AsyncMock(side_effect=lambda q, u, **k: saved.update(u["$set"])))
    with patch.object(b, "db", SimpleNamespace(browser_config=configs)), patch("lib.util.audit", AsyncMock()):
        result = asyncio.run(b.set_gemini_account(b.GeminiAccount(address=" https://gemini.google.com/u/1/app?hl=en ")))
        assert saved == {"gemini_account": "u/1"} and result["research_url"] == "https://gemini.google.com/u/1/app"
        assert asyncio.run(b.set_gemini_account(b.GeminiAccount(address="")))["research_url"] == "https://gemini.google.com/app"
        for bad in ("https://chatgpt.com/", "https://gemini.google.com/u/x/app", "gemini.google.com/u/1/app"):
            with pytest.raises(HTTPException):
                asyncio.run(b.set_gemini_account(b.GeminiAccount(address=bad)))
    assert b.research_url({"gemini_account": "u/2"}) == "https://gemini.google.com/u/2/app"


def test_the_extension_is_told_where_gemini_opens():
    from lib import browser_bridge as b
    configs = SimpleNamespace(update_one=AsyncMock(), find_one=AsyncMock(return_value={"gemini_account": "u/1"}))
    with patch.object(b, "db", SimpleNamespace(browser_config=configs)):
        reply = asyncio.run(b.workspace_state(b.WorkspaceState(tabs={})))
    assert reply["research_url"] == "https://gemini.google.com/u/1/app"


def test_links_of_the_second_account_are_kept_with_their_account():
    from lib import manual_research as m
    from lib.browser_bridge import GEMINI_CONVERSATION
    link = "https://gemini.google.com/u/1/app/026b0fa4de34145d?hl=en"
    assert m.classify_link(link) == ("https://gemini.google.com/u/1/app/026b0fa4de34145d", "gemini")
    match = GEMINI_CONVERSATION.match(link)
    assert "https://gemini.google.com/" + match.group(1) + "app/" + match.group(2) == \
        "https://gemini.google.com/u/1/app/026b0fa4de34145d"


def test_a_cleared_draft_on_the_second_accounts_new_chat_is_not_taken_for_a_conversation():
    from lib.browser_controller import Observation
    from lib.browser_startup import startup_guard
    start = datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc)
    job = {"kind": "research", "draft_seen_at": start}

    def page(empty):
        return Observation(snapshot="s", url="https://gemini.google.com/u/1/app", text="",
                           elements=[{"id": 1, "role": "textbox", "name": "Enter a prompt for Gemini", "editable": True, "empty": empty}])
    from datetime import timedelta
    patch_, _ = startup_guard(job, page(True), start + timedelta(seconds=1))
    job.update(patch_)
    patch_, decision = startup_guard(job, page(True), start + timedelta(seconds=12))
    assert decision is None and patch_["draft_seen_at"] is None, "/u/1/app is a new chat, not the owner's conversation"
