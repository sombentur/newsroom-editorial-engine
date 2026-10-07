"""Offline regression tests runnable before the missing app files are restored.

No SDK, HTTP library, Mongo server, credentials or installed test runner required.
Database and encryption dependencies are mocked only for migration orchestration.
These tests do not certify cryptographic round trips or application integration.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from lib import ai, secrets
from lib.redaction import redact
from lib.runtime import ConfigurationError, RuntimeSafety, external_operation_block_reason


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        # Windows creates a local socket pair when initializing its event loop.
        # Initialize it first, then prohibit every socket connection from tests.
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        patch("asyncio.events.new_event_loop", return_value=loop).start()
        patch.dict(os.environ, {}, clear=True).start()
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in audit tests")).start()


class ConfigurationTests(OfflineTest):
    def test_safe_defaults(self):
        safety = RuntimeSafety.from_env()
        self.assertTrue(safety.dry_run)
        self.assertFalse(safety.scheduler_enabled)
        self.assertFalse(safety.auto_publish_enabled)
        self.assertEqual(safety.operating_mode, "review")

    def test_invalid_booleans_rejected_without_echo(self):
        for name in ("DRY_RUN", "SCHEDULER_ENABLED", "AUTO_PUBLISH_ENABLED"):
            for value in ("", "0", "1", "yes", "private-invalid-value"):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ConfigurationError) as exc:
                        RuntimeSafety.from_env({name: value})
                    self.assertNotIn("private-invalid-value", str(exc.exception))

    def test_invalid_mode_rejected_without_echo(self):
        with self.assertRaises(ConfigurationError) as exc:
            RuntimeSafety.from_env({"OPERATING_MODE": "private-invalid-value"})
        self.assertNotIn("private-invalid-value", str(exc.exception))

    def test_dry_run_overrides_requested_scheduler_and_autopublish(self):
        os.environ.update(SCHEDULER_ENABLED="true", AUTO_PUBLISH_ENABLED="true", OPERATING_MODE="auto")
        self.assertTrue(external_operation_block_reason().startswith("DRY_RUN:"))

    def test_invalid_config_blocks_external_operations(self):
        os.environ["DRY_RUN"] = ""
        self.assertTrue(external_operation_block_reason().startswith("CONFIGURATION_INVALID:"))

    def test_explicit_flags_parse(self):
        safety = RuntimeSafety.from_env({"DRY_RUN": "false", "SCHEDULER_ENABLED": " true "})
        self.assertFalse(safety.dry_run)
        self.assertTrue(safety.scheduler_enabled)


class ProviderTests(OfflineTest):
    def test_direct_gemini_call_blocked_before_sdk_import(self):
        with self.assertRaises(ai.AIError) as exc:
            ai._gemini_call("configured-model", "system", "prompt", False)
        self.assertEqual(exc.exception.kind, "safety")

    def test_direct_openai_call_blocked_before_sdk_import(self):
        with self.assertRaises(ai.AIError) as exc:
            ai._openai_image("configured-model", "prompt", "1536x1024")
        self.assertEqual(exc.exception.kind, "safety")

    def test_gemini_inspection_never_invokes_generation(self):
        os.environ.update(DRY_RUN="false", GEMINI_API_KEY="unit-test-only", GEMINI_RESEARCH_MODEL="configured-model")
        with patch.object(ai, "_gemini_call", side_effect=AssertionError("Paid request forbidden")) as call:
            result = asyncio.run(ai.gemini_ping("research"))
        call.assert_not_called()
        self.assertTrue(result["configured"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["paid_request_sent"])

    def test_openai_inspection_never_generates_image(self):
        os.environ.update(DRY_RUN="false", OPENAI_API_KEY="unit-test-only", OPENAI_IMAGE_MODEL="configured-model")
        with patch.object(ai, "_openai_image", side_effect=AssertionError("Paid request forbidden")) as call:
            result = asyncio.run(ai.openai_ping())
        call.assert_not_called()
        self.assertTrue(result["configured"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["paid_request_sent"])

    def test_missing_model_has_no_fallback(self):
        self.assertEqual(secrets.get_model("image"), "")
        self.assertEqual(secrets.get_model("research"), "")
        self.assertEqual(secrets.get_model("writing"), "")

    def test_grounded_fallback_requires_explicit_opt_in(self):
        with patch.object(ai, "_gemini_json", new_callable=AsyncMock) as call:
            with self.assertRaises(ai.AIError) as exc:
                asyncio.run(ai.run_research("prompt", {}))
        call.assert_not_called()
        self.assertEqual(exc.exception.kind, "configuration")

    def test_provider_error_never_reflects_remote_body(self):
        for reason in ("401 API key", "429 quota", "503 network", "unexpected"):
            self.assertNotIn("private-test-value", ai._safe(Exception(reason + " private-test-value")))

    def test_retry_classification(self):
        self.assertEqual(ai._classify(Exception("401 authentication")), "auth")
        self.assertEqual(ai._classify(Exception("503 unavailable")), "network")
        self.assertEqual(ai._classify(Exception("429 rate limit")), "rate_limit")


class SecretTests(OfflineTest):
    def test_ai_secrets_are_environment_only(self):
        os.environ["GEMINI_API_KEY"] = "unit-test-only"
        asyncio.run(secrets.load_secrets())
        self.assertEqual(secrets.get_secret("gemini_api_key"), "unit-test-only")

    def test_owner_can_save_secret_without_browser_readback(self):
        (ROOT / ".local").mkdir(exist_ok=True)
        env_path = ROOT / ".local" / "provider-settings-test.env"
        try:
            env_path.write_text("UNRELATED=preserved\n", encoding="utf-8")
            with patch.object(secrets, "ENV_PATH", env_path):
                async def save_and_read():
                    await secrets.save_secrets({"gemini_api_key": "private-test-value", "model_research": "deep-research-preview-04-2026"})
                    return await secrets.status()
                result = asyncio.run(save_and_read())
            saved = env_path.read_text(encoding="utf-8")
            self.assertIn("UNRELATED=preserved", saved)
            self.assertIn("GEMINI_API_KEY=private-test-value", saved)
            self.assertEqual(result["gemini_key_masked"], "Configured")
            self.assertNotIn("private-test-value", repr(result))
        finally:
            env_path.unlink(missing_ok=True)

    def test_invalid_model_is_rejected_without_echo(self):
        with self.assertRaises(ConfigurationError) as exc:
            asyncio.run(secrets.save_secrets({"model_image": "private-invalid-model"}))
        self.assertNotIn("private-invalid-model", str(exc.exception))

    def test_status_contains_no_key_or_suffix(self):
        os.environ["OPENAI_API_KEY"] = "private-test-value"
        os.environ["RANKMATH_API_KEY"] = "private-rankmath-value"
        result = asyncio.run(secrets.status())
        self.assertEqual(result["openai_key_masked"], "Configured")
        self.assertEqual(result["rankmath_key_masked"], "Configured")
        self.assertNotIn("private-test-value", repr(result))
        self.assertNotIn("private-rankmath-value", repr(result))
        self.assertNotIn("alue", result["openai_key_masked"])

    def test_nested_audit_fields_redacted_without_mutation(self):
        detail = {"nested": [{"Authorization": "private-test-value", "wp_app_password": "private-test-value"}], "ok": True}
        result = redact(detail)
        self.assertNotIn("private-test-value", repr(result))
        self.assertTrue(result["ok"])
        self.assertEqual(detail["nested"][0]["Authorization"], "private-test-value")

    def test_environment_secret_redacted_in_free_text(self):
        os.environ["SESSION_SECRET"] = "private-test-value"
        self.assertNotIn("private-test-value", redact("message private-test-value"))


class WorkflowSafetyTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.db = types.SimpleNamespace(system_settings=types.SimpleNamespace(find_one=AsyncMock(return_value={"mode": "auto"})),
                                        articles=types.SimpleNamespace(find_one=AsyncMock(return_value=None)))
        modules = {
            "lib.db": types.SimpleNamespace(db=self.db),
            "lib.discovery": types.SimpleNamespace(detect_risk=Mock(return_value=[])),
            "lib.util": types.SimpleNamespace(audit=AsyncMock(), now_utc=lambda: datetime.now(timezone.utc), new_id=lambda: "test-id"),
            "lib.wordpress": types.SimpleNamespace(WPError=RuntimeError, has_credentials=lambda _: True),
            "lib.safety": types.SimpleNamespace(system_block_reason=AsyncMock(return_value=None)),
            "lib.wp_credentials": types.SimpleNamespace(is_connected=lambda _: True, connection_reason=lambda _: ""),
        }
        spec = importlib.util.spec_from_file_location("audit_workflow_module", ROOT / "backend/lib/workflow.py")
        self.workflow = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.workflow)
        self.site = {"key": "human", "auto_publish": True}
        self.workflow._preflight = AsyncMock(return_value=(self.site, None))
        self.workflow._update = AsyncMock(return_value={"stage": "held_review"})
        self.workflow._wp_write_live = AsyncMock(side_effect=AssertionError("WordPress write forbidden"))

    def test_environment_auto_publish_off_overrides_database(self):
        os.environ.update(DRY_RUN="false", OPERATING_MODE="auto", AUTO_PUBLISH_ENABLED="false")
        result = asyncio.run(self.workflow.wordpress_write({"id": "one"}, self.site, "publish"))
        self.assertEqual(result["stage"], "held_review")
        self.workflow._wp_write_live.assert_not_called()
        self.assertIn("approval", self.workflow._update.await_args.args[1]["held_reason"])

    def test_environment_review_blocks_scheduling_despite_database_auto(self):
        os.environ.update(DRY_RUN="false", AUTO_PUBLISH_ENABLED="true")
        result = asyncio.run(self.workflow.wordpress_write({"id": "one"}, self.site, "future"))
        self.assertEqual(result["stage"], "held_review")
        self.workflow._wp_write_live.assert_not_called()
        self.assertIn("approval", self.workflow._update.await_args.args[1]["held_reason"])

    def test_saved_editor_approval_releases_high_risk_publish_gate(self):
        os.environ.update(DRY_RUN="false", OPERATING_MODE="auto", AUTO_PUBLISH_ENABLED="true",
                          HIGH_RISK_REVIEW_REQUIRED="true")
        self.workflow._wp_write_live = AsyncMock(return_value={"stage": "verified"})
        article = {"id": "one", "image": {"status": "generated"},
                   "validation": {"passed": True}, "quality_gate": {"passed": True},
                   "review_flags": ["Legal Investigation"], "approval": {"by": "owner"},
                   "article": {"headline": "Reviewed report"}}
        result = asyncio.run(self.workflow.wordpress_write(article, self.site, "publish"))
        self.assertEqual(result["stage"], "verified")
        self.workflow._wp_write_live.assert_awaited_once()


class MigrationTests(OfflineTest):
    def setUp(self):
        super().setUp()
        self.db = Mock()
        self.db.system_settings.find_one = AsyncMock(return_value={})
        self.db.system_settings.update_one = AsyncMock()
        self.db.sites.update_many = AsyncMock()
        self.db.sites.update_one = AsyncMock()
        self.db.sites.find.return_value.to_list = AsyncMock(return_value=[])
        self.db.articles.find.return_value.to_list = AsyncMock(return_value=[])
        self.db.articles.update_one = AsyncMock(return_value=types.SimpleNamespace(modified_count=1))
        self.encrypt = Mock(return_value="ciphertext-test-only")
        self.audit = AsyncMock()
        class CredentialError(ValueError):
            pass
        self.credential_error = CredentialError
        modules = {
            "lib.db": types.SimpleNamespace(db=self.db),
            "lib.util": types.SimpleNamespace(audit=self.audit, now_utc=lambda: datetime.now(timezone.utc), new_id=lambda: "test-revision"),
            "lib.wp_credentials": types.SimpleNamespace(CredentialError=CredentialError, encrypt_password=self.encrypt, is_connected=lambda _: False),
        }
        spec = importlib.util.spec_from_file_location("audit_safety_module", ROOT / "backend/lib/safety.py")
        self.safety = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.safety)

    def test_dry_run_blocks_before_database_query(self):
        self.assertIn("DRY_RUN", asyncio.run(self.safety.system_block_reason()))
        self.db.system_settings.find_one.assert_not_awaited()

    def test_missing_persistent_repair_lock_blocks(self):
        os.environ["DRY_RUN"] = "false"
        self.assertIn("SAFETY_LOCK", asyncio.run(self.safety.system_block_reason()))

    def test_failed_encryption_preserves_plaintext(self):
        self.db.sites.find.return_value.to_list.return_value = [{"key": "human", "wp_app_password": "private-test-value"}]
        self.encrypt.side_effect = self.credential_error("unavailable")
        with self.assertRaises(self.credential_error):
            asyncio.run(self.safety.initialize_safety())
        for call in self.db.sites.update_one.await_args_list:
            self.assertNotIn("$unset", call.args[1])

    def test_successful_encryption_and_plaintext_removal_are_one_update(self):
        self.db.sites.find.return_value.to_list.return_value = [{"key": "human", "wp_app_password": "private-test-value"}]
        asyncio.run(self.safety.initialize_safety())
        operation = self.db.sites.update_one.await_args.args[1]
        self.assertEqual(operation["$set"]["wp_password_ciphertext"], "ciphertext-test-only")
        self.assertIn("wp_app_password", operation["$unset"])

    def test_unverified_publication_is_held_and_audited(self):
        self.db.articles.find.return_value.to_list.return_value = [{"id": "article-one", "site_key": "human", "stage": "published", "wp": None}]
        asyncio.run(self.safety.initialize_safety())
        self.assertEqual(self.db.articles.update_one.await_args.args[1]["$set"]["stage"], "held_review")
        self.assertEqual(self.audit.await_args.args[0], "publication_status_corrected")

    def test_false_publication_evidence_rejected(self):
        base = {"simulated": False, "post_id": 12, "public_url": "https://example.invalid/article",
                "status": "publish", "verified_at": "2026-09-23",
                "verification": {"creation_response_ok": True, "readback_ok": True, "readback_status": "publish", "public_page_ok": True}}
        for field, value in (("post_id", None), ("post_id", True), ("post_id", 0), ("public_url", ""), ("simulated", True), ("verification", {})):
            with self.subTest(field=field, value=value):
                self.assertFalse(self.safety.verified_wp_record({**base, field: value}))


if __name__ == "__main__":
    unittest.main()
