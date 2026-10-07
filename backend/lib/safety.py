"""Persistent fail-closed repair lock, startup migration, and publication evidence."""
from lib.db import db
from lib.util import audit, now_utc, new_id
from lib.wp_credentials import CredentialError, encrypt_password, is_connected
from lib.runtime import ConfigurationError, RuntimeSafety, external_operation_block_reason


async def discovery_block_reason(site: dict) -> str | None:
    """Manual public-feed reads are allowed in review; pause/stop still apply."""
    try:
        RuntimeSafety.from_env()
    except ConfigurationError as exc:
        return f"CONFIGURATION_INVALID: {exc}"
    system = await db.system_settings.find_one({"id": "system"})
    if not system:
        return "Discovery is unavailable until the app finishes setup."
    if system.get("killswitch"):
        return "Release Stop before running discovery."
    if system.get("global_paused"):
        return "Select Resume before running discovery."
    if site.get("paused"):
        return "Resume this website in Command Center before running discovery."
    return None


async def system_block_reason() -> str | None:
    if reason := external_operation_block_reason():
        return reason
    system = await db.system_settings.find_one({"id": "system"}) or {}
    if system.get("repair_lock", True):
        return "SAFETY_LOCK: AI generation and all WordPress writes are disabled pending owner-authorized release."
    if system.get("killswitch") or system.get("global_paused"):
        return "SYSTEM_PAUSED: generation and publishing are paused."
    return None


def verified_wp_record(wp: dict | None, status: str = "publish") -> bool:
    wp = wp or {}
    v = wp.get("verification") or {}
    return bool(wp.get("simulated") is False and type(wp.get("post_id")) is int and wp["post_id"] > 0
                and str(wp.get("public_url", "")).startswith("https://") and wp.get("status") == status
                and wp.get("verified_at") and v.get("creation_response_ok") is True
                and v.get("readback_ok") is True and v.get("readback_status") == status
                and (status != "publish" or v.get("public_page_ok") is True))


async def initialize_safety() -> None:
    """Idempotent local-only migration; never calls AI or WordPress."""
    system = await db.system_settings.find_one({"id": "system"}) or {}
    safety = RuntimeSafety.from_env()
    if safety.repair_lock_enabled and system.get("repair_lock", True):
        await db.system_settings.update_one({"id": "system"}, {"$set": {
            "mode": "review", "scheduler_enabled": False, "global_paused": True,
            "repair_lock": True, "updated_at": now_utc()}, "$setOnInsert": {"killswitch": False}}, upsert=True)
        await db.sites.update_many({}, {"$set": {"auto_publish": False}})
    elif not safety.repair_lock_enabled:
        await db.system_settings.update_one({"id": "system"}, {"$set": {
            "repair_lock": False, "updated_at": now_utc()}, "$setOnInsert": {"killswitch": False}}, upsert=True)
    for site in await db.sites.find().to_list(100):
        patch = {}
        if site.get("wp_app_password") and not site.get("wp_password_ciphertext"):
            try:
                patch["wp_password_ciphertext"] = encrypt_password(site["wp_app_password"])
            except CredentialError:
                # Preserve the only credential copy. A failed migration must never
                # erase it or allow the application to start accepting requests.
                await db.sites.update_one({"key": site["key"]}, {"$set": {"connected": False}})
                raise CredentialError("Credential migration blocked. Configure the existing encryption key before startup; stored data was retained.") from None
        if not site.get("credential_revision"):
            patch.update(credential_revision=new_id(), connected=False, connection_test=None)
        if not is_connected(site):
            patch["connected"] = False
        ops = {"$set": patch}
        if patch.get("wp_password_ciphertext"):
            ops["$unset"] = {"wp_app_password": ""}
        await db.sites.update_one({"key": site["key"]}, ops)
    statuses = {"published": "publish", "verified": "publish", "scheduled": "future", "wordpress_draft": "draft"}
    for art in await db.articles.find({"stage": {"$in": list(statuses)}}).to_list(10000):
        if verified_wp_record(art.get("wp"), statuses[art["stage"]]):
            continue
        reason = "FALSE_OR_UNVERIFIED_PUBLISH_STATUS"
        result = await db.articles.update_one({"id": art["id"], "stage": art["stage"]}, {
            "$set": {"stage": "held_review", "held_reason": reason, "updated_at": now_utc()},
            "$push": {"history": {"stage": "held_review", "at": now_utc(), "actor": "safety_migration", "note": reason}},
        })
        if result.modified_count:
            wp = art.get("wp") or {}
            await audit("publication_status_corrected", "article", art["id"], art["site_key"], detail={
                "reason": reason, "previous_stage": art["stage"], "simulated": wp.get("simulated"),
                "previous_post_id": wp.get("post_id"), "previous_permalink": wp.get("public_url"),
                "verification_result": "unverified; original record retained", "timestamp": now_utc()})
