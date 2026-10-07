# MAINTAINER NOTE (2026-09-27): STATE TRANSITIONS: This module owns research -> writing -> image -> WordPress gates. held_review is a legacy shared state for BOTH editorial holds and technical failures; inspect held_reason and ai_failure before offering approval. Never infer that every hold can be approved.
"""Article state-machine engine: select → research → validate → generate → quality gate
→ image → wordpress draft/schedule/publish → verify. Fail closed; no simulated writes.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from lib.ai import generate_image, run_article, run_research
from lib.db import db
from lib.discovery import detect_risk
from lib import menu_categories
from lib.prompts import (
    ARTICLE_PROMPT,
    ENGLISH_RULE,
    KANNADA_RULE,
    RESEARCH_LANGUAGE_RULES,
    RESEARCH_PROMPT,
)
from lib.research_validation import reconcile_provider_citations, resolve_grounding_redirects, validate_research as _validate_research
from lib.util import audit, new_id, now_utc
from lib.wordpress import WPError, has_credentials
from lib.ai import AIError
from lib.safety import system_block_reason
from lib.runtime import RuntimeSafety
from lib.wp_credentials import is_connected, connection_reason


async def _ai_hold(art: dict, stage_name: str, exc: "AIError") -> dict:
    """Stop the article safely on an AI failure — no publish, exact non-sensitive error, retryable."""
    if stopped := await _stopped_by_editor(art["id"]):
        return stopped
    if str(exc).startswith("Replaced"):
        # The editor replaced this run (Research again / Copy report again): the newer run continues; never hold it.
        current = await db.articles.find_one({"id": art["id"]}) or dict(art)
        current.pop("_id", None)
        return current
    reason = f"{stage_name} failed ({exc.kind}): {exc}"
    failure = {"task": stage_name, "kind": exc.kind, "provider": getattr(exc, "provider_label", None), "at": now_utc()}
    await audit("ai_error", "article", art["id"], art["site_key"], detail={"stage": stage_name, "kind": exc.kind, "error": str(exc)[:200]})
    return await _update(art["id"], {"stage": "held_review", "held_reason": reason, "ai_failure": failure},
                         _hist("held_review", f"AI {stage_name} error — held for review"))


async def _stopped_by_editor(art_id: str) -> dict | None:
    current = await db.articles.find_one({"id": art_id})
    # An editor's stop or rejection is final for a running step: never overwrite it (e.g. with an AI-error hold).
    if current and (current.get("stage") == "rejected"
                    or (current.get("stage") == "held_review" and current.get("held_reason") == "Stopped by editor.")):
        current.pop("_id", None)
        return current
    return None

logger = logging.getLogger(__name__)
# Owner rule: one article in production at a time (research -> SEO -> thumbnail -> WordPress).
# Held by the scheduler's sequence and by editor-started workflows alike.
ARTICLE_TURN = asyncio.Lock()
IN_PRODUCTION: dict[str, str] = {}  # {"article": id} while an article holds the turn

IMAGE_GENERATION_TIMEOUT_SECONDS = 120
# ChatGPT's image tool can fail on a prompt ("Image generation failed"; live case 28 Sep 2026: it treated the request
# as an edit, three times, and the article waited hours for the owner). The page rules release the job
# (lib/browser_actions.image_failed); the thumbnail is then made in a fresh chat, at most twice. Every request says
# it is a brand-new image.
IMAGE_TOOL_FAILED = re.compile(r"^ChatGPT's image generation failed \(")
MAX_FRESH_IMAGE_RUNS = 2
# ChatGPT's thinking level (owner rule, 28 Sep 2026): Medium for every job; each fresh chat after a failed thumbnail is
# one level higher (High, then Extra High), with a longer wait for the slower answer.
BASE_THINKING_LEVEL = "Medium"
THINKING_LEVELS = ("Low", "Medium", "High", "Extra High")
IMAGE_WAIT_LIMITS = {"Low": 300, "Medium": 300, "High": 420, "Extra High": 600}


def image_thinking_level(fresh: int) -> str:
    """The thinking level of an image job's chat: the base level, one step higher per fresh chat (Extra High at most)."""
    return THINKING_LEVELS[min(THINKING_LEVELS.index(BASE_THINKING_LEVEL) + fresh, len(THINKING_LEVELS) - 1)]
FRESH_IMAGE_NOTE = ("Create this as a brand-new image from the description above; there is no existing or uploaded "
                    "image to edit.")


def _public_image_text(value: str | None, fallback: str = "") -> str:
    """Remove generation-process labels from public WordPress media metadata."""
    text = str(value or "").strip()
    text = re.sub(
        r"(?i)\b(?:AI[- ]generated(?:\s+conceptual)?(?:\s+image)?|generated\s+by\s+(?:AI|OpenAI|Gemini)|"
        r"(?:OpenAI|Gemini|GPT)[- ]?(?:image)?[-\w.]*)\b[\s:;,—-]*",
        "",
        text,
    )
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -—:;,.")
    if text:
        text = text[0].upper() + text[1:]
    return text or fallback


def _public_image_metadata(article: dict, image: dict) -> dict:
    slug = re.sub(r"[^a-z0-9-]+", "-", str(article.get("slug") or "editorial").lower()).strip("-")[:60]
    headline = str(article.get("headline") or "Featured image").strip()
    fmt = image.get("format") or str(image.get("filename", "")).rsplit(".", 1)[-1] or "webp"
    return {
        "filename": f"{slug or 'editorial'}-featured-image.{fmt}",
        "alt_text": _public_image_text(image.get("alt_text"), headline),
        "caption": _public_image_text(image.get("caption"), ""),
        "media_title": _public_image_text(image.get("media_title"), headline)[:100],
    }

STAGES = [
    "selected", "researching", "research_validated", "writing_article", "article_generated",
    "article_validated", "generating_image", "image_ready", "wordpress_draft", "scheduled",
    "published", "verified", "held_review", "rejected", "failed",
]

# Event-handler attributes only inside a tag: "on...=" in source URLs (?context=, &section=) is text, not code.
UNSAFE_HTML = re.compile(r"<\s*(script|iframe|form|object|embed)\b|<[^>]*\son\w+\s*=", re.I)


async def _get_prompt(key: str, default: str) -> str:
    doc = await db.prompts.find_one({"key": key})
    return doc["template"] if doc else default


def _hist(stage: str, note: str = "", actor: str = "system") -> dict:
    return {"stage": stage, "at": now_utc(), "actor": actor, "note": note}


async def create_job(topic: dict, actor: str = "system") -> dict:
    idem = f"{topic['site_key']}:{topic['fingerprint']}"
    existing = await db.articles.find_one({"idempotency_key": idem})
    if existing:  # idempotency: never create a duplicate job for the same topic
        existing.pop("_id", None)
        return existing
    art = {
        "id": new_id(),
        "job_id": new_id(),
        "idempotency_key": idem,
        "site_key": topic["site_key"],
        "topic_id": topic["id"],
        "topic_snapshot": {k: topic.get(k) for k in ("topic", "angle", "category", "focus_keyword", "geography", "risk_flags", "score")},
        "stage": "selected",
        "dossier": None, "dossier_meta": None,
        "validation": None,
        "article": None, "article_meta": None,
        "quality_gate": None,
        "image": None,
        "wp": None,
        "review_flags": topic.get("risk_flags", []),
        "held_reason": None,
        "scheduled_time": None,
        "history": [_hist("selected", "Topic selected into pipeline", actor)],
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.articles.insert_one(dict(art))
    await db.topics.update_one({"id": topic["id"]}, {"$set": {"status": "used"}})
    await audit("job_created", "article", art["id"], topic["site_key"], actor, {"topic": topic["topic"]})
    art.pop("_id", None)
    return art


async def _update(art_id: str, patch: dict, hist: dict | None = None) -> dict:
    patch["updated_at"] = now_utc()
    # Clear a stale hold reason when the article makes forward progress.
    stage = patch.get("stage")
    if stage and "ai_failure" not in patch:
        patch["ai_failure"] = None
    if stage and stage not in ("held_review", "failed", "rejected") and "held_reason" not in patch:
        patch["held_reason"] = None
    ops: dict = {"$set": patch}
    if hist:
        ops["$push"] = {"history": hist}
    await db.articles.update_one({"id": art_id}, ops)
    doc = await db.articles.find_one({"id": art_id})
    doc.pop("_id", None)
    return doc


async def _preflight(art: dict, site: dict, *, ai: bool = False) -> tuple[dict, dict | None]:
    """Reload persisted settings; fail before prompts, SDK calls, media or WP writes."""
    site = await db.sites.find_one({"key": art["site_key"]}) or {}
    from lib.manual_ai import block_reason
    reason = await block_reason(art["site_key"]) if ai else await system_block_reason()
    if not ai and not reason and not is_connected(site):
        reason = "WORDPRESS_NOT_CONNECTED: " + connection_reason(site)
    if not reason and site.get("paused"):
        reason = "SITE_PAUSED: pipeline is paused for this website."
    if not ai and not reason:
        from lib.wordpress import WordPressClient, safe_wp_error
        try:
            result = await WordPressClient(site).verify()
            if not result["passed"]:
                reason = "WORDPRESS_NOT_CONNECTED: " + result["message"]
        except Exception as exc:
            reason = "WORDPRESS_NOT_CONNECTED: " + safe_wp_error(exc)
        if reason:
            await db.sites.update_one({"key": site["key"], "credential_revision": site.get("credential_revision")}, {"$set": {
                "connected": False, "connection_revision": None,
                "connection_test": {"passed": False, "authenticated": False, "simulated": False, "read_only": True,
                                    "checks": [], "message": reason, "tested_at": now_utc()}}})
    if reason:
        await audit("preflight_hold", "article", art["id"], art["site_key"], detail={"reason": reason, "paid_ai_called": False, "wordpress_write_called": False})
        held = await _update(art["id"], {"stage": "held_review", "held_reason": reason}, _hist("held_review", reason))
        return site, held
    return site, None


# ── Stage: research + validation gate ─────────────────────────────────────
def _research_hold_reason(dossier: dict, validation: dict) -> str:
    labels = {
        "has_sources": "No usable sources were found",
        "cited_urls_present": "Source links are missing",
        "claims_mapped": "Claims have no source references",
        "no_unsupported_material_claim": "Some important claims are unverified",
        "claim_urls_match_sources": "Some claim links are missing from the source list",
        "kannada_second_source": "Kannada research needs two independent source publishers",
    }
    reasons = [labels.get(name, name) for name in validation.get("failed_reasons", []) if name != "publication_ready"]
    if "publication_ready" in validation.get("failed_reasons", []):
        notes = [str(note).strip()[:180] for note in dossier.get("not_ready_reasons", []) if str(note).strip()]
        reasons.append("Research says publication is not ready" + (": " + notes[0] if notes else ""))
    return "Research needs review: " + "; ".join(reasons)


async def run_research_stage(art: dict, site: dict) -> dict:
    site, held = await _preflight(art, site, ai=True)
    if held is not None:
        return held
    if art.get("dossier") and (art.get("validation") or {}).get("passed"):
        return art
    # New research follows the report-as-article workflow; the route (Chrome Bridge or API) is chosen
    # inside it. A paid job already submitted or saved under the older dossier flow finishes on that
    # path instead, so it is never resubmitted.
    meta = art.get("dossier_meta") or {}
    if meta.get("report_mode") or not (meta.get("interaction_id") or meta.get("response_id") or meta.get("report")):
        return await _run_report_research(art, site)
    await _update(art["id"], {"stage": "researching"}, _hist("researching", "Deep Research started or resumed"))
    topic = art["topic_snapshot"]
    tmpl = await _get_prompt("research", RESEARCH_PROMPT)
    prompt = tmpl.format(
        site_name=site["name"], topic=topic["topic"], angle=topic.get("angle", ""),
        audience=site["audience"], geography=topic.get("geography", ""),
        current_datetime_with_timezone=now_utc().isoformat(),
        language="Kannada" if site["language"] == "kn" else "English",
    ) + RESEARCH_LANGUAGE_RULES["kn" if site["language"] == "kn" else "en"]
    try:
        dossier, source = await run_research(prompt, {**topic, "id": art["topic_id"], "article_id": art["id"], "site_key": art["site_key"]})
    except AIError as exc:
        return await _ai_hold(art, "research", exc)
    if stopped := await _stopped_by_editor(art["id"]):
        return stopped
    dossier = await resolve_grounding_redirects(dossier)
    saved = await db.articles.find_one({"id": art["id"]})
    dossier = await reconcile_provider_citations(dossier, (saved.get("dossier_meta") or {}).get("report") or "")
    validation = _validate_research(dossier, site.get("language"))
    meta = {**(saved.get("dossier_meta") or {}), "model": source, "prompt_version": (await db.prompts.find_one({"key": "research"}) or {}).get("version", 1),
            "started": art["updated_at"], "completed": now_utc()}
    stage = "research_validated" if validation["passed"] else "held_review"
    patch = {"dossier": dossier, "dossier_meta": meta, "validation": validation, "stage": stage, "research_approval": None}
    if not validation["passed"]:
        patch["held_reason"] = _research_hold_reason(dossier, validation)
    await audit("research_done", "article", art["id"], art["site_key"], detail={"source": source, "passed": validation["passed"]})
    return await _update(art["id"], patch, _hist(stage, f"Research via {source}; validation {'passed' if validation['passed'] else 'FAILED'}"))


_REPORT_CHECK_LABELS = {
    "has_headline": "The report has no headline",
    "complete_report": "The report is too short to be a complete article",
    "not_a_plan": "Gemini returned a research plan, not the article",
    "independent_sources": "Fewer than two source websites",
    "kannada_script": "The article is not written in Kannada script",
}


async def _run_report_research(art: dict, site: dict) -> dict:
    """Deep Research writes the article; the report is the post body.

    Route: Chrome Bridge (Gemini Pro + Deep Research in the owner's signed-in tab, no API cost)
    when the Research route is set to Chrome, otherwise the Gemini Deep Research API (paid credits).
    A job already saved for this article is resumed on its own route, never resubmitted.
    """
    from lib.browser_bridge import enabled as browser_enabled
    from lib.deep_research import research
    from lib.manual_ai import block_reason
    from lib.report_article import DEEP_RESEARCH_ARTICLE_PROMPT, report_to_article, report_validation, research_prompt
    via_chrome = await browser_enabled("research")
    await _update(art["id"], {"stage": "researching"}, _hist("researching", "Deep Research is writing the article via "
                                                             + ("Chrome Bridge (Gemini Pro)" if via_chrome else "the Gemini Deep Research API")))
    saved = await db.articles.find_one({"id": art["id"]})
    meta = dict(saved.get("dossier_meta") or {})
    try:
        if reason := await block_reason(art["site_key"]):
            raise AIError(reason, "safety")
        if capture_url := meta.pop("recopy_url", None):
            # A re-copy requested while another article held the turn: copy it now that this article holds it.
            from lib.browser_bridge import create_recopy_job
            try:
                await create_recopy_job(art["id"], meta["prompt"], capture_url)
            except ValueError as exc:
                raise AIError(str(exc), "browser")
            await db.articles.update_one({"id": art["id"]}, {"$set": {"dossier_meta": meta}})
        if not (meta.get("report_mode") and meta.get("report")):
            if not meta.get("report_mode"):
                template = await _get_prompt("deep_research_article", DEEP_RESEARCH_ARTICLE_PROMPT)
                meta = {"report_mode": True, "provider": "pending",
                        "prompt": research_prompt(template, site, art["topic_snapshot"], now_utc().isoformat()),
                        "status": "queued", "started": now_utc()}
                await db.articles.update_one({"id": art["id"]}, {"$set": {"dossier_meta": meta}})
            await research(meta["prompt"], {**art["topic_snapshot"], "article_id": art["id"], "site_key": art["site_key"]},
                           report_only=True)
            meta = dict((await db.articles.find_one({"id": art["id"]})).get("dossier_meta") or {})
            if via_chrome:
                from lib.browser_bridge import consumed
                await consumed("research", art["id"])
    except AIError as exc:
        fresh_runs = meta.get("auto_research_count", 1 if meta.get("auto_research_again") else 0)
        if STALLED_RESEARCH.search(str(exc)) and fresh_runs < MAX_FRESH_RUNS:
            # Gemini's Deep Research can hang: start a fresh run automatically (twice at most), then ask the owner.
            await db.articles.update_one({"id": art["id"]}, {
                "$set": {"dossier_meta": {"report_mode": True, "prompt": meta["prompt"], "provider": "pending",
                                          "status": "queued", "started": now_utc(), "auto_research_again": True,
                                          "auto_research_count": fresh_runs + 1}},
                "$push": {"history": {"stage": "researching", "at": now_utc(), "actor": "system",
                                      "note": "Deep Research took over 15 minutes; a fresh Deep Research starts"
                                      if "within 15 minutes" in str(exc) else
                                      "Deep Research stalled in Gemini; researching again automatically"}}})
            return await _run_report_research(await db.articles.find_one({"id": art["id"]}), site)
        return await _ai_hold(art, "research", exc)
    if stopped := await _stopped_by_editor(art["id"]):
        return stopped
    article = report_to_article(meta["report"])
    validation = report_validation(meta["report"], article, site["language"])
    first = re.search(r"<p>(.*?)</p>", article["content_html"], re.S)
    summary = re.sub(r"<[^>]+>", " ", first.group(1)).strip() if first else ""
    dossier = {"report_mode": True, "headline": article["headline"], "executive_summary": summary[:800],
               "sources": [{"title": url.split("/")[2].removeprefix("www."), "url": url} for url in article["sources"]],
               "publication_ready": validation["passed"],
               "not_ready_reasons": [_REPORT_CHECK_LABELS.get(n, n) for n in validation["failed_reasons"]]}
    stage = "research_validated" if validation["passed"] else "held_review"
    patch = {"dossier": dossier, "dossier_meta": meta, "validation": validation, "stage": stage, "research_approval": None}
    if not validation["passed"]:
        patch["held_reason"] = "Research needs review: " + "; ".join(dossier["not_ready_reasons"])
    await audit("research_done", "article", art["id"], art["site_key"],
                detail={"source": "gemini-browser", "passed": validation["passed"]})
    return await _update(art["id"], patch, _hist(stage, "Deep Research article copied from Gemini; checks "
                                                 + ("passed" if validation["passed"] else "FAILED")))


async def _run_report_article(art: dict, site: dict) -> dict:
    """ChatGPT (Chrome) reads the Deep Research article and returns SEO assets + thumbnail prompt."""
    from lib.browser_bridge import consumed, enabled, run_job
    from lib.report_article import parse_seo, report_to_article, seo_prompt
    from lib.thumbnail_prompts import design_brief, headline_from_thumbnail
    art = await _update(art["id"], {"stage": "writing_article", "held_reason": None},
                        _hist("writing_article", "ChatGPT is preparing SEO assets and the thumbnail prompt"))
    report = (art.get("dossier_meta") or {}).get("report") or ""
    article = report_to_article(report)
    if len(re.sub(r"<[^>]+>", " ", article["content_html"]).split()) < 150:
        # Never ask for SEO assets without the article: the saved report is missing, so copy it again first.
        await db.articles.update_one({"id": art["id"]}, {"$set": {"dossier": None, "validation": None}})
        return await _ai_hold(art, "SEO assets", AIError(
            "The saved Deep Research report is missing, so no SEO prompt was sent. Research again (or Copy report again) "
            "restores it.", "validation"))
    async def ask(note: str = "") -> str:
        if await enabled("seo"):
            answer = await run_job("seo", art["id"], seo_prompt(article, site) + note, 600, effort=BASE_THINKING_LEVEL)
            await consumed("seo", art["id"])
            return answer
        return await _seo_via_api(article, site, note)

    try:
        try:
            seo = parse_seo(await ask(), site["language"])
        except ValueError as exc:
            # One automatic re-ask (e.g. another script's letter inside a Kannada line) before the owner is asked.
            if stopped := await _stopped_by_editor(art["id"]):
                return stopped
            await _update(art["id"], {}, _hist("writing_article",
                                               f"SEO answer could not be used ({str(exc)[:200]}); asked once more"))
            seo = parse_seo(await ask(f"\n\nIMPORTANT: an earlier answer to this request could not be used ({exc}). "
                                      "Reply again with the complete JSON."), site["language"])
    except ValueError as exc:
        return await _ai_hold(art, "SEO assets", AIError(str(exc), "validation"))
    except AIError as exc:
        return await _ai_hold(art, "SEO assets", exc)
    if stopped := await _stopped_by_editor(art["id"]):
        return stopped
    article.update(seo)
    # Owner rule: the post title matches the thumbnail text (the report's own title is kept for reference).
    article["report_title"] = article.get("headline", "")
    context = " ".join((str(seo.get("seo_title") or ""), str(seo.get("meta_description") or ""),
                        re.sub(r"<[^>]+>", " ", article.get("content_html", ""))))
    article["headline"] = headline_from_thumbnail(seo["thumbnail_headlines"], site["language"], context)
    article.update(
        category=seo.get("category") or site.get("default_category", "News"),
        og_title=seo.get("og_title") or seo["seo_title"],
        og_description=seo.get("og_description") or seo["meta_description"],
        featured_image_brief=design_brief(seo["thumbnail_design"]), approved_external_sources=article.pop("sources"),
        review_flags=[])
    # Owner rule (29 Sep 2026): every post sits under one of the site's header-menu categories.
    menu, menu_how = menu_categories.choose(art["site_key"], seo.get("menu_categories"), article, art.get("topic_snapshot"))
    article["menu_categories"] = menu
    article = _normalize_article(article)
    gate = _quality_gate(article, site, art)
    # Deep Research articles are long-form by design; section count and paragraph length are advisory.
    gate["failed_reasons"] = [n for n in gate["failed_reasons"]
                              if n not in {"clear_section_structure", "readable_paragraphs"}]
    gate["passed"] = not gate["failed_reasons"]
    stage = "article_validated" if gate["passed"] else "held_review"
    patch = {"article": article, "quality_gate": gate, "stage": stage,
             "article_meta": {"model": "gemini-deep-research + chatgpt-seo", "completed": now_utc()}}
    if not gate["passed"]:
        patch["held_reason"] = "Article quality gate failed: " + "; ".join(gate["failed_reasons"])
    await audit("article_done", "article", art["id"], art["site_key"],
                detail={"source": "report+chatgpt-seo", "passed": gate["passed"]})
    menu_note = f"; menu category {' + '.join(m['name'] for m in menu)} ({menu_how})" if menu else ""
    return await _update(art["id"], patch, _hist(stage, "Report article + ChatGPT SEO assets; quality "
                                                 + ("passed" if gate["passed"] else "FAILED") + menu_note))


_STRINGS = {"type": "array", "items": {"type": "string"}}
_THUMBNAIL_SIDE = {"type": "object", "properties": {"title": {"type": "string"}, "intro": {"type": "string"},
                                                   "shows": _STRINGS, "note": {"type": "string"}, "colors": _STRINGS},
                   "required": ["title", "shows", "colors"]}
_SEO_SCHEMA = {"type": "object", "properties": {
    **{k: {"type": "string"} for k in ("seo_title", "meta_description", "focus_keyword", "slug", "category", "excerpt",
                                      "og_title", "og_description", "featured_image_alt_text", "featured_image_caption")},
    "tags": _STRINGS,
    "menu_categories": _STRINGS,
    "thumbnail_headlines": _STRINGS,
    "thumbnail_design": {"type": "object", "properties": {
        "story_type": {"type": "string"}, "emotion": {"type": "string"}, "feel": {"type": "string"}, "rules": _STRINGS,
        "left": _THUMBNAIL_SIDE, "right": _THUMBNAIL_SIDE, "center": _STRINGS, "style_extras": _STRINGS},
        "required": ["story_type", "emotion", "left", "right", "center"]}},
    "required": ["seo_title", "meta_description", "focus_keyword", "slug", "thumbnail_headlines", "thumbnail_design"]}


# Release reasons of a Deep Research that never finished (lib/browser_actions.research_timed_out).
STALLED_RESEARCH = re.compile(r"Deep Research did not finish within|saved Deep Research is not progressing")
MAX_FRESH_RUNS = 2  # automatic fresh runs per article; a run the owner starts resets the count


def needs_thumbnail_design(art: dict) -> bool:
    """An unpublished Deep Research article from before the owner's thumbnail format: run its SEO step again
    (for the thumbnail headlines and design) before the thumbnail."""
    return bool((art.get("dossier_meta") or {}).get("report_mode") and art.get("article") and not art.get("image")
                and not (art.get("article") or {}).get("thumbnail_design"))


async def _seo_via_api(article: dict, site: dict, note: str = "") -> str:
    """API route for SEO assets: one small Gemini call (the same instructions ChatGPT receives)."""
    from lib.ai import _gemini_call, _retry
    from lib.report_article import seo_prompt
    model = os.environ.get("GEMINI_FAST_MODEL", "gemini-flash-latest")
    return await _retry(lambda: _gemini_call(model, "You are a meticulous news SEO editor. Reply with JSON only.",
                                             seo_prompt(article, site) + note, False, _SEO_SCHEMA), "Gemini SEO assets")


async def repair_citation_source_list(art: dict, site: dict) -> dict:
    """Recheck a saved structural-only hold against provider citations, without paid AI."""
    saved = await db.articles.find_one({"id": art["id"]})
    if not saved or saved.get("stage") != "held_review":
        return saved or art
    dossier = {**(saved.get("dossier") or {}), "sources": list((saved.get("dossier") or {}).get("sources") or [])}
    report = (saved.get("dossier_meta") or {}).get("report") or ""
    dossier = await reconcile_provider_citations(dossier, report)
    validation = _validate_research(dossier, site.get("language"))
    stage = "research_validated" if validation["passed"] else "held_review"
    reason = None if validation["passed"] else _research_hold_reason(dossier, validation)
    await audit("citation_source_recheck", "article", art["id"], art["site_key"],
                detail={"passed": validation["passed"], "source_count": len(dossier.get("sources", []))})
    return await _update(art["id"], {"dossier": dossier, "validation": validation,
                                   "stage": stage, "held_reason": reason},
                         _hist(stage, "Provider citation sources rechecked; " + ("validation passed" if validation["passed"] else "review still required")))


# ── Stage: article generation + quality gate ──────────────────────────────
async def run_article_stage(art: dict, site: dict) -> dict:
    site, held = await _preflight(art, site, ai=True)
    if held is not None:
        return held
    if not art.get("dossier"):
        raise ValueError("research must complete before article generation")
    if not (art.get("validation") or {}).get("passed"):
        return await _ai_hold(art, "article generation", AIError("Research validation must pass first.", "validation"))
    if (art.get("dossier") or {}).get("report_mode"):
        return await _run_report_article(art, site)
    art = await _update(art["id"], {"stage": "writing_article", "held_reason": None},
                        _hist("writing_article", "Creating the formatted article from validated research"))
    topic = art["topic_snapshot"]
    tmpl = await _get_prompt("article", ARTICLE_PROMPT)
    prompt = tmpl.format(
        site_name=site["name"], site_profile=site.get("brand_style", site["name"]),
        audience=site["audience"], language="Kannada" if site["language"] == "kn" else "English",
        tone=site.get("tone", "authoritative, clear"),
        word_count_range=f"{site.get('word_count_min', 600)}-{site.get('word_count_max', 1100)}",
        focus_keyword=topic.get("focus_keyword", ""),
        research_dossier=json.dumps(art["dossier"], ensure_ascii=False),
        language_rule=KANNADA_RULE if site["language"] == "kn" else ENGLISH_RULE,
    )
    from lib.thumbnail_prompts import HEADLINE_RULE
    prompt += HEADLINE_RULE
    try:
        article, source = await run_article(prompt, {**topic, "id": art["topic_id"]}, art["dossier"], site["language"])
    except AIError as exc:
        return await _ai_hold(art, "article generation", exc)
    if stopped := await _stopped_by_editor(art["id"]):
        return stopped
    article = _normalize_article(article)
    kannada_audits = []
    if site["language"] == "kn" and os.environ.get("KANNADA_AI_AUDIT", "false").lower() == "true":
        from lib.kannada_audit import editorial_audit, revise_article
        try:
            await _update(art["id"], {}, _hist("writing_article", "Kannada audit 1/2: independent language and dossier review"))
            first = await editorial_audit(article, art["dossier"])
            kannada_audits.append(first)
            if not first["passed"]:
                await _update(art["id"], {}, _hist("writing_article", "Correcting Kannada copy and rechecking source consistency"))
                article, source = await revise_article(article, art["dossier"], first["issues"])
                article = _normalize_article(article)
                await _update(art["id"], {}, _hist("writing_article", "Kannada audit 2/2: reviewing corrected article"))
                kannada_audits.append(await editorial_audit(article, art["dossier"]))
        except AIError as exc:
            await _update(art["id"], {"article": article, "article_meta": {"model": source, "kannada_audits": kannada_audits}})
            return await _ai_hold(art, "Kannada editorial audit", exc)
    gate = _quality_gate(article, site, art)
    if kannada_audits:
        final_audit = kannada_audits[-1]
        gate["checks"].append({"name": "kannada_editorial_audit", "passed": final_audit["passed"],
                               "note": "; ".join(final_audit["issues"]) or "language, readability, and dossier consistency checked"})
        if not final_audit["passed"]:
            gate["passed"] = False
            gate["failed_reasons"].append("kannada_editorial_audit")
    meta = {"model": source, "prompt_version": (await db.prompts.find_one({"key": "article"}) or {}).get("version", 1),
            "completed": now_utc()}
    if kannada_audits:
        meta["kannada_audits"] = kannada_audits
    stage = "article_validated" if gate["passed"] else "held_review"
    patch = {"article": article, "article_meta": meta, "quality_gate": gate,
             "review_flags": sorted(set(art.get("review_flags", []) + article.get("review_flags", []))), "stage": stage}
    if not gate["passed"]:
        patch["held_reason"] = "Article quality gate failed: " + "; ".join(gate["failed_reasons"])
    await audit("article_done", "article", art["id"], art["site_key"], detail={"source": source, "passed": gate["passed"]})
    return await _update(art["id"], patch, _hist(stage, f"Article via {source}; quality {'passed' if gate['passed'] else 'FAILED'}"))


def _normalize_article(a: dict) -> dict:
    """Trim SEO fields to spec limits and sanitise the slug — normalise rather than hold."""
    def cut(s: str, n: int) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"

    a["seo_title"] = cut(a.get("seo_title") or a.get("headline", ""), 60)
    a["og_title"] = cut(a.get("og_title") or a.get("seo_title", ""), 60)
    md = (a.get("meta_description") or a.get("dek") or "").strip()
    if len(md) > 160:
        md = md[:157].rstrip() + "\u2026"
    a["meta_description"] = md
    a["og_description"] = cut(a.get("og_description") or md, 200)
    slug = re.sub(r"[^a-z0-9]+", "-", (a.get("slug") or a.get("headline", "")).lower()).strip("-")[:70]
    a["slug"] = slug or "news-analysis"
    return a


def _quality_gate(article: dict, site: dict, art: dict) -> dict:
    checks, failed = [], []

    def chk(name: str, ok: bool, note: str = ""):
        checks.append({"name": name, "passed": ok, "note": note})
        if not ok:
            failed.append(name)

    html = article.get("content_html", "") or ""
    seo_title = article.get("seo_title", "") or ""
    meta_desc = article.get("meta_description", "") or ""
    chk("has_headline", bool(article.get("headline")))
    chk("has_body", len(html) > 200, f"{len(html)} chars")
    h2_count = len(re.findall(r"<h2(?:\s|>)", html, re.IGNORECASE))
    paragraph_lengths = [len(re.sub(r"<[^>]+>", "", p)) for p in re.findall(r"<p(?:\s[^>]*)?>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)]
    # Long-form reporting can legitimately need more than six sections. Ten keeps
    # the page scannable while avoiding false holds on well-structured articles.
    chk("clear_section_structure", 3 <= h2_count <= 10, f"{h2_count} H2 sections")
    chk("readable_paragraphs", bool(paragraph_lengths) and max(paragraph_lengths) <= 700,
        f"longest paragraph {max(paragraph_lengths, default=0)} chars")
    chk("no_unsafe_html", not UNSAFE_HTML.search(html), "no script/iframe/form/handlers")
    chk("no_h1_in_body", "<h1" not in html.lower(), "WordPress supplies the H1")
    chk("seo_title_len", 10 <= len(seo_title) <= 70, f"{len(seo_title)} chars")
    chk("meta_desc_len", 50 <= len(meta_desc) <= 200, f"{len(meta_desc)} chars")
    chk("has_slug", bool(article.get("slug")))
    chk("category_valid", article.get("category") is not None)
    # Kannada prose must be predominantly readable Kannada, not a token glyph.
    if site["language"] == "kn":
        from lib.kannada_audit import language_checks
        for name, passed, note in language_checks(article):
            chk(name, passed, note)
    # risk flags don't fail the gate but are surfaced for human review
    checks.append({"name": "risk_flags", "passed": True, "note": ", ".join(art.get("review_flags", [])) or "none"})
    return {"passed": len(failed) == 0, "checks": checks, "failed_reasons": failed}


# ── Stage: featured image ─────────────────────────────────────────────────
async def run_image_stage(art: dict, site: dict, brief: str | None = None) -> dict:
    site, held = await _preflight(art, site, ai=True)
    if held is not None:
        return held
    art = await _update(art["id"], {"stage": "generating_image", "held_reason": None},
                        _hist("generating_image", "ChatGPT is creating the complete thumbnail (image and headline text)"))
    article = art.get("article") or {}
    brief = brief or article.get("featured_image_brief") or art["topic_snapshot"]["topic"]
    template_key = "owner_thumbnail_format"
    try:
        from lib.browser_bridge import enabled
        from lib.thumbnail_prompts import thumbnail_prompt_for
        from lib.thumbnails import validate_headlines
        headlines = validate_headlines(article.get("thumbnail_headlines"), site["language"])
        # The owner's format: the whole poster, headline text included, is made by the image model; the app adds none.
        prompt = thumbnail_prompt_for(article, site["language"], headlines, brief)
        if await enabled("image"):
            import base64, io
            from PIL import Image
            # Opening the chat, typing, sending and ChatGPT drawing the image often take several minutes;
            # the extension separately stops a generation that runs over 5 minutes after sending.
            b64 = await _image_via_browser(art, prompt)
            # Kept exactly as ChatGPT made it (no text added, nothing cropped); only stored as WEBP.
            with Image.open(io.BytesIO(base64.b64decode(b64))) as generated:
                if generated.format != "WEBP":
                    buf = io.BytesIO()
                    generated.convert("RGB").save(buf, "WEBP", quality=95)
                    b64 = base64.b64encode(buf.getvalue()).decode()
            data_uri, source, fmt = "data:image/webp;base64," + b64, "chatgpt-browser", "webp"
        else:
            data_uri, source, fmt = await _api_thumbnail(brief, site, prompt, article)
    except (ValueError, OSError) as exc:
        return await _ai_hold(art, "featured image", AIError(str(exc), "validation"))
    except TimeoutError:
        return await _ai_hold(art, "featured image", AIError("Image generation exceeded the 120-second limit. Select Retry to reconnect.", "timeout"))
    except AIError as exc:
        return await _ai_hold(art, "featured image", exc)
    if stopped := await _stopped_by_editor(art["id"]):
        return stopped
    image = {
        "data_uri": data_uri, "source": source, "brief": brief, "format": fmt,
        "alt_text": _public_image_text(article.get("featured_image_alt_text"), article.get("headline", brief[:120])),
        "caption": _public_image_text(article.get("featured_image_caption"), ""),
        "media_title": _public_image_text(article.get("headline"), "Featured image")[:100],
        "aspect_ratio": "16:9", "status": "generated", "synthetic": True,
        "headlines": article.get("thumbnail_headlines"), "template_key": template_key,
    }
    image.update(_public_image_metadata(article, image))
    await audit("image_done", "article", art["id"], art["site_key"], detail={"source": source})
    result = await _update(art["id"], {"image": image, "stage": "image_ready"}, _hist("image_ready", f"Featured image via {source}"))
    if source == "chatgpt-browser":
        from lib.browser_bridge import consumed
        await consumed("image", art["id"])
    return result


async def _image_via_browser(art: dict, prompt: str) -> str:
    """ChatGPT's thumbnail (base64). A failed generation is made again in a fresh chat, MAX_FRESH_IMAGE_RUNS times
    per article (the count is stored, so a restart does not start it again; the owner's Retry or Image resets it)."""
    from lib.browser_bridge import run_job
    request = prompt + "\n\n" + FRESH_IMAGE_NOTE + "\n\nGenerate this thumbnail image now."
    for fresh in range(min(int(art.get("image_fresh_runs") or 0), MAX_FRESH_IMAGE_RUNS), MAX_FRESH_IMAGE_RUNS + 1):
        try:
            # A job from this same owner prompt (e.g. started before a restart) is reused, never replaced.
            level = image_thinking_level(fresh)
            return await run_job("image", art["id"], request, 900, same_prompt=prompt, effort=level,
                                 wait_limit_seconds=IMAGE_WAIT_LIMITS[level])
        except AIError as exc:
            if (not IMAGE_TOOL_FAILED.search(str(exc)) or await _stopped_by_editor(art["id"])
                    or await _retry_blocked(art["site_key"])):
                raise
            if fresh == MAX_FRESH_IMAGE_RUNS:
                raise AIError(f"{exc} It failed in {fresh + 1} ChatGPT chats; press Retry to try again.", exc.kind) from None
        await _update(art["id"], {"image_fresh_runs": fresh + 1}, _hist("generating_image", "ChatGPT's image generation failed; creating the thumbnail "
                                           f"again in a new chat at {image_thinking_level(fresh + 1)} thinking "
                                           f"(automatic retry {fresh + 1} of {MAX_FRESH_IMAGE_RUNS})"))
    raise AssertionError("unreachable")


async def _retry_blocked(site_key: str) -> str | None:
    """Why no automatic retry may start now (paused app or website, kill switch), else None."""
    from lib.manual_ai import block_reason
    return await block_reason(site_key)


async def _api_thumbnail(brief, site, template, article):
    return await asyncio.wait_for(
        generate_image(brief, site["name"], site.get("brand_style", "editorial"),
                       template=template, headlines=article.get("thumbnail_headlines"), language=site["language"]),
        timeout=IMAGE_GENERATION_TIMEOUT_SECONDS)


# ── Stage: WordPress publish/draft/schedule (live, verified, fail-closed) ──
_WP_WRITES: dict[str, asyncio.Lock] = {}


async def wordpress_write(art: dict, site: dict, target_status: str, scheduled_time: str | None = None) -> dict:
    """target_status: draft | future(scheduled) | publish. Returns updated article.

    One WordPress write per article at a time: the scheduler's hand-off and the editor's Publish now / Schedule can
    meet, and the later write works from the saved record, so it updates the same post instead of creating another.
    A post that is already live is never moved back to scheduled or draft.
    """
    async with _WP_WRITES.setdefault(art["id"], asyncio.Lock()):
        if saved := await db.articles.find_one({"id": art["id"]}):
            saved.pop("_id", None)
            art = saved
        if (art.get("wp") or {}).get("status") == "publish" and target_status != "publish":
            return art
        return await _wordpress_write(art, site, target_status, scheduled_time)


async def _wordpress_write(art: dict, site: dict, target_status: str, scheduled_time: str | None = None) -> dict:
    site, held = await _preflight(art, site)
    if held is not None:
        return held
    system = await db.system_settings.find_one({"id": "system"}) or {}
    safety = RuntimeSafety.from_env()
    if (system.get("mode") == "research_only" or safety.operating_mode == "research_only"
            or (target_status in ("publish", "future") and (
                not safety.auto_publish_enabled or safety.operating_mode != "auto"
                or system.get("mode") != "auto" or not site.get("auto_publish")))):
        return await _update(art["id"], {"stage": "held_review", "held_reason": "Publishing/scheduling requires explicit global and per-site automatic-publishing approval."}, _hist("held_review", "Operating mode blocks write"))
    if not art.get("image") or not (art.get("validation") or {}).get("passed") or not (art.get("quality_gate") or {}).get("passed"):
        return await _update(art["id"], {"stage": "held_review", "held_reason": "Research, quality and image gates must pass before a WordPress write."}, _hist("held_review", "Quality gates incomplete"))
    article = art.get("article") or {}
    # Optional owner-configured high-risk gate.
    flags = art.get("review_flags", [])
    if (safety.high_risk_review_required and flags and not art.get("approval")
            and target_status in ("publish", "future")):
        await audit("held_review", "article", art["id"], art["site_key"], detail={"flags": flags})
        return await _update(art["id"], {
            "stage": "held_review",
            "held_reason": "High-risk subject requires human editorial sign-off: " + ", ".join(flags),
        }, _hist("held_review", "Held: high-risk subject"))

    if has_credentials(site):
        try:
            return await _wp_write_live(art, site, article, target_status, scheduled_time)
        except WPError as exc:
            note = str(exc)
            stage = "failed" if not exc.retryable else art["stage"]
            await audit("wordpress_error", "article", art["id"], art["site_key"], detail={"error": note[:200]})
            return await _update(art["id"], {"stage": stage, "held_reason": f"WordPress write failed: {note[:200]}"},
                                 _hist(stage, f"WordPress {target_status} FAILED — {note[:120]}"))
    return await _update(art["id"], {"stage": "held_review", "held_reason": "WORDPRESS_NOT_CONNECTED"}, _hist("held_review", "No WordPress credentials"))


async def _post_categories(wp, art: dict, article: dict, existing_id: int | None) -> tuple[list[int], int | None, list[dict]]:
    """(categories, Rank Math primary to set or None, menu categories). Owner rules (29 Sep 2026): the post's
    header-menu categories first, then its topic category (a new one is created under the main menu category);
    an existing post keeps every category it has, and one that already has a menu category keeps its own."""
    menu = article.get("menu_categories") or menu_categories.choose(art["site_key"], None, article, art.get("topic_snapshot"))[0]
    primary = menu[0]["id"] if menu else None
    topic = await wp.resolve_term("categories", article["category"], parent=primary) if article.get("category") else None
    cats = list(dict.fromkeys([m["id"] for m in menu] + ([topic] if topic else [])))
    if existing_id:
        current = [c for c in ((await wp.read_post(existing_id)).get("categories") or []) if isinstance(c, int)]
        if set(current) & menu_categories.menu_ids(art["site_key"]):
            return list(dict.fromkeys(current + ([topic] if topic else []))), None, menu
        cats = list(dict.fromkeys(cats + current))
    return cats, primary, menu


def _stage_for(target_status: str) -> str:
    return {"draft": "wordpress_draft", "future": "scheduled"}.get(target_status, "verified")


async def _wp_write_live(art: dict, site: dict, article: dict, target_status: str, scheduled_time: str | None) -> dict:
    from lib.wordpress import WordPressClient

    wp = WordPressClient(site)
    existing_id = (art.get("wp") or {}).get("post_id") if (art.get("wp") or {}).get("simulated") is False else None
    # WordPress will always attribute the post to the authenticated application-
    # password account. A display-name field must not block an otherwise verified write.
    me = await wp._call("GET", f"{wp.api}/users/me", params={"context": "edit"})
    if type(me.get("id")) is not int or me["id"] <= 0:
        raise WPError("Authenticated WordPress account did not return a valid author ID.")
    author_id = me["id"]

    # media (idempotent-ish: only upload if we don't already have one)
    media_id = (art.get("wp") or {}).get("featured_media_id") if (art.get("wp") or {}).get("simulated") is False else None
    img = art.get("image") or {}
    data_uri = img.get("data_uri", "")
    if not media_id and data_uri.startswith("data:image/"):
        import base64
        header, b64 = data_uri.split(",", 1)
        content_type = header.split(";")[0][5:] or "image/png"  # strip "data:"
        raw = base64.b64decode(b64)
        public_media = _public_image_metadata(article, img)
        media_slug = public_media["filename"].rsplit(".", 1)[0]
        existing_media = await wp.find_media_by_slug(media_slug)
        media_id = existing_media.get("id") if existing_media else None
        if not media_id:
            media_id = await wp.upload_media(raw, public_media["filename"],
                                             public_media["alt_text"], public_media["caption"],
                                             public_media["media_title"], content_type=content_type)

    cats, primary, menu = await _post_categories(wp, art, article, existing_id)
    tags = [await wp.resolve_term("tags", t) for t in (article.get("tags") or [])[:6]]

    from lib.wp_blocks import to_blocks
    body: dict = {
        "title": article.get("headline", ""),
        # As WordPress blocks, so the site's block styles give readers a premium layout (owner, 28 Sep 2026).
        "content": to_blocks(article.get("content_html", ""), site.get("language", "en")),
        "excerpt": article.get("excerpt", ""),
        "slug": article.get("slug", "post"),
        "status": target_status,
        "categories": cats,
        "tags": tags,
    }
    if media_id:
        body["featured_media"] = media_id
    was = (art.get("wp") or {}).get("status")
    if scheduled_time and target_status == "future":
        body["date"] = scheduled_time
    elif target_status == "publish" and was == "future" and not scheduled_time:
        # Publish now: WordPress keeps a scheduled post's future date (so it would stay scheduled) unless it changes.
        body["date"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat()

    body["author"] = author_id
    try:
        post = await wp.save_post(body, existing_id)
    except WPError:
        # WordPress may create the post and then time out or fail while plugins react to it. Adopt that post only
        # when it is provably this article's (same slug, title, account and featured image); otherwise stop as before.
        post = None if existing_id else await wp.find_own_post(body)
        if not post:
            raise
        if post.get("status") in {"publish", "future"}:
            target_status = post["status"]  # record what WordPress actually did
    if not isinstance(post, dict) or type(post.get("id")) is not int or post["id"] <= 0 or not str(post.get("link", "")).startswith(wp.base + "/"):
        raise WPError("WordPress creation response has no valid post ID and same-site permalink. Publication is unverified.")
    canonical = post["link"]
    # Retain the real ID immediately for safe recovery if any subsequent check fails.
    await db.articles.update_one({"id": art["id"]}, {"$set": {"wp": {"simulated": False, "post_id": post["id"], "public_url": canonical, "status": post.get("status"), "featured_media_id": media_id}}})
    seo_persisted = await wp.write_seo(post["id"], article, canonical)
    primary_set = await wp.set_primary_category(post["id"], primary) if primary else None

    readback = await wp.read_post(post["id"])
    if target_status == "future" and readback.get("status") == "publish" and str(readback.get("link", "")).startswith(wp.base + "/"):
        # WordPress already published the scheduled post (its time came, or the site publishes at once): it is live.
        target_status, canonical = "publish", readback["link"]
        post = {**post, "status": "publish", "link": canonical}
    verification = {"rest_returned_id": True, "creation_response_ok": post.get("status") == target_status,
                    "readback_ok": readback.get("id") == post["id"] and readback.get("link") == canonical and readback.get("status") == target_status,
                    "readback_status": readback.get("status")}
    if target_status == "publish":
        verification.update(await wp.verify_public(canonical))
    else:
        verification["public_page_ok"] = None

    wp_result = {
        "simulated": False,
        "post_id": post["id"],
        "status": post.get("status", target_status),
        "edit_url": f"{wp.base}/wp-admin/post.php?post={post['id']}&action=edit",
        "public_url": canonical,
        "scheduled_time": scheduled_time,
        "author": site.get("author", "editorial"),
        "category": article.get("category"),
        "categories": cats,
        "menu_categories": [m["name"] for m in menu],
        "primary_category_set": primary_set,
        "tags": article.get("tags", []),
        "featured_media_id": media_id,
        "seo_persisted": seo_persisted,
        "seo_plugin": site.get("seo_plugin", "native"),
        "verification": verification,
        "verified_at": now_utc(),
    }
    passed = verification["creation_response_ok"] and verification["readback_ok"] and (target_status != "publish" or verification.get("public_page_ok") is True)
    stage = _stage_for(target_status) if passed else "held_review"
    patch = {"wp": wp_result, "stage": stage}
    if not passed:
        patch["held_reason"] = "FALSE_OR_UNVERIFIED_PUBLISH_STATUS"
    if scheduled_time:
        patch["scheduled_time"] = scheduled_time
    elif passed and target_status == "publish" and was != "publish":
        patch["scheduled_time"] = None  # published now: its booked slot is free again
    await audit("wordpress_write", "article", art["id"], art["site_key"],
                detail={"status": target_status, "post_id": post["id"], "permalink": canonical, "timestamp": now_utc(),
                        "verification": verification, "verification_passed": passed, "simulated": False, "seo_persisted": seo_persisted})
    return await _update(art["id"], patch, _hist(stage, f"WordPress {target_status} (LIVE) → post #{post['id']}"))
