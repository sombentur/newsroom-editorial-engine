"""Owner's examples adapted into reusable, article-specific layouts."""
COMMON = """Create a 16:9 premium investigative news thumbnail for {site_name}.
Article-specific scene brief: {brief}
Brand: {brand_style}
Use realistic DSLR documentary photography aesthetics, cinematic lighting, ultra-high contrast,
shallow depth of field and a premium cinematic colour grade. Serious investigative journalism,
emotionally expressive people, clean mobile-readable composition. No illustration, cartoon,
painting, holograms or synthetic AI-art aesthetic. This is generated conceptual imagery,
not an authentic photograph or evidence of the event.
Adapt all scenes to the article's supported facts. Do not invent wrongdoing, monetary amounts,
documents, charts or evidence. Keep allegations explicitly uncertain. Do not depict an
identifiable real politician, official or company committing wrongdoing. Use generic people,
non-identifiable silhouettes and unbranded settings for sensitive stories.
LEFT: human consequences. RIGHT: the relevant institutional or technological context.
CENTER: choose at most two subtle conceptual connectors, leaving ample space; no clutter.
TEXT PLACEMENT: TOP ONLY. Reserve the top 36 percent as clean dark negative space.
The app will typeset the approved headlines there, with the second line largest.
Generate the photographic background only: no letters, numbers, logos, watermarks,
headlines, labels or readable interface text anywhere. Keep faces below the reserved area.
"""

HUMAN_IMAGE_PROMPT = COMMON + """
Prompt language: English. Audience: US / Western readers. Final headline language: English.
Premium documentary typography will be added by the app in two lines, second line dominant.
For workplace-AI stories, the layout example is an experienced but exhausted professional
at a late-night American office on the left (steel blue, desaturated grey); a credible generic
monitoring environment on the right (deep red warnings, black shadows, blue accents).
Optional conceptual connector: a broken blank ID badge or subtle surveillance cue.
Portray skill and dignity, not incompetence. Match emotions to the evidence.
Example headlines ONLY for the corresponding supported story:
AI WANTS YOU TO QUIT? / THE GHOST FIRING PROTOCOL.
Do not reuse these claims or scenes for unrelated articles.
"""

KANNADIGA_IMAGE_PROMPT = COMMON + """
Prompt language: English. Audience: Kannada / Karnataka readers. Final headline language: Kannada.
The app will add three lines in crisp Kannada newspaper-style typography; second line largest.
No random English text anywhere. Kannada wording must be editorially checked.
For a supported recruitment-investigation story, the layout example is a young Karnataka
aspirant studying late in a modest Dharwad PG room on the left: warm golden study lamp,
muted brown, books, family photograph and dignified determination after years of sacrifice.
On the right: institutional corridor, sealed examination boxes, generic official silhouettes
or back views, forensic document review and CCTV; deep red and dark blue shadows.
Choose a restrained conceptual center such as an answer-sheet pattern and magnifying glass
or scales of justice. Do not fabricate evidence or imply an identified person is guilty.
Example headlines ONLY for the corresponding supported story:
₹80 ಲಕ್ಷಕ್ಕೆ ಸರ್ಕಾರಿ ಹುದ್ದೆ? / ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ / ಓಎಂಆರ್ ತಿದ್ದಾಟದ ಆರೋಪ!
Do not reuse this amount or scandal claim for unrelated articles.
"""

HEADLINE_RULE = """
Also return thumbnail_headlines as an array: exactly three short Kannada-script-only lines
for Kannada, or exactly two English lines for English. Use the article's actual supported
topic, preserving allegation/uncertainty wording. No invented claims, amounts or quotes.
The second line is the largest: keep it especially concise (ideally under 35 characters).
Keep every line short for mobile readability. The featured_image_brief must be in English,
describing article-specific left/right photographic scenes and at most two center symbols.
Write public image metadata as neutral, factual editorial description. Do not mention the image-generation provider, model, process, or use phrases such as AI-generated.
"""


# ── Owner's thumbnail prompt format (27 Sep 2026) ────────────────────────────────────────────────────────────
# ChatGPT creates the COMPLETE thumbnail poster, headline text included; the app never adds text to the image.
# The SEO step returns article-specific content (thumbnail_headlines + thumbnail_design, in English); the app
# fills the owner's exact template: Kannada headline text for Kannadiga, English for Human.
import json
import re

KN_EXAMPLE_HEADLINES = ["₹80 ಲಕ್ಷಕ್ಕೆ ಸರ್ಕಾರಿ ಹುದ್ದೆ?", "ಕೆಪಿಎಸ್ಸಿ ನೇಮಕಾತಿ ಹಗರಣ", "ಓಎಂಆರ್ ತಿದ್ದಾಟದ ಆರೋಪ!"]
KN_EXAMPLE_DESIGN = {
    "story_type": "investigative government recruitment scandal",
    "emotion": "investigation, alleged corruption, betrayal of merit, student pain and institutional crisis",
    "feel": "a Netflix investigative documentary + Kannada breaking-news exposé",
    "rules": ["Use generic government-official silhouettes and documentary-style institutional imagery."],
    "left": {"title": "MERIT & SACRIFICE", "intro": "Realistic documentary photograph showing:",
             "shows": ["young Karnataka government-job aspirant studying late at night", "small Dharwad-style PG room",
                       "books, handwritten notes and exam preparation material", "tired but determined expression",
                       "parents' photograph near study desk", "modest room environment", "government-exam admit card",
                       "clock showing late night", "emotional sense of years of preparation and sacrifice"],
             "colors": ["warm golden study lamp", "muted brown", "realistic human emotion",
                        "hopeful but exhausted atmosphere"]},
    "right": {"title": "RECRUITMENT INVESTIGATION", "intro": "Realistic documentary photograph showing:",
              "shows": ["secure government strong-room corridor", "sealed examination boxes", "OMR answer sheets",
                        "generic government officers shown only from behind or as silhouettes", "investigation files",
                        "evidence bags", "cash bundles partially visible as symbolic evidence",
                        "forensic officials examining documents", "CCTV camera", "missing hard-drive visual cue"],
              "colors": ["deep red investigative tone", "dark blue institutional shadows", "serious forensic atmosphere"]},
    "center": ["cracked OMR answer sheet", "red circles showing altered answer bubbles", "₹80 lakh symbolic price tag",
               "broken government-job appointment file", "magnifying glass over OMR sheet", "scales of justice",
               "subtle Karnataka High Court silhouette", "investigation evidence tape",
               "arrow linking money → OMR → government appointment"],
    "style_extras": [],
}
EN_EXAMPLE_HEADLINES = ["AI WANTS YOU TO QUIT?", "THE GHOST FIRING PROTOCOL"]
EN_EXAMPLE_DESIGN = {
    "story_type": "investigative workplace-AI",
    "emotion": "Paranoia + Burnout + Betrayal + Corporate Control",
    "feel": "a Netflix corporate exposé + Black Mirror-style real-world investigation",
    "rules": ["Use a generic modern American corporate workplace."],
    "left": {"title": "THE EMPLOYEE", "intro": "Realistic photo of:",
             "shows": ["exhausted American professional in a modern office", "late-night workstation",
                       "laptop and multiple monitors", "overwhelmed expression", "several simultaneous work notifications",
                       "performance dashboard", "unread emails", "workload growing visibly",
                       "cold corporate fluorescent lighting"],
             "note": "Make the worker look experienced and professional, not incompetent.",
             "colors": ["cold steel blue", "desaturated corporate grey", "institutional lighting"]},
    "right": {"title": "THE ALGORITHM", "intro": "Realistic corporate monitoring environment showing:",
              "shows": ["employee activity dashboard", "productivity score declining", "idle-time timer",
                        "performance warning", "mouse activity graph", "generic AI monitoring interface",
                        "digital camera / webcam surveillance cue", "manager viewing employee metrics from a dashboard"],
              "note": "Avoid cartoon holograms. Make interfaces look like credible enterprise software.",
              "colors": ["deep red warning tone", "black shadows", "cold digital blue accents"]},
    "center": ["employee silhouette trapped between digital data lines", "performance score dropping from green to red",
               "subtle surveillance eye", "cracked employee ID badge", "resignation letter partly visible",
               "chain made from data points", "downward career graph", "small “VOLUNTARY RESIGNATION” document visual"],
    "style_extras": ["believable American workplace", "psychological corporate thriller atmosphere"],
}

_KN_STYLE = ("investigative journalism", "premium Kannada newsroom aesthetic", "realistic DSLR photography",
             "cinematic lighting", "ultra high contrast", "shallow depth of field", "documentary realism",
             "premium cinematic LUT", "emotionally powerful", "visually clean despite multiple elements",
             "strong mobile readability", "Netflix investigative documentary feel")
_KN_STYLE_END = ("NO illustration", "NO cartoon", "NO painting", "NO fake AI aesthetic")
_EN_STYLE = ("investigative journalism", "cinematic lighting", "ultra high contrast", "realistic DSLR photography",
             "shallow depth of field", "premium cinematic LUT", "Fortune / Bloomberg / Netflix documentary quality")
_EN_STYLE_END = ("strong facial emotion", "premium newsroom composition", "highly clickable", "no illustration",
                 "no cartoon", "no painting", "no synthetic AI-art aesthetic")
# The design never carries its own text rules: the headline text rules are part of the template.
_NO_TEXT = re.compile(r"\b(?:no|without|avoid)\s+(?:any\s+)?(?:text|letters|words|typography|headlines?|captions?)\b", re.I)


def _line(value, limit=220) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def _items(values, limit) -> list[str]:
    lines = [_line(v) for v in (values if isinstance(values, list) else [])]
    return [v for v in lines if v and not _NO_TEXT.search(v)][:limit]


def normalise_design(design, language: str) -> dict:
    """The SEO step's thumbnail content (English), tidied, with the owner's defaults where a part is missing."""
    d = design if isinstance(design, dict) else {}
    kn = language == "kn"

    def side(key, title, intro):
        s = d.get(key) if isinstance(d.get(key), dict) else {}
        note = _line(s.get("note"))
        return {"title": _line(s.get("title"), 60).upper() or title, "intro": _line(s.get("intro"), 120) or intro,
                "shows": _items(s.get("shows"), 12), "note": "" if _NO_TEXT.search(note) else note,
                "colors": _items(s.get("colors"), 5)}

    return {
        "story_type": _line(d.get("story_type"), 80) or "investigative news",
        "emotion": _line(d.get("emotion"), 200),
        "feel": _line(d.get("feel"), 160) or ("a Netflix investigative documentary + Kannada breaking-news exposé"
                                              if kn else "a Netflix investigative exposé + real-world investigation"),
        "rules": _items(d.get("rules"), 4),
        "left": side("left", "THE HUMAN STORY", "Realistic documentary photograph showing:" if kn else "Realistic photo of:"),
        "right": side("right", "THE INVESTIGATION", "Realistic documentary photograph showing:"),
        "center": _items(d.get("center"), 10),
        "style_extras": _items(d.get("style_extras"), 3),
    }


def design_complete(design: dict) -> bool:
    return len(design["left"]["shows"]) >= 4 and len(design["right"]["shows"]) >= 4 and len(design["center"]) >= 3


def fallback_design(brief: str, language: str) -> dict:
    """For older articles without a design: the owner's format around the saved scene brief."""
    scene = _line(brief, 400) or "the people and place at the heart of this story"
    return normalise_design({
        "emotion": "the human stakes of this story",
        "left": {"title": "THE HUMAN STORY", "shows": ["the people affected: " + scene],
                 "colors": ["natural documentary light", "realistic human emotion"]},
        "right": {"title": "THE CONTEXT", "shows": ["the institutional or physical setting of this story"],
                  "colors": ["deep red investigative tone", "dark blue shadows"]},
        "center": ["one restrained symbolic element that links both sides"]}, language)


def design_brief(design: dict) -> str:
    """Short English description of the thumbnail (image metadata)."""
    d = normalise_design(design, "en")
    return _line(f"{d['story_type']}: {d['left']['title'].title()} / {d['right']['title'].title()}", 200)


def render_thumbnail_prompt(language: str, design, headlines: list[str]) -> str:
    """The owner's 16:9 thumbnail prompt. ChatGPT renders the whole poster, headline text included."""
    kn = language == "kn"
    d = normalise_design(design, language)
    h = [_line(x, 90) for x in headlines]
    left_q, right_q = ('"', '"') if kn else ("\u201c", "\u201d")

    def q(value):
        return f"{left_q}{value}{right_q}"

    out = ["🎯 BLOG THUMBNAIL GENERATION PROMPT — 16:9", "Prompt Language: English",
           "Thumbnail Text: " + ("Kannada" if kn else "English"),
           "Audience: " + ("Kannada / Karnataka audience" if kn else "US / Western audience"),
           "Style: Real photography only, realistic investigative documentary photography, NO AI-art look",
           f"Create a 16:9 ultra high-impact {d['story_type']} thumbnail using realistic documentary photography."]
    if kn:
        out += ["⚠️ The final thumbnail MUST display ALL headline text in perfect Kannada script.",
                "⚠️ Kannada spelling must be 100% accurate.",
                "⚠️ Use premium Kannada newspaper-style typography.",
                "⚠️ Do NOT place random English words anywhere in the image.",
                "⚠️ Do not depict any identifiable real politician or official as committing a crime."]
        out += ["⚠️ " + rule for rule in d["rules"]]
        if d["emotion"]:
            out.append(f"⚠️ The image must communicate {d['emotion'].rstrip('.')}.")
        out.append(f"⚠️ Must feel like {d['feel'].rstrip('.')}.")
    else:
        if d["emotion"]:
            out.append(f"⚠️ Emotion = {d['emotion']}")
        out.append(f"⚠️ Must feel like {d['feel'].rstrip('.')}, but remain realistic documentary photography.")
        out.append("⚠️ NO identifiable real person or company should be accused of wrongdoing.")
        out += ["⚠️ " + rule for rule in d["rules"]]
        out.append("⚠️ Final design must be visually clean enough to remain readable on mobile.")
    out += ["TEXT PLACEMENT — TOP ONLY", "Main Headline", q(h[0]), "Second Headline — LARGEST", q(h[1])]
    if kn:
        out += ["Third Line", q(h[2]), "Use very large, bold, premium Kannada typography.",
                f"{q(h[1])} must be the strongest and largest visual text."]
    else:
        out += ["Use premium, high-end documentary typography.", f"{q(h[1])} should dominate the composition."]
    for key, label in (("left", "LEFT SIDE"), ("right", "RIGHT SIDE")):
        side = d[key]
        out += [f"{label} — {side['title']}", side["intro"], *side["shows"]]
        if side["note"]:
            out.append(side["note"])
        if side["colors"]:
            out += ["Color tone:", *side["colors"]]
    out += ["CENTER OVERLAY — HIGH CTR " + ("VISUAL" if kn else "ELEMENT"), "Show:", *d["center"],
            "Do NOT make the visual cartoonish." if kn else "Do NOT overcrowd the image."]
    if kn:
        out += ["STYLE", *_KN_STYLE, *d["style_extras"], *_KN_STYLE_END,
                "KANNADA TYPOGRAPHY REQUIREMENT", "Render ONLY these headline texts:", *[q(x) for x in h],
                "Kannada letters must be perfectly shaped, crisp, readable and professionally typeset."]
    else:
        out += ["STYLE", *_EN_STYLE, *d["style_extras"], *_EN_STYLE_END]
    out.append("Aspect Ratio: 16:9")
    return "\n".join(out)


def thumbnail_prompt_for(article: dict, language: str, headlines: list[str], brief: str = "") -> str:
    """The prompt sent to ChatGPT for this article (current headlines, so owner edits are included)."""
    design = article.get("thumbnail_design") or fallback_design(brief or article.get("featured_image_brief", ""), language)
    return render_thumbnail_prompt(language, design, headlines)


_TITLE_NOTE = ("; read top to bottom, the lines also become the post title, so together they must read as one "
               "complete, accurate headline")


def design_request(language: str) -> str:
    """What the SEO step returns for the thumbnail (the app fills the owner's template with it)."""
    kn = language == "kn"
    example = json.dumps({"thumbnail_headlines": KN_EXAMPLE_HEADLINES if kn else EN_EXAMPLE_HEADLINES,
                          "thumbnail_design": KN_EXAMPLE_DESIGN if kn else EN_EXAMPLE_DESIGN}, ensure_ascii=False)
    headlines = (
        '"thumbnail_headlines" (exactly 3 lines of Kannada-script text for the top of the thumbnail: '
        "1) the main headline, a short hook question or claim; 2) the second headline, the LARGEST text: the story "
        "in 2-4 words; 3) the third line: the key allegation or consequence. English terms are written phonetically "
        "in Kannada script (KPSC → ಕೆಪಿಎಸ್ಸಿ, OMR → ಓಎಂಆರ್); never Latin letters (digits and ₹ are fine); keep "
        "allegations as allegations" + _TITLE_NOTE + "),\n" if kn else
        '"thumbnail_headlines" (exactly 2 short UPPERCASE English lines for the top of the thumbnail: 1) the main '
        "headline, a short hook question or claim; 2) the second headline, the LARGEST text: the story in 2-5 words"
        + _TITLE_NOTE + "),\n")
    return (headlines
            + '"thumbnail_design" (an object in English describing a realistic documentary-photography thumbnail for '
            'THIS story: "story_type" (the kind of story, e.g. "investigative flood-disaster"); "emotion" '
            + ("(what the image must communicate)" if kn else '(four feelings joined by " + ")')
            + '; "feel" (e.g. "a Netflix investigative documentary + ..."); "rules" (1-3 story-specific safety or '
            'setting rules); "left" and "right" (each {"title": 2-4 UPPERCASE words, "intro": the line that opens the '
            'list, "shows": 8-10 concrete visual details, "note": optional one-line direction, "colors": 3-4 colour '
            'and lighting tones}; left = the human side, right = the institutional, evidence or cause side); '
            '"center" (6-9 symbolic overlay elements that link both sides); "style_extras" (0-2 story-specific style '
            "lines)). Build every element from the article's facts: no invented amounts, evidence or accusations, and "
            "no identifiable real person shown committing wrongdoing. Do not add rules about text, letters or "
            "typography; the thumbnail's text rules are added separately.\n"
            "Thumbnail format example from a different story (copy its structure and level of detail, never its "
            "content):\n" + example + "\n")


_SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "vs",
                "via", "with"}


def _title_word(word: str, first: bool, context: str, abbreviations: set[str]) -> str:
    match = re.match(r"([^A-Za-z]*)([A-Za-z]+)(.*)", word)
    if not match:
        return word
    lead, core, rest = match.groups()
    if len(core) > 1 and core.upper() in abbreviations:  # the article writes it U.S., U.K., ...
        return lead + core.upper() + rest.lower()
    # Keep a word the way the article usually writes it when that is special (AI, ILO, McDonald).
    forms = re.findall(r"(?<![A-Za-z])" + core + r"(?![A-Za-z])", context, re.I)
    special = [f for f in forms if f[1:] != f[1:].lower()]
    if special and len(special) * 2 > len(forms):
        return lead + max(set(special), key=special.count) + rest.lower()
    if not first and not lead and core.lower() in _SMALL_WORDS:
        return word.lower()
    return lead + core[0] + core[1:].lower() + rest.lower()


def _title_case(line: str, context: str, abbreviations: set[str]) -> str:
    """An UPPERCASE English thumbnail line in title case (the words stay the thumbnail's own)."""
    if line != line.upper():
        return line
    return " ".join("-".join(_title_word(part, not i and not j, context, abbreviations)
                             for j, part in enumerate(word.split("-")))
                    for i, word in enumerate(line.split()))


def headline_from_thumbnail(lines: list[str], language: str, context: str = "") -> str:
    """The post title: the thumbnail lines read top to bottom (owner rule: the title matches the thumbnail text).

    context: the article's own text (SEO title, description, body), the evidence for how English words are written.
    """
    context = re.sub(r"\S*(?:://|www\.|/)\S*", " ", context)  # links (source URLs) say nothing about casing
    abbreviations = {a.replace(".", "") for a in re.findall(r"(?<![A-Za-z.])(?:[A-Z]\.){2,}", context)}
    title, colon = "", False
    for i, raw in enumerate(lines):
        line = " ".join(str(raw).split())
        if language != "kn":
            line = _title_case(line, context, abbreviations)
        if i:
            if title[-1] in "?!.:":
                title += " "
            elif not colon:
                title, colon = title + ": ", True
            else:
                title += ", "
        title += line
    return title
