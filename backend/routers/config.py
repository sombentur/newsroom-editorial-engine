"""Config & read endpoints: system settings, sites, prompts, health, audit, dashboard stats."""

import re
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from lib.db import db
from lib.util import audit, clean, clean_all, new_id, now_utc, redact_site
from lib.runtime import RuntimeSafety
from lib.safety import verified_wp_record
from lib.scheduler import _as_utc, next_publish_slot
from lib.wp_credentials import encrypt_password, normalize_base_url, normalize_password, CredentialError, is_connected
from models.schemas import GenericOk, PromptUpdate, SecretsUpdate, SiteUpdate, SystemUpdate

router = APIRouter()


# ── System settings ──────────────────────────────────────────────
@router.get("/system")
async def get_system():
    doc = await db.system_settings.find_one({"id": "system"})
    if not doc:
        doc = {"id": "system", "mode": "review", "global_paused": False, "killswitch": False,
               "scheduler_enabled": False, "updated_at": now_utc()}
        await db.system_settings.insert_one(dict(doc))
    doc.setdefault("scheduler_enabled", False)
    doc.setdefault("auto_research", True)
    if RuntimeSafety.from_env().dry_run or doc.get("repair_lock", True):
        # The owner may still choose and inspect an editorial mode locally. Dry-run
        # independently blocks every WordPress write and the scheduler.
        doc.update(scheduler_enabled=False, dry_run=True)
    else:
        doc["dry_run"] = False
    from lib.manual_ai import enabled
    doc["manual_ai_enabled"] = enabled()
    doc["high_risk_review_required"] = RuntimeSafety.from_env().high_risk_review_required
    return clean(doc)


@router.patch("/system")
async def update_system(body: SystemUpdate):
    patch = body.model_dump(exclude_none=True)
    system = await db.system_settings.find_one({"id": "system"}) or {}
    if RuntimeSafety.from_env().dry_run or system.get("repair_lock", True):
        if patch.get("scheduler_enabled") is True:
            raise HTTPException(409, "Local safety mode keeps the scheduler disabled. Operating-mode selection remains available.")
    patch["updated_at"] = now_utc()
    await db.system_settings.update_one({"id": "system"}, {"$set": patch}, upsert=True)
    await audit("system_update", "system", "system", detail=patch)
    doc = await db.system_settings.find_one({"id": "system"})
    return clean(doc)


# ── Sites ────────────────────────────────────────────────────────
@router.get("/sites")
async def list_sites():
    docs = await db.sites.find().sort("key", 1).to_list(10)
    return [redact_site(d) for d in docs]


@router.get("/sites/{key}")
async def get_site(key: str):
    doc = await db.sites.find_one({"key": key})
    if not doc:
        raise HTTPException(404, "site not found")
    return redact_site(doc)


@router.put("/sites/{key}")
async def update_site(key: str, body: SiteUpdate):
    doc = await db.sites.find_one({"key": key})
    if not doc:
        raise HTTPException(404, "site not found")
    patch = body.model_dump(exclude_none=True, exclude={"wp_app_password", "revoke_wp_password"})
    # The site's domain is whatever the owner configures; the WordPress base URL must stay on it.
    domain = str(patch.get("domain", doc.get("domain") or "")).strip().lower().removeprefix("www.")
    if "domain" in patch and not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
        raise HTTPException(422, "Enter the website's domain name, for example news.example.com.")
    if patch.get("wp_base_url"):
        try:
            host = (urlsplit(patch["wp_base_url"].strip()).hostname or "").lower().removeprefix("www.")
        except ValueError:
            host = ""
        if host and ("domain" not in patch or not domain):
            domain = host  # the base URL defines the domain when none was set
    if domain != (doc.get("domain") or ""):
        patch["domain"] = domain
    expected_domain = domain
    system = await db.system_settings.find_one({"id": "system"}) or {}
    if patch.get("auto_publish") is True and (RuntimeSafety.from_env().dry_run or system.get("repair_lock", True)):
        raise HTTPException(409, "Disable dry-run and release the repair lock before enabling automatic publishing.")
    try:
        if "wp_base_url" in patch:
            patch["wp_base_url"] = normalize_base_url(patch["wp_base_url"], expected_domain) if expected_domain else "" if expected_domain else ""
        if "timezone" in patch:
            ZoneInfo(patch["timezone"])
        minimum = patch.get("word_count_min", doc["word_count_min"])
        maximum = patch.get("word_count_max", doc["word_count_max"])
        if not 100 <= minimum <= maximum <= 10000:
            raise ValueError()
        if "daily_quota" in patch and not 1 <= patch["daily_quota"] <= 20:
            raise ValueError()
        if "publish_times" in patch:
            import re
            if len(patch["publish_times"]) > 20 or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in patch["publish_times"]):
                raise ValueError()
    except CredentialError as exc:
        raise HTTPException(422, str(exc)) from None
    except (ValueError, KeyError):
        raise HTTPException(422, "Check timezone, publishing times, quota and word-count limits.") from None
    changed_credentials = any(patch.get(k, doc.get(k)) != doc.get(k) for k in ("wp_base_url", "wp_username", "author"))
    ops = {}
    if body.revoke_wp_password:
        ops["$unset"] = {"wp_password_ciphertext": "", "wp_app_password": ""}
        changed_credentials = True
    elif body.wp_app_password and body.wp_app_password.get_secret_value().strip():
        try:
            value = normalize_password(body.wp_app_password.get_secret_value())
            patch["wp_password_ciphertext"] = encrypt_password(value)
        except CredentialError as exc:
            raise HTTPException(422, str(exc)) from None
        ops["$unset"] = {"wp_app_password": ""}
        changed_credentials = True
    if changed_credentials:
        patch.update(credential_revision=new_id(), connected=False, connection_revision=None, connection_test=None)
    patch["updated_at"] = now_utc()
    ops["$set"] = patch
    await db.sites.update_one({"key": key}, ops)
    await audit("credential_revoked" if body.revoke_wp_password else "site_update", "site", key, key,
                detail={"fields": [k for k in patch if k != "wp_password_ciphertext"], "credential_changed": changed_credentials})
    return redact_site(await db.sites.find_one({"key": key}))


@router.post("/sites/{key}/connection-test")
async def connection_test(key: str):
    doc = await db.sites.find_one({"key": key})
    if not doc:
        raise HTTPException(404, "site not found")
    from lib.wordpress import WordPressClient, safe_wp_error
    try:
        # This explicit owner action is allowed in dry-run; the client cannot write.
        result = await WordPressClient(doc, read_only=True).verify()
    except Exception as exc:
        result = {"passed": False, "authenticated": False, "checks": [], "simulated": False, "message": safe_wp_error(exc)}
    result.update(tested_at=now_utc(), read_only=True)
    saved = await db.sites.update_one({"key": key, "credential_revision": doc.get("credential_revision")}, {"$set": {
        "connected": bool(result["passed"]), "connection_test": result, "connection_revision": doc.get("credential_revision")}})
    if not saved.matched_count:
        raise HTTPException(409, "WordPress settings changed during the test. Test the saved settings again.")
    await audit("connection_test", "site", key, key, detail={"passed": result["passed"], "simulated": False})
    return result


@router.get("/prompts")
async def list_prompts():
    return clean_all(await db.prompts.find().sort("key", 1).to_list(20))


@router.put("/prompts/{key}")
async def update_prompt(key: str, body: PromptUpdate):
    doc = await db.prompts.find_one({"key": key})
    if not doc:
        raise HTTPException(404, "prompt not found")
    version = doc.get("version", 1) + 1
    versions = doc.get("versions", [])
    versions.append({"version": doc.get("version", 1), "template": doc["template"], "at": now_utc()})
    patch = {"template": body.template, "version": version, "versions": versions, "updated_at": now_utc()}
    if body.name:
        patch["name"] = body.name
    await db.prompts.update_one({"key": key}, {"$set": patch})
    await audit("prompt_update", "prompt", key, detail={"version": version})
    return clean(await db.prompts.find_one({"key": key}))


@router.post("/prompts/{key}/restore/{version}")
async def restore_prompt(key: str, version: int):
    doc = await db.prompts.find_one({"key": key})
    if not doc:
        raise HTTPException(404, "prompt not found")
    target = next((v for v in doc.get("versions", []) if v["version"] == version), None)
    if not target:
        raise HTTPException(404, "version not found")
    return await update_prompt(key, PromptUpdate(template=target["template"]))


# ── AI provider secrets (owner's OWN keys — server-side, masked) ──
@router.get("/secrets")
async def get_secrets():
    from lib import secrets as sec
    return await sec.status()


@router.put("/secrets")
async def update_secrets(body: SecretsUpdate):
    from lib import secrets as sec
    await sec.save_secrets(body.model_dump(exclude_none=True))
    await audit("secrets_update", "secrets", "ai", detail={"fields": list(body.model_dump(exclude_none=True).keys())})
    return await sec.status()


@router.post("/secrets/test/{target}")
async def test_provider(target: str):
    from lib.ai import gemini_ping, openai_ping
    if target == "gemini-research":
        result = await gemini_ping("research")
    elif target == "gemini-writing":
        result = await gemini_ping("writing")
    elif target == "openai-image":
        result = await openai_ping()
    else:
        raise HTTPException(404, "unknown test target")
    await audit("provider_test", "secrets", target, detail={"ok": result.get("ok")})
    return result


# ── Integration health ───────────────────────────────────────────
@router.get("/health")
async def integration_health():
    from lib import secrets as sec

    st = await sec.status()
    sites = await db.sites.find().to_list(10)
    site_health = [{
        "key": s["key"], "name": s["name"], "domain": s["domain"],
        "connected": is_connected(s),
        "last_test": (s.get("connection_test") or {}).get("passed"),
        "mode": "authenticated" if is_connected(s) else "not_tested",
    } for s in sites]
    return {
        "wordpress": site_health,
        "gemini": {"configured": st["gemini_configured"], "key_masked": st["gemini_key_masked"],
                   "research_model": st["research_model"], "writing_model": st["writing_model"],
                   "status": "configured_not_tested" if st["gemini_configured"] else "not_configured",
                   "mode": "own Google Gemini API key (Deep Research via Gemini Interactions)"},
        "image": {"configured": st["openai_configured"], "key_masked": st["openai_key_masked"],
                  "model": st["image_model"],
                  "status": "configured_not_tested" if st["openai_configured"] else "not_configured",
                  "mode": "own OpenAI API key (official Images API)"},
        "emergent_used": False,
        "checked_at": now_utc(),
    }


# ── Audit log ────────────────────────────────────────────────────
@router.get("/audit")
async def audit_log(limit: int = 100, site_key: str | None = None):
    q = {"site_key": site_key} if site_key else {}
    return clean_all(await db.audit_logs.find(q).sort("at", -1).to_list(min(limit, 300)))


# ── Companion WordPress plugin download ──────────────────────────
@router.get("/plugin/download")
async def plugin_download():
    from pathlib import Path

    from fastapi.responses import PlainTextResponse

    path = Path(__file__).parent.parent / "wordpress_plugin" / "newsroom-seo-bridge.php"
    return PlainTextResponse(
        path.read_text(),
        headers={"Content-Disposition": 'attachment; filename="newsroom-seo-bridge.php"'},
    )


# ── Dashboard stats ──────────────────────────────────────────────
def _next_run(site: dict, articles: list[dict]) -> str | None:
    if not site.get("publish_times"):
        return None
    try:
        return next_publish_slot(site, articles, datetime.now(timezone.utc)).isoformat()
    except ValueError:
        return None


@router.get("/stats")
async def stats():
    system = await get_system()
    sites = await db.sites.find().sort("key", 1).to_list(10)
    out_sites = []
    next_runs = []
    for s in sites:
        arts = await db.articles.find({"site_key": s["key"]}).to_list(500)
        local_day = datetime.now(ZoneInfo(s["timezone"])).date()
        tz = ZoneInfo(s["timezone"])
        published = sum(1 for a in arts if verified_wp_record(a.get("wp"))
                        and (stamp := _as_utc(a.get("scheduled_time") or (a.get("wp") or {}).get("verified_at")))
                        and stamp.astimezone(tz).date() == local_day)
        scheduled = sum(1 for a in arts if a["stage"] == "scheduled"
                        and (stamp := _as_utc(a.get("scheduled_time")))
                        and stamp.astimezone(tz).date() == local_day)
        drafts = sum(1 for a in arts if a["stage"] == "wordpress_draft")
        held = sum(1 for a in arts if a["stage"] == "held_review")
        failed = sum(1 for a in arts if a["stage"] == "failed")
        in_progress = sum(1 for a in arts if a["stage"] in ("selected", "researching", "research_validated", "writing_article", "article_generated", "article_validated", "generating_image", "image_ready"))
        quota = s.get("daily_quota", 5)
        nr = _next_run(s, arts) if system.get("scheduler_enabled") else None
        if nr:
            next_runs.append(nr)
        out_sites.append({
            "key": s["key"], "name": s["name"], "domain": s["domain"],
            "language": s["language"], "brand_style": s.get("brand_style", ""),
            "daily_quota": quota, "published_today": published, "scheduled": scheduled,
            "drafts": drafts, "held_review": held, "failed": failed, "in_progress": in_progress,
            "remaining": max(0, quota - published - scheduled),
            "auto_publish": False if RuntimeSafety.from_env().dry_run else s.get("auto_publish", False), "paused": s.get("paused", False),
            "connected": is_connected(s),
            "next_run": nr, "publish_times": s.get("publish_times", []),
            "timezone": s.get("timezone", "UTC"),
        })
    from lib.turn import current_article
    from lib.workflow import IN_PRODUCTION
    producing = None
    current = await current_article()  # the one article in progress, also while it waits for the editor
    if not current and (producing_id := IN_PRODUCTION.get("article")):
        current = await db.articles.find_one({"id": producing_id}, {"_id": 0, "id": 1, "site_key": 1, "stage": 1,
                                                                 "held_reason": 1, "topic_snapshot": 1, "updated_at": 1})
    if current:
        producing = {"id": current["id"], "site_key": current["site_key"], "stage": current["stage"],
                     "held_reason": current.get("held_reason"), "since": current.get("updated_at"),
                     "topic": (current.get("topic_snapshot") or {}).get("topic", "")}
    from lib.turn import next_article
    ahead = await next_article()  # researching ahead while the current article is on its thumbnail
    return {
        "system": system,
        "sites": out_sites,
        "next_run": min(next_runs) if next_runs else None,
        "server_time": now_utc().isoformat(),
        "producing": producing,
        "next_article": {"id": ahead["id"], "site_key": ahead["site_key"], "stage": ahead["stage"],
                         "held_reason": ahead.get("held_reason"),
                         "topic": (ahead.get("topic_snapshot") or {}).get("topic", "")} if ahead else None,
        "next_site": "human" if system.get("last_sequence_site") == "kannadiga" else "kannadiga",
    }
