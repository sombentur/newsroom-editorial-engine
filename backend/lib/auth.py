"""Single-owner login with Argon2id and expiring opaque server-side sessions.

A session stays alive while the app is used: it ends after SESSION_IDLE without use, and at the latest SESSION_MAX
after sign-in (owner report, 28 Sep 2026: a fixed 8-hour session signed the owner out while the screen was locked).
"""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from lib.db import db
from lib.util import audit, now_utc

router = APIRouter(prefix="/auth")
COOKIE = "editorial_session"
hasher = PasswordHasher()
SESSION_IDLE = timedelta(hours=24)
SESSION_MAX = timedelta(days=7)
_RENEW_EVERY = timedelta(minutes=5)


def digest(token: str) -> str:
    return hmac.new(os.environ["SESSION_SECRET"].encode(), token.encode(), hashlib.sha256).hexdigest()


def allowed_origins() -> set[str]:
    return {os.environ["APP_URL"].rstrip("/")} | {s.strip().rstrip("/") for s in os.environ.get("CORS_ORIGINS", "").split(",") if s.strip()}


def require_origin(request: Request):
    if request.headers.get("origin", "").rstrip("/") not in allowed_origins():
        raise HTTPException(403, "Request origin is not allowed.")


def _set_cookie(response: Response, token: str, max_age: timedelta) -> None:
    response.set_cookie(COOKIE, token, max_age=max(0, int(max_age.total_seconds())), httponly=True,
                        secure=urlsplit(os.environ["APP_URL"]).scheme == "https", samesite="strict", path="/")


async def session(request: Request, response: Response | None = None) -> dict | None:
    """The signed-in session, renewed while the app is used (the cookie with it, when a response is given)."""
    token = request.cookies.get(COOKIE, "")
    if not token:
        return None
    now = now_utc()
    current = await db.sessions.find_one({"token_hash": digest(token), "expires_at": {"$gt": now}})
    if current:
        # Sessions from before sliding expiry lasted 8 hours from sign-in.
        signed_in = current.get("created_at") or current["expires_at"] - timedelta(hours=8)
        renewed = min(now + SESSION_IDLE, signed_in + SESSION_MAX)
        if renewed - current["expires_at"] > _RENEW_EVERY:
            await db.sessions.update_one({"_id": current["_id"]}, {"$set": {"expires_at": renewed}})
            current["expires_at"] = renewed
            if response is not None:
                _set_cookie(response, token, signed_in + SESSION_MAX - now)
    return current


async def require_admin(request: Request, response: Response) -> dict:
    current = await session(request, response)
    if not current:
        raise HTTPException(401, "Sign in to continue.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        expected = digest("csrf:" + request.cookies[COOKIE])
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), expected):
            raise HTTPException(403, "Session security check failed. Reload and try again.")
    request.state.admin = current["username"]
    return current


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: SecretStr = Field(min_length=1, max_length=256)


async def throttle(request: Request):
    stamp = now_utc()
    identity = (request.client.host if request.client else "unknown") + ":" + str(int(stamp.timestamp()) // 900)
    doc = await db.login_attempts.find_one_and_update({"id": hashlib.sha256(identity.encode()).hexdigest()}, {
        "$inc": {"attempts": 1}, "$setOnInsert": {"expires_at": stamp + timedelta(minutes=16)}
    }, upsert=True, return_document=ReturnDocument.AFTER)
    if doc["attempts"] > 10:
        raise HTTPException(429, "Too many login attempts. Try again in 15 minutes.")


async def create_session(username: str, response: Response):
    token = secrets.token_urlsafe(32)
    now = now_utc()
    await db.sessions.insert_one({"token_hash": digest(token), "username": username, "created_at": now,
                                  "expires_at": now + SESSION_IDLE})
    _set_cookie(response, token, SESSION_MAX)
    await audit("admin_login", "admin", actor=username)
    return {"authenticated": True, "username": username, "csrf_token": digest("csrf:" + token)}


@router.get("/session")
async def auth_status(request: Request, response: Response):
    current = await session(request, response)
    if current:
        return {"authenticated": True, "username": current["username"], "setup_required": False,
                "csrf_token": digest("csrf:" + request.cookies[COOKIE])}
    return {"authenticated": False, "setup_required": not bool(await db.admins.find_one({"id": "owner"}))}


@router.post("/setup")
async def setup(body: Login, request: Request, response: Response):
    require_origin(request)
    if os.environ.get("LOCAL_SETUP_ENABLED") != "true" or not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Initial administrator setup is available only on the local computer.")
    await throttle(request)
    if await db.admins.find_one({"id": "owner"}):
        raise HTTPException(409, "Administrator already configured. Sign in.")
    if len(body.password.get_secret_value()) < 12:
        raise HTTPException(422, "Choose a password of at least 12 characters.")
    username = body.username.lower()
    hashed = await run_in_threadpool(hasher.hash, body.password.get_secret_value())
    try:
        await db.admins.insert_one({"id": "owner", "username": username, "password_hash": hashed, "created_at": now_utc()})
    except DuplicateKeyError:
        raise HTTPException(409, "Administrator already configured. Sign in.") from None
    await audit("admin_created", "admin", actor=username)
    return await create_session(username, response)


@router.post("/login")
async def login(body: Login, request: Request, response: Response):
    require_origin(request)
    await throttle(request)
    admin = await db.admins.find_one({"id": "owner"})
    valid = False
    if admin:
        try:
            valid = await run_in_threadpool(hasher.verify, admin["password_hash"], body.password.get_secret_value())
        except (VerificationError, InvalidHashError):
            pass
    if not valid or admin["username"] != body.username.lower():
        await audit("admin_login_failed", "admin")
        raise HTTPException(401, "Username or password is incorrect.")
    return await create_session(admin["username"], response)


@router.post("/logout", dependencies=[Depends(require_admin)])
async def logout(request: Request, response: Response):
    await db.sessions.delete_one({"token_hash": digest(request.cookies[COOKIE])})
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    await audit("admin_logout", "admin", actor=request.state.admin)
    return {"ok": True}
