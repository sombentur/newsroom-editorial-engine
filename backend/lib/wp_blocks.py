"""The article body as WordPress blocks (owner request, 28 Sep 2026: the final post must read premium).

Plain HTML reached WordPress as a "classic" body that the theme left unstyled (bare tables). As core blocks, the
site's block styles apply: striped, mobile-scrollable tables with right-aligned figures and their source line as the
caption, a larger lead paragraph, and a collapsible list of unique, readable source links.
"""
import html
import json
import re
from urllib.parse import urlsplit

from lxml import html as lhtml

SOURCES_TITLE = {"kn": "ಮೂಲಗಳು", "en": "Sources"}
_NUMBER = re.compile(r"[+\-−–]?\s*[$₹€£]?\s*\d[\d.,]*\s*(?:%|pp|x|[kKmMbB]n?|million|billion|trillion|ಲಕ್ಷ|ಕೋಟಿ)?")
_CAPTION = re.compile(r"^\s*(?:data\s+)?sources?\s*[:：]|^\s*ಮೂಲ(?:ಗಳು)?\s*[:：]", re.I)
_SOURCES_HEADING = re.compile(r"^\s*(?:works cited|sources|references|citations|ಮೂಲಗಳು|ಆಧಾರಗಳು)\s*:?\s*$", re.I)
_URL = re.compile(r"^https?://\S+$")


def _block(name: str, inner: str, attrs: dict | None = None) -> str:
    comment = " " + json.dumps(attrs, ensure_ascii=False, separators=(",", ":")) if attrs else ""
    return f"<!-- wp:{name}{comment} -->\n{inner}\n<!-- /wp:{name} -->"


def _inner(el) -> str:
    return (html.escape(el.text or "", quote=False)
            + "".join(lhtml.tostring(child, encoding="unicode") for child in el)).strip()


def _text(el) -> str:
    return " ".join(el.text_content().split())


def _cells(row) -> list:
    return [c for c in row if c.tag in ("td", "th")]


def _table(el, caption: str) -> str:
    rows = el.findall(".//tr")
    head = el.find("thead")
    head_rows = head.findall("tr") if head is not None else rows[:1]
    body_rows = [r for r in rows if r not in head_rows]
    width = max((len(_cells(r)) for r in rows), default=0)

    def figures(i: int) -> bool:  # a column of numbers reads best right-aligned
        values = [_text(_cells(r)[i]) for r in body_rows if i < len(_cells(r)) and _text(_cells(r)[i])]
        return bool(values) and all(_NUMBER.fullmatch(v) for v in values)

    numeric = [figures(i) for i in range(width)]
    right = ' class="has-text-align-right" data-align="right"'

    def row(r, tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}{right if numeric[i] else ''}>{_inner(c)}</{tag}>"
                                for i, c in enumerate(_cells(r))) + "</tr>"

    thead = "<thead>" + "".join(row(r, "th") for r in head_rows) + "</thead>" if head_rows else ""
    tbody = "<tbody>" + "".join(row(r, "td") for r in body_rows) + "</tbody>"
    figcaption = f'<figcaption class="wp-element-caption">{caption}</figcaption>' if caption else ""
    return _block("table", f'<figure class="wp-block-table is-style-stripes"><table>{thead}{tbody}</table>{figcaption}</figure>',
                  {"hasFixedLayout": False, "className": "is-style-stripes"})


def _items(el) -> list[str]:
    items = []
    for li in el.findall("li"):
        inner = _inner(li)
        only = re.fullmatch(r"<p>(.*?)</p>", inner, re.S)  # Gemini wraps list text in a paragraph
        items.append(only.group(1).strip() if only and "<p" not in only.group(1) else inner)
    return items


def _list(el) -> str:
    tag = "ol" if el.tag == "ol" else "ul"
    items = "\n".join(_block("list-item", f"<li>{item}</li>") for item in _items(el))
    return _block("list", f'<{tag} class="wp-block-list">\n{items}\n</{tag}>', {"ordered": True} if tag == "ol" else None)


def _source_urls(el) -> list[str] | None:
    """The URLs of a list that holds only links (the report's source list), else None."""
    urls = []
    for li in el.findall("li"):
        text, anchors = _text(li), li.findall(".//a")
        url = anchors[0].get("href", "") if len(anchors) == 1 and _text(anchors[0]) == text else text
        if not _URL.match(url):
            return None
        urls.append(url)
    return urls or None


def _label(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    segments = [s for s in parts.path.split("/") if s]
    words = re.sub(r"[-_+]+", " ", re.sub(r"\.(?:html?|php|aspx?|pdf)$", "", segments[-1], flags=re.I)).strip() if segments else ""
    if not words or re.fullmatch(r"[\d\s]+", words):
        return host
    return f"{host} — {words[:1].upper()}{words[1:80]}"


def _sources(urls: list[str], language: str) -> str:
    unique: dict[str, str] = {}
    for url in urls:
        unique.setdefault(url.rstrip("/").lower(), url)
    items = "\n".join(_block("list-item", f'<li><a href="{html.escape(url, quote=True)}" target="_blank" '
                                          f'rel="noreferrer noopener">{html.escape(_label(url))}</a></li>')
                      for url in unique.values())
    listing = _block("list", f'<ol class="wp-block-list has-small-font-size">\n{items}\n</ol>',
                     {"ordered": True, "fontSize": "small"})
    title = f"{SOURCES_TITLE.get(language, SOURCES_TITLE['en'])} ({len(unique)})"
    return "\n\n".join([_block("separator", '<hr class="wp-block-separator has-alpha-channel-opacity"/>'),
                        _block("details", f'<details class="wp-block-details"><summary>{html.escape(title)}</summary>'
                                          f"{listing}</details>")])


def to_blocks(content_html: str, language: str = "en") -> str:
    """The article's sanitized HTML (p, h2-h4, ul/ol, table, blockquote) as WordPress block markup."""
    if not (content_html or "").strip():
        return ""
    nodes = lhtml.fragments_fromstring(content_html)
    blocks: list[str] = []
    lead_done, last_text, i = False, "", 0
    while i < len(nodes):
        el, i = nodes[i], i + 1
        if isinstance(el, str):  # stray text between blocks
            if el.strip():
                blocks.append(_block("paragraph", f"<p>{html.escape(el.strip(), quote=False)}</p>"))
            continue
        tail, el.tail = (el.tail or "").strip(), None
        text = _text(el)
        if el.tag == "p":
            if _inner(el):
                lead = not lead_done
                lead_done = True
                blocks.append(_block("paragraph", f'<p class="has-medium-font-size">{_inner(el)}</p>', {"fontSize": "medium"})
                              if lead else _block("paragraph", f"<p>{_inner(el)}</p>"))
        elif el.tag in ("h2", "h3", "h4"):
            level = int(el.tag[1])
            blocks.append(_block("heading", f'<{el.tag} class="wp-block-heading">{_inner(el)}</{el.tag}>',
                                 {"level": level} if level != 2 else None))
        elif el.tag in ("ul", "ol"):
            if urls := _source_urls(el):
                if blocks and _SOURCES_HEADING.match(last_text):
                    blocks.pop()  # the source list brings its own title
                blocks.append(_sources(urls, language))
            else:
                blocks.append(_list(el))
        elif el.tag == "table":
            caption = ""
            follow = nodes[i] if i < len(nodes) else None
            if follow is not None and not isinstance(follow, str) and follow.tag == "p" and _CAPTION.match(_text(follow)):
                caption, i = _inner(follow), i + 1  # its "Data source: ..." line becomes the caption
            blocks.append(_table(el, caption))
        elif el.tag == "blockquote":
            paragraphs = [c for c in el if c.tag == "p"] or [el]
            inner = "".join(_block("paragraph", f"<p>{_inner(p)}</p>") for p in paragraphs)
            blocks.append(_block("quote", f'<blockquote class="wp-block-quote">{inner}</blockquote>'))
        else:
            blocks.append(_block("html", lhtml.tostring(el, encoding="unicode")))
        last_text = text
        if tail:
            blocks.append(_block("paragraph", f"<p>{html.escape(tail, quote=False)}</p>"))
    return "\n\n".join(blocks)
