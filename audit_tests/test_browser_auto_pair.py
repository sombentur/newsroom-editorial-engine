import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

EXT = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def request(origin=EXT, host="127.0.0.1", **headers):
    return SimpleNamespace(headers={"origin": origin, **headers} if origin is not None else headers,
                           client=SimpleNamespace(host=host))


class AutoPairTests(IsolatedAsyncioTestCase):
    async def call(self, config, req):
        from lib import browser_bridge as b
        configs = SimpleNamespace(find_one=AsyncMock(return_value=config), update_one=AsyncMock())
        with patch.object(b, "db", SimpleNamespace(browser_config=configs)):
            result = await b.auto_pair(req)
        return result, configs.update_one

    async def test_local_extension_pairs_without_code(self):
        result, update = await self.call({}, request())
        self.assertTrue(result["token"])
        self.assertEqual(update.call_args.args[1]["$set"]["extension_origin"], EXT)

    async def test_web_pages_and_remote_hosts_are_refused(self):
        from fastapi import HTTPException
        for req in (request(origin="https://evil.example"), request(host="192.168.1.20")):
            with self.assertRaises(HTTPException) as caught:
                await self.call({}, req)
            self.assertEqual(caught.exception.status_code, 403)

    async def test_disconnect_in_app_blocks_auto_pair(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            await self.call({"auto_pair_blocked": True}, request())

    async def test_does_not_hijack_a_different_active_extension(self):
        from fastapi import HTTPException
        from lib.util import now_utc
        live = {"token_hash": "x", "extension_origin": "chrome-extension://other", "last_seen": now_utc()}
        with self.assertRaises(HTTPException) as caught:
            await self.call(live, request())
        self.assertEqual(caught.exception.status_code, 409)
        stale = dict(live, last_seen=now_utc() - timedelta(minutes=10))
        result, _ = await self.call(stale, request())
        self.assertTrue(result["token"])

    async def test_extension_request_without_origin_header_still_pairs(self):
        result, _ = await self.call({}, request(origin=None, **{"x-bridge-version": "0.4.0"}))
        self.assertTrue(result["token"])

    async def test_request_without_origin_or_bridge_header_is_refused(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            await self.call({}, request(origin=None))
