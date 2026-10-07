"""Owner's thumbnail format (27 Sep 2026): the prompt matches the owner's examples, and ChatGPT's complete poster
(headline text included) is kept exactly as made: no text added, nothing cropped."""
import asyncio
import base64
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from lib.thumbnail_prompts import (EN_EXAMPLE_DESIGN, EN_EXAMPLE_HEADLINES, KN_EXAMPLE_DESIGN, KN_EXAMPLE_HEADLINES,  # noqa: E402
                                   render_thumbnail_prompt)

OWNER_KN = """🎯 BLOG THUMBNAIL GENERATION PROMPT — 16:9
Prompt Language: English
Thumbnail Text: Kannada
Audience: Kannada / Karnataka audience
Style: Real photography only, realistic investigative documentary photography, NO AI-art look
Create a 16:9 ultra high-impact investigative government recruitment scandal thumbnail using realistic documentary photography.
⚠️ The final thumbnail MUST display ALL headline text in perfect Kannada script.
⚠️ Kannada spelling must be 100% accurate.
⚠️ Use premium Kannada newspaper-style typography.
⚠️ Do NOT place random English words anywhere in the image.
⚠️ Do not depict any identifiable real politician or official as committing a crime.
⚠️ Use generic government-official silhouettes and documentary-style institutional imagery.
⚠️ The image must communicate investigation, alleged corruption, betrayal of merit, student pain and institutional crisis.
⚠️ Must feel like a Netflix investigative documentary + Kannada breaking-news exposé.
TEXT PLACEMENT — TOP ONLY
Main Headline
"₹80 ಲಕ್ಷಕ್ಕೆ ಸರ್ಕಾರಿ ಹುದ್ದೆ?"
Second Headline — LARGEST
"ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ"
Third Line
"ಓಎಂಆರ್ ತಿದ್ದಾಟದ ಆರೋಪ!"
Use very large, bold, premium Kannada typography.
"ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ" must be the strongest and largest visual text.
LEFT SIDE — MERIT & SACRIFICE
Realistic documentary photograph showing:
young Karnataka government-job aspirant studying late at night
small Dharwad-style PG room
books, handwritten notes and exam preparation material
tired but determined expression
parents' photograph near study desk
modest room environment
government-exam admit card
clock showing late night
emotional sense of years of preparation and sacrifice
Color tone:
warm golden study lamp
muted brown
realistic human emotion
hopeful but exhausted atmosphere
RIGHT SIDE — RECRUITMENT INVESTIGATION
Realistic documentary photograph showing:
secure government strong-room corridor
sealed examination boxes
OMR answer sheets
generic government officers shown only from behind or as silhouettes
investigation files
evidence bags
cash bundles partially visible as symbolic evidence
forensic officials examining documents
CCTV camera
missing hard-drive visual cue
Color tone:
deep red investigative tone
dark blue institutional shadows
serious forensic atmosphere
CENTER OVERLAY — HIGH CTR VISUAL
Show:
cracked OMR answer sheet
red circles showing altered answer bubbles
₹80 lakh symbolic price tag
broken government-job appointment file
magnifying glass over OMR sheet
scales of justice
subtle Karnataka High Court silhouette
investigation evidence tape
arrow linking money → OMR → government appointment
Do NOT make the visual cartoonish.
STYLE
investigative journalism
premium Kannada newsroom aesthetic
realistic DSLR photography
cinematic lighting
ultra high contrast
shallow depth of field
documentary realism
premium cinematic LUT
emotionally powerful
visually clean despite multiple elements
strong mobile readability
Netflix investigative documentary feel
NO illustration
NO cartoon
NO painting
NO fake AI aesthetic
KANNADA TYPOGRAPHY REQUIREMENT
Render ONLY these headline texts:
"₹80 ಲಕ್ಷಕ್ಕೆ ಸರ್ಕಾರಿ ಹುದ್ದೆ?"
"ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ"
"ಓಎಂಆರ್ ತಿದ್ದಾಟದ ಆರೋಪ!"
Kannada letters must be perfectly shaped, crisp, readable and professionally typeset.
Aspect Ratio: 16:9"""


def test_kannada_prompt_reproduces_the_owners_example_exactly():
    assert render_thumbnail_prompt("kn", KN_EXAMPLE_DESIGN, KN_EXAMPLE_HEADLINES) == OWNER_KN


def test_english_prompt_follows_the_owners_example():
    prompt = render_thumbnail_prompt("en", EN_EXAMPLE_DESIGN, EN_EXAMPLE_HEADLINES).split("\n")
    expected_order = ["🎯 BLOG THUMBNAIL GENERATION PROMPT — 16:9", "Thumbnail Text: English", "Audience: US / Western audience",
                      "⚠️ Emotion = Paranoia + Burnout + Betrayal + Corporate Control",
                      "⚠️ Must feel like a Netflix corporate exposé + Black Mirror-style real-world investigation, but remain realistic documentary photography.",
                      "⚠️ Use a generic modern American corporate workplace.",
                      "⚠️ Final design must be visually clean enough to remain readable on mobile.",
                      "TEXT PLACEMENT — TOP ONLY", "Main Headline", "“AI WANTS YOU TO QUIT?”", "Second Headline — LARGEST",
                      "“THE GHOST FIRING PROTOCOL”", "Use premium, high-end documentary typography.",
                      "“THE GHOST FIRING PROTOCOL” should dominate the composition.", "LEFT SIDE — THE EMPLOYEE",
                      "Realistic photo of:", "Make the worker look experienced and professional, not incompetent.",
                      "Color tone:", "RIGHT SIDE — THE ALGORITHM", "Realistic corporate monitoring environment showing:",
                      "CENTER OVERLAY — HIGH CTR ELEMENT", "Show:", "Do NOT overcrowd the image.", "STYLE",
                      "Fortune / Bloomberg / Netflix documentary quality", "believable American workplace",
                      "no synthetic AI-art aesthetic", "Aspect Ratio: 16:9"]
    positions = [prompt.index(line) for line in expected_order]
    assert positions == sorted(positions), "sections in the owner's order"
    assert "KANNADA TYPOGRAPHY REQUIREMENT" not in prompt


def test_design_text_rules_are_dropped_and_parse_requires_a_complete_design():
    from lib.report_article import parse_seo
    base = ('{"seo_title":"t","meta_description":"m","focus_keyword":"k","slug":"s",'
            '"thumbnail_headlines":["ONE HOOK?","THE STORY"],"thumbnail_design":')
    full = ('{"story_type":"investigative flood-disaster","emotion":"Grief + Urgency + Anger + Resilience",'
            '"rules":["No text or letters anywhere.","Use a generic flooded village."],'
            '"left":{"title":"the families","shows":["a","b","c","d"],"colors":["grey"]},'
            '"right":{"title":"the response","shows":["e","f","g","h"],"colors":["red"]},"center":["x","y","z"]}')
    seo = parse_seo(base + full + "}", "en")
    assert "No text or letters" not in seo["thumbnail_prompt"] and "⚠️ Use a generic flooded village." in seo["thumbnail_prompt"]
    assert "LEFT SIDE — THE FAMILIES" in seo["thumbnail_prompt"] and seo["thumbnail_prompt"].endswith("Aspect Ratio: 16:9")
    with pytest.raises(ValueError, match="incomplete"):
        parse_seo(base + '{"left":{"shows":["a"]}}}', "en")
    with pytest.raises(ValueError, match="Kannada script"):
        parse_seo(base.replace('["ONE HOOK?","THE STORY"]', '["KPSC ಹಗರಣ","ಎರಡು","ಮೂರು"]') + full + "}", "kn")


def test_chatgpt_poster_is_kept_exactly_as_made():
    from lib.browser_bridge import keep_generated_image
    buf = io.BytesIO()
    poster = Image.new("RGB", (1536, 1024), "#1d2a3a")
    poster.paste(Image.new("RGB", (1536, 120), "#f5c542"), (0, 0))  # headline band at the very top
    poster.save(buf, "PNG")
    kept = Image.open(io.BytesIO(keep_generated_image(buf.getvalue())))
    assert kept.format == "WEBP" and kept.size == (1536, 1024), "never cropped to 16:9"
    assert kept.convert("RGB").getpixel((768, 20))[0] > 200, "the top headline band is still there"
    portrait = io.BytesIO()
    Image.new("RGB", (1024, 1536)).save(portrait, "PNG")
    with pytest.raises(ValueError):
        keep_generated_image(portrait.getvalue())


def test_image_step_sends_owner_prompt_and_adds_no_text():
    from lib import workflow as w
    buf = io.BytesIO()
    Image.new("RGB", (1536, 1024), "#223344").save(buf, "WEBP")
    b64 = base64.b64encode(buf.getvalue()).decode()
    stored = {"id": "A", "site_key": "kannadiga", "topic_snapshot": {"topic": "t"},
              "article": {"headline": "ಶೀರ್ಷಿಕೆ", "slug": "story", "thumbnail_headlines": KN_EXAMPLE_HEADLINES,
                          "thumbnail_design": KN_EXAMPLE_DESIGN}}

    async def update(art_id, patch_, hist=None):
        stored.update(patch_)
        return dict(stored)
    run_job = AsyncMock(return_value=b64)
    with patch.object(w, "_preflight", AsyncMock(return_value=({"key": "kannadiga", "language": "kn", "name": "Kannada Edition"}, None))), \
            patch.object(w, "_update", side_effect=update), patch.object(w, "audit", AsyncMock()), \
            patch.object(w, "_stopped_by_editor", AsyncMock(return_value=None)), \
            patch("lib.browser_bridge.enabled", AsyncMock(return_value=True)), \
            patch("lib.browser_bridge.run_job", run_job), patch("lib.browser_bridge.consumed", AsyncMock()), \
            patch("lib.thumbnails.add_headlines") as overlay:
        asyncio.run(w.run_image_stage(dict(stored), {"key": "kannadiga", "language": "kn", "name": "Kannada Edition"}))
    sent = run_job.await_args.args[2]
    assert sent.startswith(OWNER_KN) and sent.endswith("Generate this thumbnail image now.")
    assert not overlay.called, "the app adds no text"
    assert stored["image"]["data_uri"] == "data:image/webp;base64," + b64, "ChatGPT's poster unchanged"


def test_post_title_matches_the_thumbnail_text():
    from lib.thumbnail_prompts import design_request, headline_from_thumbnail
    assert headline_from_thumbnail(KN_EXAMPLE_HEADLINES, "kn") == "₹80 ಲಕ್ಷಕ್ಕೆ ಸರ್ಕಾರಿ ಹುದ್ದೆ? ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ: ಓಎಂಆರ್ ತಿದ್ದಾಟದ ಆರೋಪ!"
    assert headline_from_thumbnail(["19 ಪಟ್ಟು ಮಳೆ ತಂದ ಮಹಾ ಅನಾಹುತ?", "ಉತ್ತರ ಪ್ರದೇಶ ಪ್ರವಾಹ", "56 ಸಾವು, ಸಾವಿರಕ್ಕೂ ಹೆಚ್ಚು ಮನೆ ಹಾನಿ"],
                                   "kn") == "19 ಪಟ್ಟು ಮಳೆ ತಂದ ಮಹಾ ಅನಾಹುತ? ಉತ್ತರ ಪ್ರದೇಶ ಪ್ರವಾಹ: 56 ಸಾವು, ಸಾವಿರಕ್ಕೂ ಹೆಚ್ಚು ಮನೆ ಹಾನಿ"
    article = "Employers now use AI tools to watch workers. The ILO says AI-driven monitoring is spreading."
    assert headline_from_thumbnail(EN_EXAMPLE_HEADLINES, "en", article) == "AI Wants You to Quit? The Ghost Firing Protocol"
    assert headline_from_thumbnail(["WHO PAYS FOR AI-DRIVEN LAYOFFS?", "THE ILO WARNS"], "en", article) == \
        "Who Pays for AI-Driven Layoffs? The ILO Warns"
    for language in ("kn", "en"):
        assert "the lines also become the post title" in design_request(language)
    # Live case: the ILO article writes "U.S."; its only lowercase "us" were inside source links.
    ilo = "The U.S. voted against the convention. Sources: https://www.hrw.org/report/platform-work-in-the-us earn.us/x"
    assert headline_from_thumbnail(["GLOBAL RIGHTS FOR GIG WORKERS", "US VOTES NO"], "en", ilo) == \
        "Global Rights for Gig Workers: US Votes No"


def test_kannada_lines_reject_letters_of_another_script():
    from lib.thumbnails import validate_headlines
    # Live case (post 2983): Gujarati vowel sign and letter inside ರಾಜೀನಾಮೆ.
    with pytest.raises(ValueError, match="another script: .*U\\+0AA8"):
        validate_headlines(["ಇಂಡಿ–ಚಡಚಣ ಬರ ಪಟ್ಟಿಯಿಂದ ಹೊರಗೆ", "ಡೇಟಾ, ರಾಜಕೀಯ", "ಶಾಸಕ ರಾಜીનಾಮೆ ಒತ್ತಡ"], "kn")
    assert validate_headlines(KN_EXAMPLE_HEADLINES, "kn") == KN_EXAMPLE_HEADLINES  # ₹, digits, punctuation are fine
    assert validate_headlines(["ಟೌನ್\u200cಶಿಪ್ ವಿರುದ್ಧ", "ರೈತರ ಕಿಚ್ಚು", "೨೦೨೬ರ ಹೋರಾಟ"], "kn")  # ZWNJ and Kannada digits


def _image_stage(run_job, blocked=None, **saved):
    from lib import workflow as w
    stored = {"id": "A", "site_key": "human", "stage": "article_validated", "topic_snapshot": {"topic": "t"}, **saved,
              "article": {"headline": "Headline", "slug": "story", "thumbnail_headlines": EN_EXAMPLE_HEADLINES,
                          "thumbnail_design": EN_EXAMPLE_DESIGN}}
    history = []

    async def update(art_id, patch_, hist=None):
        stored.update(patch_)
        history.append((hist or {}).get("note", ""))
        return dict(stored)
    with patch.object(w, "_preflight", AsyncMock(return_value=({"key": "human", "language": "en", "name": "English Edition"}, None))), \
            patch.object(w, "_update", side_effect=update), patch.object(w, "audit", AsyncMock()), \
            patch.object(w, "_stopped_by_editor", AsyncMock(return_value=None)), \
            patch.object(w, "_retry_blocked", AsyncMock(return_value=blocked)), \
            patch("lib.browser_bridge.enabled", AsyncMock(return_value=True)), \
            patch("lib.browser_bridge.run_job", run_job), patch("lib.browser_bridge.consumed", AsyncMock()):
        asyncio.run(w.run_image_stage(dict(stored), {"key": "human", "language": "en", "name": "English Edition"}))
    return stored, history


RELEASED = 'ChatGPT\'s image generation failed (it showed "Image generation failed").'


def test_a_failed_chatgpt_image_is_made_again_in_a_fresh_chat():
    """Live case (28 Sep 2026): ChatGPT's image tool failed ("treated the request as an edit") and the article waited
    for the owner for hours."""
    from lib import workflow as w
    from lib.ai import AIError
    buf = io.BytesIO()
    Image.new("RGB", (1536, 1024), "#223344").save(buf, "WEBP")
    b64 = base64.b64encode(buf.getvalue()).decode()
    run_job = AsyncMock(side_effect=[AIError(RELEASED, "browser"), b64])
    stored, history = _image_stage(run_job)
    (first, second) = run_job.await_args_list
    assert first.args[2] == second.args[2], "one wording, so a job is never replaced after a restart"
    assert first.args[2].endswith(w.FRESH_IMAGE_NOTE + "\n\nGenerate this thumbnail image now.")
    assert first.args[2].startswith(first.kwargs["same_prompt"]) and w.FRESH_IMAGE_NOTE not in first.kwargs["same_prompt"]
    assert stored["stage"] == "image_ready" and stored["image"]["data_uri"].endswith(b64)
    assert any("again in a new chat at High thinking (automatic retry 1 of 2)" in note for note in history)
    assert stored["image_fresh_runs"] == 1
    levels = [(c.kwargs["effort"], c.kwargs["wait_limit_seconds"]) for c in run_job.await_args_list]
    assert levels == [("Medium", 300), ("High", 420)], "one thinking level up for the fresh chat"
    assert any("new chat at High thinking" in note for note in history)


def test_a_chatgpt_image_failing_in_three_chats_waits_for_the_owner_and_other_stops_are_not_retried():
    from lib.ai import AIError
    run_job = AsyncMock(side_effect=AIError(RELEASED, "browser"))
    stored, _ = _image_stage(run_job)
    assert run_job.await_count == 3 and stored["stage"] == "held_review"
    assert [c.kwargs["effort"] for c in run_job.await_args_list] == ["Medium", "High", "Extra High"]
    assert "failed in 3 ChatGPT chats; press Retry" in stored["held_reason"]
    for stop in (AIError("Chrome extension is offline. Open Chrome with the Newsroom extension", "browser"),
                 AIError('ChatGPT showed "Image generation failed"; a fresh ChatGPT chat starts shortly.', "browser")):
        run_job = AsyncMock(side_effect=stop)
        stored, _ = _image_stage(run_job)
        assert run_job.await_count == 1 and stored["stage"] == "held_review", "only a real release is retried"
    run_job = AsyncMock(side_effect=AIError(RELEASED, "browser"))
    stored, _ = _image_stage(run_job, blocked="AI is paused. Select Resume before starting a manual article action.")
    assert run_job.await_count == 1 and stored["stage"] == "held_review", "no automatic retry while paused"
    run_job = AsyncMock(side_effect=AIError("Page changed; ChatGPT's image generation failed (maybe)", "browser"))
    _image_stage(run_job)
    assert run_job.await_count == 1, "only the exact release message is retried"


def test_the_fresh_chat_count_survives_a_restart():
    """Review finding (28 Sep 2026): the count is stored on the article, so a restart cannot start it again."""
    from lib.ai import AIError
    run_job = AsyncMock(side_effect=AIError(RELEASED, "browser"))
    stored, _ = _image_stage(run_job, image_fresh_runs=2)
    assert run_job.await_count == 1 and "failed in 3 ChatGPT chats" in stored["held_reason"]
    run_job = AsyncMock(side_effect=AIError(RELEASED, "browser"))
    stored, _ = _image_stage(run_job)
    assert stored["image_fresh_runs"] == 2
