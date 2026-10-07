"""Owner report (28 Sep 2026): a fixed 8-hour session signed the owner out while the screen was locked. A session
now stays alive while the app is used: 24 hours without use, or 7 days after sign-in, ends it."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

ENV = {"SESSION_SECRET": "test-secret", "APP_URL": "http://127.0.0.1:8001"}


def _renew(stored):
    from lib import auth
    sessions = SimpleNamespace(find_one=AsyncMock(return_value=dict(stored)), update_one=AsyncMock())
    response = Mock()
    with patch.object(auth, "db", SimpleNamespace(sessions=sessions)), patch.dict(os.environ, ENV):
        current = asyncio.run(auth.session(SimpleNamespace(cookies={auth.COOKIE: "token"}), response))
    return current, sessions.update_one, response.set_cookie


def test_a_session_in_use_is_renewed_for_a_day_and_the_cookie_with_it():
    now = datetime.now(timezone.utc)
    current, update, cookie = _renew({"_id": 1, "username": "owner", "created_at": now - timedelta(hours=10),
                                      "expires_at": now + timedelta(minutes=30)})
    expiry = update.await_args.args[1]["$set"]["expires_at"]
    assert timedelta(hours=23, minutes=59) < expiry - now <= timedelta(hours=24, seconds=5)
    assert timedelta(days=6, hours=13) < timedelta(seconds=cookie.call_args.kwargs["max_age"]) <= timedelta(days=6, hours=14)


def test_renewal_is_capped_a_week_after_sign_in_and_not_written_on_every_request():
    now = datetime.now(timezone.utc)
    _, update, _ = _renew({"_id": 1, "username": "owner", "created_at": now - timedelta(days=6, hours=23),
                           "expires_at": now + timedelta(minutes=30)})
    assert update.await_args.args[1]["$set"]["expires_at"] - now <= timedelta(hours=1, seconds=5), "7 days at most"
    _, update, cookie = _renew({"_id": 1, "username": "owner", "created_at": now - timedelta(hours=1),
                                "expires_at": now + timedelta(hours=23, minutes=58)})
    assert not update.called and not cookie.called, "renewed at most every 5 minutes"


def test_an_old_8_hour_session_is_extended_too():
    now = datetime.now(timezone.utc)
    _, update, cookie = _renew({"_id": 1, "username": "owner", "expires_at": now + timedelta(hours=7)})
    assert update.await_args.args[1]["$set"]["expires_at"] - now > timedelta(hours=23)
    assert cookie.called


def test_sign_in_creates_a_day_long_session_with_a_week_long_cookie():
    from lib import auth
    sessions = SimpleNamespace(insert_one=AsyncMock())
    response = Mock()
    with (patch.object(auth, "db", SimpleNamespace(sessions=sessions)), patch.object(auth, "audit", AsyncMock()),
          patch.dict(os.environ, ENV)):
        asyncio.run(auth.create_session("owner", response))
    stored = sessions.insert_one.await_args.args[0]
    assert stored["expires_at"] - stored["created_at"] == timedelta(hours=24)
    assert response.set_cookie.call_args.kwargs["max_age"] == 7 * 24 * 3600
