"""Strictly one article at a time (owner rule, 2026-09-27), with the next article's research started ahead.

The current article holds the turn until WordPress has it (published, or scheduled for its publishing slot)
or it is rejected. Meanwhile - also while it is held for the owner's review - no other article's SEO, thumbnail or
publishing starts: the scheduler waits, editor actions on other articles wait for their turn, and the Chrome work
tabs take jobs only for the current article. One exception (owner rule, 28 Sep 2026): an article held only for the
owner's editorial sign-off (a high-risk subject, everything else done) lets the next article start; once approved,
the publishing step schedules it into the next free slot.

Research ahead (optional; off since 28 Sep 2026, when the owner asked that queued articles start only once the current
one is sent to the Broadcast Schedule): with system_settings.research_ahead on, once the current article is on its
thumbnail (research and SEO done, so the Gemini tab is free) the next article in line runs its Deep Research. One
article at most is ahead (next_article); it takes the turn next, and the work tabs take its Gemini (research) jobs.
"""
import asyncio

from lib.db import db
from lib.manual_research import awaiting_manual, waits_for_link
from lib.util import now_utc

# Complete: WordPress has it (published, scheduled for its slot, or a draft in review modes), or rejected.
FINISHED = {"scheduled", "published", "verified", "wordpress_draft", "rejected"}
TURN_POLL_SECONDS = 30
_FREE = {"$or": [{"current_article": {"$exists": False}}, {"current_article": None}]}
_NEXT_FREE = {"$or": [{"next_article": {"$exists": False}}, {"next_article": None}]}


def finished(article: dict | None) -> bool:
    return (not article or article.get("stage") in FINISHED
            or (article.get("wp") or {}).get("status") in {"publish", "future"})


SIGN_OFF = "High-risk subject requires human editorial sign-off"


def awaiting_sign_off(article: dict | None) -> bool:
    """Held only for the owner's editorial approval (high-risk subject): research, SEO and thumbnail are done."""
    return bool(article and article.get("stage") == "held_review" and not article.get("approval")
                and str(article.get("held_reason") or "").startswith(SIGN_OFF))


def title(article: dict) -> str:
    return ((article.get("topic_snapshot") or {}).get("topic") or (article.get("dossier") or {}).get("headline")
            or article.get("id", ""))[:90]


def needs_research(article: dict) -> bool:
    return not article.get("dossier") or not (article.get("validation") or {}).get("passed")


def on_thumbnail(article: dict | None) -> bool:
    """Research and SEO are done: the article is on its thumbnail or waits for WordPress, so Gemini is free."""
    return bool(article and article.get("article") and (article.get("quality_gate") or {}).get("passed"))


async def current_article() -> dict | None:
    """The article holding the turn, or None. A finished holder releases the turn here."""
    system = await db.system_settings.find_one({"id": "system"}, {"current_article": 1, "auto_research": 1}) or {}
    art_id = system.get("current_article")
    if not art_id:
        return None
    article = await db.articles.find_one({"id": art_id})
    # Automatic research off: a topic without research (not being researched now) waits for its link outside the turn.
    waiting = waits_for_link(article, system) and (article or {}).get("stage") in {"selected", "held_review", "failed"}
    if finished(article) or awaiting_sign_off(article) or awaiting_manual(article) or waiting:
        # (A topic reserved for the owner's manual research waits for its report outside the turn.)
        released = await db.system_settings.update_one({"id": "system", "current_article": art_id},
                                                       {"$unset": {"current_article": "", "current_since": ""}})
        if released.modified_count and awaiting_sign_off(article):
            await db.articles.update_one({"id": art_id}, {"$push": {"history": {
                "stage": "held_review", "at": now_utc(), "actor": "system",
                "note": "Waiting for your editorial approval; the next article has started meanwhile. Once approved, "
                        "it takes the next free publishing slot."}}})
        return None
    article.pop("_id", None)
    return article


async def next_article() -> dict | None:
    """The article researching ahead (or researched and next in line), or None. Released once it holds the turn,
    or when it is finished, rejected, removed or stopped by the editor."""
    system = await db.system_settings.find_one({"id": "system"}, {"next_article": 1, "current_article": 1}) or {}
    art_id = system.get("next_article")
    if not art_id:
        return None
    article = await db.articles.find_one({"id": art_id})
    if (finished(article) or system.get("current_article") == art_id
            or article.get("held_reason") == "Stopped by editor."):
        await db.system_settings.update_one({"id": "system", "next_article": art_id},
                                            {"$unset": {"next_article": "", "next_since": ""}})
        return None
    article.pop("_id", None)
    return article


async def take_turn(art_id: str) -> dict | None:
    """Give art_id the turn if no other article holds it. None: art_id holds it; else the article that goes first
    (the current holder, or the article researched ahead, which takes the turn next)."""
    holder = await current_article()
    if holder:
        return None if holder["id"] == art_id else holder
    if (ahead := await next_article()) and ahead["id"] != art_id:
        return ahead
    claimed = await db.system_settings.update_one({"id": "system", **_FREE},
                                                  {"$set": {"current_article": art_id, "current_since": now_utc()}})
    if claimed.modified_count:
        await db.system_settings.update_one({"id": "system", "next_article": art_id},
                                            {"$unset": {"next_article": "", "next_since": ""}})
        await db.articles.update_one({"id": art_id}, {"$unset": {"turn_wait": ""}})
        return None
    holder = await current_article()  # another start claimed it first
    return None if not holder or holder["id"] == art_id else holder


async def research_ahead_on() -> bool:
    system = await db.system_settings.find_one({"id": "system"}, {"research_ahead": 1}) or {}
    return bool(system.get("research_ahead"))


async def claim_next(art_id: str) -> bool:
    """Let art_id go next and research ahead: only while the current article is on its thumbnail, one at a time."""
    if not await research_ahead_on():
        return False  # the next article starts once the current one is scheduled (owner rule, 28 Sep 2026)
    current = await current_article()
    if not current or current["id"] == art_id or not on_thumbnail(current):
        return False
    if ahead := await next_article():
        return ahead["id"] == art_id
    claimed = await db.system_settings.update_one({"id": "system", **_NEXT_FREE},
                                                  {"$set": {"next_article": art_id, "next_since": now_utc()}})
    if not claimed.modified_count:
        return bool((ahead := await next_article()) and ahead["id"] == art_id)
    article = await db.articles.find_one({"id": art_id}) or {}
    note = (f"Next in line: its research starts now, while \u201c{title(current)}\u201d is on its thumbnail."
            if needs_research(article) else "Next in line: it continues once the current article is published.")
    await db.articles.update_one({"id": art_id}, {"$unset": {"turn_wait": ""}, "$push": {"history": {
        "stage": article.get("stage"), "at": now_utc(), "actor": "system", "note": note}}})
    return True


async def wait_for_turn(art_id: str) -> bool:
    """Wait, without doing any work, until art_id holds the turn. False if it was finished or rejected meanwhile."""
    queued = False
    while holder := await take_turn(art_id):
        article = await db.articles.find_one({"id": art_id})
        if finished(article):
            return False
        if not queued:
            queued = True
            await db.articles.update_one({"id": art_id}, {
                "$set": {"turn_wait": {"behind": holder["id"], "since": now_utc()}},
                "$push": {"history": {"stage": article.get("stage"), "at": now_utc(), "actor": "system",
                                      "note": f"Queued: this article's work starts once \u201c{title(holder)}\u201d is "
                                              "scheduled for publishing."}}})
        await asyncio.sleep(TURN_POLL_SECONDS)
    return not finished(await db.articles.find_one({"id": art_id}))


async def wait_for_research(art_id: str) -> str | None:
    """Wait, without doing any work, until art_id may run its research: "turn" once it holds the turn, "ahead" when
    it goes next while the current article is on its thumbnail. None if it was finished or rejected meanwhile."""
    if not await research_ahead_on():
        return "turn" if await wait_for_turn(art_id) else None
    queued = False
    while True:
        article = await db.articles.find_one({"id": art_id})
        if finished(article):
            return None
        holder = await take_turn(art_id)
        if holder is None:
            return "turn"
        if await claim_next(art_id):
            return "ahead"
        if not queued:
            queued = True
            ahead = await next_article()
            behind = ahead if ahead and ahead["id"] != art_id else holder
            await db.articles.update_one({"id": art_id}, {
                "$set": {"turn_wait": {"behind": behind["id"], "since": now_utc()}},
                "$push": {"history": {"stage": article.get("stage"), "at": now_utc(), "actor": "system",
                                      "note": f"Queued behind \u201c{title(behind)}\u201d: its research starts as soon "
                                              "as that article is on its thumbnail."}}})
        await asyncio.sleep(TURN_POLL_SECONDS)
