"""Recognize the small set of observed controls used to start a browser job."""
import re
from datetime import datetime

from lib.browser_controller import Decision, SEND_BUTTON_NAMES
from lib.browser_startup import draft_look


def initial_action(job, obs):
    if obs.submitted or any(e.get('action') == 'submit' for e in job.get('activity', [])):
        return None
    elements = [e for e in obs.elements if not e.disabled]
    def unique(predicate):
        matches = [e for e in elements if predicate(e)]
        return matches[0] if len(matches) == 1 else None
    def click(element, reason):
        return Decision(action='click', target=element.id, reason=reason) if element else None
    def named_button(label):
        return unique(lambda e: e.role == 'button' and e.name.strip().lower() == label)

    if job['kind'] == 'research':
        picker = unique(lambda e: e.role == 'button' and e.name.lower().startswith('open mode picker'))
        if not picker:
            return None
        if not re.search(r'currently\s+(?:3(?:\.\d+)?\s+)?pro\b', picker.name, re.I):
            pro = unique(lambda e: e.role == 'menuitem' and re.fullmatch(r'(?:3(?:\.\d+)?\s+)?pro', e.name.split('\n')[0].strip(), re.I))
            return click(pro or picker, 'Select Gemini Pro before starting Deep Research.')
        if not deep_research_active(elements):
            tool = unique(lambda e: e.role in {'menuitemcheckbox','menuitem','menuitemradio','button'}
                          and control_label(e.name).lower() == 'deep research')
            if tool:
                return click(tool, 'Enable Deep Research before sending the research prompt.')
            # Gemini moves its tools between menus: open each candidate menu (at most twice) and look for Deep research.
            clicks = [control_label((a.get('control') or {}).get('name', '')).lower()
                      for a in job.get('activity', []) if a.get('action') == 'click']
            for label in DEEP_RESEARCH_MENUS:
                menu = unique(lambda e, label=label: e.role == 'button' and control_label(e.name).lower() == label)
                if menu and clicks.count(label) < 2:
                    return click(menu, 'Open this menu to find the Deep Research tool.')
            return None

    if level := thinking_level_action(job, obs, elements):
        return level
    if tool := create_image_action(job, obs, elements):
        return tool
    if obs.prompt_verified:
        send = unique(lambda e: e.role == 'button' and e.name.lower().strip() in SEND_BUTTON_NAMES)
        if send:
            return Decision(action='submit', target=send.id, reason='Send the verified prompt once using the protected Send action.')
        return None
    # Do not fill any second composer when a restored draft is present.
    if any(e.editable and not e.empty for e in elements):
        return None
    # ChatGPT renamed its composer "Ask ChatGPT" (28 Sep 2026); until then every ChatGPT prompt waited for the planner.
    labels = {'enter a prompt for gemini'} if job['kind'] == 'research' else {'chat with chatgpt', 'ask chatgpt'}
    composer = unique(lambda e: e.editable and e.empty and e.name.lower().strip() in labels)
    if composer:
        return Decision(action='fill_prompt', target=composer.id, reason='Enter the job prompt into the empty chat composer.')
    return None


# ChatGPT's thinking level (owner rule, 28 Sep 2026): Medium for every job, one step up for each fresh chat after a
# failed thumbnail. It is the "Power" item of the composer's model menu (5 steps; the 5th is locked and never used);
# ChatGPT keeps the last level for new chats, so every job sets its own before its prompt is entered.
THINKING_LEVELS = ('low', 'medium', 'high', 'extra high')
MODEL_MENU = 'select chatgpt model'
MAX_LEVEL_STEPS = 12  # menu openings and steps; then the job continues at whatever level is shown


def thinking_level_action(job, obs, elements):
    """The next step towards the job's thinking level (open the menu, one step, close it), or None when done."""
    target = (job.get('effort') or '').strip().lower()
    if job['kind'] not in {'image', 'seo'} or target not in THINKING_LEVELS or obs.filled or obs.prompt_verified:
        return None
    activity = job.get('activity', [])
    steps = sum(a.get('action') in {'level_up', 'level_down', 'close_menu'}
                or (a.get('action') == 'click' and control_label((a.get('control') or {}).get('name', '')).lower() == MODEL_MENU)
                for a in activity)
    current = (obs.effort or '').strip().lower()
    power = [e for e in elements if e.role == 'menuitem' and control_label(e.name).lower() == 'power']
    if power:  # the model menu is open
        if current == target or steps >= MAX_LEVEL_STEPS or current not in THINKING_LEVELS:
            if sum(a.get('action') == 'close_menu' for a in activity) >= 3:
                return None
            return Decision(action='close_menu', target=0, reason=f"ChatGPT's thinking level is {obs.effort or 'unknown'}; closing its menu.")
        up = THINKING_LEVELS.index(target) > THINKING_LEVELS.index(current)
        return Decision(action='level_up' if up else 'level_down', target=power[0].id,
                        reason=f"Setting ChatGPT's thinking level to {job['effort']} (now {obs.effort}).")
    if current == target or current not in THINKING_LEVELS or steps >= MAX_LEVEL_STEPS:
        return None  # set, or no level control offered (e.g. another model): the prompt goes in as it is
    picker = [e for e in elements if e.role == 'button' and control_label(e.name).lower() == MODEL_MENU]
    if len(picker) != 1:
        return None
    return Decision(action='click', target=picker[0].id,
                    reason=f"Opening ChatGPT's model menu to set the thinking level to {job['effort']} (now {obs.effort}).")


# ChatGPT's "Create image" tool (owner rule, 28 Sep 2026): without it ChatGPT kept routing thumbnail prompts to image
# editing ("treated this request as an edit"). It is chosen from the composer's + menu before every image prompt; the
# chip it adds ("Remove Create image") shows it is on, and a new chat starts without it.
# ChatGPT renames these UI elements occasionally; keep both sets growing as new labels are observed in the wild.
_ADD_MENU_LABELS = frozenset({
    'add files and more',           # original label (Sep 2026)
    'attach files and more',
    'add photos & files and more',
    'add photos and files and more',
    'add attachments',
    'attachments',
})
_IMAGE_TOOL_ON_LABELS = frozenset({
    'remove create image',          # original chip label (Sep 2026)
    'deselect create image',
    'disable create image',
    'turn off create image',
})
MAX_IMAGE_TOOL_CLICKS = 6  # then the prompt goes in without it (ChatGPT decides, as before)


def _is_add_menu(label: str) -> bool:
    """True if label belongs to ChatGPT's composer + (attach/add-tools) button."""
    l = label.strip().lower()
    if l in _ADD_MENU_LABELS:
        return True
    # ChatGPT periodically renames this button; accept anything mentioning add/attach + file/photo.
    return l.startswith(('add file', 'attach file', 'add photo', 'attach photo'))


def _image_tool_is_on(labels: list) -> bool:
    """True when the 'Create image' chip is active in the composer."""
    for l in labels:
        if l in _IMAGE_TOOL_ON_LABELS:
            return True
        if 'create image' in l and any(w in l for w in ('remove', 'deselect', 'turn off', 'disable')):
            return True
    return False


def create_image_action(job, obs, elements):
    """For an image job: open the + menu, then choose Create image; None once it is on (or cannot be found)."""
    if job['kind'] != 'image' or obs.filled or obs.prompt_verified:
        return None
    labels = [control_label(e.name).lower() for e in elements]
    if _image_tool_is_on(labels):
        return None
    # Since Oct 2026 ChatGPT shows the chosen tool only as a chip inside the message box (no labelled Remove button);
    # page helpers 0.4.32+ report the chip text, so one choice is enough and the menu is not opened again.
    if any(e.editable and e.chips and 'create image' in e.chips.lower() for e in obs.elements):
        return None
    clicks = sum(a.get('action') == 'click'
                 and (_is_add_menu(control_label((a.get('control') or {}).get('name', '')))
                      or control_label((a.get('control') or {}).get('name', '')).lower().startswith('create image'))
                 for a in job.get('activity', []))
    if clicks >= MAX_IMAGE_TOOL_CLICKS:
        return None
    item = [e for e in elements if e.role in {'button', 'menuitem', 'option'}
            and control_label(e.name).lower().startswith('create image')]
    if len(item) == 1:
        return Decision(action='click', target=item[0].id,
                        reason="Choosing ChatGPT's Create image tool, so the thumbnail is generated (never treated as an edit).")
    menu = [e for e in elements if e.role == 'button' and _is_add_menu(control_label(e.name))]
    if len(menu) == 1:
        return Decision(action='click', target=menu[0].id, reason="Opening ChatGPT's + menu to choose Create image.")
    return None


# ── After the prompt was sent: known states are handled by rules, not the (rate-limited) planner ──
STOP_LABEL = re.compile(r"(?:^|\s)(?:stop|cancel)\s+(?:response|responding|generating|generation|streaming|research|researching|answering)(?:\s|$)", re.I)
START_RESEARCH = re.compile(r"^(?:start research|ಸಂಶೋಧನೆ ಪ್ರಾರಂಭಿಸಿ)$", re.I)
SHARE_EXPORT = re.compile(r"(?:^|\s)share\s*(?:&|and)\s*export(?:\s|$)", re.I)
IMAGE_IN_PROGRESS = re.compile(r"(?:^|\s)\d{1,3}\s?%(?=\s|$)|creating image|generating image", re.I)
# ChatGPT's stop button is now labelled just "Stop"; its answer bar ("Read aloud", "Regenerate") appears when done.
STOP_BARE = {'stop', 'stop streaming', 'stop answering'}
ANSWER_DONE = {'read aloud', 'regenerate', 'regenerate response'}
# ChatGPT's own image tool can fail ("Image generation failed"); a usage or plan limit is for the owner, never retried.
IMAGE_FAILED = re.compile(r"image generation failed", re.I)
USAGE_LIMIT = re.compile(r"\b(?:usage|rate|plan|message|image|generation)s?\s+(?:limit|cap)|\blimit\s+(?:resets|will\s+reset)"
                         r"|\b(?:reached|hit)\s+(?:\w+\s+){0,4}limit|too many requests", re.I)
IMAGE_FAILED_SETTLE_SECONDS = 15  # the failure must stay on the page this long before the job is released
IMAGE_WAIT_LIMIT_SECONDS = 300  # the extension stops waiting this long after Send (a job may set a longer limit)


def _generating(element):
    label = control_label(element.name)
    return bool(STOP_LABEL.search(label)) or label.lower() in STOP_BARE


_LIGATURE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")


def control_label(name):
    """Visible label without Material icon ligatures (e.g. "keyboard_arrow_down")."""
    return " ".join(_LIGATURE.sub(" ", name or "").split())


def _seconds_since(event):
    from datetime import datetime, timezone
    at = event.get('at')
    if not isinstance(at, datetime):
        return 0
    at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - at).total_seconds()


def _after_prompt(text, prompt):
    """The page text after the job's own prompt (whitespace-normalised); all of it if the prompt is not shown."""
    flat, end = ' '.join(text.split()), ' '.join(prompt.split())[-80:]
    at = flat.rfind(end) if end else -1
    return flat[at + len(end):] if at >= 0 else flat


def progress_action(job, obs):
    """Decide known post-submit states without AI; None means only the planner can tell."""
    activity = job.get('activity', [])
    if not (obs.submitted or any(a.get('action') == 'submit' for a in activity)):
        return None
    elements = [e for e in obs.elements if not e.disabled]
    short = [e for e in elements if len(control_label(e.name)) <= 40]
    reports = [e for e in elements if e.role == 'report']
    if job['kind'] == 'research':
        # Gemini keeps "Stop response" visible while its research plan waits for approval, so the
        # Start research button must be handled before the "still generating" rule.
        start = [e for e in short if e.role == 'button' and START_RESEARCH.fullmatch(control_label(e.name))]
        clicks = [a for a in activity if a.get('action') == 'click'
                  and START_RESEARCH.fullmatch(control_label((a.get('control') or {}).get('name', '')))]
        if start and (not clicks or (len(clicks) < 2 and _seconds_since(clicks[-1]) > 60)):
            return Decision(action='click', target=start[-1].id, reason='Start the Deep Research plan.')
    if any(_generating(e) for e in short):
        # Never reload a page that shows the work going on: a reload cuts its live view, and Gemini then shows
        # "You stopped this task" although the research goes on (live finding, 28 Sep 2026).
        return Decision(action='wait', target=0, reason='Generation in progress; waiting.')
    # Sending clears the composer. If it still holds exactly this job's prompt 20 s after Send, nothing was sent
    # (e.g. the click was ignored): send it once more, as a person would. Never a second time.
    if obs.prompt_verified:
        submits = [a for a in activity if a.get('action') == 'submit']
        send = [e for e in short if e.role == 'button' and control_label(e.name).lower() in SEND_BUTTON_NAMES]
        if send and len(submits) == 1 and _seconds_since(submits[-1]) > 20:
            return Decision(action='submit', target=send[-1].id,
                            reason='The prompt is still in the composer, so it was not sent; sending it once more.')
    if job['kind'] == 'research':
        sent_at = job.get('submitted_at') or next((a.get('at') for a in activity if a.get('action') == 'submit'), None)
        young = isinstance(sent_at, datetime) and _seconds_since({'at': sent_at}) < COLLECT_AFTER_MINUTES * 60
        if reports and any(e.role in {'button', 'menuitem'} and SHARE_EXPORT.search(control_label(e.name)) for e in short):
            if young and not job.get('capture_existing'):
                # No Deep Research finishes this fast: the open report is an earlier conversation's (its panel can stay
                # open in the tab). Wait for this job's own report.
                return Decision(action='wait', target=0,
                                reason='A report is open, but this Deep Research only just started; waiting for its own report.')
            return Decision(action='collect_report', target=reports[-1].id,
                            reason='The Deep Research report is complete and open; copying it.')
        started = [a for a in activity if a.get('action') == 'click'
                   and START_RESEARCH.fullmatch(control_label((a.get('control') or {}).get('name', '')))]
        if started or (sent_at and _seconds_since({'at': sent_at}) > 15 * 60):
            # The research runs on Gemini's servers even when this page shows no progress (e.g. "You stopped this task"
            # after its live view dropped): it is not over, and never a matter for the planner. Look again with a
            # fresh page every 10 minutes, at most three times; research_timed_out releases a run that never finishes.
            reloads = [a for a in activity if a.get('action') == 'reload_page' and not draft_look(a)]
            last = reloads[-1] if reloads else (started[-1] if started else {'at': sent_at})
            if len(reloads) < 3 and _seconds_since(last) > 10 * 60:
                return Decision(action='reload_page', target=0,
                                reason='Deep Research shows no progress on this page; reloading its conversation to look for the report.')
            return Decision(action='wait', target=0, reason='Deep Research is running on Gemini; waiting for its report.')
        return None
    if job['kind'] == 'seo':
        answers = [e for e in reports if 'seo_title' in e.name]
        if answers and not any(control_label(e.name).lower() in ANSWER_DONE for e in short):
            return Decision(action='wait', target=0, reason='ChatGPT is still writing the SEO answer; waiting.')
        if answers:
            return Decision(action='collect_report', target=answers[-1].id, reason='ChatGPT finished the SEO answer; collecting it.')
        return None
    if job['kind'] == 'image':
        images = [e for e in elements if e.role == 'image']
        # ChatGPT draws the image progressively ("Thinking 37%", "Creating image"): never take a partial one.
        # Only the text after our own prompt counts (the prompt itself may say e.g. "keep the top 35% clear").
        after = _after_prompt(obs.text or '', job.get('prompt') or '')[-3000:]
        if IMAGE_IN_PROGRESS.search(after):
            return Decision(action='wait', target=0, reason='ChatGPT is still creating the image; waiting.')
        if images:
            return Decision(action='collect_image', target=images[-1].id, reason='ChatGPT finished the image; collecting it.')
        if image_failure(job, obs):
            # ChatGPT's image tool failed (live case, 28 Sep 2026: it "treated the request as an edit"). image_failed
            # releases the job once the failure has stayed on the page, and the thumbnail is made in a fresh chat.
            return Decision(action='wait', target=0,
                            reason='ChatGPT showed "Image generation failed"; a fresh ChatGPT chat starts shortly.')
    return None


def image_failure(job, obs):
    """True when ChatGPT's finished answer shows "Image generation failed": no image, nothing in progress, no limit."""
    if job.get('kind') != 'image':
        return False
    if not (obs.submitted or any(a.get('action') == 'submit' for a in job.get('activity', []))):
        return False
    elements = [e for e in obs.elements if not e.disabled]
    if any(e.role == 'image' for e in elements) or any(_generating(e) for e in elements if len(control_label(e.name)) <= 40):
        return False
    after = _after_prompt(obs.text or '', job.get('prompt') or '')[-3000:]
    return bool(IMAGE_FAILED.search(after) and not IMAGE_IN_PROGRESS.search(after) and not USAGE_LIMIT.search(after))


def image_failure_mark(job, obs, now):
    """Job fields to store when the failure appears or goes away (when it was first seen); None when unchanged."""
    failed = image_failure(job, obs)
    if failed == isinstance(job.get('image_failure_seen_at'), datetime):
        return None
    return {'image_failure_seen_at': now if failed else None}


def image_failed(job, obs):
    """Reason to release an image job whose generation ChatGPT reported as failed, else None.

    Released once the failure has stayed on the page for IMAGE_FAILED_SETTLE_SECONDS, or at once near the extension's
    5-minute wait limit; the thumbnail is then made in a fresh chat (workflow._image_via_browser). ChatGPT's own Try
    again is not used: it failed in the live case, and its time counts against that limit.
    """
    seen = job.get('image_failure_seen_at')
    if not isinstance(seen, datetime) or not image_failure(job, obs):
        return None
    activity = job.get('activity', [])
    sent_at = job.get('submitted_at') or next((a.get('at') for a in activity if a.get('action') == 'submit'), None)
    limit = (job.get('wait_limit_seconds') or IMAGE_WAIT_LIMIT_SECONDS) - 30  # release before the extension gives up
    near_limit = isinstance(sent_at, datetime) and _seconds_since({'at': sent_at}) >= limit
    if _seconds_since({'at': seen}) < IMAGE_FAILED_SETTLE_SECONDS and not near_limit:
        return None
    return 'ChatGPT\'s image generation failed (it showed "Image generation failed").'


COLLECT_AFTER_MINUTES = 5
FIRST_RUN_MINUTES = 15  # owner rule (28 Sep 2026): a first Deep Research not done by then is replaced once
RERUN_STALL_MINUTES = 10  # a fresh run with no visible progress this long is stuck (it is replaced too)
RESEARCH_TIMEOUT_MINUTES = 90
RESEARCH_STALL_MINUTES = 30
CAPTURE_STALL_MINUTES = 10  # a saved conversation frozen mid-research (copy report again)
CAPTURE_NO_REPORT_MINUTES = 5  # a saved conversation without a finished report
RESEARCH_HARD_LIMIT_MINUTES = 180


def research_timed_out(job, obs):
    """Reason to release a Deep Research job that never finished, else None.

    Releasing frees the Gemini tab so the sequence continues; the conversation URL stays on the job,
    so "Copy report again" can still collect the report if Gemini finishes it later.
    """
    if job.get('kind') != 'research':
        return None
    if job.get('capture_existing'):
        # Copying a saved conversation: one frozen mid-research (Gemini can hang, e.g. at "Starting research...") or
        # one with no finished report is released instead of waiting (live case, 28 Sep 2026).
        since = job.get('progress_at') or job.get('created_at')
        waited = _seconds_since({'at': since}) if since else 0
        if any(_generating(e) for e in obs.elements if not e.disabled):
            if waited >= CAPTURE_STALL_MINUTES * 60:
                return (f"Gemini's saved Deep Research is not progressing (the same step for {CAPTURE_STALL_MINUTES} "
                        "minutes), so its report cannot be copied. It is researched again.")
            return None
        ready = any(SHARE_EXPORT.search(control_label(e.name)) for e in obs.elements
                    if not e.disabled and len(control_label(e.name)) <= 40)
        if not ready and waited >= CAPTURE_NO_REPORT_MINUTES * 60:
            return ("This Gemini conversation shows no finished report (no Share & Export). Open the finished report in "
                    "the Newsroom Gemini tab and press Copy report again, or press Research again.")
        return None
    activity = job.get('activity', [])
    sent_at = job.get('submitted_at') or next((a.get('at') for a in activity if a.get('action') == 'submit'), None)
    reloads = [a for a in activity if a.get('action') == 'reload_page' and not draft_look(a)]
    ready = any(SHARE_EXPORT.search(control_label(e.name)) for e in obs.elements
                if not e.disabled and len(control_label(e.name)) <= 40)
    if (not job.get('rerun') and not ready and isinstance(sent_at, datetime)
            and _seconds_since({'at': sent_at}) >= FIRST_RUN_MINUTES * 60
            and not (reloads and _seconds_since(reloads[-1]) < 120)):
        # Owner rule: replaced by one fresh Deep Research even if still working; the fresh run may finish.
        return (f"Deep Research did not finish within {FIRST_RUN_MINUTES} minutes, so a fresh Deep Research starts "
                "(owner rule). This run's Gemini conversation stays saved.")
    progress_at = job.get('progress_at')
    if (job.get('rerun') and not ready and isinstance(sent_at, datetime)
            and _seconds_since({'at': sent_at}) >= RERUN_STALL_MINUTES * 60
            and (not isinstance(progress_at, datetime) or _seconds_since({'at': progress_at}) >= RERUN_STALL_MINUTES * 60)
            and not (reloads and _seconds_since(reloads[-1]) < 120)):
        # A fresh run may finish while it works; one showing no progress is stuck (live case, 28 Sep 2026).
        return (f"Deep Research did not finish within {int(_seconds_since({'at': sent_at}) // 60)} minutes and made no "
                f"visible progress for {RERUN_STALL_MINUTES} minutes. This run's Gemini conversation stays saved.")
    if not sent_at or _seconds_since({'at': sent_at}) < RESEARCH_TIMEOUT_MINUTES * 60:
        return None
    # Still writing (its visible progress text keeps changing): keep waiting, up to a hard limit.
    progress_at = job.get('progress_at')
    if (progress_at and _seconds_since({'at': progress_at}) < RESEARCH_STALL_MINUTES * 60
            and _seconds_since({'at': sent_at}) < RESEARCH_HARD_LIMIT_MINUTES * 60):
        return None
    if reloads and _seconds_since(reloads[-1]) < 10 * 60:
        return None  # give a fresh look at the page a chance first
    if any(SHARE_EXPORT.search(control_label(e.name)) for e in obs.elements
           if not e.disabled and len(control_label(e.name)) <= 40):
        return None  # the report is ready after all
    return (f"Deep Research did not finish within {RESEARCH_TIMEOUT_MINUTES} minutes and made no visible progress for "
            f"{RESEARCH_STALL_MINUTES} minutes. "
            "Its Gemini conversation is saved: use Copy report again once it finishes, or Research again.")


# Menus that have held Gemini's Deep Research tool (fresh chats show "File upload" instead of "Upload & tools").
DEEP_RESEARCH_MENUS = ('tools', 'more tools', 'upload & tools', 'file upload', 'add files', 'open upload file menu')
DEEP_RESEARCH_ON = re.compile(r"^(?:deselect|remove|turn off|disable)\s+deep\s+research$", re.I)


def deep_research_active(elements):
    """True only when Gemini shows the Deep Research tool switched on (never inferred from the model name)."""
    return any(DEEP_RESEARCH_ON.fullmatch(control_label(e.name))
               or (control_label(e.name).lower() == 'deep research' and e.selected) for e in elements)
