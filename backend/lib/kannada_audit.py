"""Two Kannada editorial checks: script/readability guard and independent model review."""

import html
import json
import re
from lib.ai import provider_json

KANNADA = re.compile(r"[\u0c80-\u0cff]")
TAGS = re.compile(r"<[^>]+>")


def script_share(value: str) -> float:
    plain = html.unescape(TAGS.sub(" ", value or ""))
    # URLs and citations are source metadata, not article prose.
    plain = re.sub(r"https?://\S+|\[cite:\s*\d+\]", " ", plain)
    letters = [char for char in plain if char.isalpha()]
    return sum(bool(KANNADA.match(char)) for char in letters) / len(letters) if letters else 0.0


# Deep Research reports end with an English source list; it is not article prose.
SOURCES_HEADING = re.compile(r"<h[2-4]>\s*(?:works cited|sources|references|citations|bibliography|ಮೂಲಗಳು|ಆಧಾರಗಳು|ಉಲ್ಲೇಖ\S*|ಆಕರ\S*)", re.I)
LINKED_ITEM = re.compile(r"<li>(?:(?!</li>).)*?https?://(?:(?!</li>).)*?</li>", re.S | re.I)


def prose_html(body: str) -> str:
    """The article prose only: everything before a sources heading, without link-only list items."""
    body = body or ""
    heading = SOURCES_HEADING.search(body)
    return LINKED_ITEM.sub(" ", body[:heading.start()] if heading else body)


def language_checks(article: dict) -> list[tuple[str, bool, str]]:
    body = article.get("content_html") or ""
    headline = article.get("headline") or ""
    body_share = script_share(prose_html(body))
    headline_share = script_share(headline)
    visible = html.unescape(TAGS.sub(" ", body))
    return [
        ("kannada_body_script", body_share >= 0.65, f"{body_share:.0%} of body letters use Kannada script"),
        ("kannada_headline_script", headline_share >= 0.60, f"{headline_share:.0%} of headline letters use Kannada script"),
        ("kannada_text_integrity", "\ufffd" not in visible + headline and "???" not in visible,
         "no replacement characters or unreadable placeholders"),
    ]


async def editorial_audit(article: dict, dossier: dict) -> dict:
    system = (
        "You are an independent Kannada news copy editor and evidence auditor. "
        "Check natural, clear Karnataka Kannada spelling and grammar; flag awkward literal translation, "
        "untranslated English sentences, broken characters, and misleading headlines. "
        "Compare every important factual assertion with the supplied research dossier. "
        "Do not assume a claim is verified merely because it appears in the draft. "
        "Return ONLY JSON with booleans language_ok, readability_ok, grounding_ok and a short issues array. "
        "List only issues that need correction; use an empty issues array when the copy is ready. "
        "Set any uncertain check to false. Do not rewrite the article in this audit."
    )
    prompt = ("RESEARCH DOSSIER:\n" + json.dumps(dossier, ensure_ascii=False) +
              "\n\nKANNADA ARTICLE:\n" + json.dumps(article, ensure_ascii=False))
    verdict, model = await provider_json("kannada_audit", system, prompt)
    issues = [str(item)[:240] for item in verdict.get("issues", []) if isinstance(item, str)][:8]
    passed = all(verdict.get(key) is True for key in ("language_ok", "readability_ok", "grounding_ok")) and not issues
    if not passed and not issues:
        issues = ["Kannada language, readability, or source consistency needs correction."]
    return {"passed": passed, "checks": {key: verdict.get(key) is True for key in
                                   ("language_ok", "readability_ok", "grounding_ok")},
            "issues": issues, "model": model}


async def revise_article(article: dict, dossier: dict, issues: list[str]) -> tuple[dict, str]:
    system = (
        "You are a native Kannada news editor. Correct the draft's listed language or grounding issues "
        "using only the dossier. Preserve valid facts, source links, article fields, and clean HTML. "
        "Remove unsupported claims; never invent facts. Return only the complete corrected article JSON."
    )
    prompt = ("ISSUES:\n" + json.dumps(issues, ensure_ascii=False) +
              "\n\nRESEARCH DOSSIER:\n" + json.dumps(dossier, ensure_ascii=False) +
              "\n\nARTICLE TO CORRECT:\n" + json.dumps(article, ensure_ascii=False))
    return await provider_json("writing", system, prompt)
