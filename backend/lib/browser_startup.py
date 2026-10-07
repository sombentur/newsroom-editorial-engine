"""Wait for the provider page to settle before entering a browser-job prompt."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from lib.browser_controller import Decision, Observation


# A provider page that failed to load (a person would press Reload). Never sign out.
PAGE_LOAD_ERROR = re.compile(r"couldn.t load your account|something went wrong|an error occurred|unable to load|"
                             r"network error|try reloading", re.I)
MAX_PAGE_RELOADS = 2
# Text the app did not type in the message box before sending (ChatGPT restores an unsent new-chat message, e.g. one
# the owner is writing in another ChatGPT tab; live case 28 Sep 2026) is never overwritten. The job waits for it to be
# sent or cleared, looking at a freshly loaded page every 2 minutes, within the image step's 15-minute limit.
DRAFT_WAIT_MINUTES = 7
DRAFT_LOOK_AGAIN_SECONDS = 120
DRAFT_LOOK_REASON = ("The message box still holds text the app did not type; loading the page again to see if it was "
                     "sent or cleared.")
# ChatGPT shows the chosen tool as a chip inside the message box ("Create image"; live case 3 Oct 2026). A composer whose
# only text is such a chip holds no draft. Page helpers before 0.4.31 send no draft text (and count the chip as text).
TOOL_CHIP = re.compile(r"^\s*(?:create image|image|deep research|web search|search|canvas|think longer|study and learn|"
                       r"agent mode|study|shopping|record)\s*$", re.I)


def has_draft(obs: Observation) -> bool:
    """An editable element holds text the app did not type (a tool chip reported as draft text is not a draft)."""
    return any(element.editable and not element.empty and not (element.draft and TOOL_CHIP.match(element.draft))
               for element in obs.elements)


def draft_look(event: dict) -> bool:
    """A page reload made by the draft wait (it never counts against other reload limits)."""
    return event.get("action") == "reload_page" and event.get("note") == DRAFT_LOOK_REASON


def _utc(value):
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _fingerprint(obs: Observation) -> str:
    # IDs are observation-local. Ignore response text, images, and reports;
    # observe the composer and controls that change during page hydration.
    controls = [
        [element.role, " ".join(element.name.split()), element.editable,
         element.empty if element.editable else None, element.disabled, element.selected]
        for element in obs.elements if element.role not in {"report", "image"}
    ]
    return hashlib.sha256(json.dumps(controls, ensure_ascii=False).encode("utf-8")).hexdigest()


def _draft_attention(obs: Observation) -> Decision | None:
    if has_draft(obs) and not obs.prompt_verified:
        return Decision(action="attention", target=0, reason=(
            "An existing draft is present after the chat page loaded. It has been preserved without changes. "
            "Inspect the job tab and provide an empty composer before continuing."))
    return None


def startup_guard(job: dict, obs: Observation, now: datetime) -> tuple[dict, Decision | None]:
    """Return a MongoDB $set patch and a local decision, or None to ask the planner.

    Existing extension observations remain supported: this uses only fields
    already supplied by v0.2.2. It deliberately does not claim to prove that
    hydration has completed; the prompt must still be checked before sending.
    """
    attempted = {event.get("action") for event in job.get("activity", [])}
    if obs.submitted or "submit" in attempted:
        return {}, None
    if obs.filled and not obs.prompt_verified:
        return {}, Decision(action="attention", target=0, reason=(
            "The composer changed after prompt entry, possibly because the page restored an existing draft. "
            "The draft is preserved; no prompt was sent. Inspect the job tab before continuing."))
    if obs.filled or "fill_prompt" in attempted:
        return {}, None

    now = _utc(now)
    if now is None:
        raise TypeError("now must be a datetime")
    previous = job.get("browser_startup") or {}
    if not isinstance(previous, dict):
        previous = {}
    first_seen = _utc(previous.get("first_seen_at"))
    if first_seen is None or first_seen > now:
        first_seen = now
        previous = {}

    ready_at = _utc(previous.get("ready_at"))
    if ready_at is not None and first_seen <= ready_at <= now:
        # Opening model/tool menus is expected to change the controls after
        # startup. Do not restart the warm-up, but still protect a late draft.
        return {}, _draft_attention(obs)

    fingerprint = _fingerprint(obs)
    stable_since = _utc(previous.get("stable_since"))
    count = previous.get("stable_observations", 0)
    if (previous.get("fingerprint") != fingerprint or stable_since is None
            or stable_since > now or stable_since < first_seen):
        stable_since, count = now, 1
    else:
        count = count + 1 if isinstance(count, int) and count >= 1 else 1
    patch = {"browser_startup": {
        "first_seen_at": first_seen,
        "fingerprint": fingerprint,
        "stable_since": stable_since,
        "stable_observations": count,
    }}

    if (now - first_seen).total_seconds() < 10 or (now - stable_since).total_seconds() < 5 or count < 2:
        return patch, Decision(action="wait", target=0, reason=(
            "Waiting for the chat page and composer to settle before entering the prompt. "
            "This protects any draft restored while the page loads."))

    composers = [element for element in obs.elements if element.editable]
    if not composers:
        reloads = sum(event.get("action") == "reload_page" and not draft_look(event) for event in job.get("activity", []))
        if PAGE_LOAD_ERROR.search((obs.text or "")[-2000:]) and reloads < MAX_PAGE_RELOADS:
            # Restart the settle wait after the reload.
            return {"browser_startup": {}}, Decision(action="reload_page", target=0, reason=(
                "The chat page shows a loading error (for example \"We couldn't load your account\"); reloading it."))
        return patch, Decision(action="attention", target=0, reason=(
            "The page has settled but no chat composer is visible. Inspect the job tab; no prompt was entered."))
    if has_draft(obs) and not obs.prompt_verified:
        return _restored_draft(job, patch, now)
    if job.get("draft_seen_at"):
        if not re.fullmatch(r"(?:/u/\d{1,2})?(?:/app)?", urlsplit(obs.url).path.rstrip("/")):
            # The draft was sent from this work tab: it now shows the owner's conversation, not a new chat.
            return patch, Decision(action="attention", target=0, reason=(
                "The text in the message box was sent in this work tab, so the tab now shows that conversation instead "
                "of a new chat. No prompt was entered. Press Retry to start in a new chat."))
        patch["draft_seen_at"] = None
    patch["browser_startup"]["ready_at"] = now
    return patch, None


def _restored_draft(job: dict, patch: dict, now: datetime) -> tuple[dict, Decision]:
    """Wait for a restored draft to be sent or cleared elsewhere, looking at a freshly loaded page every 2 minutes (not
    while it is being edited in this tab); after DRAFT_WAIT_MINUTES, one last look, then the owner decides."""
    provider = "Gemini" if job.get("kind") == "research" else "ChatGPT"
    seen = _utc(job.get("draft_seen_at"))
    if seen is None or seen > now:
        seen = patch["draft_seen_at"] = now
    looks = [_utc(event.get("at")) for event in job.get("activity", []) if draft_look(event)]
    last = max([at for at in looks if at and at >= seen], default=seen)
    edited = _utc(job.get("progress_at"))  # the page text changed (e.g. the draft is being edited in this tab)
    editing = edited is not None and seen < edited <= now and (now - edited).total_seconds() < DRAFT_LOOK_AGAIN_SECONDS
    deadline = seen + timedelta(minutes=DRAFT_WAIT_MINUTES)
    if now >= deadline and (last >= deadline or editing):
        return patch, Decision(action="attention", target=0, reason=(
            "An existing draft is present after the chat page loaded: text the app did not type, for example an unsent "
            f"message started in {provider}. It has been preserved without changes. Send or clear it, then press Retry."))
    if not editing and (now >= deadline or (now - last).total_seconds() >= DRAFT_LOOK_AGAIN_SECONDS):
        # A fresh page load restores the draft again only if it was not sent or cleared meanwhile.
        return {**patch, "browser_startup": {}}, Decision(action="reload_page", target=0, reason=DRAFT_LOOK_REASON)
    return patch, Decision(action="wait", target=0, reason=(
        f"The message box holds text the app did not type (for example an unsent message started in {provider}). It "
        "is never overwritten: waiting for it to be sent or cleared."))
