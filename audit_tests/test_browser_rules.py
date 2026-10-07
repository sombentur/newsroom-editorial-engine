"""Known Gemini/ChatGPT states are handled by rules, so a free Gemini key's planner quota is not needed."""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib import browser_controller as bc  # noqa: E402
from lib.browser_actions import progress_action  # noqa: E402

SENT = [{"action": "submit", "at": datetime.now(timezone.utc)}]


def obs(host, *elements):
    return bc.Observation(snapshot="s", url=f"https://{host}/x", text="", submitted=True,
                          elements=[{"id": i + 1, **e} for i, e in enumerate(elements)])


def test_research_rules_follow_the_manual_flow():
    job = {"kind": "research", "activity": list(SENT)}
    plan = obs("gemini.google.com", {"role": "report", "name": "plan text"}, {"role": "button", "name": "ಸಂಶೋಧನೆ ಪ್ರಾರಂಭಿಸಿ"})
    assert progress_action(job, plan).action == "click", "start the research plan"
    clicked = {**job, "activity": [*SENT, {"action": "click", "control": {"name": "ಸಂಶೋಧನೆ ಪ್ರಾರಂಭಿಸಿ"}, "at": datetime.now(timezone.utc)}]}
    assert progress_action(clicked, plan).action == "wait", "never click Start research twice in a row"
    # Gemini shows "Stop response" while the plan waits for approval: Start research still gets clicked.
    waiting_plan = obs("gemini.google.com", {"role": "button", "name": "ಸಂಶೋಧನೆ ಪ್ರಾರಂಭಿಸಿ"}, {"role": "button", "name": "Stop response"})
    assert progress_action(job, waiting_plan).action == "click"
    assert progress_action(clicked, waiting_plan).action == "wait"
    working = obs("gemini.google.com", {"role": "button", "name": "Stop response"}, {"role": "button", "name": "Share & Export"})
    assert progress_action(job, working).action == "wait"
    done = obs("gemini.google.com", {"role": "report", "name": "chat"}, {"role": "report", "name": "Report"},
               {"role": "button", "name": "Share & Export keyboard_arrow_down"})
    assert progress_action(job, done).action == "wait", "a report open right after sending is an earlier conversation's"
    later = {"kind": "research", "activity": [{"action": "submit", "at": datetime.now(timezone.utc) - timedelta(minutes=10)}]}
    decision = progress_action(later, done)
    assert decision.action == "collect_report" and decision.target == 2
    assert progress_action({"kind": "research", "activity": []}, bc.Observation(
        snapshot="s", url="https://gemini.google.com/app", text="", elements=[])) is None, "before sending: not this rule set"


def test_chatgpt_rules_for_seo_and_thumbnail():
    seo = obs("chatgpt.com", {"role": "report", "name": '{"seo_title": "x", "meta_description": "y"}'},
              {"role": "button", "name": "Read aloud"})  # ChatGPT shows its answer bar once the answer is finished
    assert progress_action({"kind": "seo", "activity": list(SENT)}, seo).action == "collect_report"
    streaming = obs("chatgpt.com", {"role": "button", "name": "Stop streaming"}, {"role": "image", "name": ""})
    assert progress_action({"kind": "image", "activity": list(SENT)}, streaming).action == "wait"
    image = obs("chatgpt.com", {"role": "image", "name": "Generated image"})
    assert progress_action({"kind": "image", "activity": list(SENT)}, image).action == "collect_image"


def test_quota_exhausted_models_are_skipped():
    used = []

    def planner(job, observation, model=None):
        used.append(model)
        if model == "gemini-flash-latest":
            raise RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return bc.Decision(action="wait", target=0, reason="ok")

    bc._EXHAUSTED_UNTIL.clear()
    job = {"kind": "research", "prompt": "p", "activity": list(SENT)}
    page = obs("gemini.google.com", {"role": "button", "name": "Thinking"})
    with (patch.object(bc, "_plan", side_effect=planner),
          patch.object(bc, "controller_settings", return_value=("gemini", "gemini-flash-latest")),
          patch.dict("os.environ", {"BROWSER_CONTROLLER_FALLBACKS": "gemini-3-flash-preview"})):
        asyncio.run(bc.plan(job, page))
        asyncio.run(bc.plan(job, page))
    assert used == ["gemini-flash-latest", "gemini-3-flash-preview", "gemini-3-flash-preview"], "exhausted model skipped next time"
    bc._EXHAUSTED_UNTIL.clear()


def test_working_research_is_never_reloaded_and_an_idle_page_is_looked_at_again():
    now = datetime.now(timezone.utc)
    started = [{"action": "submit", "at": now - timedelta(minutes=50)},
               {"action": "click", "control": {"name": "Start research"}, "at": now - timedelta(minutes=49)}]
    running = obs("gemini.google.com", {"role": "button", "name": "Stop response"})
    assert progress_action({"kind": "research", "activity": started}, running).action == "wait", "never reload a working page"
    # Live case (28 Sep 2026): Gemini showed "You stopped this task" after its view dropped, yet finished the report.
    idle = bc.Observation(snapshot="s", url="https://gemini.google.com/app/x", text="You stopped this task", submitted=True,
                          elements=[{"id": 1, "role": "button", "name": "Send message"}])
    assert progress_action({"kind": "research", "activity": started}, idle).action == "reload_page", "look again"
    looked = [*started, {"action": "reload_page", "at": now - timedelta(minutes=2)}]
    assert progress_action({"kind": "research", "activity": looked}, idle).action == "wait", "wait; never the planner"
    thrice = [*started, *({"action": "reload_page", "at": now - timedelta(minutes=m)} for m in (40, 30, 20))]
    assert progress_action({"kind": "research", "activity": thrice}, idle).action == "wait", "at most three looks"
    chatgpt = {"kind": "image", "activity": [{"action": "submit", "at": now - timedelta(minutes=50)}]}
    assert progress_action(chatgpt, obs("chatgpt.com", {"role": "button", "name": "Stop streaming"})).action == "wait"


def test_planner_cannot_reload_pages():
    with patch.object(bc, "_plan", return_value=bc.Decision(action="reload_page", target=0, reason="reload")):
        decision = asyncio.run(bc.plan({"kind": "research", "prompt": "p", "activity": list(SENT)},
                                       obs("gemini.google.com", {"role": "button", "name": "Thinking"})))
    assert decision.action == "wait"


def test_stuck_research_is_released_after_timeout_and_refresh():
    from lib.browser_actions import research_timed_out
    running = obs("gemini.google.com", {"role": "button", "name": "Stop response"})
    old = datetime.now(timezone.utc) - timedelta(minutes=100)
    refreshed_long_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    job = {"kind": "research", "activity": [{"action": "submit", "at": old}, {"action": "reload_page", "at": refreshed_long_ago}]}
    assert "did not finish" in research_timed_out(job, running)
    just_refreshed = {**job, "activity": [{"action": "submit", "at": old}, {"action": "reload_page", "at": datetime.now(timezone.utc)}]}
    assert research_timed_out(just_refreshed, running) is None, "give the refresh a chance first"
    assert "did not finish" in research_timed_out({**job, "activity": [{"action": "submit", "at": old}]}, running), \
        "the time limits apply without a refresh (working pages are never reloaded)"
    ready = obs("gemini.google.com", {"role": "button", "name": "Share & Export"})
    assert research_timed_out(job, ready) is None, "a finished report is collected, not released"
    assert research_timed_out({**job, "kind": "seo"}, running) is None


def test_research_prompt_is_never_sent_without_deep_research_on():
    import pytest
    from lib.browser_actions import deep_research_active
    fresh = bc.Observation(snapshot="s", url="https://gemini.google.com/app", text="", elements=[
        {"id": 1, "role": "button", "name": "Open mode picker, currently Pro Extended"},
        {"id": 2, "role": "textbox", "name": "Enter a prompt for Gemini", "editable": True, "empty": True}])
    assert not deep_research_active(fresh.elements)
    job = {"kind": "research", "prompt": "p", "activity": []}
    with pytest.raises(ValueError, match="Deep Research is not turned on"):
        bc.validate_decision(job, fresh, bc.Decision(action="fill_prompt", target=2, reason="type"))
    ready = bc.Observation(**{**fresh.model_dump(), "elements": [*fresh.model_dump()["elements"],
                                                                {"id": 3, "role": "button", "name": "Deselect Deep research"}]})
    assert deep_research_active(ready.elements)
    assert bc.validate_decision(job, ready, bc.Decision(action="fill_prompt", target=2, reason="type")).action == "fill_prompt"
    # "Extended thinking" is a mode, not the Deep Research tool.
    assert not deep_research_active([bc.Element(id=4, role="menuitem", name="Extended thinking Complex problem solving", selected=True)])


def test_planner_gets_one_corrected_retry_before_typing_without_deep_research():
    fresh = bc.Observation(snapshot="s", url="https://gemini.google.com/app", text="", elements=[
        {"id": 1, "role": "button", "name": "Tools"},
        {"id": 2, "role": "textbox", "name": "Enter a prompt for Gemini", "editable": True, "empty": True}])
    hints = []

    def planner(job, observation, model=None):
        hints.append(job.get("hint", ""))
        if job.get("dr_hint"):
            return bc.Decision(action="click", target=1, reason="Open Tools")
        return bc.Decision(action="fill_prompt", target=2, reason="type the prompt")

    with patch.object(bc, "_plan", side_effect=planner):
        decision = asyncio.run(bc.plan({"kind": "research", "prompt": "p", "activity": []}, fresh))
    assert decision.action == "click" and "not a model" in hints[1]


def test_upload_menu_may_be_opened_to_reach_tools():
    """The + / File upload menu can hold Gemini's tools; file dialogs are intercepted by the extension."""
    page = obs("gemini.google.com", {"role": "button", "name": "File upload"}, {"role": "button", "name": "Upload & tools"})
    job = {"kind": "research", "prompt": "p", "activity": []}
    assert bc.validate_decision(job, page, bc.Decision(action="click", target=1, reason="open")).action == "click"


def test_partial_chatgpt_image_is_not_collected():
    partial = bc.Observation(snapshot="s", url="https://chatgpt.com/c/1", text="Thinking 55%", submitted=True,
                             elements=[{"id": 1, "role": "image", "name": "Generated image"}])
    assert progress_action({"kind": "image", "activity": list(SENT)}, partial).action == "wait"
    done = bc.Observation(**{**partial.model_dump(), "text": "Image created"})
    assert progress_action({"kind": "image", "activity": list(SENT)}, done).action == "collect_image"


def test_research_still_making_progress_is_not_released():
    from lib.browser_actions import research_timed_out
    running = obs("gemini.google.com", {"role": "button", "name": "Stop response"})
    now = datetime.now(timezone.utc)
    base = {"kind": "research", "rerun": True, "activity": [{"action": "submit", "at": now - timedelta(minutes=100)},
                                              {"action": "reload_page", "at": now - timedelta(minutes=20)}]}
    assert research_timed_out({**base, "progress_at": now - timedelta(minutes=5)}, running) is None, "still writing"
    assert "no visible progress" in research_timed_out({**base, "progress_at": now - timedelta(minutes=45)}, running)
    very_long = {**base, "activity": [{"action": "submit", "at": now - timedelta(minutes=200)}, base["activity"][1]],
                 "progress_at": now - timedelta(minutes=1)}
    assert research_timed_out(very_long, running), "hard limit still applies"


def test_unsent_prompt_is_sent_exactly_once_more():
    now = datetime.now(timezone.utc)
    stuck = bc.Observation(snapshot="s", url="https://chatgpt.com/c/1", text="", submitted=True, filled=True, prompt_verified=True,
                           elements=[{"id": 1, "role": "textbox", "name": "Ask anything", "editable": True},
                                     {"id": 2, "role": "button", "name": "Send"}])
    once = [{"action": "submit", "at": now - timedelta(seconds=60)}]
    decision = progress_action({"kind": "seo", "activity": once}, stuck)
    assert (decision.action, decision.target) == ("submit", 2)
    assert bc.validate_decision({"kind": "seo", "activity": once}, stuck, decision).action == "submit"
    assert progress_action({"kind": "seo", "activity": [{"action": "submit", "at": now}]}, stuck) is None, "give it time"
    twice = once + [{"action": "submit", "at": now - timedelta(seconds=30)}]
    assert progress_action({"kind": "seo", "activity": twice}, stuck) is None, "never a second time"
    try:
        bc.validate_decision({"kind": "seo", "activity": twice}, stuck, decision)
        raise AssertionError("a third send must be refused")
    except ValueError as e:
        assert "Duplicate submission prevented" in str(e)
    sent = bc.Observation(**{**stuck.model_dump(), "prompt_verified": False})
    assert progress_action({"kind": "seo", "activity": once}, sent) is None, "composer emptied: it was sent"


def test_deep_research_is_looked_for_in_each_candidate_menu():
    from lib.browser_actions import initial_action
    fresh = bc.Observation(snapshot="s", url="https://gemini.google.com/app", text="", elements=[
        {"id": 1, "role": "button", "name": "Open mode picker, currently Pro"},
        {"id": 2, "role": "button", "name": "Sources, Google Search selected"},
        {"id": 3, "role": "button", "name": "File upload"},
        {"id": 4, "role": "textbox", "name": "Enter a prompt for Gemini", "editable": True, "empty": True}])
    first = initial_action({"kind": "research", "activity": []}, fresh)
    assert (first.action, first.target) == ("click", 3), "open the upload/tools menu"
    tried = [{"action": "click", "control": {"name": "File upload"}}]
    assert initial_action({"kind": "research", "activity": tried}, fresh).target == 3, "a second look"
    assert initial_action({"kind": "research", "activity": tried * 2}, fresh) is None, "then the planner"
    menu = bc.Observation(**{**fresh.model_dump(), "elements": [*fresh.model_dump()["elements"],
                                                              {"id": 9, "role": "menuitemcheckbox", "name": "Deep research"}]})
    assert (initial_action({"kind": "research", "activity": tried}, menu).target) == 9, "pick Deep research"


def test_percent_in_our_own_prompt_is_not_image_progress():
    prompt = "Create a 16:9 news thumbnail; keep the top 35% as clean dark negative space. Create the image now."
    done = bc.Observation(snapshot="s", url="https://chatgpt.com/c/1", submitted=True,
                          text="You said: " + prompt + " ChatGPT said: Edit Latest response",
                          elements=[{"id": 4, "role": "image", "name": "Generated image 1"}])
    job = {"kind": "image", "prompt": prompt, "activity": list(SENT)}
    assert progress_action(job, done).action == "collect_image"
    drawing = bc.Observation(**{**done.model_dump(), "text": done.text + " Creating image 42%"})
    assert progress_action(job, drawing).action == "wait"


def test_page_load_error_is_reloaded_before_asking_the_owner():
    from lib.browser_startup import _fingerprint, startup_guard
    now = datetime.now(timezone.utc)
    broken = bc.Observation(snapshot="s", url="https://chatgpt.com/", text="We couldn\u2019t load your account Try reloading, or sign out and sign in again Reload Sign out",
                            elements=[{"id": 1, "role": "button", "name": "Reload"}, {"id": 2, "role": "button", "name": "Sign out"}])
    settled = {"first_seen_at": now - timedelta(seconds=30), "stable_since": now - timedelta(seconds=20),
               "fingerprint": _fingerprint(broken), "stable_observations": 3}
    patch_, decision = startup_guard({"kind": "seo", "activity": [], "browser_startup": settled}, broken, now)
    assert decision.action == "reload_page" and patch_ == {"browser_startup": {}}
    twice = [{"action": "reload_page"}, {"action": "reload_page"}]
    _, decision = startup_guard({"kind": "seo", "activity": twice, "browser_startup": settled}, broken, now)
    assert decision.action == "attention", "then the owner decides"


def test_chatgpt_answer_is_collected_only_when_finished():
    answer = {"id": 7, "role": "report", "name": '{"seo_title": "ILO Convention 193", "meta_description": "'}
    streaming = bc.Observation(snapshot="s", url="https://chatgpt.com/c/1", submitted=True, text="",
                               elements=[answer, {"id": 3, "role": "button", "name": "Stop"}])
    job = {"kind": "seo", "activity": list(SENT)}
    assert progress_action(job, streaming).action == "wait", "plain Stop means still generating"
    no_bar = bc.Observation(**{**streaming.model_dump(), "elements": [answer]})
    assert progress_action(job, no_bar).action == "wait", "no Read aloud / Regenerate yet"
    done = bc.Observation(**{**streaming.model_dump(), "elements": [answer, {"id": 4, "role": "button", "name": "Read aloud"},
                                                                    {"id": 5, "role": "button", "name": "Regenerate response"}]})
    assert progress_action(job, done).action == "collect_report"
    guard = bc.validate_decision(job, streaming, bc.Decision(action="collect_report", target=7, reason="x"))
    assert guard.action == "wait", "the server never collects while Stop is shown"


def test_first_deep_research_is_replaced_after_15_minutes_and_the_fresh_run_may_finish():
    """Owner rule (28 Sep 2026): replaced by one fresh Deep Research even if still working."""
    from lib.browser_actions import research_timed_out
    now = datetime.now(timezone.utc)
    working = obs("gemini.google.com", {"role": "button", "name": "Stop response"})
    first = {"kind": "research", "activity": [{"action": "submit", "at": now - timedelta(minutes=16)}]}
    assert "within 15 minutes" in research_timed_out(first, working)
    assert research_timed_out({**first, "activity": [{"action": "submit", "at": now - timedelta(minutes=10)}]}, working) is None
    assert research_timed_out({**first, "rerun": True, "progress_at": now - timedelta(minutes=1)}, working) is None, "a working fresh run is allowed to finish"
    ready = obs("gemini.google.com", {"role": "button", "name": "Share & Export"})
    assert research_timed_out(first, ready) is None, "a finished report is collected, not replaced"


def test_a_fresh_run_showing_no_progress_for_10_minutes_is_replaced():
    """Live case (28 Sep 2026): a fresh run showed no progress after its first 2 minutes, for 16 minutes."""
    from lib.browser_actions import research_timed_out
    now = datetime.now(timezone.utc)
    working = obs("gemini.google.com", {"role": "button", "name": "Stop response"})
    stuck = {"kind": "research", "rerun": True, "progress_at": now - timedelta(minutes=16),
             "activity": [{"action": "submit", "at": now - timedelta(minutes=18)}]}
    assert "no visible progress for 10 minutes" in research_timed_out(stuck, working)
    assert research_timed_out({**stuck, "progress_at": now - timedelta(minutes=2)}, working) is None, "still working"


PROMPT = "Create a 16:9 thumbnail.\n\nGenerate this thumbnail image now."
SAID = (" ChatGPT said: I can generate it, but the image generator incorrectly treated this as an edit request. "
        "Please resend the same prompt once more in a new message. Image generation failed Try again")
FAILED_CONTROLS = [{"id": 1, "role": "button", "name": "Try again"}, {"id": 2, "role": "button", "name": "Regenerate response"},
                   {"id": 3, "role": "button", "name": "Read aloud"}]


def _failed_page(**changes):
    values = dict(snapshot="s", url="https://chatgpt.com/c/1", text=PROMPT + SAID, submitted=True, elements=FAILED_CONTROLS)
    return bc.Observation(**{**values, **changes})


def test_failed_chatgpt_image_is_released_for_a_fresh_chat():
    """Live case (28 Sep 2026): ChatGPT's image tool "treated the request as an edit"; the planner asked the owner."""
    from lib.browser_actions import image_failed, image_failure_mark
    from lib.workflow import IMAGE_TOOL_FAILED
    now = datetime.now(timezone.utc)
    failed = _failed_page()
    job = {"kind": "image", "prompt": PROMPT, "activity": [{"action": "submit", "at": now - timedelta(minutes=1)}]}
    waiting = progress_action(job, failed)
    assert waiting.action == "wait", "ChatGPT's own Try again is not used (it failed in the live case)"
    assert not IMAGE_TOOL_FAILED.search(waiting.reason), "a wait message is never taken for a release"
    assert image_failed(job, failed) is None, "not before the failure was seen"
    mark = image_failure_mark(job, failed, now)
    assert mark == {"image_failure_seen_at": now}
    seen = {**job, **mark}
    assert image_failure_mark(seen, failed, now) is None, "stored once"
    assert image_failed(seen, failed) is None, "it must stay on the page first"
    seen["image_failure_seen_at"] = now - timedelta(seconds=20)
    assert IMAGE_TOOL_FAILED.search(image_failed(seen, failed))
    prose = _failed_page(text=failed.text + " The request may exceed the limits of the image tool.")
    assert image_failed(seen, prose), "ordinary prose about limits is not a usage limit"
    working = _failed_page(elements=[*FAILED_CONTROLS, {"id": 4, "role": "button", "name": "Stop streaming"}])
    assert image_failed(seen, working) is None and image_failure_mark(seen, working, now) == {"image_failure_seen_at": None}
    made = _failed_page(elements=[*FAILED_CONTROLS, {"id": 4, "role": "image", "name": "Generated image"}])
    assert image_failed(seen, made) is None and progress_action(seen, made).action == "collect_image"
    limit = _failed_page(text=failed.text + " You've hit the plan limit for image generations requests. "
                                            "You can create more images when the limit resets in 20 hours.")
    assert image_failed(seen, limit) is None and progress_action(seen, limit) is None, "a usage limit is for the owner"
    assert image_failed({**seen, "kind": "seo"}, failed) is None


def test_a_failure_near_the_extensions_5_minute_limit_is_released_at_once():
    """Review finding (28 Sep 2026): the extension stops waiting 5 minutes after Send."""
    from lib.browser_actions import image_failed
    now = datetime.now(timezone.utc)
    job = {"kind": "image", "prompt": PROMPT, "activity": [{"action": "submit", "at": now - timedelta(seconds=280)}],
           "image_failure_seen_at": now}
    assert image_failed(job, _failed_page())
    unsent = {"kind": "image", "prompt": PROMPT, "activity": [], "image_failure_seen_at": now - timedelta(minutes=1)}
    assert image_failed(unsent, _failed_page(submitted=False)) is None


def test_a_finished_image_from_the_same_owner_prompt_is_reused_not_replaced():
    """Review finding (28 Sep 2026): a completed job whose closing lines differ must not be thrown away."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from lib import browser_bridge

    def run(stored):
        jobs = SimpleNamespace(find_one=AsyncMock(return_value=dict(stored)), update_one=AsyncMock(), insert_one=AsyncMock())
        with (patch.object(browser_bridge, "db", SimpleNamespace(browser_jobs=jobs)),
              patch.object(browser_bridge, "_wait_for_job", AsyncMock(return_value="IMAGE")) as wait):
            result = asyncio.run(browser_bridge.run_job("image", "A", "OWNER\n\nNOTE\n\nGenerate this thumbnail image now.",
                                                        900, same_prompt="OWNER"))
        return result, jobs, wait.await_args.args[0]

    done = {"id": "J", "article_id": "A", "kind": "image", "status": "completed",
            "prompt": "OWNER\n\nGenerate this thumbnail image now."}
    result, jobs, waited_for = run(done)
    assert result == "IMAGE" and waited_for["id"] == "J" and not jobs.update_one.called and not jobs.insert_one.called
    _, jobs, waited_for = run({**done, "prompt": "ANOTHER PROMPT"})
    assert jobs.update_one.called and jobs.insert_one.called and waited_for["id"] != "J", "another prompt is replaced"


def test_draft_looks_before_sending_leave_deep_researchs_own_looks_alone():
    """Review finding (28 Sep 2026): the draft wait's reloads must not use up the post-send look-again budget."""
    from lib.browser_startup import DRAFT_LOOK_REASON
    now = datetime.now(timezone.utc)
    looks = [{"action": "reload_page", "note": DRAFT_LOOK_REASON, "at": now - timedelta(minutes=40)}] * 3
    job = {"kind": "research", "activity": [*looks, {"action": "submit", "at": now - timedelta(minutes=30)},
                                            {"action": "click", "control": {"name": "Start research"},
                                             "at": now - timedelta(minutes=29)}]}
    idle = obs("gemini.google.com", {"role": "button", "name": "Share"})
    assert progress_action(job, idle).action == "reload_page"


def _chatgpt(effort, *elements):
    return bc.Observation(snapshot="s", url="https://chatgpt.com/", text="", effort=effort,
                          elements=[{"id": 1, "role": "textbox", "name": "Chat with ChatGPT", "editable": True, "empty": True},
                                    *[{"id": i + 2, **e} for i, e in enumerate(elements)]])


def test_chatgpt_thinking_level_is_set_before_the_prompt():
    """Owner rule (28 Sep 2026): Medium for every job, one level up per fresh chat after a failed thumbnail."""
    from lib.browser_actions import initial_action
    picker = {"role": "button", "name": "Select ChatGPT model"}
    power = {"role": "menuitem", "name": "Power"}
    job = {"kind": "image", "prompt": "p", "effort": "Medium", "activity": []}
    closed = _chatgpt("Extra High", picker)
    opening = initial_action(job, closed)
    assert opening.action == "click" and opening.target == 2 and bc.validate_decision(job, closed, opening).action == "click"
    menu = _chatgpt("Extra High", picker, power)
    down = initial_action(job, menu)
    assert down.action == "level_down" and down.target == 3 and bc.validate_decision(job, menu, down).action == "level_down"
    assert initial_action({**job, "effort": "Extra High"}, _chatgpt("High", picker, power)).action == "level_up"
    assert initial_action(job, _chatgpt("Medium", picker, power)).action == "close_menu", "set: close the menu"
    assert initial_action(job, _chatgpt("Medium", picker)).action == "fill_prompt", "then the prompt goes in"
    assert initial_action({**job, "effort": None}, closed).action == "fill_prompt", "jobs without a level are not touched"
    assert initial_action(job, _chatgpt("GPT-5.5", picker)).action == "fill_prompt", "no level control: continue"
    many = {**job, "activity": [{"action": "level_down"}] * 12}
    assert initial_action(many, closed).action == "fill_prompt", "bounded; then it continues at the shown level"
    assert initial_action(many, menu).action == "close_menu"


def test_thinking_level_actions_are_refused_after_the_prompt_and_on_other_controls():
    import pytest
    job = {"kind": "image", "prompt": "p", "effort": "Medium", "activity": []}
    menu = _chatgpt("High", {"role": "button", "name": "Select ChatGPT model"}, {"role": "menuitem", "name": "Power"})
    with pytest.raises(ValueError):
        bc.validate_decision(job, bc.Observation(**{**menu.model_dump(), "submitted": True}), bc.Decision(action="level_down", target=3, reason="r"))
    with pytest.raises(ValueError):
        bc.validate_decision(job, menu, bc.Decision(action="level_down", target=2, reason="r"))
    with pytest.raises(ValueError):
        bc.validate_decision({**job, "kind": "research"}, bc.Observation(**{**menu.model_dump(), "url": "https://gemini.google.com/app"}),
                             bc.Decision(action="close_menu", target=0, reason="r"))


def test_a_longer_image_wait_limit_moves_the_early_release():
    from lib.browser_actions import image_failed
    now = datetime.now(timezone.utc)
    job = {"kind": "image", "prompt": PROMPT, "activity": [{"action": "submit", "at": now - timedelta(seconds=280)}],
           "image_failure_seen_at": now}
    assert image_failed(job, _failed_page()), "near the 5-minute limit"
    assert image_failed({**job, "wait_limit_seconds": 600}, _failed_page()) is None, "an Extra High job waits longer"


def test_the_image_deadline_grows_with_the_wait_after_send_and_a_queued_job_takes_the_current_level():
    """Review findings (28 Sep 2026)."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from lib import browser_bridge

    def run(stored, **kwargs):
        jobs = SimpleNamespace(find_one=AsyncMock(return_value=dict(stored) if stored else None), update_one=AsyncMock(),
                               insert_one=AsyncMock())
        with (patch.object(browser_bridge, "db", SimpleNamespace(browser_jobs=jobs)),
              patch.object(browser_bridge, "_wait_for_job", AsyncMock(return_value="IMAGE")) as wait):
            asyncio.run(browser_bridge.run_job("image", "A", "P", 900, **kwargs))
        return jobs, wait.await_args.args

    _, (job, _, timeout) = run(None, effort="Extra High", wait_limit_seconds=600)
    assert timeout == 1200 and job["effort"] == "Extra High", "Extra High waits 10 minutes after Send"
    _, (_, _, timeout) = run(None, effort="Medium", wait_limit_seconds=300)
    assert timeout == 900
    queued = {"id": "J", "article_id": "A", "kind": "image", "status": "queued", "prompt": "P", "effort": "High",
              "wait_limit_seconds": 420}
    jobs, (job, _, timeout) = run(queued, effort="Medium", wait_limit_seconds=300)
    assert job["effort"] == "Medium" and timeout == 900
    assert jobs.update_one.await_args.args == ({"id": "J", "status": "queued"}, {"$set": {"effort": "Medium", "wait_limit_seconds": 300}})


def test_the_planner_never_sets_the_thinking_level():
    job = {"kind": "image", "prompt": "p", "effort": "Medium", "activity": []}
    menu = _chatgpt("High", {"role": "button", "name": "Select ChatGPT model"}, {"role": "menuitem", "name": "Power"})
    with patch.object(bc, "_plan", return_value=bc.Decision(action="level_up", target=3, reason="r")), \
            patch.object(bc, "controller_settings", return_value=("gemini", "m")), \
            patch.object(bc, "_fallback_models", return_value=[]):
        assert asyncio.run(bc.plan(job, menu)).action == "wait"


def test_chatgpts_ask_chatgpt_composer_is_filled_by_the_rule():
    """Live finding (28 Sep 2026): the composer is now "Ask ChatGPT"; the planner had typed every ChatGPT prompt."""
    from lib.browser_actions import initial_action
    page = bc.Observation(snapshot="s", url="https://chatgpt.com/", text="", effort="Medium",
                          elements=[{"id": 1, "role": "textbox", "name": "Ask ChatGPT", "editable": True, "empty": True},
                                    {"id": 2, "role": "button", "name": "Select ChatGPT model"}])
    for kind in ("seo", "image"):
        decision = initial_action({"kind": kind, "prompt": "p", "effort": "Medium", "activity": []}, page)
        assert decision.action == "fill_prompt" and decision.target == 1


def test_image_jobs_choose_chatgpts_create_image_tool_before_the_prompt():
    """Owner rule (28 Sep 2026): ChatGPT kept treating thumbnail prompts as edits; Create image is chosen first."""
    from lib.browser_actions import initial_action
    composer = {"id": 1, "role": "textbox", "name": "Ask ChatGPT", "editable": True, "empty": True}
    plus = {"id": 2, "role": "button", "name": "Add files and more"}
    picker = {"id": 3, "role": "button", "name": "Select ChatGPT model"}

    def page(*extra):
        return bc.Observation(snapshot="s", url="https://chatgpt.com/", text="", effort="Medium",
                              elements=[composer, plus, picker, *extra])
    job = {"kind": "image", "prompt": "p", "effort": "Medium", "activity": []}
    opening = initial_action(job, page())
    assert opening.action == "click" and opening.target == 2 and bc.validate_decision(job, page(), opening).action == "click"
    menu = page({"id": 4, "role": "button", "name": "Add photos & files\nUpload from computer"},
                {"id": 5, "role": "button", "name": "Create image\nVisualize anything"})
    choose = initial_action(job, menu)
    assert choose.action == "click" and choose.target == 5 and bc.validate_decision(job, menu, choose).action == "click"
    on = page({"id": 4, "role": "button", "name": "Remove Create image"})
    assert initial_action(job, on).action == "fill_prompt", "then the prompt goes in"
    assert initial_action({**job, "kind": "seo"}, page()).action == "fill_prompt", "SEO jobs are not touched"
    tried = {**job, "activity": [{"action": "click", "control": {"name": "Add files and more"}}] * 6}
    assert initial_action(tried, page()).action == "fill_prompt", "bounded; then ChatGPT decides, as before"
    high = page({"id": 4, "role": "menuitem", "name": "Power"})
    assert initial_action({**job, "effort": "High"}, bc.Observation(**{**high.model_dump(), "effort": "Medium"})).action == "level_up", \
        "the thinking level is set first"
