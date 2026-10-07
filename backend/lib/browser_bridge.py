# MAINTAINER NOTE (2026-09-27): BROWSER BRIDGE: Admin/session routes manage pairing and jobs; bearer-authenticated worker routes exchange bounded observations/actions/results. Browser connectivity is NOT proof a generation succeeded. Completed results require content validation.
"""Local, paired Chrome worker. No cookies, passwords or arbitrary commands cross the bridge."""
import asyncio
import hashlib
import re
import secrets
import time
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from lib.auth import require_admin
from lib.db import db
from lib.util import now_utc, new_id

import logging
logger = logging.getLogger(__name__)
PLANNER_FAILURE_LIMIT = 5
# Optional local diagnostics: only while .local/debug-screenshots exists, the latest work-tab screenshot per job
# kind is kept in .local/diagnostics/ on this computer (overwritten each time; nothing is sent anywhere).
_LOCAL = __import__("pathlib").Path(__file__).resolve().parents[2] / ".local"


def _debug_screenshot(kind: str, screenshot: str | None) -> None:
    if not screenshot or not (_LOCAL / "debug-screenshots").exists():
        return
    try:
        import base64
        (_LOCAL / "diagnostics").mkdir(exist_ok=True)
        (_LOCAL / "diagnostics" / f"{kind}.jpg").write_bytes(base64.b64decode(screenshot))
    except Exception:  # diagnostics must never affect a job
        logger.exception("debug screenshot not saved")


def version_at_least(version, minimum):
    """Compare extension versions like "0.4.1" numerically (None/garbage counts as too old)."""
    try:
        return tuple(int(part) for part in str(version).split(".")) >= tuple(int(p) for p in minimum.split("."))
    except ValueError:
        return False

admin = APIRouter(prefix="/browser", dependencies=[Depends(require_admin)])
worker = APIRouter(prefix="/browser-worker")
# Current job preview only: bounded memory, never stored in MongoDB or on disk.
_page_previews = {}
_PREVIEW_TTL = 300


def _remember_page(job_id, body):
    stamp = time.monotonic()
    for key, (saved, _) in list(_page_previews.items()):
        if stamp - saved >= _PREVIEW_TTL:
            _page_previews.pop(key, None)
    if len(_page_previews) >= 4 and job_id not in _page_previews:
        _page_previews.pop(min(_page_previews, key=lambda key: _page_previews[key][0]))
    _page_previews[job_id] = (stamp, body.model_dump())
    def expire():
        if _page_previews.get(job_id, (None,))[0] == stamp:
            _page_previews.pop(job_id, None)
    asyncio.get_running_loop().call_later(_PREVIEW_TTL, expire)


@admin.get("/jobs/{job_id}/page")
async def job_page(job_id: str):
    import html
    import re
    from fastapi.responses import HTMLResponse
    saved, page = _page_previews.get(job_id, (0, None))
    if not page or time.monotonic() - saved >= _PREVIEW_TTL:
        _page_previews.pop(job_id, None)
        raise HTTPException(404, "No recent page view. Start a browser test to see its next observation.")
    esc = html.escape
    screenshot = page.get("screenshot") or ""
    picture = (f'<img alt="Extension job page" src="data:image/jpeg;base64,{screenshot}">' if re.fullmatch(r'[A-Za-z0-9+/=]+', screenshot) else '')
    controls = '\n'.join(f'{e["id"]}: {e["role"]} {e["name"]}' for e in page['elements'])
    result = '<!doctype html><html><head><meta charset="utf-8"><title>Browser job page</title><meta http-equiv="refresh" content="5"><style>body{background:#101820;color:#ecf3fa;font:16px sans-serif;margin:20px}img{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#7dd3fc}</style></head><body>'
    result += '<h1>Browser job page</h1><p>Latest extension observation. Refreshes every 5 seconds; expires after 5 minutes. Kept only in memory.</p>'
    result += f'<p>{esc(page["url"])} · {int(time.monotonic()-saved)} seconds ago</p>{picture}<h2>Visible page text</h2><pre>{esc(page["text"])}</pre><h2>Observed controls</h2><pre>{esc(controls)}</pre></body></html>'
    return HTMLResponse(result, headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'", "Referrer-Policy": "no-referrer"})


@admin.get("/download")
async def download():
    import io, zipfile
    from pathlib import Path
    from fastapi.responses import Response
    root = Path(__file__).resolve().parents[2] / "chrome-extension"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest.json", "worker.js", "content.js", "policy.mjs", "workspace.mjs", "research-export.mjs", "observer.mjs", "popup.html", "popup.css", "popup.js", "README.md"):
            archive.write(root / name, name)
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="newsroom-browser-bridge.zip"'})


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Settings(BaseModel):
    research: bool = False
    image: bool = False


@admin.get("/status")
async def status():
    from lib.browser_controller import controller_settings
    from lib.secrets import get_secret
    config = await db.browser_config.find_one({"id": "browser"}) or {}
    jobs = await db.browser_jobs.find({}, {"_id": 0, "prompt": 0, "result": 0}).sort("created_at", -1).limit(20).to_list(20)
    return {"research": config.get("research", False), "image": config.get("image", False), "version": config.get("version"),
            "paired": bool(config.get("token_hash")), "last_seen": config.get("last_seen"), "jobs": jobs,
            "workspace": config.get("workspace", {}), "workspace_seen": config.get("workspace_seen"),
            "controller_model": controller_settings()[1], "controller_configured": bool(get_secret(controller_settings()[0] + "_api_key")),
            "auto_pair_blocked": bool(config.get("auto_pair_blocked")), "latest_version": latest_extension_version(),
            "gemini_account": config.get("gemini_account"), "research_url": research_url(config)}


class GeminiAccount(BaseModel):
    address: str = Field(default="", max_length=500)  # the Gemini address of the chosen account; empty: first account


@admin.post("/gemini-account")
async def set_gemini_account(body: GeminiAccount):
    """The Google account Gemini Deep Research runs in (owner request, 28 Sep 2026): its /u/N/ part, from the address
    Gemini shows in that account (no e-mail address is stored)."""
    address = body.address.strip()
    account = None
    if address:
        match = GEMINI_ADDRESS.match(address)
        if not match:
            raise HTTPException(422, "Paste the Gemini address shown for that account, e.g. https://gemini.google.com/u/1/app.")
        account = match.group(1)
    await db.browser_config.update_one({"id": "browser"}, {"$set": {"gemini_account": account}}, upsert=True)
    from lib.util import audit
    await audit("gemini_account_changed", "system", "browser", detail={"account": account or "first signed-in account"})
    return {"gemini_account": account, "research_url": research_url({"gemini_account": account})}


@admin.post("/test")
async def test_connection():
    config = await db.browser_config.find_one({"id": "browser"}) or {}
    if not config.get("token_hash") or not version_at_least(config.get("version"), "0.2.0"):
        raise HTTPException(409, "Reload and connect extension 0.2.2 before testing.")
    system = await db.system_settings.find_one({"id": "system"}) or {}
    if system.get("global_paused", True) or system.get("killswitch"):
        raise HTTPException(409, "Resume the app before testing.")
    if await db.browser_jobs.find_one({"article_id": "browser-connection-test", "status": {"$in": ["queued", "running", "attention"]}}):
        raise HTTPException(409, "A connection test already exists. Continue or stop it first.")
    ids = []
    for kind, prompt in [
        ("image", "Generate one cinematic documentary-style editorial background, 1536 by 864 pixels, 16:9. Bengaluru street after rain at blue hour, a generic commuter in the foreground, warm light and deep perspective. No text, logos, or identifiable public figures. Keep top 30 percent quiet for later typesetting."),
        ("research", "Use Deep Research to write a short report in clear Kannada about Karnataka's geography and major rivers. Include clickable official government or educational source URLs and preserve uncertainty. This is a connection test, not a publication request.")]:
        job = {"id": new_id(), "article_id": "browser-connection-test", "kind": kind, "prompt": prompt,
               "status": "queued", "message": "Connection test; no publication", "created_at": now_utc()}
        if kind == "image":  # ChatGPT's thinking level is set for every job (owner rule, 28 Sep 2026)
            from lib.workflow import BASE_THINKING_LEVEL, IMAGE_WAIT_LIMITS
            job.update(effort=BASE_THINKING_LEVEL, wait_limit_seconds=IMAGE_WAIT_LIMITS[BASE_THINKING_LEVEL])
        await db.browser_jobs.insert_one(job)
        ids.append(job["id"])
    return {"jobs": ids}


@admin.get("/jobs/{job_id}/result")
async def test_result(job_id: str):
    from fastapi.responses import Response
    import base64
    job = await db.browser_jobs.find_one({"id": job_id, "status": "completed"})
    if not job or not job.get("result"):
        raise HTTPException(404, "Result unavailable; check the article for consumed results.")
    if job["kind"] == "image":
        return Response(base64.b64decode(job["result"]), media_type="image/webp")
    return Response(job["result"], media_type="text/plain; charset=utf-8")


@admin.put("/settings")
async def settings(body: Settings):
    config = await db.browser_config.find_one({"id": "browser"}) or {}
    if (body.research or body.image) and not config.get("token_hash"):
        raise HTTPException(409, "Install and pair Chrome before enabling browser jobs.")
    await db.browser_config.update_one({"id": "browser"}, {"$set": body.model_dump()}, upsert=True)
    return {"ok": True}


@admin.post("/pair-code")
async def pair_code():
    code = secrets.token_urlsafe(24)
    await db.browser_config.update_one({"id": "browser"}, {"$set": {
        "pair_hash": digest(code), "pair_expires": now_utc() + timedelta(minutes=10)}}, upsert=True)
    return {"code": code}


class RecopyBody(BaseModel):
    url: str | None = Field(default=None, max_length=500)  # the Gemini link of the finished report (owner-pasted)


GEMINI_CONVERSATION = re.compile(r"^https://gemini\.google\.com/((?:u/\d{1,2}/)?)app/([A-Za-z0-9_-]{6,64})(?:[/?#].*)?$")
GEMINI_CONVERSATION_URL = r"^https://gemini\.google\.com/(u/\d{1,2}/)?app/[^/?#]+"
GEMINI_ADDRESS = re.compile(r"^https://gemini\.google\.com/(?:(u/\d{1,2})/)?app(?:[/?#].*)?$")


def research_url(config: dict | None) -> str:
    """Where the Gemini work tab opens a new chat: the chosen account's address (Setup Wizard), else the first account."""
    account = (config or {}).get("gemini_account")
    return f"https://gemini.google.com/{account}/app" if account else "https://gemini.google.com/app"


@admin.post("/articles/{art_id}/recopy")
async def recopy_report(art_id: str, body: RecopyBody | None = None):
    """Copy a finished Deep Research report again (no new research): from the Gemini link the owner pasted, else from
    the article's last recorded conversation. An open tab showing it is used as it is."""
    art = await db.articles.find_one({"id": art_id})
    if not art:
        raise HTTPException(404, "Article not found.")
    if art.get("stage") in {"scheduled", "published", "verified"} or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked.")
    meta = dict(art.get("dossier_meta") or {})
    pasted = bool(body and body.url and body.url.strip())
    if not pasted and (not meta.get("report_mode") or not meta.get("prompt")):
        raise HTTPException(409, "Only Deep Research article reports can be copied again.")
    if pasted:
        match = GEMINI_CONVERSATION.match(body.url.strip())
        if not match:
            raise HTTPException(422, "Paste the link of the Gemini conversation that shows the finished report "
                                     "(it starts with https://gemini.google.com/app/ or /u/1/app/).")
        previous = {"conversation_url": "https://gemini.google.com/" + match.group(1) + "app/" + match.group(2)}
    else:
        previous = await db.browser_jobs.find_one(
            {"article_id": art_id, "kind": "research", "conversation_url": {"$regex": GEMINI_CONVERSATION_URL}},
            sort=[("created_at", -1)])
    if not previous:
        raise HTTPException(409, "This report's Gemini conversation was not recorded. Paste its Gemini link in the box, "
                                 "or use Research again.")
    # Fetched at once, whatever holds the queue, through the Manual Workbench import (owner report, 29 Sep 2026: a
    # copy queued behind other articles threw away a report already imported); the topic then goes next.
    from lib import manual_research
    try:
        record = await manual_research.import_again(art_id, previous["conversation_url"])
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"job": None, "waiting_for": None, "manual_research": record}


async def _conversation_urls(art_id: str) -> list[str]:
    """The Gemini conversations this article's research jobs ran in, newest first."""
    jobs = await db.browser_jobs.find({"article_id": art_id, "kind": "research",
                                       "conversation_url": {"$regex": GEMINI_CONVERSATION_URL}},
                                      {"conversation_url": 1}).sort("created_at", -1).to_list(20)
    return list(dict.fromkeys(j["conversation_url"] for j in jobs))


async def create_recopy_job(art_id: str, prompt: str, capture_url: str, tab_id=None) -> dict:
    """A capture-only research job: copy the finished report from its saved Gemini conversation (no new research)."""
    if tab_id is None:
        config = await db.browser_config.find_one({"id": "browser"}) or {}
        tab_id = ((config.get("workspace") or {}).get("research") or {}).get("tab_id")
    if not tab_id:
        raise ValueError("Connect the Gemini work tab first.")
    # Every conversation this article's research ran in, newest first: the extension copies from an open Gemini tab
    # showing one of them with a finished report (owner report, 28 Sep 2026), before opening capture_url.
    candidates = list(dict.fromkeys([capture_url, *await _conversation_urls(art_id)]))
    # Every other research job of this article gives way, also one running or waiting for attention: it would keep
    # the Gemini lane busy, and the workflow would wait on it instead of on the copy (live case, 28 Sep 2026).
    await db.browser_jobs.update_many({"article_id": art_id, "kind": "research",
                                       "status": {"$in": ["queued", "running", "attention", "completed"]}},
                                      {"$set": {"status": "cancelled", "message": "Replaced by a report re-copy"}})
    job = {"id": new_id(), "article_id": art_id, "kind": "research", "prompt": prompt, "status": "queued",
           "message": "Copying the finished report again from its Gemini conversation", "capture_existing": True,
           "capture_tab_id": tab_id, "capture_url": capture_url, "capture_candidates": candidates[:10],
           "created_at": now_utc()}
    await db.browser_jobs.insert_one(dict(job))
    return job


@admin.post("/articles/{art_id}/research-again")
async def research_again(art_id: str):
    """Run Deep Research again for an article (e.g. its earlier report was copied without formatting)."""
    art = await db.articles.find_one({"id": art_id})
    if not art:
        raise HTTPException(404, "Article not found.")
    if art.get("stage") in {"scheduled", "published", "verified"} or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked.")
    meta = art.get("dossier_meta") or {}
    if not meta.get("report_mode") or not meta.get("prompt"):
        raise HTTPException(409, "Only Deep Research articles can be researched again here.")
    await db.browser_jobs.update_many({"article_id": art_id, "kind": "research", "status": {"$in": ["queued", "running", "attention", "completed"]}},
                                      {"$set": {"status": "cancelled", "message": "Replaced by a new Deep Research run"}})
    fresh = {"report_mode": True, "prompt": meta["prompt"], "provider": "pending", "status": "queued", "started": now_utc()}
    await db.articles.update_one({"id": art_id}, {"$set": {
        "dossier_meta": fresh, "dossier": None, "validation": None, "research_approval": None, "stage": "selected",
        "held_reason": None, "ai_failure": None, "updated_at": now_utc()},
        "$push": {"history": {"stage": "selected", "at": now_utc(), "actor": "editor",
                              "note": "Deep Research will run again for this article (its turn comes in the sequence)"}}})
    return {"ok": True}


@admin.post("/auto-pair/allow")
async def allow_auto_pair():
    """Let the extension on this computer connect itself again after a Disconnect."""
    await db.browser_config.update_one({"id": "browser"}, {"$unset": {"auto_pair_blocked": ""}}, upsert=True)
    return {"ok": True}


@admin.post("/disconnect")
async def disconnect():
    await db.browser_config.update_one({"id": "browser"}, {"$unset": {"token_hash": "", "pair_hash": ""},
                                       "$set": {"research": False, "image": False, "auto_pair_blocked": True}})
    await db.browser_jobs.update_many({"status": {"$in": ["queued", "running", "attention"]}}, {"$set": {"status": "cancelled", "message": "Browser disconnected"}})
    return {"ok": True}


@admin.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    await db.browser_jobs.update_one({"id": job_id, "status": {"$in": ["queued", "running", "attention"]}}, {"$set": {"status": "cancelled", "message": "Stopped by editor"}})
    return {"ok": True}


class Pair(BaseModel):
    code: str = Field(min_length=20, max_length=100)


@worker.post("/pair")
async def pair(body: Pair):
    token = secrets.token_urlsafe(40)
    row = await db.browser_config.find_one_and_update(
        {"id": "browser", "pair_hash": digest(body.code), "pair_expires": {"$gt": now_utc()}},
        {"$set": {"token_hash": digest(token), "last_seen": now_utc()},
         "$unset": {"pair_hash": "", "pair_expires": "", "auto_pair_blocked": ""}})
    if not row:
        raise HTTPException(401, "Pairing code expired or already used.")
    return {"token": token}


@worker.post("/auto-pair")
async def auto_pair(request: Request):
    """Pair the Chrome extension on this computer without a typed code.

    Loopback only. Accepted from a chrome-extension:// origin, or with no Origin at all but the bridge's
    version header (a web page's cross-site request always carries its own Origin and cannot add that
    header without a CORS preflight this server refuses). A connected extension is never replaced by a
    different one, and Disconnect in the app blocks this until the owner allows it again.
    """
    origin = request.headers.get("origin", "")
    host = request.client.host if request.client else ""
    from_extension = origin.startswith("chrome-extension://") or (not origin and request.headers.get("x-bridge-version"))
    if host not in {"127.0.0.1", "::1", "testclient"} or not from_extension:
        raise HTTPException(403, "Automatic pairing is only available to the Chrome extension on this computer.")
    config = await db.browser_config.find_one({"id": "browser"}) or {}
    if config.get("auto_pair_blocked"):
        raise HTTPException(403, "Chrome was disconnected in the app. Pair again from the Browser Extension page.")
    seen = config.get("last_seen")
    other_active = (config.get("token_hash") and config.get("extension_origin") not in (None, origin)
                    and seen is not None and now_utc() - seen < EXTENSION_STALE)
    if other_active:
        raise HTTPException(409, "A different Chrome extension is connected. Disconnect it in the app first.")
    token = secrets.token_urlsafe(40)
    await db.browser_config.update_one({"id": "browser"}, {
        "$set": {"token_hash": digest(token), "extension_origin": origin, "last_seen": now_utc()},
        "$unset": {"pair_hash": "", "pair_expires": ""}}, upsert=True)
    return {"token": token}


async def authorized(request: Request):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token or len(token) > 200:
        raise HTTPException(401, "Pair Chrome with the app first.")
    config = await db.browser_config.find_one({"id": "browser", "token_hash": digest(token)})
    if not config:
        raise HTTPException(401, "Browser connection revoked.")
    await db.browser_config.update_one({"id": "browser"}, {"$set": {"last_seen": now_utc(), "version": request.headers.get("x-bridge-version", "0.1")[:20]}})


class WorkspaceTab(BaseModel):
    tab_id: int = Field(ge=0)
    attached: bool = False
    ready: bool = False
    message: str = Field(max_length=200)


class WorkspaceState(BaseModel):
    tabs: dict[str, WorkspaceTab]


@worker.post('/workspace', dependencies=[Depends(authorized)])
async def workspace_state(body: WorkspaceState):
    if set(body.tabs) - {'research', 'image'}:
        raise HTTPException(422, 'Only Gemini and ChatGPT work tabs are supported.')
    await db.browser_config.update_one({'id':'browser'}, {'$set':{
        'workspace':{key:value.model_dump() for key,value in body.tabs.items()}, 'workspace_seen':now_utc()}})
    config = await db.browser_config.find_one({'id':'browser'}) or {}
    # latest_version lets an extension loaded from a synced folder reload itself after an update.
    return {'command':config.get('workspace_command'), 'latest_version': latest_extension_version(),
            'research_url': research_url(config)}


def latest_extension_version():
    import json
    from pathlib import Path
    try:
        manifest = Path(__file__).resolve().parents[2] / "chrome-extension" / "manifest.json"
        return json.loads(manifest.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


class WorkspaceCommand(BaseModel):
    action: Literal['connect','disconnect']


@admin.post('/workspace')
async def workspace_command(body: WorkspaceCommand):
    config = await db.browser_config.find_one({'id':'browser'}) or {}
    if not version_at_least(config.get('version'), '0.3.0'):
        raise HTTPException(409, 'Install and reload extension 0.3.0 to connect both work tabs.')
    if body.action == 'disconnect':
        await db.browser_jobs.update_many({'status':{'$in':['running','queued','attention']}},
            {'$set':{'status':'cancelled','message':'Browser workspace released by editor'}})
    await db.browser_config.update_one({'id':'browser'}, {'$set':{
        'workspace_command':{'id':new_id(),'action':body.action}}})
    return {'ok':True}


class WorkspaceAck(BaseModel):
    id: str = Field(max_length=80)


@worker.post('/workspace/ack', dependencies=[Depends(authorized)])
async def workspace_ack(body: WorkspaceAck):
    await db.browser_config.update_one({'id':'browser','workspace_command.id':body.id},
        {'$unset':{'workspace_command':''}})
    return {'ok':True}


@worker.post("/claim", dependencies=[Depends(authorized)])
async def claim(request: Request):
    if not version_at_least(request.headers.get("x-bridge-version"), "0.2.0"):
        raise HTTPException(409, "Reload Newsroom Browser Bridge version 0.2.2 to use the adaptive controller.")
    system = await db.system_settings.find_one({"id": "system"}) or {}
    if system.get("global_paused", True) or system.get("killswitch"):
        return {"job": None}
    # One article at a time: the work tabs take jobs only for the article holding the turn, plus Gemini research
    # for the next article once the current one is on its thumbnail (owner rule, 27 Sep 2026).
    from lib.turn import current_article, next_article
    current = await current_article()
    eligible = {"status": "queued", "article_id": {"$in": ["browser-connection-test"] + ([current["id"]] if current else [])},
                "$or": [{"id": {"$in": list(_awaiting)}},
                                            {"article_id": "browser-connection-test"}, {"capture_existing": True},
                                            {"resume_on_completion": True}]}
    if ahead := await next_article():
        articles = {"$or": [{"article_id": eligible.pop("article_id")}, {"article_id": ahead["id"], "kind": "research"}]}
        eligible = {"status": "queued", "$and": [articles, {"$or": eligible.pop("$or")}]}
    try:
        lane = (await request.json() or {}).get("lane")
    except ValueError:
        lane = None
    if lane in LANE_KINDS:
        eligible["kind"] = {"$in": LANE_KINDS[lane]}
    if not version_at_least(request.headers.get("x-bridge-version"), "0.3.1"):
        eligible["capture_existing"] = {"$ne": True}
    if version_at_least(request.headers.get("x-bridge-version"), "0.4.28"):
        # Manual Editorial Workbench imports only copy a finished report: they run whichever article holds the turn.
        manual = {"status": "queued", "manual_import": True}
        if lane in LANE_KINDS:
            manual["kind"] = {"$in": LANE_KINDS[lane]}
        eligible = {"$or": [eligible, manual]}
    job = await db.browser_jobs.find_one_and_update(eligible,
        {"$set": {"status": "running", "message": "Opening browser tab", "updated_at": now_utc()}},
        sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
    if job:
        job.pop("_id", None)
    return {"job": job}


@worker.get("/jobs/{job_id}", dependencies=[Depends(authorized)])
async def job_status(job_id: str):
    job = await db.browser_jobs.find_one({"id": job_id}, {"_id": 0, "result": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    system = await db.system_settings.find_one({"id": "system"}) or {}
    art = await db.articles.find_one({"id": job["article_id"]}) or {}
    site = await db.sites.find_one({"key": art.get("site_key")}) or {}
    if system.get("global_paused", True) or system.get("killswitch") or site.get("paused") or art.get("held_reason") == "Stopped by editor.":
        job["status"] = "cancelled"
        await db.browser_jobs.update_one({"id": job_id}, {"$set": {"status": "cancelled"}})
    elif reason := _stale_attention_reason(job):
        job.update(status="cancelled", message=reason)
        await db.browser_jobs.update_one({"id": job_id, "status": "attention"}, {"$set": {"status": "cancelled", "message": reason}})
    return job


def _stale_attention_reason(job):
    """Release an attention job that blocks its work tab when doing so cannot lose or duplicate work."""
    if job.get("status") != "attention":
        return None
    idle = now_utc() - (job.get("updated_at") or job.get("created_at") or now_utc())
    sent = (job.get("last_observation") or {}).get("send_attempted") or any(
        a.get("action") == "submit" for a in job.get("activity") or [])
    if job.get("article_id") == "browser-connection-test" and idle > timedelta(minutes=10):
        return "Connection test released after waiting for attention; no article was affected."
    if not sent and not job.get("capture_existing") and idle > timedelta(minutes=15):
        return "Released after waiting for attention; nothing had been sent. Retry runs it again."
    return None


class Progress(BaseModel):
    message: str = Field(max_length=300)
    attention: bool = False
    saved_text: str | None = Field(default=None, max_length=20000)  # leftover work-tab text, saved before clearing
    result: str | None = Field(default=None, max_length=12000000)


from lib.browser_controller import Decision, Observation, PlannerUnavailable, plan
# While a job is waiting, the AI planner is consulted at most this often (free Gemini keys allow ~20 calls/day/model).
PLANNER_INTERVAL_AFTER_SEND = 600
PLANNER_INTERVAL_BEFORE_SEND = 60
_decision_locks: dict[str, asyncio.Lock] = {}


@worker.post("/jobs/{job_id}/observe", dependencies=[Depends(authorized)])
async def observe(job_id: str, body: Observation):
    job = await job_status(job_id)
    if job["status"] != "running":
        raise HTTPException(409, "Job is not running. Resolve the attention message and use Continue.")
    lock = _decision_locks.setdefault(job_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "A browser decision is already in progress.")
    async with lock:
        from urllib.parse import urlsplit
        expected = "gemini.google.com" if job["kind"] == "research" else "chatgpt.com"
        if urlsplit(body.url).scheme != "https" or urlsplit(body.url).netloc != expected:
            raise HTTPException(422, "Observation is outside this job's website.")
        _remember_page(job_id, body)
        _debug_screenshot(job["kind"], body.screenshot)
        # A recorded Send is never forgotten, even when the extension restarted and lost its own flag.
        if not body.submitted and any(a.get("action") == "submit" for a in job.get("activity") or []):
            body.submitted = True
        # Progress signal for long Deep Research runs: the visible status text changes while Gemini works.
        tail_digest = digest(" ".join((body.text or "")[-400:].split()))
        if tail_digest != job.get("tail_digest"):
            await db.browser_jobs.update_one({"id": job_id}, {"$set": {"tail_digest": tail_digest, "progress_at": now_utc()}})
            job["progress_at"] = now_utc()
        # Small, current-page diagnostics; retain neither screenshots nor page text.
        await db.browser_jobs.update_one({"id": job_id}, {"$set": {"last_observation": {
            "at": now_utc(), "send_attempted": body.submitted, "page_visible": body.visible, "dom_hint": body.hint,
            "prompt_in_composer": body.prompt_verified,
            "composer_visible": any(e.editable for e in body.elements),
            "composer_empty": any(e.editable for e in body.elements) and all(e.empty for e in body.elements if e.editable),
            # First characters of what the composer holds (typed prompt, restored draft or a tool chip), for diagnosis.
            "composer_text": next((" ".join(e.draft.split())[:120] for e in body.elements if e.editable and not e.empty and e.draft), None),
            "composer_chips": next((" ".join(e.chips.split())[:120] for e in body.elements if e.editable and e.chips), None),
            "report_count": sum(e.role == "report" for e in body.elements),
            # Control labels only (no page text, reports or screenshots) to diagnose stuck page states.
            "controls": [f"{e.role}{' (disabled)' if e.disabled else ''}: {' '.join(e.name.split())[:60]}" for e in body.elements
                         if e.role not in {"report", "image", "textbox"}][:80],
            "image_count": sum(e.role == "image" for e in body.elements),
            # Last lines of visible text (status such as "Researching 40 websites" or an error), for diagnosis.
            "text_tail": " ".join((body.text or "")[-400:].split()),
        }}})
        if job.get("action_count", 0) >= 60:
            await progress(job_id, Progress(message="Browser action limit reached. Review this job before continuing.", attention=True))
            return {"action": "attention", "target": 0, "reason": "Browser action limit reached"}
        await db.browser_jobs.update_one({"id": job_id}, {"$inc": {"decision_count": 1}})
        try:
            from lib.browser_startup import startup_guard
            startup_patch, decision = startup_guard(job, body, now_utc())
            if startup_patch:
                await db.browser_jobs.update_one({"id": job_id}, {"$set": startup_patch})
            if decision is None:
                from lib.browser_actions import (image_failed, image_failure_mark, initial_action, progress_action,
                                                 research_timed_out)
                from lib.browser_controller import validate_decision
                if mark := image_failure_mark(job, body, now_utc()):
                    await db.browser_jobs.update_one({"id": job_id}, {"$set": mark})
                    job.update(mark)
                if timeout_reason := research_timed_out(job, body) or image_failed(job, body):
                    await db.browser_jobs.update_one({"id": job_id, "status": "running"}, {"$set": {
                        "status": "cancelled", "message": timeout_reason, "conversation_url": body.url[:500], "updated_at": now_utc()}})
                    return {"action": "wait", "target": 0, "reason": timeout_reason, "snapshot": body.snapshot}
                known = initial_action(job, body) or progress_action(job, body)
                sent = body.submitted or any(a.get("action") == "submit" for a in job.get("activity", []))
                interval = PLANNER_INTERVAL_AFTER_SEND if sent else PLANNER_INTERVAL_BEFORE_SEND
                last_plan = job.get("last_plan_at")
                if known:
                    decision = validate_decision(job, body, known)
                elif (last_plan and job.get("last_plan_action") == "wait"
                      and (now_utc() - last_plan).total_seconds() < interval):
                    decision = Decision(action="wait", target=0, reason="Still working; checking again shortly.")
                else:
                    decision = await plan(job, body)
                    await db.browser_jobs.update_one({"id": job_id}, {"$set": {
                        "last_plan_at": now_utc(), "last_plan_action": decision.action}})
            if job.get("planner_failures"):
                await db.browser_jobs.update_one({"id": job_id}, {"$unset": {"planner_failures": ""}})
        except PlannerUnavailable as exc:
            # A planner hiccup must not stop the job: observe again and retry. Only repeated
            # failures ask the owner, with the real cause.
            failures = job.get("planner_failures", 0) + 1
            note = f"Page planner busy ({str(exc)[:80]}); retrying ({failures}/{PLANNER_FAILURE_LIMIT - 1})."
            await db.browser_jobs.update_one({"id": job_id}, {
                "$set": {"planner_failures": failures, "message": note, "updated_at": now_utc()},
                "$push": {"activity": {"$each": [{"action": "wait", "note": note, "at": now_utc()}], "$slice": -60}}})
            logger.warning("browser planner unavailable for job %s (%d in a row): %s", job_id, failures, exc)
            if failures >= PLANNER_FAILURE_LIMIT:
                reason = f"The page planner failed {failures} times in a row ({str(exc)[:150]}). Check the Gemini API key/quota, then Continue."
                await progress(job_id, Progress(message=reason, attention=True))
                return {"action": "attention", "target": 0, "reason": reason}
            return {"action": "wait", "target": 0, "reason": f"Page planner busy; retrying ({failures}/{PLANNER_FAILURE_LIMIT - 1}).",
                    "snapshot": body.snapshot}
        except Exception as exc:
            logger.warning("browser controller error for job %s: %s %s", job_id, type(exc).__name__, str(exc)[:200])
            from lib.ai import AIError
            reason = str(exc)[:250] if isinstance(exc, (ValueError, AIError)) else "Browser controller could not respond. Check the writing AI settings and Continue."
            await progress(job_id, Progress(message=reason, attention=True))
            return {"action": "attention", "target": 0, "reason": reason}
        # Stop/pause may have happened while the model was thinking.
        if (await job_status(job_id))["status"] != "running":
            raise HTTPException(409, "Job stopped while the controller was thinking.")
        if decision.action not in {"wait", "attention"}:
            await db.browser_jobs.update_one({"id": job_id}, {"$inc": {"action_count": 1}})
        target = next((e for e in body.elements if e.id == decision.target), None)
        event = {"action": decision.action, "note": decision.reason, "at": now_utc()}
        if target and decision.action in {"click", "submit"}:
            event["control"] = {"role": target.role, "name": target.name[:100]}
        last_event = (job.get("activity") or [{}])[-1]
        repeated_wait = (decision.action == "wait" and last_event.get("action") == "wait"
                         and last_event.get("note") == decision.reason)
        # conversation_url lets "Copy report again" reopen exactly this Gemini/ChatGPT conversation.
        update = {"$set": {"message": decision.reason, "updated_at": now_utc(), "conversation_url": body.url[:500]}}
        if decision.action == "submit" and not job.get("submitted_at"):
            update["$set"]["submitted_at"] = now_utc()
        if not repeated_wait:
            update["$push"] = {"activity": {"$each": [event], "$slice": -60}}
        await db.browser_jobs.update_one({"id": job_id}, update)
        if decision.action == "attention":
            await progress(job_id, Progress(message=decision.reason, attention=True))
        return {**decision.model_dump(), "snapshot": body.snapshot}


@worker.post("/jobs/{job_id}/resume", dependencies=[Depends(authorized)])
async def resume_job(job_id: str):
    job = await job_status(job_id)
    if job["status"] != "attention":
        raise HTTPException(409, "Only a job needing attention can be resumed.")
    await db.browser_jobs.update_one({"id": job_id, "status": "attention"}, {"$set": {"status": "running", "message": "Continuing after owner review", "decision_count": 0, "action_count": 0}})
    return {"ok": True}


@worker.post("/jobs/{job_id}/cancel", dependencies=[Depends(authorized)])
async def worker_cancel(job_id: str, body: dict | None = None):
    reason = str((body or {}).get("reason") or "")[:300]
    if not reason:
        return await cancel(job_id)
    await db.browser_jobs.update_one({"id": job_id, "status": {"$in": ["queued", "running", "attention"]}},
                                     {"$set": {"status": "cancelled", "message": reason}})
    return {"ok": True}


@worker.post("/jobs/{job_id}", dependencies=[Depends(authorized)])
async def progress(job_id: str, body: Progress):
    job = await job_status(job_id)
    if job["status"] not in {"running", "attention"}:
        raise HTTPException(409, "Job is no longer accepting results.")
    patch = {"message": body.message, "updated_at": now_utc(), "status": "attention" if body.attention else "running"}
    if body.result is not None:
        if job["kind"] == "research" and len(body.result.strip()) < 500:
            raise HTTPException(422, "Research report is too short.")
        if job["kind"] == "seo" and "seo_title" not in body.result:
            raise HTTPException(422, "ChatGPT's answer does not contain the SEO JSON yet.")
        if job["kind"] == "image":
            import base64
            try:
                body.result = base64.b64encode(keep_generated_image(base64.b64decode(body.result, validate=True))).decode()
            except Exception:
                raise HTTPException(422, "Use a valid landscape image at least 1024 pixels wide.") from None
        patch.update(status="completed", result=body.result)
    updated = await db.browser_jobs.update_one({"id": job_id, "status": {"$in": ["running", "attention"]}}, {"$set": patch})
    if not updated.matched_count:
        raise HTTPException(409, "Job stopped before the result could be saved.")
    if body.saved_text:
        # Text found in the work tab (not typed by the app) is kept in full before the box is cleared.
        art = await db.articles.find_one({"id": job["article_id"]}, {"stage": 1}) or {}
        await db.articles.update_one({"id": job["article_id"]}, {"$push": {"history": {
            "stage": art.get("stage", "held_review"), "at": now_utc(), "actor": "system",
            "note": "Text found in the " + ("Gemini" if job["kind"] == "research" else "ChatGPT")
                    + " work tab was saved here and cleared so the job could continue: " + body.saved_text}}})
    if body.result is not None:
        # Release only our own wait/attention hold; editorial holds remain intact.
        await db.articles.update_one({"id": job["article_id"], "stage": "held_review",
            "held_reason": {"$regex": r"^(research|featured image|SEO assets) failed \(browser\):"}},
            {"$set": {"stage": {"research": "selected", "seo": "research_validated"}.get(job["kind"], "article_validated"),
                      "held_reason": None, "updated_at": now_utc()}})
    return {"ok": True}


def keep_generated_image(raw: bytes) -> bytes:
    """ChatGPT's complete thumbnail poster, headline text included: validated and stored as WEBP, never cropped
    (the owner's format puts the headlines at the top, so a 3:2 image must not be cut to 16:9)."""
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        if image.width < 1024 or image.width <= image.height or image.width * image.height > 20000000:
            raise ValueError("Use a valid landscape image at least 1024 pixels wide.")
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        output = io.BytesIO()
        image.convert("RGB").save(output, "WEBP", quality=95)
        return output.getvalue()


async def enabled(kind):
    config = await db.browser_config.find_one({"id": "browser"}) or {}
    return bool(config.get(TAB_FOR_KIND[kind]) and config.get("token_hash"))


async def cancel_jobs_for_articles(article_ids, reason):
    """Cancel waiting browser jobs of articles that will not continue (e.g. rejected)."""
    if article_ids:
        await db.browser_jobs.update_many({"article_id": {"$in": list(article_ids)}, "status": {"$in": ["queued", "attention"]}},
                                          {"$set": {"status": "cancelled", "message": reason}})


async def consumed(kind, article_id):
    await db.browser_jobs.update_many({"article_id": article_id, "kind": kind, "status": "completed"},
        {"$set": {"status": "consumed"}, "$unset": {"result": ""}})


EXTENSION_STALE = timedelta(minutes=2)
UNAVAILABLE_GRACE = 180  # seconds a queued job may wait on an offline extension / released work tab
_WORK_TAB = {"research": "Gemini research", "image": "ChatGPT", "seo": "ChatGPT"}
TAB_FOR_KIND = {"research": "research", "image": "image", "seo": "image"}
LANE_KINDS = {"research": ["research"], "image": ["image", "seo"]}
# Jobs an in-process workflow is currently waiting for. Orphaned queued jobs (their workflow ended,
# e.g. after a restart) are never claimed, so they cannot run with an outdated prompt.
_awaiting: dict[str, int] = {}


async def unavailable_reason(kind):
    """Why the extension cannot run a `kind` job right now, or None if it can."""
    config = await db.browser_config.find_one({"id": "browser"}) or {}
    seen = config.get("last_seen")
    if seen is None or now_utc() - seen > EXTENSION_STALE:
        return "Chrome extension is offline. Open Chrome with the Newsroom extension"
    tab = (config.get("workspace") or {}).get(TAB_FOR_KIND[kind]) or {}
    if version_at_least(config.get("version"), "0.3.0") and not tab.get("attached"):
        return (f"The {_WORK_TAB[kind]} work tab is not connected ({tab.get('message') or 'no tab'}). "
                "Click Connect both work tabs on the Browser Extension page")
    return None


async def run_job(kind, article_id, prompt, timeout, same_prompt=None, effort=None, wait_limit_seconds=None):
    """Result of this article's `kind` job. `same_prompt`: a waiting or finished job whose prompt starts with it is
    reused although its closing lines differ (e.g. made before a restart with an earlier wording). A new ChatGPT job
    gets its thinking level (`effort`) and, for images, how long the extension waits after sending."""
    from lib.ai import AIError
    job = await db.browser_jobs.find_one({"article_id": article_id, "kind": kind, "status": {"$in": ["queued", "running", "attention", "completed"]}})
    reusable = job and (job.get("prompt") == prompt
                        or (same_prompt and str(job.get("prompt") or "").startswith(same_prompt)))
    if job and not reusable and job["status"] in {"queued", "completed"}:
        # Never reuse a waiting or finished job created with a different (older) prompt.
        await db.browser_jobs.update_one({"id": job["id"], "status": job["status"]}, {"$set": {
            "status": "cancelled", "message": "Replaced by a job with the current prompt"}, "$unset": {"result": ""}})
        job = None
    if job and job["status"] == "queued" and effort:
        # Not claimed yet: it runs at the level of the current request (e.g. Medium again after Retry).
        levels = {"effort": effort, **({"wait_limit_seconds": int(wait_limit_seconds)} if wait_limit_seconds else {})}
        await db.browser_jobs.update_one({"id": job["id"], "status": "queued"}, {"$set": levels})
        job.update(levels)
    if not job:
        job = {"id": new_id(), "article_id": article_id, "kind": kind, "prompt": prompt,
               "status": "queued", "message": "Waiting for paired Chrome", "created_at": now_utc()}
        if effort:
            job["effort"] = effort
        if wait_limit_seconds:
            job["wait_limit_seconds"] = int(wait_limit_seconds)
        if kind == "research":
            # The automatic fresh run after the 15-minute limit is allowed to finish (owner rule, 28 Sep 2026).
            art = await db.articles.find_one({"id": article_id}, {"dossier_meta.auto_research_again": 1}) or {}
            job["rerun"] = bool((art.get("dossier_meta") or {}).get("auto_research_again"))
        await db.browser_jobs.insert_one(dict(job))
    # Queue wait must not consume the image execution timeout. Browser research has no local elapsed-time failure here.
    # A job queued behind a busy extension may wait indefinitely, but one that cannot run because the
    # extension is offline or its work tab is released is held after UNAVAILABLE_GRACE, so the scheduler
    # is not frozen behind it. The job stays queued; progress() releases the "(browser)" hold on completion.
    if kind == "image":
        # The deadline covers the time before Send (page settle, a restored draft) plus the extension's wait after it,
        # which is longer at a higher thinking level.
        timeout += max(0, int(job.get("wait_limit_seconds") or 300) - 300)
    _awaiting[job["id"]] = _awaiting.get(job["id"], 0) + 1
    try:
        return await _wait_for_job(job, kind, timeout)
    finally:
        _awaiting[job["id"]] -= 1
        if _awaiting[job["id"]] <= 0:
            _awaiting.pop(job["id"], None)


async def _wait_for_job(job, kind, timeout):
    from lib.ai import AIError
    deadline = None
    unavailable_since = None
    while True:
        current = await job_status(job["id"])
        if current["status"] == "completed":
            saved = await db.browser_jobs.find_one({"id": job["id"]})
            return saved["result"]
        if current["status"] in {"cancelled", "attention"}:
            raise AIError(current.get("message", "Browser job stopped. Open Browser Extension settings."), "browser")
        if current["status"] == "queued" and (reason := await unavailable_reason(kind)):
            if unavailable_since is None:
                unavailable_since = time.monotonic()
            if time.monotonic() - unavailable_since >= UNAVAILABLE_GRACE:
                # Keep it claimable after this workflow stops waiting; completion releases the hold.
                await db.browser_jobs.update_one({"id": job["id"]}, {"$set": {"resume_on_completion": True}})
                raise AIError(reason + ". The job stays queued and resumes automatically once connected.", "browser")
        else:
            unavailable_since = None
        if kind == "image" and current["status"] == "running":
            if deadline is None:
                deadline = time.monotonic() + timeout
            elif time.monotonic() >= deadline:
                raise AIError("Browser image job is still running. Open Browser Extension settings; Retry reconnects to the same job.", "browser")
        await asyncio.sleep(2)
