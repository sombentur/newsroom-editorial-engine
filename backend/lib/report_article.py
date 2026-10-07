"""Report-as-article workflow (owner's manual process, automated).

1. Gemini Deep Research (Chrome, Gemini Pro) writes the article itself; Share & Export -> Copy contents.
2. The copied report becomes the WordPress post body (no rewrite).
3. ChatGPT (Chrome) reads the article and returns SEO assets + the thumbnail headlines and design.
4. The app fills the owner's thumbnail prompt format; ChatGPT generates the COMPLETE poster (headline text
   included) and the app uploads it to WordPress unchanged.
"""

import difflib
import html
import json
import re
from urllib.parse import urlsplit

from lib.editorial_html import sanitize_html
from lib.kannada_audit import prose_html, script_share

KANNADA_STYLE = (
    "Write everything in Kannada script. When an English word is the term readers actually use or search for "
    "(for example Fake Seeds, Black Market, Urea, Scam, Mafia), write it phonetically in Kannada script "
    "(ಫೇಕ್ ಸೀಡ್ಸ್, ಬ್ಲ್ಯಾಕ್ ಮಾರ್ಕೆಟ್, ಯೂರಿಯಾ, ಸ್ಕ್ಯಾಮ್, ಮಾಫಿಯಾ) instead of using English letters. "
    "Use English (Latin) letters only for URLs and for source titles/publisher names in the source list."
)

DEEP_RESEARCH_ARTICLE_PROMPT = """Use Deep Research to investigate this topic and write a complete, publication-ready long-form news article for {site_name}.

Topic: {topic}
Angle: {angle}
Audience: {audience}
Geographic focus: {geography}
Current date and time: {current_datetime_with_timezone}
Article language: {language}

Write it as the final article that will be published as-is, not as a research memo:
- Start with one engaging, click-worthy but truthful headline on the first line (no label before it).
- Open with two or three short paragraphs: what happened, why it matters now, who is affected.
- Then 4 to 8 clear section headings, each with short readable paragraphs (2 to 4 sentences).
- Use a compact table only where readers must compare numbers or dates.
- Verify the central event and its date from primary or authoritative sources. Separate established facts from
  allegations, estimates and opinions, and attribute each important claim in the text. Never invent quotes,
  numbers, people or events. Flag anything that needs legal/editorial caution in neutral wording.
- End with a "What happens next" section when supported, then a numbered source list with full https URLs.
"""

LANGUAGE_RULES = {
    "kn": "\n\nLANGUAGE (mandatory): Write the ENTIRE article in Kannada for Karnataka readers: headline, headings, "
          "body and table text. Search Kannada AND English sources (Prajavani, Vijay Karnataka, Udayavani, Kannada "
          "Prabha, TV9 Kannada, national outlets, Government of Karnataka and Government of India). "
          + KANNADA_STYLE +
          " Spell people, places and departments the way the Government of Karnataka and major Kannada newspapers do. "
          "Write amounts with ₹ and ಸಾವಿರ / ಲಕ್ಷ / ಕೋಟಿ. Deliver the completed article, not a research plan.",
    "en": "\n\nLANGUAGE (mandatory): Write the ENTIRE article in clear American English for US readers, centred on the "
          "consequences for ordinary people, workers and families. Deliver the completed article, not a research plan.",
}

SEO_FIELDS = ("seo_title", "meta_description", "focus_keyword", "slug", "category", "menu_categories", "tags", "excerpt",
              "og_title", "og_description", "featured_image_alt_text", "featured_image_caption",
              "thumbnail_headlines", "thumbnail_design")


def research_prompt(template: str, site: dict, topic: dict, now_iso: str) -> str:
    language = "kn" if site["language"] == "kn" else "en"
    return template.format(
        site_name=site["name"], topic=topic["topic"], angle=topic.get("angle", ""),
        audience=site.get("audience", ""), geography=topic.get("geography", ""),
        current_datetime_with_timezone=now_iso, language="Kannada" if language == "kn" else "English",
    ) + LANGUAGE_RULES[language]


# ── Copied report -> WordPress HTML ─────────────────────────────────────────
_CITATION_APPENDIX = re.compile(r"\n+PROVIDER CITATION LINKS\b.*\Z", re.S)
_CITE_LABEL = re.compile(r"[ \t]*\[cite:\s*\d+(?:\s*,\s*\d+)*\]", re.I)
_URL = re.compile(r"https?://[^\s<>()\[\]\"']+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_LIST = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_SOURCES_HEADING = re.compile(r"^(works cited|sources|references|citations|ಮೂಲಗಳು|ಆಧಾರಗಳು|ಉಲ್ಲೇಖ\S*)\b", re.I)


def _inline(text: str) -> str:
    links: list[str] = []

    def keep(match):
        links.append(f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>')
        return f"\x00{len(links) - 1}\x00"

    text = _MD_LINK.sub(keep, text)
    text = html.escape(text, quote=False)
    text = _URL.sub(lambda m: f'<a href="{m.group(0).rstrip(".,;")}">{m.group(0).rstrip(".,;")}</a>'
                    + m.group(0)[len(m.group(0).rstrip(".,;")):], text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], text)


def _heading_text(line: str) -> str:
    return re.sub(r"^#+\s*", "", line).strip().strip("*").strip()


def _is_heading(line: str, next_blank: bool) -> bool:
    if line.startswith("#"):
        return True
    bare = line.strip("*").strip()
    # Plain-text exports lose "#": a short standalone line without end punctuation is a heading.
    return (line.startswith("**") and line.endswith("**") and len(bare) < 120) or (
        next_blank and 0 < len(bare) < 90 and not re.search(r"[.!?:;,।]$", bare) and not _LIST.match(line))


_HTML_REPORT = re.compile(r"<(?:p|h[1-6]|ul|ol|table|div|section|article|blockquote)\b", re.I)
_HTML_KEEP = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "a",
              "table", "thead", "tbody", "tr", "th", "td", "blockquote"}


def _plain(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _sentences(fragment: str) -> list[str]:
    """Sentences of the paragraphs and list items in an HTML fragment (headings left out)."""
    texts = [_plain(t) for t in re.findall(r"<(?:p|li)\b[^>]*>(.*?)</(?:p|li)>", fragment, re.S | re.I)]
    return [s for t in texts for s in re.split(r"(?<=[.!?।])\s+", t) if len(s) >= 40]


_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)


def _tidy_tables(body: str) -> tuple[str, str]:
    """Remove tables without data. Gemini sometimes restarts its report: a table header, then the real headline
    absorbed as a lone row. That table goes, and so does the false start before it when the article repeats it.
    Returns (body, the headline found in such a table, or "")."""
    headline, start = "", 0
    while match := _TABLE.search(body, start):
        rows = re.findall(r"<tr\b.*?</tr>", match.group(0), re.S | re.I)
        cells = [[_plain(c) for c in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row, re.S | re.I)] for row in rows]
        if any(sum(1 for c in row if c) >= 2 for row in cells[1:]):
            start = match.end()  # a real table
            continue
        before, after = body[:match.start()], body[match.end():]
        lone = [c for row in cells[1:] for c in row if c]
        if len(lone) == 1 and 15 <= len(lone[0]) <= 200 and not lone[0].endswith("."):
            headline = lone[0]
            early, later = _sentences(before), _sentences(after)
            repeated = sum(1 for s in early if difflib.get_close_matches(s, later, n=1, cutoff=0.75))
            if early and repeated * 2 >= len(early):
                before = ""  # a false start that the article repeats
        body, start = before + after, len(before)
    return body, headline


def _tidy_text(body: str) -> str:
    """Gemini's copy pads text with non-breaking spaces and blank lines where its citation chips were."""
    body = re.sub(r"\s+", " ", re.sub(r"&nbsp;|\xa0", " ", body))
    body = re.sub(r"\s+(</(?:p|li|td|th|h[1-6]|a|strong|em)>)", r"\1", body)
    body = re.sub(r"(<(?:p|li|td|th|h[1-6])\b[^>]*>)\s+", r"\1", body)
    body = re.sub(r"<p>\s*</p>", "", body)
    return re.sub(r"\s*(<(?:p|h[1-6]|ul|ol|table|blockquote)\b)", r"\n\1", body).strip()


def _html_report_to_article(report: str) -> dict:
    """Gemini's formatted (HTML) copy: keep its headings, paragraphs, lists, tables and source links."""
    import bleach
    cleaned = bleach.clean(report, tags=_HTML_KEEP, attributes={"a": ["href"]}, protocols={"http", "https"},
                           strip=True, strip_comments=True)
    # Gemini's screen-reader page headings ("Conversation with Gemini", "Gemini said") are not the title.
    cleaned = re.sub(r"<(h[1-6])>\s*(?:conversation with gemini|gemini said|you said)\s*</\1>", "", cleaned, flags=re.I)
    headline = ""
    first = re.search(r"<(h[1-3])>(.*?)</\1>", cleaned, re.S | re.I)
    if first:
        headline = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", first.group(2))).split())
        cleaned = cleaned[:first.start()] + cleaned[first.end():]
    cleaned = re.sub(r"<(/?)h1>", r"<\1h2>", cleaned, flags=re.I)
    cleaned = re.sub(r"<(/?)h[4-6]>", r"<\1h3>", cleaned, flags=re.I)
    cleaned = re.sub(r"<(/?)b>", r"<\1strong>", cleaned, flags=re.I)
    cleaned = re.sub(r"<(/?)i>", r"<\1em>", cleaned, flags=re.I)
    cleaned = re.sub(r"<p>\s*(?:<br>\s*)*</p>", "", cleaned)
    body, restart = _tidy_tables(sanitize_html(cleaned))
    body, headline = _tidy_text(body), restart or headline
    if not headline:
        para = re.search(r"<p>(.*?)</p>", body, re.S)
        headline = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", para.group(1) if para else "")).split())[:120]
    text_urls = _URL.findall(html.unescape(re.sub(r"<[^>]+>", " ", body)))
    sources = list(dict.fromkeys(u.rstrip(".,;") for u in [*re.findall(r'href="(https?://[^"]+)"', body), *text_urls]))
    return {"headline": headline[:200], "content_html": body, "sources": sources}


def report_to_article(report: str) -> dict:
    """Convert Gemini's copied report (formatted HTML or Markdown/plain text) into {headline, content_html, sources}."""
    # Gemini's grounding labels ("[cite: 10] https://...", "[cite: 1, 2]") are not for readers.
    report = _CITE_LABEL.sub("", report or "")
    if _HTML_REPORT.search(report):
        return _html_report_to_article(report)
    text = _CITATION_APPENDIX.sub("", report.replace("\r\n", "\n")).strip()
    lines = text.split("\n")
    title_index = next((i for i, line in enumerate(lines) if line.strip()), 0)
    headline = _heading_text(lines[title_index]) if lines else ""
    lines = lines[title_index + 1:]

    out: list[str] = []
    para: list[str] = []
    items: list[str] = []
    ordered = False
    table: list[list[str]] = []

    def flush():
        nonlocal para, items, table
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para = []
        if items:
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{tag}>")
            items = []
        if table:
            head, *body = table
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>" for row in body)
                       + "</tbody></table>")
            table = []

    for index, raw in enumerate(lines):
        line = raw.strip()
        next_blank = index + 1 >= len(lines) or not lines[index + 1].strip()
        if not line:
            flush()
            continue
        if line.startswith("|"):
            if para or items:
                flush()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                table.append(cells)
            continue
        if table:
            flush()
        if _LIST.match(line):
            if para:
                flush()
            is_ordered = bool(re.match(r"^\s*\d+[.)]", line))
            if items and is_ordered != ordered:
                flush()
            ordered = is_ordered
            items.append(_LIST.sub("", line))
            continue
        if not para and not items and _is_heading(line, next_blank):
            flush()
            tag = "h3" if line.startswith("###") else "h2"
            out.append(f"<{tag}>{_inline(_heading_text(line))}</{tag}>")
            continue
        if items:
            flush()
        para.append(line)
    flush()

    body, restart = _tidy_tables(sanitize_html("\n".join(out)))
    body, headline = _tidy_text(body), restart or headline
    sources = list(dict.fromkeys(u.rstrip(".,;") for u in _URL.findall(report)))
    return {"headline": headline[:200], "content_html": body, "sources": sources}


def report_validation(report: str, article: dict, language: str) -> dict:
    checks, failed = [], []

    def chk(name, ok, note=""):
        checks.append({"name": name, "passed": bool(ok), "note": note})
        if not ok:
            failed.append(name)

    plain = re.sub(r"<[^>]+>", " ", article["content_html"])
    domains = {urlsplit(u).netloc.lower().removeprefix("www.") for u in article["sources"]}
    chk("has_headline", len(article["headline"]) >= 10, article["headline"][:80])
    chk("complete_report", len(plain) >= 2500, f"{len(plain)} characters of article text")
    chk("not_a_plan", not re.search(r"research plan|I.ve put together a", report[:600], re.I), "completed article, not a plan")
    chk("independent_sources", len(domains) >= 2, f"{len(domains)} source websites")
    if language == "kn":
        share = script_share(prose_html(article["content_html"]))
        chk("kannada_script", share >= 0.65, f"{share:.0%} of prose letters in Kannada script (source list excluded)")
    return {"passed": not failed, "checks": checks, "failed_reasons": failed, "report_mode": True}


# ── ChatGPT SEO assets ──────────────────────────────────────────────────────
def seo_prompt(article: dict, site: dict) -> str:
    kn = site["language"] == "kn"
    body = html.unescape(re.sub(r"<[^>]+>", " ", article["content_html"]))
    body = re.sub(r"\s+", " ", body)[:12000]
    from lib.menu_categories import seo_key, seo_list
    from lib.thumbnail_prompts import design_request
    key = site.get("key", "")
    return (
        f"You are the SEO editor for {site['name']} (WordPress with Rank Math). Read the article below and reply with "
        'ONE JSON object only, no other text, starting with "seo_title", with these keys:\n'
        '"seo_title" (max 60 characters, contains the focus keyword), "meta_description" (140-155 characters), '
        '"focus_keyword", "slug" (lowercase English words joined by hyphens, max 6 words), "category" (one short '
        'category name), "tags" (array of 4-6 tags), "excerpt" (one or two sentences), "og_title", "og_description", '
        '"featured_image_alt_text", "featured_image_caption",\n'
        + seo_key(key)
        + design_request(site["language"])
        + (KANNADA_STYLE + " This applies to seo_title, meta_description, focus_keyword, tags, excerpt, og_title, "
           "og_description, alt text, caption and thumbnail_headlines; slug and thumbnail_design stay in English.\n"
           if kn else "All values in English.\n")
        + seo_list(key)
        + "Only state facts that appear in the article.\n\n"
        f"ARTICLE HEADLINE: {article['headline']}\n\nARTICLE:\n{body}"
    )


def parse_seo(answer: str, language: str) -> dict:
    """Extract the JSON object from ChatGPT's answer and normalise it."""
    text = re.sub(r"\n+PROVIDER CITATION LINKS\b.*\Z", "", answer, flags=re.S)
    decoder, found = json.JSONDecoder(), None
    for start in (m.start() for m in re.finditer(r"\{", text)):
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "seo_title" in value:
            found = value
    if found is None:
        raise ValueError("ChatGPT did not return the SEO JSON. Retry the SEO step.")
    seo = {k: found.get(k) for k in SEO_FIELDS if found.get(k) not in (None, "", [])}
    missing = [k for k in ("seo_title", "meta_description", "focus_keyword", "slug", "thumbnail_headlines",
                           "thumbnail_design") if k not in seo]
    if missing:
        raise ValueError("ChatGPT SEO answer is missing: " + ", ".join(missing))
    seo["slug"] = re.sub(r"[^a-z0-9]+", "-", str(seo["slug"]).lower()).strip("-")[:70]
    seo["tags"] = [str(t).strip() for t in (seo.get("tags") or []) if str(t).strip()][:6]
    from lib.thumbnail_prompts import design_complete, normalise_design, render_thumbnail_prompt
    from lib.thumbnails import validate_headlines
    headlines = [str(t).strip() for t in seo["thumbnail_headlines"]] if isinstance(seo["thumbnail_headlines"], list) else []
    seo["thumbnail_headlines"] = validate_headlines([t for t in headlines if t], language)
    seo["thumbnail_design"] = normalise_design(seo["thumbnail_design"], language)
    if not design_complete(seo["thumbnail_design"]):
        raise ValueError("ChatGPT's thumbnail design is incomplete (left/right scenes or center elements missing). "
                         "Retry the SEO step.")
    # The owner's prompt format; ChatGPT renders the complete poster from it, headline text included.
    seo["thumbnail_prompt"] = render_thumbnail_prompt(language, seo["thumbnail_design"], seo["thumbnail_headlines"])
    return seo
