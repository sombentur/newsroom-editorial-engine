# MAINTAINER NOTE (2026-09-27): WORKFLOW ENTRY POINTS: Research/Retry/Go ahead start background work; publication is a separate guarded action. Research approval is an explicit editor override, not an automatic validation pass. Preserve its original warnings and audit history.
"""Pipeline endpoints: discovery, topic queue, and the per-article state machine actions."""

import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from lib.manual_ai import manual_request
from lib.safety import discovery_block_reason, system_block_reason

from lib.dates import today_iso
from lib.db import db
from lib.discovery import DiscoveryError, discover
from lib.util import audit, clean, clean_all, new_id, now_utc
from lib.workflow import (
    create_job,
    run_article_stage,
    run_image_stage,
    run_research_stage,
    wordpress_write,
)
from models.schemas import DiscoverBody, ImageRegenBody, ManualImageBody, RejectBody, ScheduleBody

router = APIRouter()
_article_locks: dict[str, asyncio.Lock] = {}
_research_tasks: dict[str, asyncio.Task] = {}
# Separate stage queues prevent long browser research waits from starving approved article writing.
# Do not wrap the entire pipeline in the research semaphore again. Counts are per process, not distributed locks.
_workflow_slots = asyncio.Semaphore(2)
_writing_slots = asyncio.Semaphore(2)
_image_slots = asyncio.Semaphore(2)
TERMINAL_ARTICLE_STAGES = {"wordpress_draft", "scheduled", "published", "verified"}
NOT_WAITING = TERMINAL_ARTICLE_STAGES | {"rejected", "held_review", "failed", "image_ready"}

async def manual_article_action(art_id: str):
    lock = _article_locks.setdefault(art_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "An action is already running for this article.")
    async with lock:
        token = manual_request.set(True)
        try:
            yield
        finally:
            manual_request.reset(token)
            _article_locks.pop(art_id, None)



async def _site_or_404(key: str) -> dict:
    site = await db.sites.find_one({"key": key})
    if not site:
        raise HTTPException(404, "site not found")
    return site


async def _article_or_404(art_id: str) -> dict:
    art = await db.articles.find_one({"id": art_id})
    if not art:
        raise HTTPException(404, "article not found")
    art.pop("_id", None)
    return art


# ── Stage A/B/C: discover, dedupe, score, select ─────────────────
@router.post("/pipeline/discover")
async def run_discovery(body: DiscoverBody):
    site = await _site_or_404(body.site_key)
    if reason := await discovery_block_reason(site):
        raise HTTPException(409, reason)
    run_date = today_iso(site.get("timezone"))
    existing = await db.topics.find({"site_key": body.site_key}).to_list(1000)
    published = await db.published_posts.find({"site_key": body.site_key}).to_list(1000)
    try:
        candidates = await discover(site, existing, run_date, published)
    except DiscoveryError as exc:
        raise HTTPException(502, str(exc)) from None
    if reason := await discovery_block_reason(await _site_or_404(body.site_key)):
        raise HTTPException(409, reason)
    if candidates:
        await db.topics.insert_many([dict(c) for c in candidates])
    rejected_dupes = sum(1 for c in candidates if c["status"] == "rejected")
    await audit("discovery", "topic", None, body.site_key,
                detail={"candidates": len(candidates),
                        "selected": sum(1 for c in candidates if c["status"] == "selected"),
                        "rejected_duplicates": rejected_dupes,
                        "published_checked": len(published)})
    queued = []
    if ((await db.system_settings.find_one({"id": "system"})) or {}).get("mode") == "auto":
        from lib.scheduler import _auto_queue
        queued = await _auto_queue(site)  # 70+ topics move to the Editorial Workbench (owner rule, 28 Sep 2026)
    return {"count": len(candidates), "rejected_duplicates": rejected_dupes, "queued": len(queued),
            "published_checked": len(published), "candidates": clean_all(candidates)}


@router.post("/pipeline/import-posts")
async def import_posts(body: DiscoverBody):
    if reason := await system_block_reason():
        raise HTTPException(409, reason)
    raise HTTPException(409, "WordPress import remains held until the live integration is verified. No sample records were created.")


@router.get("/published")
async def list_published(site_key: str | None = None):
    q = {"site_key": site_key} if site_key else {}
    return clean_all(await db.published_posts.find(q).sort("imported_at", -1).to_list(500))


@router.get("/topics")
async def list_topics(site_key: str | None = None, status: str | None = None):
    q = {}
    if site_key:
        q["site_key"] = site_key
    if status:
        q["status"] = status
    docs = await db.topics.find(q).sort("score", -1).to_list(500)
    return clean_all(docs)


@router.post("/topics/{topic_id}/select")
async def select_topic(topic_id: str):
    topic = await db.topics.find_one({"id": topic_id})
    if not topic:
        raise HTTPException(404, "topic not found")
    topic.pop("_id", None)
    return await create_job(topic)


@router.post("/topics/{topic_id}/reject")
async def reject_topic(topic_id: str, body: RejectBody):
    await db.topics.update_one({"id": topic_id}, {"$set": {"status": "rejected", "selection_reason": body.reason}})
    await audit("topic_reject", "topic", topic_id, detail={"reason": body.reason})
    return {"ok": True}


# ── Articles: list / get ─────────────────────────────────────────
@router.get("/articles")
async def list_articles(site_key: str | None = None, stage: str | None = None):
    q = {}
    if site_key:
        q["site_key"] = site_key
    if stage:
        q["stage"] = stage
    docs = await db.articles.find(q).sort("created_at", -1).to_list(500)
    from lib.turn import current_article, next_article
    current, ahead = await current_article(), await next_article()
    system = await db.system_settings.find_one({"id": "system"}, {"last_sequence_site": 1}) or {}
    waiting = await db.articles.find({"stage": {"$nin": list(NOT_WAITING)}},
                                     {"_id": 0, "id": 1, "site_key": 1, "created_at": 1}).sort("created_at", 1).to_list(500)
    position = {art_id: i + 1 for i, art_id in enumerate(_queue_order(waiting, current, ahead, system.get("last_sequence_site")))}
    # strip heavy image data from list payloads
    for d in docs:
        d.pop("_id", None)
        # Its place in line: in production now, next (researching ahead), or waiting in the queue (with its position).
        d["queue"] = ("current" if current and d["id"] == current["id"] else "next" if ahead and d["id"] == ahead["id"]
                      else "queued" if d["stage"] not in NOT_WAITING else None)
        d["queue_position"] = position.get(d["id"])
        if d.get("image"):
            d["image"] = {k: v for k, v in d["image"].items() if k != "data_uri"} | {"has_image": True}
    # The Workbench shows the work in the order it happens: the current article, then the queue, then the rest.
    docs.sort(key=lambda d: (0, 0) if d["queue"] == "current" else (1, d["queue_position"]) if d["queue_position"] else (2, 0))
    return docs


def _queue_order(waiting: list[dict], current: dict | None, ahead: dict | None, last_site: str | None) -> list[str]:
    """Waiting article ids in the order the sequence takes them: the article researched ahead first, then the sites in
    turn (the site that did not go last first), oldest first within a site."""
    skip = {a["id"] for a in (current, ahead) if a}
    order = [ahead["id"]] if ahead else []
    by_site: dict[str, list[str]] = {}
    for w in waiting:  # oldest first
        if w["id"] not in skip:
            by_site.setdefault(w["site_key"], []).append(w["id"])
    last = (ahead or current or {}).get("site_key") or last_site
    sites = sorted(by_site, key=lambda k: (k == last, k != "kannadiga"))
    turn = sites[0] if sites else None
    while any(by_site.values()):
        if not by_site.get(turn):
            turn = next(k for k in sites if by_site[k])
        order.append(by_site[turn].pop(0))
        others = [k for k in sites if k != turn and by_site[k]]
        if others:
            turn = others[0]
    return order


@router.get("/ai-alerts")
async def ai_alerts():
    from lib.secrets import get_provider, get_model
    rows = await db.articles.find({"stage":"held_review", "$or":[{"ai_failure.kind":{"$in":["rate_limit","quota","auth","model_unavailable"]}}, {"held_reason":{"$regex":r"failed \((rate_limit|quota|auth|model_unavailable)\)"}}]}).sort("updated_at",-1).to_list(100)
    alerts = []
    for art in rows:
        reason = art.get("held_reason", "")
        failure = art.get("ai_failure") or {}
        task = failure.get("task") or reason.split(" failed")[0]
        kind = failure.get("kind") or ("quota" if "(quota)" in reason else "auth" if "(auth)" in reason else "model_unavailable" if "(model_unavailable)" in reason else "rate_limit")
        provider = failure.get("provider")
        setting = "image" if "image" in task else "research" if task == "research" else "writing"
        alerts.append({"article_id":art["id"],"task":task,"kind":kind,"provider":provider or f"{get_provider(setting)} / {get_model(setting)} (current setting; original provider was not recorded)","at":failure.get("at") or art.get("updated_at")})
    return alerts


@router.get("/sign-off-alerts")
async def sign_off_alerts():
    """Articles waiting for the owner's editorial approval (high-risk subjects): shown as a popup and a banner."""
    from lib.turn import SIGN_OFF
    rows = await db.articles.find({"stage": "held_review", "approval": None, "held_reason": {"$regex": "^" + SIGN_OFF}},
                                  {"_id": 0, "id": 1, "site_key": 1, "article.headline": 1, "topic_snapshot.topic": 1,
                                   "review_flags": 1, "updated_at": 1}).sort("updated_at", 1).to_list(50)
    return [{"article_id": a["id"], "site_key": a.get("site_key"), "flags": a.get("review_flags") or [],
             "title": ((a.get("article") or {}).get("headline") or (a.get("topic_snapshot") or {}).get("topic") or "")[:160],
             "since": a.get("updated_at")} for a in rows]


@router.get("/articles/{art_id}")
async def get_article(art_id: str):
    return await _article_or_404(art_id)


# ── State-machine actions ────────────────────────────────────────
def _scheduler_running(art_id: str) -> bool:
    """A scheduler task (the current article's step, or the next article's research ahead) works on art_id."""
    from lib.scheduler import _ai_tasks, _task_article
    return any(article_id == art_id and (task := _ai_tasks.get(key)) and not task.done()
               for key, article_id in list(_task_article.items()))


async def _pipeline_in_background(art_id: str) -> None:
    from lib.turn import needs_research, wait_for_research, wait_for_turn
    from lib.workflow import ARTICLE_TURN, IN_PRODUCTION
    try:
        if needs_research(await _article_or_404(art_id)):
            # Its research may start ahead, once the current article is on its thumbnail (owner rule, 27 Sep 2026).
            slot = await wait_for_research(art_id)
            if slot is None:
                return
            if slot == "ahead":
                await _run_pipeline_in_background(art_id, research_only=True)
                if (await _article_or_404(art_id)).get("stage") in {"held_review", "failed", "rejected"}:
                    return  # held after its research: it goes next and waits for the editor
        # One article at a time: its SEO, thumbnail and publishing start only after the current one is published.
        if not await wait_for_turn(art_id):
            return
        async with ARTICLE_TURN:
            IN_PRODUCTION["article"] = art_id
            try:
                await _run_pipeline_in_background(art_id)
            finally:
                IN_PRODUCTION.pop("article", None)
    except HTTPException:
        return  # the article was removed meanwhile
    finally:
        if _research_tasks.get(art_id) is asyncio.current_task():
            _research_tasks.pop(art_id, None)


# Recovery is deliberately narrow: previously editor-approved research only, respecting runtime/site pause.
# This is not general durable-task recovery for every in-flight stage.
async def recover_approved_research() -> None:
    """Resume explicitly approved research after a service restart."""
    from lib.manual_ai import block_reason
    token = manual_request.set(True)
    try:
        async for art in db.articles.find({"stage": "research_validated", "research_approval.by": {"$exists": True}, "validation.passed": True}):
            if art.get("article") or (art.get("wp") or {}).get("post_id") or await block_reason(art["site_key"]):
                continue
            running = _research_tasks.get(art["id"])
            if not running or running.done():
                _research_tasks[art["id"]] = asyncio.create_task(_pipeline_in_background(art["id"]))
    finally:
        manual_request.reset(token)


async def _run_pipeline_in_background(art_id: str, research_only: bool = False) -> None:
    """Continue every missing AI stage independently of the browser connection (research_only: research ahead)."""
    token = manual_request.set(True)
    try:
        art = await _article_or_404(art_id)
        site = await _site_or_404(art["site_key"])
        if not art.get("dossier") or not (art.get("validation") or {}).get("passed"):
            async with _workflow_slots:
                art = await run_research_stage(art, site)
        if research_only or art.get("stage") == "held_review" or not (art.get("validation") or {}).get("passed"):
            return
        from lib.workflow import needs_thumbnail_design
        if not art.get("article") or needs_thumbnail_design(art):
            async with _writing_slots:
                art = await _article_or_404(art_id)
                if art.get("stage") in TERMINAL_ARTICLE_STAGES or art.get("held_reason") == "Stopped by editor.":
                    return
                art = await run_article_stage(art, site)
        if art.get("stage") == "held_review" or not (art.get("quality_gate") or {}).get("passed"):
            return
        if not art.get("image"):
            async with _image_slots:
                art = await _article_or_404(art_id)
                if art.get("stage") in TERMINAL_ARTICLE_STAGES or art.get("held_reason") == "Stopped by editor.":
                    return
                await run_image_stage(art, site)
    except Exception:
        # The normal provider path converts expected failures into a safe hold.
        # This catches only unexpected worker faults and never exposes provider data.
        await db.articles.update_one({"id": art_id}, {"$set": {
            "stage": "held_review",
            "held_reason": "The background workflow stopped unexpectedly. Select Retry to continue from the saved stage.",
            "updated_at": now_utc(),
        }})
        await audit("pipeline_worker_error", "article", art_id,
                    detail={"error": "unexpected background workflow failure"})
    finally:
        manual_request.reset(token)
        if not research_only:  # a run that researched ahead continues in _pipeline_in_background
            _research_tasks.pop(art_id, None)


async def _single_stage_in_background(art_id: str, stage: str, brief: str | None = None) -> None:
    from lib.turn import wait_for_turn
    from lib.workflow import ARTICLE_TURN, IN_PRODUCTION
    token = manual_request.set(True)
    try:
        # One article at a time: another article's work starts only after the current one is published.
        if not await wait_for_turn(art_id):
            return
        async with ARTICLE_TURN:
            IN_PRODUCTION["article"] = art_id
            try:
                art = await _article_or_404(art_id)
                site = await _site_or_404(art["site_key"])
                if stage == "generate":
                    await run_article_stage(art, site)
                else:
                    await run_image_stage(art, site, brief)
            finally:
                IN_PRODUCTION.pop("article", None)
    except asyncio.CancelledError:
        await db.articles.update_one({"id": art_id}, {"$set": {
            "stage": "held_review", "held_reason": "Stopped by editor.", "updated_at": now_utc(),
        }, "$push": {"history": {"stage": "held_review", "at": now_utc(), "actor": "editor",
                                "note": f"Stopped {stage}"}}})
        raise
    finally:
        manual_request.reset(token)
        _research_tasks.pop(art_id, None)


async def _replace_stuck_jobs(art_id: str) -> None:
    """Retry and Research run the step again: a browser job waiting for attention (e.g. Gemini stopped without a
    report) would otherwise be re-joined and fail at once."""
    await db.browser_jobs.update_many({"article_id": art_id, "status": "attention"}, {"$set": {
        "status": "cancelled", "message": "Replaced: Retry runs this step again", "updated_at": now_utc()}})


@router.post("/articles/{art_id}/research", dependencies=[Depends(manual_article_action)])
async def do_research(art_id: str):
    art = await _article_or_404(art_id)
    if art.get("stage") in TERMINAL_ARTICLE_STAGES or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked. Create a revision instead of rerunning research.")
    if art.get("dossier"):
        return art
    running = _research_tasks.get(art_id)
    if (running and not running.done()) or _scheduler_running(art_id):
        return art
    await _site_or_404(art["site_key"])
    await _replace_stuck_jobs(art_id)
    queued_meta = {**(art.get("dossier_meta") or {})}
    # A run the owner starts is a first run again (the 15-minute rule and automatic fresh runs apply anew).
    queued_meta.pop("auto_research_again", None)
    queued_meta.pop("auto_research_count", None)
    queued_meta.setdefault("status", "queued")
    await db.articles.update_one({"id": art_id}, {"$set": {
        "stage": "researching", "held_reason": None,
        "dossier_meta": queued_meta,
        "updated_at": now_utc(),
    }})
    _research_tasks[art_id] = asyncio.create_task(_pipeline_in_background(art_id))
    await audit("research_queued", "article", art_id, art["site_key"],
                detail={"background": True, "duplicate": False})
    return await _article_or_404(art_id)


@router.get("/articles/{art_id}/research.docx")
async def download_research_docx(art_id: str):
    art = await _article_or_404(art_id)
    if not art.get("dossier"):
        raise HTTPException(404, "Research dossier is not available yet.")
    site = await _site_or_404(art["site_key"])
    from lib.research_docx import build_research_docx
    content = build_research_docx(art, site)
    filename = f"research-dossier-{art_id[:8]}.docx"
    return Response(content=content,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/articles/{art_id}/generate", dependencies=[Depends(manual_article_action)])
async def do_generate(art_id: str):
    art = await _article_or_404(art_id)
    if art.get("stage") in TERMINAL_ARTICLE_STAGES or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked. Create a revision instead of regenerating them.")
    if not art.get("dossier"):
        raise HTTPException(400, "run research first")
    running = _research_tasks.get(art_id)
    if running and not running.done():
        return art
    await _site_or_404(art["site_key"])
    _research_tasks[art_id] = asyncio.create_task(_single_stage_in_background(art_id, "generate"))
    await asyncio.sleep(0)
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/image", dependencies=[Depends(manual_article_action)])
async def do_image(art_id: str, body: ImageRegenBody | None = None):
    art = await _article_or_404(art_id)
    if art.get("stage") in TERMINAL_ARTICLE_STAGES or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked. Create a revision instead of regenerating them.")
    if not art.get("article"):
        raise HTTPException(400, "generate the article first")
    running = _research_tasks.get(art_id)
    if running and not running.done():
        return art
    await _site_or_404(art["site_key"])
    await db.articles.update_one({"id": art_id}, {"$unset": {"image_fresh_runs": ""}})  # the owner starts the step
    _research_tasks[art_id] = asyncio.create_task(
        _single_stage_in_background(art_id, "image", body.brief if body else None))
    await asyncio.sleep(0)
    return await _article_or_404(art_id)



@router.post("/articles/{art_id}/set-image")
async def set_image_manually(art_id: str, body: ManualImageBody):
    # Accept a manually-provided image (URL fetch or base64 data-URI).
    # Converts to WEBP, stores in the article, and advances to image_ready.
    art = await _article_or_404(art_id)
    if art.get("stage") in TERMINAL_ARTICLE_STAGES:
        raise HTTPException(409, "Published or scheduled articles are locked.")
    if not body.url and not body.data_uri:
        raise HTTPException(400, "Provide url or data_uri")

    import base64 as _b64, io
    try:
        from PIL import Image as _PIL
    except ImportError:
        raise HTTPException(500, "Pillow not installed")

    if body.url:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                r = await client.get(body.url)
                r.raise_for_status()
                image_bytes = r.content
        except Exception as exc:
            raise HTTPException(400, f"Could not fetch image URL: {exc}")
    else:
        try:
            _, data = body.data_uri.split(",", 1)
            image_bytes = _b64.b64decode(data)
        except Exception:
            raise HTTPException(400, "Invalid data_uri")

    try:
        with _PIL.open(io.BytesIO(image_bytes)) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "WEBP", quality=95)
            b64 = _b64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        raise HTTPException(400, f"Could not decode image: {exc}")

    data_uri = "data:image/webp;base64," + b64
    article = art.get("article") or {}
    topic   = art.get("topic_snapshot") or {}
    image = {
        "data_uri": data_uri,
        "source": body.source,
        "brief": article.get("featured_image_brief") or topic.get("topic", ""),
        "format": "webp",
        "alt_text": article.get("featured_image_alt_text") or article.get("headline", ""),
        "caption": article.get("featured_image_caption") or "",
        "media_title": (article.get("headline") or "Featured image")[:100],
        "aspect_ratio": "16:9",
        "status": "generated",
        "synthetic": False,
        "headlines": article.get("thumbnail_headlines"),
    }
    await db.articles.update_one(
        {"id": art_id},
        {
            "$set": {"image": image, "stage": "image_ready", "held_reason": None, "updated_at": now_utc()},
            "$push": {"history": {"stage": "image_ready", "at": now_utc(), "actor": "editor",
                                  "note": f"Image set manually ({body.source})"}},
        },
    )
    # The browser job that failed (or is still waiting) must not later overwrite the editor's image.
    await db.browser_jobs.update_many(
        {"article_id": art_id, "kind": "image", "status": {"$in": ["queued", "running", "attention", "completed"]}},
        {"$set": {"status": "cancelled", "message": "Replaced by a manually supplied image"}, "$unset": {"result": ""}})
    await audit("image_done", "article", art_id, art["site_key"], detail={"source": body.source})
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/stop")
async def stop_article_action(art_id: str):
    art = await _article_or_404(art_id)
    task = _research_tasks.get(art_id)
    meta = art.get("dossier_meta") or {}
    if art.get("stage") == "researching" and meta.get("provider") == "gemini" and meta.get("interaction_id"):
        from lib.deep_research import BASE
        from lib.secrets import get_secret
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20, headers={"x-goog-api-key": get_secret("gemini_api_key")}) as client:
                response = await client.post(f"{BASE}/{meta['interaction_id']}/cancel")
                response.raise_for_status()
        except Exception:
            # The local task is still stopped; the provider may have completed
            # between the last poll and the cancellation request.
            pass
    if art.get("stage") == "researching" and meta.get("provider") == "openai" and meta.get("response_id"):
        from lib.secrets import get_secret
        from openai import OpenAI
        try:
            client = OpenAI(api_key=get_secret("openai_api_key"), max_retries=0, timeout=20)
            await asyncio.to_thread(client.responses.cancel, meta["response_id"])
        except Exception:
            # The local task stops even if the provider job has already finished.
            pass
    if task and not task.done():
        task.cancel()
    patch = {"stage": "held_review", "held_reason": "Stopped by editor.", "updated_at": now_utc()}
    if art.get("stage") == "researching":
        patch["dossier_meta.status"] = "cancelled"
    await db.articles.update_one({"id": art_id}, {"$set": patch,
        "$push": {"history": {"stage": "held_review", "at": now_utc(), "actor": "editor",
                                "note": f"Stopped {art.get('stage', 'workflow')}"}}})
    await audit("article_action_stopped", "article", art_id, art["site_key"], actor="editor",
                detail={"stage": art.get("stage")})
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/run-all", dependencies=[Depends(manual_article_action)])
async def run_all(art_id: str):
    """Convenience: research → generate → image in one call (each has its own gate)."""
    art = await _article_or_404(art_id)
    site = await _site_or_404(art["site_key"])
    art = await run_research_stage(art, site)
    if art["stage"] == "held_review":
        return art
    art = await run_article_stage(art, site)
    if art["stage"] == "held_review":
        return art
    return await run_image_stage(art, site)


@router.patch("/articles/{art_id}")
async def edit_article(art_id: str, body: dict):
    art = await _article_or_404(art_id)
    article = art.get("article") or {}
    allowed = {"headline", "dek", "excerpt", "content_html", "seo_title",
               "meta_description", "slug", "category", "tags", "thumbnail_headlines"}
    for k, v in body.items():
        if k in allowed:
            article[k] = v
    from lib.util import now_utc
    from lib.editorial_html import sanitize_html
    if "content_html" in article:
        article["content_html"] = sanitize_html(article["content_html"])
    await db.articles.update_one({"id": art_id}, {
        "$set": {"article": article, "updated_at": now_utc(), "approval": None,
                 "quality_gate": None, "stage": "held_review", "held_reason": "Edited article requires validation and approval."},
        "$push": {"history": {"stage": art["stage"], "at": now_utc(), "actor": "editor", "note": "Article edited"}},
    })
    await audit("article_edit", "article", art_id, art["site_key"], actor="editor", detail={"fields": list(body.keys())})
    return await _article_or_404(art_id)


@router.patch("/articles/{art_id}/thumbnail-headlines", dependencies=[Depends(manual_article_action)])
async def edit_thumbnail_headlines(art_id: str, body: dict):
    art = await _article_or_404(art_id)
    if art.get("stage") in TERMINAL_ARTICLE_STAGES or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked. Create a revision instead of rerunning the workflow.")
    if not art.get("article"):
        raise HTTPException(400, "Generate the article first.")
    from lib.thumbnails import validate_headlines
    language = "kn" if art["site_key"] == "kannadiga" else "en"
    try:
        # ChatGPT renders the headlines into the new thumbnail (owner's format); the app adds no text.
        lines = validate_headlines(body.get("headlines"), language)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    from lib.thumbnail_prompts import headline_from_thumbnail
    # The post title matches the thumbnail text (owner rule), so it follows the edited lines.
    article = art["article"]
    context = " ".join((str(article.get("seo_title") or ""), str(article.get("meta_description") or ""),
                        re.sub(r"<[^>]+>", " ", article.get("content_html", ""))))
    patch = {"article.thumbnail_headlines": lines, "article.headline": headline_from_thumbnail(lines, language, context),
             "image": None, "approval": None, "updated_at": now_utc()}
    if art["stage"] == "image_ready":
        patch["stage"] = "article_validated"
    await db.articles.update_one({"id": art_id}, {"$set": patch})
    await audit("thumbnail_headlines_edited", "article", art_id, art["site_key"], actor="editor")
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/research/go-ahead", dependencies=[Depends(manual_article_action)])
async def approve_research(art_id: str, request: Request):
    art = await _article_or_404(art_id)
    if art.get("stage") != "held_review" or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Only research held for review can be approved here.")
    if not art.get("dossier") or not art.get("validation") or art["validation"].get("passed") or art.get("article"):
        raise HTTPException(409, "A completed research dossier awaiting validation review is required. Use Retry for missing research or provider errors.")
    running = _research_tasks.get(art_id)
    if running and not running.done():
        raise HTTPException(409, "Wait for the current article action to finish.")
    from lib.manual_ai import block_reason
    if reason := await block_reason(art["site_key"]):
        raise HTTPException(409, reason)
    approval = {"by": request.state.admin, "at": now_utc(), "automatic_validation": art["validation"], "reason": art.get("held_reason")}
    validation = {**art["validation"], "passed": True, "accepted_by_editor": True}
    result = await db.articles.update_one({"id": art_id, "stage": "held_review", "dossier": art["dossier"], "validation": art["validation"]}, {
        "$set": {"research_approval": approval, "validation": validation, "stage": "research_validated", "held_reason": None, "updated_at": now_utc()},
        "$push": {"history": {"stage": "research_validated", "at": now_utc(), "actor": request.state.admin,
                               "note": "Go ahead: editor accepted the saved research despite automatic review warnings; continuing article and image generation."}}})
    if not result.modified_count:
        raise HTTPException(409, "Research changed. Refresh and review the latest version.")
    await audit("research_approved_by_editor", "article", art_id, art["site_key"], actor=request.state.admin)
    _research_tasks[art_id] = asyncio.create_task(_pipeline_in_background(art_id))
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/approve")
async def approve_article(art_id: str, request: Request):
    art = await _article_or_404(art_id)
    if not art.get("article") or not (art.get("quality_gate") or {}).get("passed"):
        raise HTTPException(409, "Complete article validation before approval.")
    if not art.get("image"):
        raise HTTPException(409, "Generate the featured image before approval.")
    if art.get("stage") in {"scheduled", "published", "verified"}:
        # Already on WordPress: record the approval only. Handing it to the publishing workflow again booked a new
        # slot for a scheduled post (UP rain moved from 20:30 to the next morning, 27 Sep 2026).
        where = "scheduled for its booked slot" if art["stage"] == "scheduled" else "live"
        await db.articles.update_one({"id": art_id}, {"$set": {"approval": {"by": request.state.admin, "at": now_utc()},
            "updated_at": now_utc()}, "$push": {"history": {"stage": art["stage"], "at": now_utc(), "actor": request.state.admin,
                                                           "note": f"Approved locally; it stays {where} on WordPress"}}})
        await audit("article_approved", "article", art_id, art["site_key"], actor=request.state.admin)
        return await _article_or_404(art_id)
    await db.articles.update_one({"id": art_id}, {"$set": {"approval": {"by": request.state.admin, "at": now_utc()},
        "stage": "image_ready", "held_reason": None, "updated_at": now_utc()},
        "$push": {"history": {"stage": "image_ready", "at": now_utc(), "actor": request.state.admin,
                               "note": "Approved locally; ready for the configured publishing workflow"}}})
    await audit("article_approved", "article", art_id, art["site_key"], actor=request.state.admin)
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/reject")
async def reject_article(art_id: str, body: RejectBody):
    from lib.util import now_utc
    await db.articles.update_one({"id": art_id}, {
        "$set": {"stage": "rejected", "held_reason": body.reason, "updated_at": now_utc()},
        "$push": {"history": {"stage": "rejected", "at": now_utc(), "actor": "editor", "note": body.reason}},
    })
    await audit("reject", "article", art_id, actor="editor", detail={"reason": body.reason})
    from lib.browser_bridge import cancel_jobs_for_articles
    await cancel_jobs_for_articles([art_id], "Article was rejected; this browser job will not run.")
    return await _article_or_404(art_id)


@router.post("/articles/{art_id}/schedule")
async def schedule_article(art_id: str, body: ScheduleBody):
    art = await _article_or_404(art_id)
    site = await _site_or_404(art["site_key"])
    if not art.get("article") or not art.get("image"):
        raise HTTPException(400, "article and image must be ready before scheduling")
    return await wordpress_write(art, site, "future", body.scheduled_time)


@router.post("/articles/{art_id}/publish", dependencies=[Depends(manual_article_action)])
async def publish_article(art_id: str):
    """Publish now (Broadcast Schedule): a ready or scheduled article goes live at once; a scheduled one frees its slot."""
    art = await _article_or_404(art_id)
    if (art.get("wp") or {}).get("status") == "publish" or art.get("stage") in {"published", "verified"}:
        raise HTTPException(409, "This article is already live.")
    if art.get("stage") == "rejected":
        raise HTTPException(409, "Rejected articles are not published.")
    system = await db.system_settings.find_one({"id": "system"})
    if system and (system.get("killswitch") or system.get("global_paused")):
        raise HTTPException(409, "publishing is paused or stopped by the killswitch")
    site = await _site_or_404(art["site_key"])
    if site.get("paused"):
        raise HTTPException(409, f"{site['name']} publishing is paused")
    if not art.get("article") or not art.get("image"):
        raise HTTPException(400, "article and image must be ready before publishing")
    return await wordpress_write(art, site, "publish")


@router.post("/articles/{art_id}/retry", dependencies=[Depends(manual_article_action)])
async def retry_article(art_id: str):
    """Resume every missing stage in the background from the last saved result."""
    art = await _article_or_404(art_id)
    if art.get("stage") in TERMINAL_ARTICLE_STAGES or (art.get("wp") or {}).get("post_id"):
        raise HTTPException(409, "Published or scheduled articles are locked. Create a revision instead of retrying them.")
    await _site_or_404(art["site_key"])
    running = _research_tasks.get(art_id)
    if running and not running.done():
        return art
    if art.get("stage") in {"researching", "writing_article", "generating_image"} and _scheduler_running(art_id):
        return art
    from lib.workflow import needs_thumbnail_design
    if not art.get("dossier") or not (art.get("validation") or {}).get("passed"):
        stage, note = "researching", "Resuming Deep Research"
    elif not art.get("article") or needs_thumbnail_design(art):
        stage, note = "writing_article", "Resuming article generation"
    elif not art.get("image"):
        stage, note = "generating_image", "Resuming thumbnail generation"
    else:
        raise HTTPException(400, "nothing to retry — article is ready")
    await _replace_stuck_jobs(art_id)
    update = {"$set": {"stage": stage, "held_reason": None, "updated_at": now_utc()},
              "$push": {"history": {"stage": stage, "at": now_utc(), "actor": "owner", "note": note}}}
    if stage == "researching":  # a run the owner starts is a first run again
        update["$unset"] = {"dossier_meta.auto_research_again": "", "dossier_meta.auto_research_count": ""}
    elif stage == "generating_image":  # the automatic fresh ChatGPT chats start again too
        update["$unset"] = {"image_fresh_runs": ""}
    await db.articles.update_one({"id": art_id}, update)
    _research_tasks[art_id] = asyncio.create_task(_pipeline_in_background(art_id))
    await audit("pipeline_resumed", "article", art_id, art["site_key"], detail={"stage": stage})
    return await _article_or_404(art_id)
