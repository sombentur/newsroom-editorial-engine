"""A page-planner hiccup is retried; it never stops a browser job on the first failure."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib import browser_controller as bc  # noqa: E402

OBS = bc.Observation(snapshot="s", url="https://gemini.google.com/app/x", text="", submitted=True,
                     elements=[{"id": 1, "role": "button", "name": "Start research"}])
JOB = {"kind": "research", "prompt": "p", "activity": [{"action": "submit"}]}


def test_transient_planner_errors_are_retried():
    calls = []

    def flaky(job, obs, model=None):
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("slow provider")
        return bc.Decision(action="click", target=1, reason="Start research")

    with patch.object(bc, "_plan", side_effect=flaky), patch.object(bc.asyncio, "sleep", new=AsyncMock()):
        decision = asyncio.run(bc.plan(JOB, OBS))
    assert decision.action == "click" and len(calls) == 3


def test_persistent_planner_failure_is_reported_as_unavailable():
    with patch.object(bc, "_plan", side_effect=ConnectionError("503 overloaded")), \
            patch.object(bc.asyncio, "sleep", new=AsyncMock()):
        with pytest.raises(bc.PlannerUnavailable, match="ConnectionError"):
            asyncio.run(bc.plan(JOB, OBS))


def test_configuration_errors_are_not_retried():
    from lib.ai import AIError
    calls = []

    def missing_key(job, obs, model=None):
        calls.append(1)
        raise AIError("Configure the writing AI API key for the browser controller.", "auth")

    with patch.object(bc, "_plan", side_effect=missing_key):
        with pytest.raises(AIError):
            asyncio.run(bc.plan(JOB, OBS))
    assert len(calls) == 1


def test_research_report_is_opened_before_copying():
    """Without Share & Export visible, the planner is asked again with that fact, then waits."""
    card = bc.Observation(snapshot="s", url="https://gemini.google.com/app/x", text="Report ready", submitted=True,
                          elements=[{"id": 1, "role": "report", "name": "Deep Research report"},
                                    {"id": 2, "role": "button", "name": "Open"}])
    seen_hints = []

    def planner(job, obs, model=None):
        seen_hints.append(job.get("hint", ""))
        if job.get("hint"):
            return bc.Decision(action="click", target=2, reason="Open the full report")
        return bc.Decision(action="collect_report", target=1, reason="Report complete")

    with patch.object(bc, "_plan", side_effect=planner):
        decision = asyncio.run(bc.plan(JOB, card))
    assert decision.action == "click" and decision.target == 2
    assert seen_hints[0] == "" and "Share & Export is not visible" in seen_hints[1]

    with patch.object(bc, "_plan", return_value=bc.Decision(action="collect_report", target=1, reason="done")):
        assert asyncio.run(bc.plan(JOB, card)).action == "wait"

    opened = bc.Observation(**{**card.model_dump(), "elements": [*card.model_dump()["elements"],
                                                                   {"id": 3, "role": "button", "name": "Share & Export"}]})
    with patch.object(bc, "_plan", return_value=bc.Decision(action="collect_report", target=1, reason="done")):
        assert asyncio.run(bc.plan(JOB, opened)).action == "collect_report"


def test_overloaded_model_falls_back_to_the_next_model():
    used = []

    def overloaded(job, obs, model=None):
        used.append(model)
        if model == "gemini-3.8-flash":
            raise RuntimeError("503 UNAVAILABLE high demand")
        return bc.Decision(action="wait", target=0, reason="Research running")

    with (patch.object(bc, "_plan", side_effect=overloaded),
          patch.object(bc, "controller_settings", return_value=("gemini", "gemini-3.8-flash")),
          patch.dict("os.environ", {"BROWSER_CONTROLLER_FALLBACKS": "gemini-2.5-flash"})):
        assert asyncio.run(bc.plan(JOB, OBS)).action == "wait"
    assert used == ["gemini-3.8-flash", "gemini-2.5-flash"]
