"""Offline provider-contract tests. No real credentials or paid requests."""
import importlib.util
import io
import base64
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from lib import ai, manual_ai
from lib.runtime import external_operation_block_reason
from lib.thumbnails import add_headlines, validate_headlines
from lib.thumbnail_prompts import HUMAN_IMAGE_PROMPT


class ManualSafety(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_context_allows_ai_only_when_scheduler_is_enabled(self):
        with patch.dict(os.environ, {"MANUAL_AI_ENABLED": "false", "DRY_RUN": "false", "SCHEDULER_ENABLED": "true"}):
            token = manual_ai.automated_request.set(True)
            try:
                self.assertIsNone(manual_ai.environment_reason())
                os.environ["SCHEDULER_ENABLED"] = "false"
                self.assertIn("Scheduled AI is disabled", manual_ai.environment_reason())
            finally:
                manual_ai.automated_request.reset(token)

    async def test_explicit_request_required_even_with_environment_enabled(self):
        with patch.dict(os.environ, {"MANUAL_AI_ENABLED": "true", "DRY_RUN": "true"}):
            self.assertIsNotNone(manual_ai.environment_reason())
            token = manual_ai.manual_request.set(True)
            try:
                self.assertIsNone(manual_ai.environment_reason())
                self.assertIn("DRY_RUN", external_operation_block_reason())
            finally:
                manual_ai.manual_request.reset(token)

    async def test_pause_and_site_pause_block_manual_generation(self):
        database = Mock()
        database.system_settings.find_one = AsyncMock(return_value={"global_paused": True})
        database.sites.find_one = AsyncMock(return_value={"paused": True})
        with patch.dict(os.environ, {"MANUAL_AI_ENABLED": "true"}), patch.dict(sys.modules, {"lib.db": types.SimpleNamespace(db=database)}):
            token = manual_ai.manual_request.set(True)
            try:
                self.assertIn("paused", await manual_ai.block_reason("human"))
                database.system_settings.find_one.return_value = {"global_paused": False}
                self.assertIn("website", await manual_ai.block_reason("human"))
                database.sites.find_one.return_value = {"paused": False}
                self.assertIsNone(await manual_ai.block_reason("human"))
            finally:
                manual_ai.manual_request.reset(token)


class DeepResearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bridge_patch = patch("lib.browser_bridge.enabled", new=AsyncMock(return_value=False))
        bridge_patch.start()
        self.addCleanup(bridge_patch.stop)
        self.doc = {"id": "article-1", "dossier_meta": None}
        self.database = Mock()
        self.database.articles.find_one = AsyncMock(side_effect=lambda q, *args: self.doc.copy())

        async def update(q, operation):
            self.doc.update(operation["$set"])
        self.database.articles.update_one = AsyncMock(side_effect=update)
        spec = importlib.util.spec_from_file_location("deep_research_test_module", ROOT / "backend/lib/deep_research.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"lib.db": types.SimpleNamespace(db=self.database)}):
            spec.loader.exec_module(self.module)
        self.module.block_reason = AsyncMock(return_value=None)
        self.module.get_provider = lambda kind: "gemini"
        self.module.get_model = lambda kind: "deep-research-preview-04-2026"
        self.module.get_secret = lambda kind: "unit-test-only"
        self.module.provider_json = AsyncMock(return_value=({"sources": []}, "formatter"))
        self.topic = {"article_id": "article-1", "site_key": "human"}
        self.requests = []

    async def call_with(self, handler):
        real_client = httpx.AsyncClient
        def factory(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        with patch.object(self.module.httpx, "AsyncClient", side_effect=factory):
            return await self.module.research("schema instructions", self.topic)

    def complete(self, request):
        self.requests.append(request)
        if request.method == "POST":
            self.assertEqual(self.doc["dossier_meta"]["status"], "submitting")
            return httpx.Response(200, json={"id": "job-1", "status": "in_progress"})
        return httpx.Response(200, json={"status": "completed", "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": "Cited report https://example.org/source"}]}]})

    async def test_browser_report_is_saved_and_formatted_without_api_research(self):
        with patch("lib.browser_bridge.enabled", new=AsyncMock(return_value=True)), \
             patch("lib.browser_bridge.run_job", new=AsyncMock(return_value="Browser report with https://example.org/source")) as run, \
             patch("lib.browser_bridge.consumed", new=AsyncMock()) as consumed:
            result = await self.call_with(self.complete)
        self.assertEqual(self.requests, [])
        self.assertEqual(result[1], "gemini-browser-deep-research")
        self.assertEqual(self.doc["dossier_meta"]["provider"], "gemini-browser")
        self.assertIn("Browser report", self.doc["dossier_meta"]["report"])
        run.assert_awaited_once()
        consumed.assert_awaited_once_with("research", "article-1")

    async def test_new_job_saved_before_formatting_and_report_retained(self):
        result = await self.call_with(self.complete)
        self.assertEqual(result[1], "deep-research-preview-04-2026")
        self.assertEqual(self.doc["dossier_meta"]["interaction_id"], "job-1")
        self.assertIn("https://example.org/source", self.doc["dossier_meta"]["report"])
        self.assertEqual(sum(r.method == "POST" for r in self.requests), 1)
        self.assertIn(self.doc["dossier_meta"]["report"], self.module.provider_json.await_args.args[2])

    async def test_reconnect_never_creates_another_paid_job(self):
        self.doc["dossier_meta"] = {"interaction_id": "job-existing", "status": "in_progress"}
        await self.call_with(self.complete)
        self.assertTrue(all(r.method == "GET" for r in self.requests))

    async def test_unknown_submission_does_not_resubmit(self):
        self.doc["dossier_meta"] = {"status": "submitting"}
        with self.assertRaisesRegex(ai.AIError, "unknown outcome"):
            await self.call_with(self.complete)
        self.assertEqual(self.requests, [])

    async def test_formatter_retry_reuses_saved_report_without_network(self):
        self.doc["dossier_meta"] = {"interaction_id": "job-existing", "status": "formatting", "report": "Saved citations"}
        await self.call_with(self.complete)
        self.assertEqual(self.requests, [])

    async def test_pause_cancels_existing_job_and_does_not_format(self):
        self.doc["dossier_meta"] = {"interaction_id": "job-existing", "status": "in_progress"}
        self.module.block_reason.side_effect = [None, "AI is paused"]
        def handler(request):
            self.requests.append(request)
            return httpx.Response(200, json={"status": "cancelled"})
        with self.assertRaisesRegex(ai.AIError, "paused"):
            await self.call_with(handler)
        self.assertTrue(str(self.requests[0].url).endswith("/job-existing/cancel"))
        self.assertEqual(self.doc["dossier_meta"]["status"], "cancelled")
        self.module.provider_json.assert_not_awaited()

    async def test_timeout_keeps_submission_ambiguous_and_redacts_exception(self):
        def handler(request):
            raise httpx.ReadTimeout("private-test-secret")
        with self.assertRaises(ai.AIError) as error:
            await self.call_with(handler)
        self.assertNotIn("private-test-secret", str(error.exception))
        self.assertEqual(self.doc["dossier_meta"]["status"], "submitting")

    async def test_openai_job_id_is_saved_and_retry_does_not_resubmit(self):
        self.module.get_provider = lambda kind: "openai"
        self.module.get_model = lambda kind: "o4-mini-deep-research"
        self.module.provider_json = AsyncMock(return_value=({"sources": []}, "formatter"))
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(id="response-1", status="in_progress")
        client.responses.retrieve.return_value = SimpleNamespace(status="completed", output_text="Report with sources")

        async def immediate(call, label):
            return call()

        with patch("openai.OpenAI", return_value=client), patch.object(self.module, "_retry", side_effect=immediate):
            await self.module.research("instructions", self.topic)
            self.assertEqual(self.doc["dossier_meta"]["response_id"], "response-1")
            self.assertEqual(self.doc["dossier_meta"]["report"], "Report with sources")
            self.doc["dossier_meta"].pop("report")
            self.doc["dossier_meta"]["status"] = "in_progress"
            await self.module.research("instructions", self.topic)
        self.assertEqual(client.responses.create.call_count, 1)

    async def test_openai_uncertain_submission_never_duplicates_job(self):
        self.module.get_provider = lambda kind: "openai"
        self.doc["dossier_meta"] = {"provider": "openai", "status": "submitting"}
        with patch("openai.OpenAI") as client:
            with self.assertRaisesRegex(ai.AIError, "unknown outcome"):
                await self.module.research("instructions", self.topic)
        client.return_value.responses.create.assert_not_called()


class ThumbnailTests(unittest.IsolatedAsyncioTestCase):
    def test_public_image_metadata_has_editorial_filename_and_no_generator_label(self):
        from lib.workflow import _public_image_metadata
        metadata = _public_image_metadata(
            {"slug": "worker-monitoring-analysis", "headline": "Workers Under Watch"},
            {"format": "webp", "alt_text": "AI-generated conceptual image showing an office", "caption": "Generated by OpenAI", "media_title": "GPT image"},
        )
        self.assertEqual(metadata["filename"], "worker-monitoring-analysis-featured-image.webp")
        self.assertNotIn("AI", metadata["alt_text"].upper())
        self.assertNotIn("OPENAI", metadata["caption"].upper())
        self.assertNotIn("GPT", metadata["media_title"].upper())

    def test_image_provider_timeout_stays_below_workflow_limit(self):
        from lib import workflow
        self.assertLess(ai.IMAGE_PROVIDER_TIMEOUT_SECONDS, workflow.IMAGE_GENERATION_TIMEOUT_SECONDS)
        self.assertEqual(workflow.IMAGE_GENERATION_TIMEOUT_SECONDS, 120)

    def test_kannada_shape_fit_and_exact_aspect(self):
        lines = ["₹80 ಲಕ್ಷಕ್ಕೆ ಸರ್ಕಾರಿ ಹುದ್ದೆ?", "ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ", "ಓಎಂಆರ್ ತಿದ್ದಾಟದ ಆರೋಪ!"]
        im = add_headlines(Image.new("RGB", (1536, 864), "#233348"), lines, "kn")
        self.assertEqual(im.size, (1536, 864))
        self.assertGreater(len(im.crop((0, 0, 1536, 311)).getcolors(100000)), 2)
        self.assertEqual(im.getpixel((500, 500)), (35, 51, 72))
        with self.assertRaisesRegex(ValueError, "not 16:9"):
            add_headlines(Image.new("RGB", (1536, 1024)), lines, "kn")

    async def test_bad_headlines_fail_before_paid_image_call(self):
        with patch.object(ai, "_openai_image") as paid:
            with self.assertRaises(ai.AIError):
                await ai.generate_image("brief", "site", "brand", template=HUMAN_IMAGE_PROMPT,
                    headlines=["English", "ಅಭ್ಯರ್ಥಿ", "ತನಿಖೆ"], language="kn")
        paid.assert_not_called()

    async def test_saved_template_used_and_output_16_by_9(self):
        buf = io.BytesIO()
        Image.new("RGB", (1536, 864)).save(buf, "PNG")
        async def run(call, label):
            return call()
        with patch.object(ai, "_retry", side_effect=run), patch.object(ai, "_openai_image", return_value=base64.b64encode(buf.getvalue()).decode()) as paid:
            uri, model, fmt = await ai.generate_image("current story", "Human", "documentary",
                template="Saved custom template: {brief}", headlines=["AI AT WORK?", "WORKERS UNDER WATCH"], language="en")
        self.assertEqual(paid.call_args.args[1], "Saved custom template: current story")
        self.assertEqual(paid.call_args.args[2], "1536x864")
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(uri.split(",")[1]))).size, (1536, 864))
        self.assertEqual(fmt, "webp")


if __name__ == "__main__":
    unittest.main()
