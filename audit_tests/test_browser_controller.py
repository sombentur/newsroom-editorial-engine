"""Controller contract tests: model proposals cannot bypass executor boundaries."""
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from lib.browser_controller import Observation, Decision, validate_decision, plan, _decision_from_proposal

class BrowserControllerTests(unittest.IsolatedAsyncioTestCase):
    def observation(self,**kw):
        values=dict(snapshot='fresh',url='https://chatgpt.com/',text='composer',elements=[
            dict(id=1,role='textbox',name='Prompt',editable=True,empty=True),
            dict(id=2,role='button',name='Send prompt'),
            dict(id=3,role='button',name='Upgrade plan'),
            dict(id=4,role='image',name='Generated image'),
            dict(id=5,role='report',name='Finished report')])
        values.update(kw);return Observation(**values)
    def decision(self,action,target=0):return Decision(action=action,target=target,reason='test')
    def test_gemini_deep_research_checkbox_is_allowed(self):
        obs = self.observation(url='https://gemini.google.com/app', elements=[dict(id=1, role='menuitemcheckbox', name='Deep research')])
        validate_decision({'kind': 'research'}, obs, self.decision('click', 1))

    def test_image_preview_is_not_collected_while_generation_is_running(self):
        obs = self.observation(submitted=True, elements=[dict(id=1,role='image',name='Generated image'),
            dict(id=2,role='button',name='Stop answering')])
        self.assertEqual(validate_decision({'kind':'image'},obs,self.decision('collect_image',1)).action,'wait')

    def test_gemini_empty_home_after_submission_does_not_wait_forever(self):
        obs = self.observation(url='https://gemini.google.com/app', submitted=True,
            text='Conversation with Gemini\nWhat can I help with?', elements=[])
        job = {'kind':'research','activity':[{'action':'submit'},{'action':'wait'},{'action':'wait'}]}
        self.assertEqual(validate_decision(job,obs,self.decision('wait')).action,'attention')
        obs.text = "Conversation with Gemini\nLet's jump in"
        obs.elements = self.observation(elements=[dict(id=1,role='button',name='Temporary chat')]).elements
        self.assertEqual(validate_decision(job,obs,self.decision('wait')).action,'attention')
        obs.elements = self.observation(elements=[dict(id=1,role='button',name='Stop response')]).elements
        self.assertEqual(validate_decision(job,obs,self.decision('wait')).action,'wait')

    def test_unknown_target_and_external_origin_are_rejected(self):
        for obs,d in [(self.observation(),self.decision('click',200)),(self.observation(url='https://evil.example/'),self.decision('wait'))]:
            with self.assertRaises(ValueError):validate_decision({'kind':'image'},obs,d)
    def test_submit_requires_verified_prompt_and_cannot_repeat(self):
        for obs in [self.observation(),self.observation(filled=True),self.observation(filled=True,prompt_verified=True,submitted=True)]:
            with self.assertRaises(ValueError):validate_decision({'kind':'image'},obs,self.decision('submit',2))
        validate_decision({'kind':'image'},self.observation(filled=True,prompt_verified=True),self.decision('submit',2))
    def test_submit_only_uses_a_recognized_send_button(self):
        for label in ['Send', 'Send message', 'Send prompt', 'Submit', 'Submit prompt']:
            with self.subTest(label=label):
                obs = self.observation(filled=True, prompt_verified=True,
                    elements=[dict(id=2, role='button', name=label)])
                self.assertEqual(validate_decision({'kind':'image'}, obs, self.decision('submit',2)).action, 'submit')
        for role, label in [('button', 'Deep research'), ('menuitemcheckbox', 'Send'), ('button', 'Send feedback')]:
            with self.subTest(role=role, label=label):
                obs = self.observation(filled=True, prompt_verified=True,
                    elements=[dict(id=2, role=role, name=label)])
                result = validate_decision({'kind':'image'}, obs, self.decision('submit',2))
                self.assertEqual((result.action, result.target), ('attention', 0))
                self.assertIn('not a recognized Send/Submit button', result.reason)
    def test_initial_delivery_wait_allows_the_editor_to_settle(self):
        obs = self.observation(submitted=True, prompt_verified=True)
        for history in [[{'action':'submit'}], [{'action':'submit'}, {'action':'wait'}]]:
            with self.subTest(history=history):
                result = validate_decision({'kind':'image', 'activity':history}, obs, self.decision('wait'))
                self.assertEqual(result.action, 'wait')
    def test_repeated_wait_with_prompt_in_composer_requires_attention(self):
        once = {'kind':'image', 'activity':[{'action':'submit'}, {'action':'wait'}, {'action':'wait'}]}
        stuck = self.observation(submitted=True, prompt_verified=True)
        # After one Send the rules send the unsent prompt once more before the owner is asked.
        self.assertEqual(validate_decision(once, stuck, self.decision('wait')).action, 'wait')
        no_send = self.observation(submitted=True, prompt_verified=True, elements=[dict(id=1, role='textbox', name='Prompt', editable=True)])
        self.assertEqual(validate_decision(once, no_send, self.decision('wait')).action, 'attention')
        job = {'kind':'image', 'activity':[{'action':'submit'}, {'action':'wait'}, {'action':'submit'}, {'action':'wait'}, {'action':'wait'}]}
        result = validate_decision(job, self.observation(submitted=True, prompt_verified=True), self.decision('wait'))
        self.assertEqual((result.action, result.target), ('attention', 0))
        self.assertIn('will not be sent again automatically', result.reason)
        self.assertEqual(validate_decision(job, self.observation(submitted=True), self.decision('wait')).action, 'wait')
    def test_delivery_wait_guard_only_counts_after_latest_submit(self):
        obs = self.observation(submitted=True, prompt_verified=True)
        for history in [
            [{'action':'wait'}, {'action':'wait'}, {'action':'submit'}, {'action':'wait'}],
            [{'action':'submit'}, {'action':'wait'}, {'action':'wait'}, {'action':'submit'}],
            [{'action':'wait'}, {'action':'wait'}],
        ]:
            with self.subTest(history=history):
                result = validate_decision({'kind':'image', 'activity':history}, obs, self.decision('wait'))
                self.assertEqual(result.action, 'wait')
    def test_verbose_model_reason_is_truncated_without_changing_action(self):
        proposal = {'action':'wait', 'target':0, 'reason':'A' * 300}
        result = _decision_from_proposal(proposal)
        self.assertEqual((result.action, result.target, result.reason), ('wait', 0, 'A' * 250))
        self.assertEqual(len(proposal['reason']), 300)
    def test_reason_truncation_does_not_relax_model_action_or_target_validation(self):
        for proposal in [
            {'action':'execute_script', 'target':0, 'reason':'A' * 300},
            {'action':'wait', 'target':501, 'reason':'A' * 300},
            {'action':'wait', 'target':0, 'reason':123},
        ]:
            with self.subTest(proposal=proposal):
                with self.assertRaises(ValueError):
                    _decision_from_proposal(proposal)
    def test_sensitive_control_and_unprotected_send_are_rejected(self):
        for target in [2,3]:
            with self.assertRaises(ValueError):validate_decision({'kind':'image'},self.observation(),self.decision('click',target))
    def test_result_must_match_job_and_be_submitted(self):
        with self.assertRaises(ValueError):validate_decision({'kind':'image'},self.observation(),self.decision('collect_image',4))
        with self.assertRaises(ValueError):validate_decision({'kind':'image'},self.observation(submitted=True),self.decision('collect_report',5))
        validate_decision({'kind':'image'},self.observation(submitted=True),self.decision('collect_image',4))
    async def test_model_decision_still_passes_validation(self):
        with patch('lib.browser_controller._plan',return_value=self.decision('click',200)):
            with self.assertRaises(ValueError):await plan({'kind':'image'},self.observation())
    def test_gemini_schema_is_accepted_by_installed_sdk(self):
        from google.genai import types
        config=types.GenerateContentConfig(response_mime_type='application/json',response_json_schema=Decision.model_json_schema())
        self.assertIsNotNone(config.response_json_schema)
