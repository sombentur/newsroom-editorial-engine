"""Real local Mongo + ASGI tests. Uses and removes only its own new test database.

Run after Start Local.cmd starts the loopback Mongo instance. Never uses the
desktop database or external websites. All passwords here are synthetic fixtures.
"""
import asyncio
import base64
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import AsyncMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


@unittest.skipUnless(os.environ.get("RUN_LOCAL_INTEGRATION") == "true", "Requires explicit local integration test mode")
class LocalAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pymongo import MongoClient
        cls.name = "editorial_test_" + uuid.uuid4().hex
        cls.environment = patch.dict(os.environ, {
            "MONGO_URL": "mongodb://127.0.0.1:27018", "DB_NAME": cls.name,
            "APP_URL": "http://127.0.0.1:8001", "CORS_ORIGINS": "http://127.0.0.1:8001",
            "SESSION_SECRET": secrets.token_urlsafe(48),
            "WP_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "MANUAL_AI_ENABLED": "false", "LOCAL_SETUP_ENABLED": "true", "DRY_RUN": "true", "SCHEDULER_ENABLED": "false",
            "AUTO_PUBLISH_ENABLED": "false", "OPERATING_MODE": "review",
            "REPAIR_LOCK": "true",
        })
        cls.environment.start()
        from fastapi.testclient import TestClient
        from server import app
        cls.mongo = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000, tz_aware=True)
        cls.database = cls.mongo[cls.name]
        cls.client = TestClient(app, base_url="http://127.0.0.1:8001")
        cls.client.__enter__()
        cls.remote = patch("httpx.AsyncClient.request", new=AsyncMock(side_effect=AssertionError("External HTTP forbidden")))
        cls.remote.start()
        assert cls.client.get("/api/auth/session").json()["setup_required"] is True
        cls.login_body = {"username": "fixture-owner", "password": "synthetic-local-test-password"}
        result = cls.client.post("/api/auth/setup", json=cls.login_body, headers={"Origin": "http://127.0.0.1:8001"})
        assert result.status_code == 200, result.status_code
        cls.headers = {"Origin": "http://127.0.0.1:8001", "X-CSRF-Token": result.json()["csrf_token"]}
        cls.cookie = result.headers["set-cookie"]

    def setUp(self):
        # One article at a time: each test starts with no article in progress (the suite shares one database).
        from lib import turn
        turn.TURN_POLL_SECONDS = 0.2
        self.database.system_settings.update_one({"id": "system"}, {"$unset": {"current_article": "", "current_since": ""}})

    @classmethod
    def tearDownClass(cls):
        cls.remote.stop()
        cls.client.__exit__(None, None, None)
        # Only this UUID-named database created by this test class is removed.
        assert cls.name.startswith("editorial_test_") and cls.name != "editorial_desktop"
        cls.mongo.drop_database(cls.name)
        cls.mongo.close()
        cls.environment.stop()

    def test_research_go_ahead_records_editor_and_continues(self):
        article_id = "research-approval-fixture"
        row = {"id": article_id, "site_key": "human", "stage": "held_review", "held_reason": "Research needs review", "dossier": {"summary": "Saved report"}, "validation": {"passed": False, "checks": []}}
        self.database.articles.insert_one(row)
        path = f"/api/articles/{article_id}/research/go-ahead"
        try:
            self.assertEqual(self.client.post(path).status_code, 403)
            with patch("lib.manual_ai.block_reason", new=AsyncMock(return_value=None)), patch("routers.pipeline._pipeline_in_background", new=AsyncMock()) as pipeline:
                response = self.client.post(path, headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                saved = self.database.articles.find_one({"id": article_id})
                self.assertTrue(saved["validation"]["accepted_by_editor"])
                self.assertFalse(saved["research_approval"]["automatic_validation"]["passed"])
                self.assertEqual(saved["research_approval"]["by"], "fixture-owner")
                self.assertEqual(saved["dossier"], row["dossier"])
                self.assertEqual(self.client.post(path, headers=self.headers).status_code, 409)
                pipeline.assert_called_once_with(article_id)
                for changes in [{"stage":"published"}, {"stage":"held_review","dossier":None,"validation":{"passed":False}}]:
                    self.database.articles.update_one({"id":article_id},{"$set":changes})
                    self.assertEqual(self.client.post(path,headers=self.headers).status_code,409)
        finally:
            self.database.articles.delete_one({"id":article_id})

    def test_provider_alerts_report_only_active_holds(self):
        row = {"id":"alert-fixture","site_key":"human","stage":"held_review","held_reason":"article generation failed (quota)","ai_failure":{"task":"article generation","kind":"quota","provider":"OpenAI writing"}}
        self.database.articles.insert_one(row)
        try:
            alerts = self.client.get("/api/ai-alerts").json()
            item = next(a for a in alerts if a["article_id"] == row["id"])
            self.assertEqual(item["provider"], "OpenAI writing")
            self.assertEqual(item["kind"], "quota")
            self.database.articles.update_one({"id":row["id"]},{"$set":{"stage":"writing_article"}})
            self.assertFalse(any(a["article_id"] == row["id"] for a in self.client.get("/api/ai-alerts").json()))
        finally:
            self.database.articles.delete_one({"id":row["id"]})

    def test_no_fake_data_and_safe_startup(self):
        self.assertEqual(self.database.sites.count_documents({}), 2)
        self.assertEqual(self.database.prompts.count_documents({}), 5)
        self.assertEqual(self.database.articles.count_documents({}), 0)
        self.assertEqual(self.database.topics.count_documents({}), 0)
        state = self.client.get("/api/system").json()
        self.assertEqual(state["mode"], "review")
        self.assertTrue(state["dry_run"])
        self.assertFalse(state["scheduler_enabled"])
        self.assertTrue(state["repair_lock"])

    def test_browser_bridge_pairing_and_cancellation(self):
        from datetime import datetime, timezone
        config = self.database.browser_config
        jobs = self.database.browser_jobs
        old_system = self.database.system_settings.find_one({"id": "system"})
        try:
            self.assertEqual(self.client.post("/api/browser-worker/claim", json={}).status_code, 401)
            self.assertEqual(self.client.post("/api/browser/pair-code").status_code, 403)
            code = self.client.post("/api/browser/pair-code", headers=self.headers).json()["code"]
            paired = self.client.post("/api/browser-worker/pair", json={"code": code})
            self.assertEqual(paired.status_code, 200)
            self.assertEqual(self.client.post("/api/browser-worker/pair", json={"code": code}).status_code, 401)
            headers = {"Authorization": "Bearer " + paired.json()["token"], "X-Bridge-Version": "0.2.0"}
            modern = {**headers, "X-Bridge-Version": "0.3.0"}
            payload = {"tabs": {"research": {"tab_id": 12, "attached": True, "ready": True, "message": "Ready"}}}
            self.assertEqual(self.client.post('/api/browser-worker/workspace', json=payload).status_code, 401)
            self.assertEqual(self.client.post('/api/browser-worker/workspace', json=payload, headers=modern).status_code, 200)
            self.assertEqual(self.client.post('/api/browser/workspace', json={"action":"connect"}).status_code, 403)
            self.assertEqual(self.client.post('/api/browser/workspace', json={"action":"connect"}, headers=self.headers).status_code, 200)
            command = self.client.post('/api/browser-worker/workspace', json=payload, headers=modern).json()['command']
            self.client.post('/api/browser-worker/workspace/ack', json={"id":"stale"}, headers=modern)
            self.assertEqual(config.find_one({"id":"browser"})['workspace_command']['id'], command['id'])
            self.client.post('/api/browser-worker/workspace/ack', json={"id":command['id']}, headers=modern)
            self.assertNotIn('workspace_command', config.find_one({"id":"browser"}))
            status = self.client.get("/api/browser/status").json()
            self.assertNotIn("token_hash", status)
            self.assertNotIn("pair_hash", status)
            self.assertEqual(self.client.get("/api/browser/download").status_code, 200)
            # Only jobs a workflow will consume are claimable (orphans never run with stale prompts).
            jobs.insert_one({"id": "bridge-fixture", "article_id": "bridge-article", "kind": "research", "prompt": "fixture", "status": "queued", "resume_on_completion": True, "created_at": datetime.now(timezone.utc)})
            self.database.system_settings.update_one({"id": "system"}, {"$set": {"global_paused": False, "killswitch": False}})
            # One article at a time: the work tabs take only the current article's jobs.
            self.assertIsNone(self.client.post("/api/browser-worker/claim", json={}, headers=headers).json()["job"])
            self.database.articles.insert_one({"id": "bridge-article", "site_key": "human", "stage": "researching",
                                               "idempotency_key": "bridge-article"})
            self.addCleanup(self.database.articles.delete_one, {"id": "bridge-article"})
            self.database.system_settings.update_one({"id": "system"}, {"$set": {"current_article": "bridge-article"}})
            self.assertIsNotNone(self.client.post("/api/browser-worker/claim", json={}, headers=headers).json()["job"])
            self.assertIsNone(self.client.post("/api/browser-worker/claim", json={}, headers=headers).json()["job"])
            jobs.update_one({"id":"bridge-fixture"}, {"$set":{"decision_count":100}})
            from lib.browser_controller import Decision
            observation = {"snapshot": "s1", "url": "https://gemini.google.com/app", "text": "Research running", "elements": []}
            with patch("lib.browser_bridge.plan", new=AsyncMock(return_value=Decision(action="wait", target=0, reason="Research running"))):
                response = self.client.post("/api/browser-worker/jobs/bridge-fixture/observe", json=observation, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["action"], "wait")
            self.assertEqual(len(jobs.find_one({"id": "bridge-fixture"})["activity"]), 1)
            diagnostic = jobs.find_one({"id": "bridge-fixture"})["last_observation"]
            self.assertFalse(diagnostic["composer_visible"])
            self.assertFalse(diagnostic["composer_empty"])
            self.assertNotIn("text", diagnostic)
            self.assertNotIn("screenshot", diagnostic)
            page = self.client.get("/api/browser/jobs/bridge-fixture/page")
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.headers['cache-control'], 'no-store')
            self.assertIn('Research running', page.text)
            from lib.browser_bridge import _page_previews
            with patch('lib.browser_bridge.time.monotonic', return_value=_page_previews['bridge-fixture'][0]+301):
                self.assertEqual(self.client.get('/api/browser/jobs/bridge-fixture/page').status_code, 404)
            external = {**observation, "url": "https://untrusted.invalid/"}
            self.assertEqual(self.client.post("/api/browser-worker/jobs/bridge-fixture/observe", json=external, headers=headers).status_code, 422)
            self.client.post("/api/browser/jobs/bridge-fixture/cancel", headers=self.headers)
            late = self.client.post("/api/browser-worker/jobs/bridge-fixture", json={"message": "Late result", "result": "x" * 600}, headers=headers)
            self.assertEqual(late.status_code, 409)
            self.client.post("/api/browser/disconnect", headers=self.headers)
            self.assertEqual(self.client.post("/api/browser-worker/claim", json={}, headers=headers).status_code, 401)
        finally:
            config.delete_many({})
            jobs.delete_many({})
            self.database.system_settings.replace_one({"id": "system"}, old_system)

    def test_cookie_and_password_hash(self):
        self.assertIn("HttpOnly", self.cookie)
        self.assertIn("SameSite=strict", self.cookie)
        owner = self.database.admins.find_one({"id": "owner"})
        self.assertTrue(owner["password_hash"].startswith("$argon2id$"))
        self.assertNotIn("password", owner)

    def test_all_sensitive_reads_require_authentication(self):
        saved = dict(self.client.cookies)
        self.client.cookies.clear()
        try:
            for path in ("sites", "system", "stats", "audit", "secrets", "prompts", "topics", "articles", "published", "health", "plugin/download", "browser/status", "browser/download", "browser/jobs/fixture/page"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get("/api/" + path).status_code, 401)
        finally:
            self.client.cookies.update(saved)

    def test_mutations_require_csrf_and_origin(self):
        self.assertEqual(self.client.patch("/api/system", json={"killswitch": True}).status_code, 403)
        self.assertEqual(self.client.patch("/api/system", json={"killswitch": True}, headers={**self.headers, "Origin": "https://untrusted.invalid"}).status_code, 403)

    def test_owner_can_select_mode_but_cannot_release_write_guards(self):
        self.assertEqual(self.client.patch("/api/system", json={"scheduler_enabled": True}, headers=self.headers).status_code, 409)
        selected = self.client.patch("/api/system", json={"mode": "auto"}, headers=self.headers)
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["mode"], "auto")
        state = self.client.get("/api/system").json()
        self.assertEqual(state["mode"], "auto")
        self.assertTrue(state["dry_run"])
        self.assertFalse(state["scheduler_enabled"])
        self.assertEqual(self.client.put("/api/sites/human", json={"auto_publish": True}, headers=self.headers).status_code, 409)

    def test_discovery_import_paid_probes_and_missing_credentials_do_not_use_network(self):
        for path in ("pipeline/discover", "pipeline/import-posts"):
            self.assertEqual(self.client.post("/api/" + path, json={"site_key": "human"}, headers=self.headers).status_code, 409)
        result = self.client.post("/api/sites/human/connection-test", headers=self.headers).json()
        self.assertFalse(result["passed"])
        self.assertFalse(result["simulated"])
        result = self.client.post("/api/secrets/test/openai-image", headers=self.headers).json()
        self.assertFalse(result["paid_request_sent"])

    @contextmanager
    def discovery_fixture(self):
        original = self.database.system_settings.find_one({"id": "system"})
        sites = list(self.database.sites.find({}))
        try:
            result = self.client.patch("/api/system", json={"global_paused": False}, headers=self.headers)
            self.assertEqual(result.status_code, 200)
            yield
        finally:
            self.database.system_settings.replace_one({"id": "system"}, original)
            for site in sites:
                self.database.sites.replace_one({"key": site["key"]}, site)
            # Only synthetic topic records in this test class's UUID database.
            self.database.topics.delete_many({})

    def test_public_discovery_runs_in_review_without_unlocking_paid_or_wordpress_work(self):
        import httpx
        from lib.editorial_briefs import FEEDS, source_urls
        requests = []

        async def feed(client, method, url, **kwargs):
            requests.append((method, url))
            self.assertEqual(method, "GET")
            self.assertTrue(str(url) in FEEDS["kannadiga"] or str(url).startswith("https://news.google.com/rss/search?"))
            self.assertIsNone(client.auth)
            self.assertNotIn("Authorization", kwargs.get("headers") or {})
            if str(url) == "https://tv9kannada.com/feed":
                return httpx.Response(200, request=httpx.Request(method, url), text="""
                    <rss><channel><title>TV9 Kannada</title><item><title>ಕರ್ನಾಟಕದ ಸುದ್ದಿ ಪರೀಕ್ಷೆ</title>
                    <link>https://example.org/kannada-fixture</link></item></channel></rss>""")
            return httpx.Response(200, request=httpx.Request(method, url), text="""
                <rss><channel><item><title>Fixture public news lead</title>
                <link>https://example.org/fixture-story</link><source>Fixture Publisher</source>
                </item></channel></rss>""")

        with self.discovery_fixture(), patch("httpx.AsyncClient.request", new=feed):
            before = self.client.get("/api/system").json()
            for key in ("kannadiga", "human"):
                result = self.client.post("/api/pipeline/discover", json={"site_key": key}, headers=self.headers)
                self.assertEqual(result.status_code, 200, result.text)
                candidates = result.json()["candidates"]
                # Every source of the site is read; the same story from several sources is one candidate.
                self.assertEqual(result.json()["count"], 2 if key == "kannadiga" else 1)
                publishers = {c["sources"][0]["publisher"] for c in candidates}
                self.assertIn("TV9 Kannada" if key == "kannadiga" else "Fixture Publisher", publishers)
                if key == "kannadiga":
                    self.assertTrue(any("ಕರ್ನಾಟಕ" in c["topic"] for c in candidates))
                self.assertTrue(all(c["score"] < 70 for c in candidates), "no 70+ score without the AI editor")
                repeat = self.client.post("/api/pipeline/discover", json={"site_key": key}, headers=self.headers)
                self.assertEqual(repeat.json()["count"], 0)
            self.assertEqual(len(requests), 2 * (len(source_urls("kannadiga")) + len(source_urls("human"))))
            self.assertEqual(self.database.articles.count_documents({}), 0)
            self.assertEqual(self.database.topics.count_documents({}), 3)
            self.assertEqual(self.client.get("/api/system").json(), before)
            self.assertTrue(before["dry_run"])
            self.assertTrue(before["repair_lock"])
            self.assertFalse(before["scheduler_enabled"])
            self.assertEqual(self.client.post("/api/pipeline/import-posts", json={"site_key": "human"}, headers=self.headers).status_code, 409)
            probe = self.client.post("/api/secrets/test/openai-image", headers=self.headers).json()
            self.assertFalse(probe["paid_request_sent"])
            self.assertEqual(len(requests), 2 * (len(source_urls("kannadiga")) + len(source_urls("human"))))

    def test_discovery_respects_global_stop_site_pause_and_invalid_configuration(self):
        with self.discovery_fixture(), patch("httpx.AsyncClient.request", new=AsyncMock()) as remote:
            for field in ("global_paused", "killswitch"):
                self.database.system_settings.update_one({"id": "system"}, {"$set": {field: True}})
                result = self.client.post("/api/pipeline/discover", json={"site_key": "human"}, headers=self.headers)
                self.assertEqual(result.status_code, 409)
                self.database.system_settings.update_one({"id": "system"}, {"$set": {field: False}})
            self.database.sites.update_one({"key": "human"}, {"$set": {"paused": True}})
            self.assertEqual(self.client.post("/api/pipeline/discover", json={"site_key": "human"}, headers=self.headers).status_code, 409)
            self.database.sites.update_one({"key": "human"}, {"$set": {"paused": False}})
            with patch.dict(os.environ, {"DRY_RUN": "invalid-private-value"}):
                result = self.client.post("/api/pipeline/discover", json={"site_key": "human"}, headers=self.headers)
            self.assertEqual(result.status_code, 409)
            self.assertNotIn("invalid-private-value", result.text)
            remote.assert_not_awaited()

    def test_discovery_reports_feed_failure_without_inventing_topics(self):
        import httpx
        failures = [httpx.ConnectError("private-remote-value"), httpx.Response(200, request=httpx.Request("GET", "https://news.google.com"), text="invalid xml")]
        with self.discovery_fixture():
            for failure in failures:
                mock = AsyncMock(side_effect=failure) if isinstance(failure, Exception) else AsyncMock(return_value=failure)
                with patch("httpx.AsyncClient.request", new=mock):
                    result = self.client.post("/api/pipeline/discover", json={"site_key": "human"}, headers=self.headers)
                self.assertEqual(result.status_code, 502)
                self.assertIn("Could not read", result.json()["detail"])
                self.assertNotIn("private-remote-value", result.text)
                self.assertEqual(self.database.topics.count_documents({}), 0)

    def test_stop_during_discovery_prevents_saving_results(self):
        with self.discovery_fixture():
            async def stop_during_fetch(*args):
                self.database.system_settings.update_one({"id": "system"}, {"$set": {"killswitch": True}})
                return [{"topic": "Fixture lead", "link": "https://example.org/fixture", "publisher": "Fixture", "pub": ""}]
            with patch("lib.discovery._fetch_rss", side_effect=stop_during_fetch):
                result = self.client.post("/api/pipeline/discover", json={"site_key": "human"}, headers=self.headers)
            self.assertEqual(result.status_code, 409)
            self.assertEqual(self.database.topics.count_documents({}), 0)

    @contextmanager
    def wordpress_fixture(self, key="human"):
        original = self.database.sites.find_one({"key": key})
        body = {"wp_base_url": "https://" + original["domain"], "wp_username": "fixture-editor",
                "wp_app_password": "synthetic-wp-fixture-password", "author": "42"}
        try:
            result = self.client.put("/api/sites/" + key, json=body, headers=self.headers)
            self.assertEqual(result.status_code, 200)
            yield self.database.sites.find_one({"key": key})
        finally:
            # Restore only the fixture site in this class's isolated test database.
            self.database.sites.replace_one({"key": key}, original)

    def test_manual_ai_route_context_and_publication_lock(self):
        import threading
        from lib.manual_ai import block_reason, manual_request
        from lib.safety import system_block_reason
        article_id = "manual-ai-fixture-" + uuid.uuid4().hex
        self.database.articles.insert_one({"id": article_id, "site_key": "human", "stage": "selected", "dossier_meta": None})
        completed = threading.Event()
        async def action(art, site):
            self.assertTrue(manual_request.get())
            self.assertIsNone(await block_reason("human"))
            self.assertIn("DRY_RUN", await system_block_reason())
            completed.set()
            return {**art, "stage": "research_validated"}
        try:
            with self.discovery_fixture(), patch.dict(os.environ, {"MANUAL_AI_ENABLED": "true"}), patch("routers.pipeline.run_research_stage", side_effect=action):
                response = self.client.post(f"/api/articles/{article_id}/research", headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["stage"], "researching")
                self.assertEqual(response.json()["dossier_meta"]["status"], "queued")
                self.assertTrue(completed.wait(5))
                self.assertTrue(self.client.get("/api/system").json()["manual_ai_enabled"])
            self.assertFalse(manual_request.get())
        finally:
            self.database.articles.delete_one({"id": article_id})

    def test_duplicate_research_click_reuses_one_background_worker(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        article_id = "manual-lock-fixture-" + uuid.uuid4().hex
        self.database.articles.insert_one({"id": article_id, "site_key": "human", "stage": "selected", "dossier_meta": None})
        started, release = threading.Event(), threading.Event()
        async def action(art, site):
            started.set()
            await asyncio.to_thread(release.wait, 10)
            return art
        try:
            with patch("routers.pipeline.run_research_stage", side_effect=action) as research, ThreadPoolExecutor(max_workers=1) as pool:
                running = pool.submit(self.client.post, f"/api/articles/{article_id}/research", headers=self.headers)
                self.assertTrue(started.wait(5))
                self.assertEqual(running.result(timeout=5).status_code, 200)
                second = self.client.post(f"/api/articles/{article_id}/research", headers=self.headers)
                release.set()
                self.assertEqual(second.status_code, 200)
                self.assertEqual(second.json()["stage"], "researching")
                for _ in range(50):
                    if research.await_count:
                        break
                    threading.Event().wait(0.02)
                self.assertEqual(research.await_count, 1)
        finally:
            release.set()
            self.database.articles.delete_one({"id": article_id})

    @staticmethod
    def wordpress_response(method, url, **kwargs):
        import httpx
        if url.endswith("/users/me"):
            return httpx.Response(200, json={"id": 42, "username": "fixture-editor", "slug": "fixture-editor",
                                             "capabilities": {"edit_posts": True, "upload_files": True}})
        if url.endswith(("/posts", "/categories")):
            return httpx.Response(200, json=[])
        if url.endswith("/newsroom/v1/ping"):
            return httpx.Response(404, json={"message": "fixture plugin absent"})
        raise AssertionError("Unexpected WordPress endpoint")

    def test_read_only_connection_allowed_in_dry_run_for_each_site(self):
        from lib.wordpress import WordPressClient
        before = self.client.get("/api/system").json()
        for key in ("human", "kannadiga"):
            with self.subTest(site=key), self.wordpress_fixture(key) as site:
                transport = AsyncMock()
                transport.__aenter__.return_value = transport
                transport.request.side_effect = self.wordpress_response
                clients = []

                def fake_client(client):
                    clients.append(client)
                    return transport

                with patch.object(WordPressClient, "_client", autospec=True, side_effect=fake_client):
                    result = self.client.post(f"/api/sites/{key}/connection-test", headers=self.headers)
                self.assertEqual(result.status_code, 200)
                payload = result.json()
                self.assertTrue(payload["passed"])
                self.assertTrue(payload["authenticated"])
                self.assertTrue(payload["read_only"])
                self.assertFalse(payload["simulated"])
                self.assertTrue(self.client.get(f"/api/sites/{key}").json()["connected"])
                self.assertFalse(self.client.get("/api/sites/" + ("human" if key == "kannadiga" else "kannadiga")).json()["connected"])
                self.assertEqual(transport.request.await_count, 4)
                for call in transport.request.await_args_list:
                    self.assertEqual(call.args[0], "GET")
                    self.assertTrue(call.args[1].startswith(site["wp_base_url"] + "/wp-json/"))
                for client in clients:
                    self.assertTrue(client.read_only)
                    self.assertEqual(client._auth, ("fixture-editor", "synthetic-wp-fixture-password"))
                self.assertFalse(next(c for c in payload["checks"] if c["name"] == "seo_field_support")["passed"])
                self.assertIn("NOT been live-tested", payload["message"])
        self.assertEqual(self.client.get("/api/system").json(), before)

    def test_failed_connection_clears_verified_status_without_leaking_remote_body(self):
        import httpx
        from lib.wordpress import WordPressClient
        with self.wordpress_fixture():
            transport = AsyncMock()
            transport.__aenter__.return_value = transport
            transport.request.side_effect = self.wordpress_response
            with patch.object(WordPressClient, "_client", return_value=transport):
                self.assertTrue(self.client.post("/api/sites/human/connection-test", headers=self.headers).json()["passed"])
                transport.request.side_effect = None
                transport.request.return_value = httpx.Response(401, json={"message": "private-remote-fixture"})
                result = self.client.post("/api/sites/human/connection-test", headers=self.headers)
            self.assertFalse(result.json()["passed"])
            self.assertFalse(result.json()["authenticated"])
            self.assertIn("authentication rejected", result.json()["message"])
            self.assertNotIn("private-remote-fixture", result.text)
            self.assertFalse(self.client.get("/api/sites/human").json()["connected"])

    def test_credentials_changed_during_probe_cannot_report_success(self):
        from lib.wordpress import WordPressClient
        with self.wordpress_fixture():
            transport = AsyncMock()
            transport.__aenter__.return_value = transport

            def change_credentials(method, url, **kwargs):
                if url.endswith("/users/me"):
                    self.database.sites.update_one({"key": "human"}, {"$set": {
                        "credential_revision": uuid.uuid4().hex, "connected": False, "connection_test": None}})
                return self.wordpress_response(method, url, **kwargs)

            transport.request.side_effect = change_credentials
            with patch.object(WordPressClient, "_client", return_value=transport):
                result = self.client.post("/api/sites/human/connection-test", headers=self.headers)
            self.assertEqual(result.status_code, 409)
            self.assertFalse(self.client.get("/api/sites/human").json()["connected"])
            self.assertIsNone(self.database.sites.find_one({"key": "human"})["connection_test"])

    def test_read_only_client_blocks_writes_even_if_dry_run_is_off(self):
        from lib.wordpress import WordPressClient, WPError
        with self.wordpress_fixture() as site, patch.dict(os.environ, {"DRY_RUN": "false"}):
            client = WordPressClient(site, read_only=True)
            with patch.object(client, "_client") as transport:
                for method in ("POST", "PUT", "PATCH", "DELETE", "post"):
                    with self.subTest(method=method), self.assertRaisesRegex(WPError, "read-only GET"):
                        asyncio.run(client._call(method, client.api + "/posts", json={}))
                transport.assert_not_called()

    def test_regular_wordpress_client_still_blocks_writes_in_dry_run(self):
        from lib.wordpress import WordPressClient, WPError
        with self.wordpress_fixture() as site:
            client = WordPressClient(site)
            with patch.object(client, "_client") as transport:
                with self.assertRaisesRegex(WPError, "DRY_RUN"):
                    asyncio.run(client._call("POST", client.api + "/posts", json={}))
                transport.assert_not_called()

    def test_site_settings_persist_and_credentials_are_separate(self):
        body = {"timezone": "Asia/Kolkata", "publish_times": ["08:00", "12:30"], "wp_base_url": "https://kannada.example.com", "wp_username": "fixture-editor", "wp_app_password": "synthetic-wp-fixture-password"}
        result = self.client.put("/api/sites/kannadiga", json=body, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["has_wp_password"])
        self.assertNotIn(body["wp_app_password"], result.text)
        self.assertNotIn("wp_password_ciphertext", result.text)
        raw = self.database.sites.find_one({"key": "kannadiga"})
        self.assertNotIn("wp_app_password", raw)
        self.assertNotEqual(raw["wp_password_ciphertext"], body["wp_app_password"])
        self.assertFalse(self.client.get("/api/sites/human").json()["has_wp_password"])
        blank = self.client.put("/api/sites/kannadiga", json={"wp_app_password": "", "word_count_min": 650}, headers=self.headers)
        self.assertEqual(blank.status_code, 200)
        current = self.database.sites.find_one({"key": "kannadiga"})
        self.assertEqual(current["wp_password_ciphertext"], raw["wp_password_ciphertext"])
        self.assertEqual(self.client.get("/api/sites/kannadiga").json()["word_count_min"], 650)
        from lib.wp_credentials import decrypt_password
        self.assertEqual(decrypt_password(current), body["wp_app_password"].replace(" ", ""))
        self.assertNotIn(body["wp_app_password"], self.client.get("/api/audit").text)
        revoked = self.client.put("/api/sites/kannadiga", json={"revoke_wp_password": True}, headers=self.headers)
        self.assertFalse(revoked.json()["has_wp_password"])

    def test_invalid_settings_safe_errors(self):
        for body in ({"timezone": "No/SuchZone"}, {"publish_times": ["25:99"]}, {"word_count_min": 0}, {"domain": "not a domain!"}):
            self.assertEqual(self.client.put("/api/sites/human", json=body, headers=self.headers).status_code, 422)
        response = self.client.put("/api/sites/human", json={"wp_app_password": {"invalid": "private-fixture"}}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("private-fixture", response.text)

    def test_new_instance_cannot_replace_administrator(self):
        self.assertEqual(self.client.post("/api/auth/setup", json=self.login_body, headers=self.headers).status_code, 409)

    def test_logout_and_login(self):
        self.assertEqual(self.client.post("/api/auth/logout", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/api/sites").status_code, 401)
        bad = self.client.post("/api/auth/login", json={**self.login_body, "password": "wrong-fixture"}, headers=self.headers)
        self.assertEqual(bad.status_code, 401)
        good = self.client.post("/api/auth/login", json=self.login_body, headers=self.headers)
        self.assertEqual(good.status_code, 200)
        type(self).headers = {"Origin": "http://127.0.0.1:8001", "X-CSRF-Token": good.json()["csrf_token"]}


if __name__ == "__main__":
    unittest.main()
