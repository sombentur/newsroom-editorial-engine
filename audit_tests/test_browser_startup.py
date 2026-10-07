"""Deterministic hydration and restored-draft guards; no browser or API calls."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from lib.browser_controller import Observation
from lib.browser_startup import startup_guard


class BrowserStartupTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
        self.job = {}

    def observation(self, *, empty=True, name="Ask Gemini", control="Tools", **overrides):
        values = dict(snapshot="fresh", url="https://gemini.google.com/app", text="",
                      elements=[dict(id=1, role="textbox", name=name, editable=True, empty=empty),
                                dict(id=2, role="button", name=control)])
        values.update(overrides)
        return Observation(**values)

    def check(self, seconds, obs=None):
        patch, decision = startup_guard(self.job, obs or self.observation(), self.start + timedelta(seconds=seconds))
        self.job.update(patch)
        return patch, decision

    def test_first_observation_waits_without_a_model(self):
        patch, decision = self.check(0)
        self.assertEqual(decision.action, "wait")
        self.assertEqual(patch["browser_startup"]["stable_observations"], 1)
        self.assertEqual(patch["browser_startup"]["first_seen_at"], self.start)

    def test_stable_composer_still_needs_ten_second_warmup(self):
        self.check(0)
        self.assertEqual(self.check(9)[1].action, "wait")
        self.assertIsNone(self.check(10)[1])

    def test_two_observations_across_thirty_seconds_are_sufficient(self):
        self.check(0)
        patch, decision = self.check(30)
        self.assertIsNone(decision)
        self.assertEqual(patch["browser_startup"]["stable_observations"], 2)

    def test_late_hydration_requires_another_five_stable_seconds(self):
        self.check(0)
        changed = self.observation(control="Personal account")
        self.assertEqual(self.check(9, changed)[1].action, "wait")
        self.assertEqual(self.check(10, changed)[1].action, "wait")
        self.assertIsNone(self.check(14, changed)[1])

    def test_model_and_tool_changes_do_not_repeat_completed_startup(self):
        self.check(0)
        patch, decision = self.check(10)
        self.assertIsNone(decision)
        self.assertEqual(patch["browser_startup"]["ready_at"], self.start + timedelta(seconds=10))
        for second, control in [(11, "Pro"), (12, "Deep Research"), (13, "Close tools")]:
            with self.subTest(control=control):
                self.assertEqual(self.check(second, self.observation(control=control)), ({}, None))

    def test_draft_restored_after_startup_is_still_preserved(self):
        self.check(0)
        self.check(10)
        patch, decision = self.check(11, self.observation(empty=False, control="Pro"))
        self.assertEqual(patch, {})
        self.assertEqual(decision.action, "attention")
        self.assertIn("preserved", decision.reason)

    def test_tool_menu_can_temporarily_hide_composer_after_startup(self):
        self.check(0)
        self.check(10)
        menu = self.observation(elements=[dict(id=1, role="menuitemcheckbox", name="Deep Research")])
        self.assertEqual(self.check(11, menu), ({}, None))

    def look(self, seconds, obs):
        """Check, and record a reload the way the bridge does (the decision's reason becomes the event's note)."""
        patch, decision = self.check(seconds, obs)
        if decision is not None and decision.action == "reload_page":
            self.job.setdefault("activity", []).append(
                {"action": "reload_page", "note": decision.reason, "at": self.start + timedelta(seconds=seconds)})
        return patch, decision

    def test_restored_draft_is_preserved_after_stability(self):
        """Live case (28 Sep 2026): ChatGPT restored the owner's unsent message. It is waited for, never overwritten."""
        self.job["kind"] = "research"
        self.check(0)
        draft = self.observation(empty=False)
        self.assertEqual(self.check(30, draft)[1].action, "wait")
        decision = self.check(35, draft)[1]
        self.assertEqual(decision.action, "wait")
        self.assertIn("never overwritten", decision.reason)
        self.assertIn("started in Gemini", decision.reason, "this fixture is a Gemini page")
        self.assertEqual(self.job["draft_seen_at"], self.start + timedelta(seconds=35))
        self.assertEqual(self.check(100, draft)[1].action, "wait")
        patch, decision = self.look(155, draft)
        self.assertEqual(decision.action, "reload_page", "a fresh page shows whether it was sent or cleared")
        self.assertEqual(patch["browser_startup"], {})
        self.look(165, draft)
        self.assertEqual(self.look(175, draft)[1].action, "wait", "the next look is 2 minutes later")
        self.assertEqual(self.look(400, draft)[1].action, "reload_page")
        self.look(410, draft)
        self.assertEqual(self.look(454, draft)[1].action, "wait", "7 minutes are not over yet (35 + 420 s)")
        self.assertEqual(self.look(455, draft)[1].action, "reload_page", "one last look at a fresh page")
        self.look(465, draft)
        decision = self.look(475, draft)[1]
        self.assertEqual(decision.action, "attention", "then the owner decides")
        self.assertIn("existing draft is present", decision.reason)  # the phrase the Workbench guide matches
        self.assertIn("preserved", decision.reason)

    def test_draft_looks_do_not_use_up_the_page_load_error_reloads(self):
        self.job["activity"] = [{"action": "reload_page", "note": "The message box still holds text the app did not type; "
                                 "loading the page again to see if it was sent or cleared."}] * 3
        broken = self.observation(text="We couldn't load your account. Try reloading.", elements=[dict(id=2, role="button", name="Reload")])
        self.check(0, broken)
        self.assertEqual(self.check(10, broken)[1].action, "reload_page")

    def test_no_reload_while_the_draft_is_being_edited_in_the_tab(self):
        draft = self.observation(empty=False)
        self.check(0, draft)
        self.check(10, draft)
        self.job["progress_at"] = self.start + timedelta(seconds=100)
        self.assertEqual(self.check(140, draft)[1].action, "wait", "the owner is typing here")
        self.assertEqual(self.check(221, draft)[1].action, "reload_page")

    def test_a_draft_sent_from_the_work_tab_is_not_continued_in_that_conversation(self):
        draft = self.observation(empty=False)
        self.check(0, draft)
        self.check(10, draft)
        conversation = self.observation(url="https://gemini.google.com/app/abc123")
        self.check(60, conversation)
        decision = self.check(70, conversation)[1]
        self.assertEqual(decision.action, "attention")
        self.assertIn("sent in this work tab", decision.reason)

    def test_a_draft_sent_or_cleared_elsewhere_lets_the_job_continue(self):
        draft = self.observation(empty=False)
        self.check(0, draft)
        self.assertEqual(self.check(10, draft)[1].action, "wait")
        self.check(200, self.observation())
        patch, decision = self.check(210, self.observation())
        self.assertIsNone(decision)
        self.assertIsNone(patch["draft_seen_at"])

    def test_existing_draft_on_first_observation_is_not_overwritten(self):
        draft = self.observation(empty=False)
        self.check(0, draft)
        self.assertEqual(self.check(10, draft)[1].action, "wait")

    def test_changed_verified_prompt_stops_immediately(self):
        self.job["activity"] = [{"action": "fill_prompt"}]
        patch, decision = self.check(0, self.observation(empty=False, filled=True))
        self.assertEqual(patch, {})
        self.assertEqual(decision.action, "attention")
        self.assertIn("composer changed", decision.reason)

    def test_changed_prompt_can_be_empty_after_restoration(self):
        patch, decision = self.check(0, self.observation(filled=True))
        self.assertEqual(patch, {})
        self.assertEqual(decision.action, "attention")

    def test_existing_fill_or_submit_history_bypasses_initialization(self):
        for action in ("fill_prompt", "submit"):
            with self.subTest(action=action):
                patch, decision = startup_guard({"activity": [{"action": action}]}, self.observation(), self.start)
                self.assertEqual(patch, {})
                self.assertIsNone(decision)

    def test_submitted_job_can_have_an_empty_composer(self):
        for job, obs in [
            ({}, self.observation(filled=True, submitted=True)),
            ({"activity": [{"action": "submit"}]}, self.observation(filled=True)),
        ]:
            with self.subTest(job=job):
                self.assertEqual(startup_guard(job, obs, self.start), ({}, None))

    def test_verified_filled_prompt_does_not_restart_startup(self):
        self.assertEqual(startup_guard({}, self.observation(empty=False, filled=True, prompt_verified=True), self.start), ({}, None))

    def test_observation_ids_and_page_text_do_not_reset_stability(self):
        self.check(0)
        changed = self.observation(snapshot="new", text="Changing status text", elements=[
            dict(id=5, role="textbox", name="Ask Gemini", editable=True, empty=True),
            dict(id=6, role="button", name="Tools")])
        self.assertIsNone(self.check(10, changed)[1])

    def test_missing_composer_requires_attention_after_wait(self):
        obs = self.observation(elements=[])
        self.check(0, obs)
        self.assertEqual(self.check(10, obs)[1].action, "attention")

    def test_state_does_not_store_control_names_or_draft_text(self):
        patch, _ = self.check(0, self.observation(name="Private draft text", empty=False))
        self.assertNotIn("Private draft text", str(patch))

    def test_legacy_naive_database_dates_are_read_as_utc(self):
        self.check(0)
        self.job["browser_startup"]["first_seen_at"] = self.start.replace(tzinfo=None)
        self.job["browser_startup"]["stable_since"] = self.start.replace(tzinfo=None)
        self.assertIsNone(self.check(10)[1])

    def test_clock_moving_back_restarts_the_guard(self):
        self.check(10)
        patch, decision = self.check(0)
        self.assertEqual(decision.action, "wait")
        self.assertEqual(patch["browser_startup"]["first_seen_at"], self.start)
