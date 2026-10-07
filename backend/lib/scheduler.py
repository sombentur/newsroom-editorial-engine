# MAINTAINER NOTE (2026-09-27): AUTOMATIC ADVANCEMENT (sequential, one article at a time, alternating sites): Check mode, pause/Stop All, per-site settings, quota/timezone and active manual tasks before advancing. Browser attention can block browser jobs even while this scheduler is healthy. Publishing gates remain separate from research approval.
"""Background scheduler: daily discovery and strictly sequential article production.

One article at a time goes from Deep Research to WordPress before the next starts, alternating
sites (Kannadiga, Human, Kannadiga, ...); only the next article's Deep Research starts early, once the current
article is on its thumbnail (owner rule, 27 Sep 2026). Gated by system_settings.scheduler_enabled (default off)
so it never uses AI or publishes without an explicit opt-in.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from lib.dates import today_iso
from lib.db import db
from lib.discovery import discover
from lib.editorial_briefs import AUTO_QUEUE_SCORE
from lib.util import audit, now_utc
from lib.manual_research import (auto_research_enabled, awaiting_manual, ensure_runner as ensure_manual_imports,
                                 has_research, proceed_key, waits_for_link)
from lib.safety import system_block_reason
from lib.manual_ai import automated_request
from lib.runtime import RuntimeSafety
from lib.wp_credentials import is_connected
from lib.turn import claim_next, current_article, needs_research, next_article, on_thumbnail, take_turn
from lib.workflow import (
    ARTICLE_TURN,
    IN_PRODUCTION,
    create_job,
    needs_thumbnail_design,
    repair_citation_source_list,
    run_article_stage,
    run_image_stage,
    run_research_stage,
    wordpress_write,
)

logger = logging.getLogger(__name__)
INTERVAL = 45  # seconds between ticks

TERMINAL = {"rejected"}
DONE = {"scheduled", "published", "verified", "wordpress_draft"}
STOPPED = DONE | TERMINAL | {"held_review", "failed"}
SEQUENCE = "sequence"
AHEAD = "ahead"  # the next article's research, while the current article is on its thumbnail
DISCOVERY_COOLDOWN = timedelta(minutes=60)
DISCOVERY_EVERY = timedelta(hours=2)  # Topic Intelligence keeps adding topics (owner rule, 28 Sep 2026)
# Strictly one article at a time: a single task takes one article from research to WordPress
# before the next starts. Kept as dicts so the Retry endpoint can see which article is running.
_ai_tasks: dict[str, asyncio.Task] = {}
_task_article: dict[str, str] = {}
_task_site: dict[str, str] = {}
_discovery_tasks: dict[str, asyncio.Task] = {}


async def _run_ai_step(key: str, step, article: dict, site: dict) -> None:
    try:
        if key == AHEAD:  # the next article's research runs beside the current article, outside its turn
            await step(article, site)
        else:
            async with ARTICLE_TURN:
                IN_PRODUCTION["article"] = article["id"]
                try:
                    await step(article, site)
                finally:
                    IN_PRODUCTION.pop("article", None)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("automated workflow step failed for %s (%s)", key, type(exc).__name__)
    finally:
        if _ai_tasks.get(key) is asyncio.current_task():
            _ai_tasks.pop(key, None)
            _task_article.pop(key, None)
            _task_site.pop(key, None)


def _slot_datetimes(site: dict, run_date: str) -> list[datetime]:
    tz = ZoneInfo(site.get("timezone", "UTC"))
    out = []
    for t in site.get("publish_times", []):
        try:
            hh, mm = map(int, t.split(":"))
            y, m, d = map(int, run_date.split("-"))
            out.append(datetime(y, m, d, hh, mm, tzinfo=tz))
        except ValueError:
            continue
    return sorted(out)


def _as_utc(value) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _reserved_slots(articles: list[dict]) -> set[datetime]:
    return {
        stamp for a in articles
        if a.get("stage") in {"scheduled", "published", "verified"}
        or (a.get("wp") or {}).get("status") in {"future", "publish"}
        if (stamp := _as_utc(a.get("scheduled_time") or (a.get("wp") or {}).get("scheduled_time")))
    }


def next_publish_slot(site: dict, articles: list[dict], now: datetime) -> datetime:
    """Reserve the next future slot, counting scheduled and published posts by site-local day."""
    tz = ZoneInfo(site.get("timezone", "UTC"))
    quota = max(1, int(site.get("daily_quota") or 5))
    now = now.astimezone(timezone.utc)
    occupied: dict[str, set[str]] = {}
    for article in articles:
        wp = article.get("wp") or {}
        if article.get("stage") not in {"scheduled", "published", "verified"} and wp.get("status") not in {"future", "publish"}:
            continue
        stamp = _as_utc(article.get("scheduled_time") or wp.get("scheduled_time"))
        if stamp is None and wp.get("status") == "publish":
            stamp = _as_utc(wp.get("verified_at"))
        if stamp is None:
            continue
        day = stamp.astimezone(tz).date().isoformat()
        occupied.setdefault(day, set()).add(article.get("id") or str(id(article)))

    reserved = _reserved_slots(articles)
    local_day = now.astimezone(tz).date()
    for offset in range(366):
        day = (local_day + timedelta(days=offset)).isoformat()
        if len(occupied.get(day, set())) >= quota:
            continue
        for slot in _slot_datetimes(site, day)[:quota]:
            utc_slot = slot.astimezone(timezone.utc)
            if utc_slot > now + timedelta(minutes=1) and utc_slot not in reserved:
                return utc_slot
    raise ValueError("No publishing slot is configured in the next year")


def _citation_reformat_candidate(article: dict) -> bool:
    meta = article.get("dossier_meta") or {}
    validation = article.get("validation") or {}
    return bool(article.get("stage") == "held_review"
                and str(article.get("held_reason") or "").startswith("Research needs review:")
                and validation.get("failed_reasons") == ["claim_urls_match_sources"]
                and (article.get("dossier") or {}).get("publication_ready") is True
                and meta.get("interaction_id") and meta.get("report")
                and not meta.get("citations_included")
                and not meta.get("citation_reformat_attempted"))


def _citation_source_recheck_candidate(article: dict) -> bool:
    meta = article.get("dossier_meta") or {}
    return bool(article.get("stage") == "held_review"
                and str(article.get("held_reason") or "").startswith("Research needs review:")
                and (article.get("validation") or {}).get("failed_reasons") == ["claim_urls_match_sources"]
                and (article.get("dossier") or {}).get("publication_ready") is True
                and meta.get("citations_included") and "PROVIDER CITATION LINKS" in str(meta.get("report") or "")
                and not meta.get("citation_source_recheck_attempted"))


async def _reconcile_due_posts(site: dict, articles: list[dict], system: dict) -> None:
    """Show WordPress's eventual publication in the workbench after a future slot fires."""
    due = next((a for a in articles if a.get("stage") == "scheduled"
                and (stamp := _as_utc(a.get("scheduled_time")))
                and stamp <= datetime.now(timezone.utc)
                and type((a.get("wp") or {}).get("post_id")) is int), None)
    if due is None:
        return
    from lib.wordpress import WordPressClient, WPError
    wp = WordPressClient(site)
    try:
        post = await wp.read_post(due["wp"]["post_id"])
        if post.get("id") != due["wp"]["post_id"]:
            return
        if post.get("status") == "future":
            # WordPress cron can run late on quiet sites. Reuse the same post ID
            # after a short grace period, subject to the normal publication gates.
            if (system.get("mode") == "auto" and site.get("auto_publish")
                    and datetime.now(timezone.utc) - _as_utc(due["scheduled_time"]) >= timedelta(minutes=5)):
                await wordpress_write(due, site, "publish", due["scheduled_time"])
            return
        if post.get("status") != "publish":
            return
        permalink = post.get("link", "")
        if not isinstance(permalink, str) or not permalink.startswith(wp.base + "/"):
            return
        public = await wp.verify_public(permalink)
        if not public.get("public_page_ok"):
            return
    except WPError as exc:
        logger.warning("Could not verify scheduled WordPress post for %s (%s)", site["key"], type(exc).__name__)
        return
    result = dict(due["wp"])
    result.update(status="publish", public_url=permalink, verified_at=now_utc())
    result["verification"] = {**(result.get("verification") or {}),
                              "readback_ok": True, "readback_status": "publish", **public}
    await db.articles.update_one({"id": due["id"], "stage": "scheduled"}, {"$set": {
        "stage": "verified", "wp": result, "updated_at": now_utc(), "held_reason": None,
    }, "$push": {"history": {"stage": "verified", "at": now_utc(), "actor": "scheduler",
                           "note": "Scheduled WordPress post is live and verified"}}})
    await audit("scheduled_post_verified", "article", due["id"], site["key"])


async def _publish_ready(site: dict, system: dict) -> None:
    """WordPress follow-up for one site: verify due posts and hand one finished article to WordPress.

    Runs every tick for both sites, independent of the AI sequence, so publishing never waits
    behind a multi-minute research job.
    """
    key = site["key"]
    if site.get("paused") or not is_connected(site):
        return
    arts = await db.articles.find({"site_key": key}).sort("created_at", 1).to_list(500)
    await _reconcile_due_posts(site, arts, system)
    safety = RuntimeSafety.from_env()

    # If the owner disabled the exceptional high-risk hold, automatically
    # release articles that were stopped only by that gate.
    if not safety.high_risk_review_required:
        for article in arts:
            if (article.get("stage") == "held_review"
                    and str(article.get("held_reason", "")).startswith("High-risk subject requires human editorial sign-off")
                    and article.get("image")
                    and (article.get("validation") or {}).get("passed")
                    and (article.get("quality_gate") or {}).get("passed")):
                await db.articles.update_one({"id": article["id"]}, {"$set": {
                    "stage": "image_ready", "held_reason": None, "updated_at": now_utc(),
                }, "$push": {"history": {"stage": "image_ready", "at": now_utc(), "actor": "scheduler",
                                       "note": "Automatic publishing policy released the prior high-risk hold"}}})
                article["stage"] = "image_ready"
                article["held_reason"] = None
                await audit("high_risk_hold_released", "article", article["id"], key)

    ready = [a for a in arts if a["stage"] == "image_ready"]
    if ready and system.get("mode") != "research_only":
        article = ready[0]
        if (article.get("wp") or {}).get("status") == "publish":
            # Already live: updated in place, never moved back to scheduled or draft.
            await wordpress_write(article, site, "publish")
        elif system.get("mode") != "auto" or not site.get("auto_publish"):
            await wordpress_write(article, site, "draft")
        else:
            now = datetime.now(timezone.utc)
            others = [a for a in arts if a.get("id") != article.get("id")]  # its own booking never blocks it
            booked = _as_utc(article.get("scheduled_time"))
            if booked and booked > now + timedelta(minutes=1) and booked not in _reserved_slots(others):
                slot = booked  # an article that already has a future slot keeps it
            else:
                slot = next_publish_slot(site, others, now)
            await wordpress_write(article, site, "future", slot.isoformat())


def _site_order(sites: list[dict], last_key: str | None) -> list[dict]:
    """Alternate sites: whichever did not go last goes next; Kannadiga starts a fresh sequence."""
    ordered = sorted(sites, key=lambda s: s["key"] != "kannadiga")
    return sorted(ordered, key=lambda s: s["key"] == last_key)


async def _complete_article(article: dict, site: dict) -> None:
    """Take one article through research, SEO/article and thumbnail, stopping when it needs the editor.

    It ends at image_ready; _publish_ready hands it to WordPress on the next tick.
    """
    def progress(a: dict) -> tuple:
        return (a.get("stage"), bool(a.get("dossier")), bool((a.get("validation") or {}).get("passed")),
                bool(a.get("article")), bool(a.get("image")))

    while True:
        current = await db.articles.find_one({"id": article["id"]})
        if (not current or current["stage"] in STOPPED or current["stage"] == "image_ready"
                or await system_block_reason()):
            return
        before = progress(current)
        if not current.get("dossier") or not (current.get("validation") or {}).get("passed"):
            if not has_research(current) and not auto_research_enabled(
                    await db.system_settings.find_one({"id": "system"}, {"auto_research": 1})):
                return  # automatic research is off: the topic waits for its report link
            await run_research_stage(current, site)
        elif not current.get("article") or needs_thumbnail_design(current):
            await run_article_stage(current, site)
        elif not current.get("image"):
            await run_image_stage(current, site)
        else:
            return
        if progress(await db.articles.find_one({"id": article["id"]}) or {}) == before:
            return  # no progress (e.g. blocked); the next tick decides again


async def _reformat_research(article: dict, site: dict) -> None:
    await db.articles.update_one({"id": article["id"]}, {"$set": {
        "dossier_meta.citation_reformat_attempted": True, "updated_at": now_utc(),
    }, "$push": {"history": {"stage": "researching", "at": now_utc(), "actor": "scheduler",
                           "note": "Reformatting saved research with provider citation links"}}})
    await run_research_stage(article, site)


async def _recheck_citations(article: dict, site: dict) -> None:
    await db.articles.update_one({"id": article["id"]}, {"$set": {
        "dossier_meta.citation_source_recheck_attempted": True, "updated_at": now_utc(),
    }, "$push": {"history": {"stage": "held_review", "at": now_utc(), "actor": "scheduler",
                           "note": "Checking omitted source links against provider citations"}}})
    await repair_citation_source_list(article, site)


async def _next_work(site: dict, system: dict):
    """(article, step) for the site's article already mid-workflow, oldest first.

    step None means the article is busy elsewhere (an editor-started run, or waiting for WordPress),
    so the sequence must wait. (None, None) means the site has nothing in progress.
    """
    from routers.pipeline import _research_tasks
    arts = await db.articles.find({"site_key": site["key"], "stage": {"$nin": list(TERMINAL)}}).sort("created_at", 1).to_list(500)
    arts.sort(key=proceed_key)  # the owner's Proceed (Manual Workbench) first; otherwise oldest first
    for a in arts:
        worker = _research_tasks.get(a["id"])
        if worker and not worker.done():
            return a, None
        if awaiting_manual(a) or waits_for_link(a, system):
            continue  # its research comes from the owner (Manual Editorial Workbench; automatic research reserved/off)
        if _citation_source_recheck_candidate(a):
            return a, _recheck_citations
        if _citation_reformat_candidate(a):
            return a, _reformat_research
        if a["stage"] == "image_ready":
            if system.get("mode") == "research_only":
                continue  # research-only mode never publishes; do not stall the sequence on it
            return a, None
        if a["stage"] not in STOPPED:
            return a, _complete_article
    return None, None


async def _create_next_article(site: dict, pending: str | None = None) -> dict | None:
    """The site's next article: today's best topic scoring 70+ (owner rule, 28 Sep 2026), within the daily quota.
    Topic Intelligence keeps discovering more in the background (_discover_if_due)."""
    created = await _auto_queue(site)
    return created[0] if created else None


async def _auto_queue(site: dict) -> list[dict]:
    """Owner rule (28 Sep 2026): today's topics that the AI editor scored 70+ against the site's brief move to the
    Editorial Workbench by themselves, up to the site's daily quota; the rest stay in Topic Intelligence."""
    key = site["key"]
    run_date = today_iso(site.get("timezone"))
    local_tz = ZoneInfo(site.get("timezone", "UTC"))
    quota = max(1, int(site.get("daily_quota") or 5))
    arts = await db.articles.find({"site_key": key}, {"stage": 1, "created_at": 1}).to_list(2000)
    todays = sum(1 for a in arts if a.get("stage") not in TERMINAL and (stamp := _as_utc(a.get("created_at")))
                 and stamp.astimezone(local_tz).date().isoformat() == run_date)
    room = quota - todays
    if room <= 0:
        return []
    topics = await db.topics.find({"site_key": key, "run_date": run_date, "status": {"$in": ["candidate", "selected"]},
                                   "ai_ranked": True, "score": {"$gte": AUTO_QUEUE_SCORE}}).sort("score", -1).to_list(room)
    created = []
    for topic in topics:
        topic.pop("_id", None)
        article = await create_job(topic, actor="topic intelligence")
        await db.topics.update_one({"id": topic["id"]}, {"$set": {"status": "used"}})
        if article.get("topic_id") == topic["id"] and article.get("stage") == "selected":
            created.append(article)
    if created:
        await audit("topics_auto_queued", "topic", None, key, detail={"count": len(created), "min_score": AUTO_QUEUE_SCORE})
    return created


async def _discover_if_due(site: dict) -> None:
    """Topic Intelligence keeps adding fresh topics (owner rule, 28 Sep 2026): every 2 hours per site, and sooner
    (after an hour) when nothing waits in the Workbench for the site. Runs beside the sequence, never blocking it."""
    key = site["key"]
    if (task := _discovery_tasks.get(key)) and not task.done():
        return
    now = datetime.now(timezone.utc)
    last = _as_utc(site.get("last_discovery_at"))
    if last and now - last < DISCOVERY_EVERY:
        if now - last < DISCOVERY_COOLDOWN:
            return
        if await db.articles.count_documents({"site_key": key, "stage": {"$nin": list(STOPPED | {"image_ready"})}}):
            return
    await db.sites.update_one({"key": key}, {"$set": {"last_discovery_at": now}})
    _discovery_tasks[key] = asyncio.create_task(_run_discovery(site))


async def _run_discovery(site: dict) -> None:
    key = site["key"]
    run_date = today_iso(site.get("timezone"))
    try:
        existing = await db.topics.find({"site_key": key}).to_list(5000)
        published = await db.published_posts.find({"site_key": key}).to_list(1000)
        candidates = await discover(site, existing, run_date, published)
    except Exception as exc:
        logger.warning("topic discovery failed for %s (%s)", key, type(exc).__name__)
        return
    # Earlier topics stay in Topic Intelligence; only those older than two weeks are pruned.
    cutoff = (datetime.now(ZoneInfo(site.get("timezone", "UTC"))).date() - timedelta(days=14)).isoformat()
    await db.topics.delete_many({"site_key": key, "status": {"$in": ["candidate", "selected", "rejected"]},
                                 "run_date": {"$lt": cutoff}})
    if candidates:
        await db.topics.insert_many([dict(c) for c in candidates])
    strong = sum(1 for c in candidates if c.get("ai_ranked") and c["score"] >= AUTO_QUEUE_SCORE)
    await audit("scheduler_discovery", "topic", None, key, detail={"candidates": len(candidates), "strong": strong})


def _researching_ahead(art_id: str) -> bool:
    task = _ai_tasks.get(AHEAD)
    return bool(task and not task.done() and _task_article.get(AHEAD) == art_id)


async def _next_in_line(site: dict, exclude: str) -> dict | None:
    """The site's oldest article waiting in the Workbench (not held, not the current article)."""
    article = await db.articles.find_one({"site_key": site["key"], "id": {"$ne": exclude},
                                          "stage": {"$nin": list(STOPPED | {"image_ready"})}},
                                         sort=[("created_at", 1)])
    if article:
        article.pop("_id", None)
    return article


async def _research_only(article: dict, site: dict) -> None:
    """Only the research step (Gemini), for the next article while the current one is on its thumbnail."""
    latest = await db.articles.find_one({"id": article["id"]})
    if latest and latest["stage"] not in STOPPED and needs_research(latest):
        latest.pop("_id", None)
        await run_research_stage(latest, site)


async def _research_ahead(sites: list[dict], system: dict) -> None:
    """Owner rule (27 Sep 2026): once the current article is on its thumbnail (ChatGPT), the next article's Deep
    Research (Gemini) starts. Next in line is what the sequence would take: queued Workbench articles first (the
    other site first, oldest first), else a new article from today's selected topics. One article at most.
    Optional (system_settings.research_ahead): off since 28 Sep 2026, so the next article starts once the current one
    is scheduled."""
    if not system.get("research_ahead"):
        return
    task = _ai_tasks.get(AHEAD)
    if task and not task.done():
        return
    current = await current_article()
    if not current or not on_thumbnail(current):
        return
    from routers.pipeline import _research_tasks
    article = await next_article()
    if article is None:
        order = _site_order([s for s in sites if not s.get("paused") and is_connected(s)], current["site_key"])
        for site in order:
            if article := await _next_in_line(site, current["id"]):
                break
        else:
            for site in order:
                try:
                    if article := await _create_next_article(site, pending=current["id"]):
                        break
                except Exception as exc:
                    logger.warning("could not prepare the next %s article (%s)", site["key"], type(exc).__name__)
        if article is None or not await claim_next(article["id"]):
            return
    site = next((s for s in sites if s["key"] == article["site_key"]), None)
    worker = _research_tasks.get(article["id"])
    if (site and not site.get("paused") and is_connected(site) and article["stage"] not in STOPPED
            and needs_research(article) and not (worker and not worker.done())):
        _ai_tasks[AHEAD] = asyncio.create_task(_run_ai_step(AHEAD, _research_only, article, site))
        _task_article[AHEAD] = article["id"]
        _task_site[AHEAD] = site["key"]


async def _advance_sequence(sites: list[dict], system: dict) -> None:
    """Strictly one article at a time, alternating sites: Kannadiga, Human, Kannadiga, Human ...

    The current article keeps the turn until WordPress has it (or it is rejected). While it is held for the
    editor or waits for WordPress, nothing else starts - except the next article's research, once the current
    article is on its thumbnail (_research_ahead). That article takes the turn next.
    """
    await _research_ahead(sites, system)
    task = _ai_tasks.get(SEQUENCE)
    if (task and not task.done()) or ARTICLE_TURN.locked():
        return  # an article (scheduled or editor-started) is still in production
    if current := await current_article():
        from routers.pipeline import _research_tasks
        site = next((s for s in sites if s["key"] == current["site_key"]), None)
        worker = _research_tasks.get(current["id"])
        if (not site or site.get("paused") or not is_connected(site) or (worker and not worker.done())
                or _researching_ahead(current["id"])):
            return  # (also while its research, started ahead, is still running)
        step = (_recheck_citations if _citation_source_recheck_candidate(current)
                else _reformat_research if _citation_reformat_candidate(current)
                else None if current["stage"] in STOPPED or current["stage"] == "image_ready"
                else _complete_article)
        if step is not None:
            await _start(site, current, step)
        return  # held for the editor, or waiting for WordPress: the next article waits
    if ahead := await next_article():
        # The article researched ahead takes the turn first (an editor-started run takes it itself).
        from routers.pipeline import _research_tasks
        site = next((s for s in sites if s["key"] == ahead["site_key"]), None)
        worker = _research_tasks.get(ahead["id"])
        if site and not site.get("paused") and is_connected(site) and not (worker and not worker.done()):
            waits = _researching_ahead(ahead["id"]) or ahead["stage"] in STOPPED or ahead["stage"] == "image_ready"
            await _start(site, ahead, None if waits else _complete_article)
        return
    eligible = [s for s in sites if not s.get("paused") and is_connected(s)]
    order = _site_order(eligible, system.get("last_sequence_site"))
    found = []
    for site in order:
        article, step = await _next_work(site, system)
        if article is not None:
            found.append((site, article, step))
    # The owner's Proceed (Manual Workbench) goes first; otherwise the sites alternate as before (stable sort).
    found.sort(key=lambda item: proceed_key(item[1]))
    if found:
        site, article, step = found[0]
        if step is not None:
            await _start(site, article, step)
        elif article["stage"] == "image_ready":
            await take_turn(article["id"])  # it keeps the turn until WordPress has it
        return
    for site in order:
        try:
            article = await _create_next_article(site)
        except Exception as exc:
            logger.warning("could not start the next %s article (%s)", site["key"], type(exc).__name__)
            continue
        if article:
            await _start(site, article, _complete_article)
            return


async def _start(site: dict, article: dict, step) -> None:
    if await take_turn(article["id"]):
        return  # another article holds the turn
    await db.system_settings.update_one({"id": "system"}, {"$set": {"last_sequence_site": site["key"]}})
    if step is None:
        return  # it holds the turn and waits (for the editor, WordPress, or its research started ahead)
    _ai_tasks[SEQUENCE] = asyncio.create_task(_run_ai_step(SEQUENCE, step, article, site))
    _task_article[SEQUENCE] = article["id"]
    _task_site[SEQUENCE] = site["key"]


async def tick() -> None:
    safety = RuntimeSafety.from_env()
    if safety.dry_run or not safety.scheduler_enabled:
        return
    system = await db.system_settings.find_one({"id": "system"})
    if not system or not system.get("scheduler_enabled"):
        return
    if await system_block_reason():
        for task in list(_ai_tasks.values()):
            task.cancel()
        return
    sites = await db.sites.find().to_list(10)
    for key in (SEQUENCE, AHEAD):
        running_site = next((s for s in sites if s["key"] == _task_site.get(key)), None)
        if running_site and (running_site.get("paused") or not is_connected(running_site)):
            if task := _ai_tasks.get(key):
                task.cancel()
    for site in sites:
        try:
            await _publish_ready(site, system)
        except Exception as exc:
            logger.error("publishing follow-up failed for %s (%s)", site.get("key"), type(exc).__name__)
    if system.get("mode") == "auto":
        # Topic Intelligence keeps finding fresh topics; 70+ picks move to the Workbench (owner rule, 28 Sep 2026).
        for site in sites:
            if site.get("paused") or not is_connected(site):
                continue
            try:
                await _discover_if_due(site)
                await _auto_queue(site)
            except Exception as exc:
                logger.error("topic intelligence failed for %s (%s)", site.get("key"), type(exc).__name__)
    # Reports the owner linked in the Manual Editorial Workbench are fetched in the background, one topic at a time.
    ensure_manual_imports()
    try:
        await _advance_sequence(sites, system)
    except Exception as exc:
        logger.error("article sequence failed (%s)", type(exc).__name__)


async def scheduler_loop() -> None:
    safety = RuntimeSafety.from_env()
    if safety.dry_run or not safety.scheduler_enabled:
        logger.info("scheduler disabled by environment safety controls")
        return
    logger.info("scheduler loop started (interval %ss)", INTERVAL)
    try:
        from lib.browser_bridge import cancel_jobs_for_articles
        rejected = [a["id"] for a in await db.articles.find({"stage": "rejected"}, {"id": 1}).to_list(5000)]
        await cancel_jobs_for_articles(rejected, "Article was rejected; this browser job will not run.")
    except Exception as exc:
        logger.warning("could not tidy browser jobs of rejected articles (%s)", type(exc).__name__)
    token = automated_request.set(True)
    try:
        while True:
            try:
                await tick()
            except Exception as exc:
                logger.error("scheduler loop error (%s)", type(exc).__name__)
            await asyncio.sleep(INTERVAL)
    finally:
        tasks = list(_ai_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        automated_request.reset(token)
