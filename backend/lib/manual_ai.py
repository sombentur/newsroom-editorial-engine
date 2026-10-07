"""An explicit manual request may use paid AI without releasing publication locks."""
import os
from contextvars import ContextVar

from lib.runtime import ConfigurationError, RuntimeSafety, boolean

manual_request = ContextVar("manual_ai_request", default=False)
automated_request = ContextVar("automated_ai_request", default=False)


def enabled() -> bool:
    return boolean("MANUAL_AI_ENABLED", False, os.environ)


def environment_reason() -> str | None:
    try:
        safety = RuntimeSafety.from_env()
        if automated_request.get():
            if safety.dry_run or not safety.scheduler_enabled:
                return "Scheduled AI is disabled by the server safety controls."
            return None
        if not enabled() or not manual_request.get():
            return "Manual AI is disabled. Enable it in server configuration and use an article action."
    except ConfigurationError as exc:
        return str(exc)
    return None


async def block_reason(site_key: str | None = None) -> str | None:
    if reason := environment_reason():
        return reason
    from lib.db import db
    system = await db.system_settings.find_one({"id": "system"})
    if not system or system.get("global_paused") or system.get("killswitch"):
        return "AI is paused. Select Resume before starting a manual article action."
    if site_key:
        site = await db.sites.find_one({"key": site_key})
        if not site or site.get("paused"):
            return "This website is paused or unavailable."
    return None
