"""The sites' header-menu categories (sample configuration).

Every post must sit under one of its site's menu categories: the Kannada site exactly one, the English site one (or two when the article
clearly spans two, e.g. US immigration enforcement → Immigration + United States). ChatGPT picks them in the SEO step
("menu_categories"); `choose` validates that answer and, when it is missing or invalid, falls back to the rules
below (keywords, then the site's default). The topic category ChatGPT names ("category") is kept as a secondary
category; a new one is created under the main menu category, never at the top level.

The IDs, names and descriptions are a SAMPLE. Replace them with the categories of your own WordPress sites
(Posts → Categories; the ID is the `tag_ID` number in each category's edit link) before publishing.
"""
import html
import re

MENUS: dict[str, dict] = {
    "kannadiga": {
        "max": 1,
        "items": [
            {"id": 182, "name": "ಕರ್ನಾಟಕ", "aliases": ("Karnataka",), "about": "Karnataka govt/politics, Bengaluru, Hubballi-Dharwad, Mysuru, any "
             "district story, Kannada issues, state schemes, state crime/courts, state education/agriculture/water"},
            {"id": 18, "name": "ಭಾರತ", "aliases": ("India", "Bharat"), "about": "Central govt, national rules/schemes (LPG, Aadhaar, tax, railways), "
             "other Indian states, Supreme Court, national politics"},
            {"id": 14, "name": "ಜಾಗತಿಕ", "aliases": ("Global", "World", "International"), "about": "International affairs outside India and the US (wars, UK, Gulf, China, etc.)"},
            {"id": 13, "name": "ಅಮೆರಿಕ", "aliases": ("America", "United States", "US", "USA", "ಅಮೆರಿಕಾ"), "about": "US politics/economy/immigration, H-1B, NRI Kannadigas in the US"},
            {"id": 20, "name": "ತಂತ್ರಜ್ಞಾನ", "aliases": ("Technology", "Tech"), "about": "AI, software, cybersecurity, gadgets, IT jobs/layoffs, apps"},
            {"id": 645, "name": "ಹೂಡಿಕೆ", "aliases": ("Investment", "Finance", "Money"), "about": "Stock market, mutual funds, insurance, real estate, UPI/banking fees, "
             "personal finance, economy"},
            {"id": 33, "name": "ಸಿನಿಮಾ", "aliases": ("Cinema", "Movies", "Film", "Entertainment"), "about": "Kannada/Indian cinema, actors, box office, entertainment"},
        ],
        "rules": "A Karnataka-located story is ಕರ್ನಾಟಕ even if the topic is education, agriculture or crime. A national "
                 "rule or scheme is ಭಾರತ. Money, markets and fees are ಹೂಡಿಕೆ.",
        "default": 18,
    },
    "human": {
        "max": 2,
        "items": [
            {"id": 97, "name": "United States", "aliases": ("US", "USA", "U.S.", "America"), "about": "US politics, federal/state policy, American institutions, "
             "US-specific social issues"},
            {"id": 186, "name": "World", "about": "international affairs, geopolitics, wars/conflicts, other countries, global economy"},
            {"id": 1336, "name": "Economy", "about": "cost of living, prices, debt, housing, healthcare costs, markets, wealth, "
             "household finances, private equity"},
            {"id": 1331, "name": "Work & Labor", "aliases": ("Work and Labor", "Work & Labour", "Labor", "Work"), "about": "jobs, layoffs, wages, hiring, unions, gig work, workplace practices, "
             "burnout, AI's effect on jobs"},
            {"id": 1355, "name": "Immigration", "about": "immigration policy and enforcement, visas/H-1B, immigrant communities"},
            {"id": 35, "name": "Society", "about": "culture, family life, technology's social impact, loneliness, "
             "generational issues, entertainment"},
        ],
        "rules": "Add a second name only when the article clearly spans two (e.g. US immigration enforcement → "
                 "Immigration, United States). If it genuinely fits none, use Society.",
        "default": 35,
    },
}

# Fallback only (the AI's own choice comes first): words that point to each menu category, most specific first.
KEYWORDS: dict[int, tuple[str, ...]] = {
    # Kannada site
    33: ("ಸಿನಿಮಾ", "ಚಿತ್ರರಂಗ", "ಬಾಕ್ಸ್ ಆಫೀಸ್", "cinema", "film", "movie", "actor", "actress", "box office", "sandalwood"),
    20: ("ತಂತ್ರಜ್ಞಾನ", "ಎಐ", "ಕೃತಕ ಬುದ್ಧಿಮತ್ತೆ", "ಸಾಫ್ಟ್‌ವೇರ್", "ಸೈಬರ್", "ಆ್ಯಪ್", "ಐಟಿ", "ಲೇಆಫ್", "artificial intelligence",
         "software", "cybersecurity", "cyber", "gadget", "smartphone", "app", "it jobs", "layoff", "tech", "technology"),
    645: ("ಹೂಡಿಕೆ", "ಷೇರ","ಮ್ಯೂಚುವಲ್", "ವಿಮೆ", "ರಿಯಲ್ ಎಸ್ಟೇಟ್", "ಯುಪಿಐ", "ಬ್ಯಾಂಕ್", "ಇಎಂಐ", "ಚಿನ್ನ", "ಸೆನ್ಸೆಕ್ಸ್", "ನಿಫ್ಟಿ",
          "ಆರ್ಥಿಕ", "stock", "share market", "mutual fund", "insurance", "real estate", "upi", "bank", "loan", "emi",
          "gold", "sensex", "nifty", "investment", "personal finance"),
    13: ("ಅಮೆರಿಕ", "ಅಮೆರಿಕಾ", "ಟ್ರಂಪ್", "ಎಚ್-1ಬಿ", "ಎಚ್1ಬಿ", "h-1b", "h1b", "america", "united states", "trump", "nri"),
    14: ("ಜಾಗತಿಕ", "ಯುದ್ಧ", "ಚೀನಾ", "ಗಲ್ಫ್", "ಬ್ರಿಟನ್", "ರಷ್ಯಾ", "ಉಕ್ರೇನ್", "ಇಸ್ರೇಲ್", "ಇರಾನ್", "ಪಾಕಿಸ್ತಾನ", "war", "china",
         "gulf", "britain", "russia", "ukraine", "israel", "iran", "pakistan", "global"),
    # Kannada stems without the final vowel sign, so inflected forms match (ಬೆಂಗಳೂರಿನಲ್ಲಿ, ಮೈಸೂರಿನ).
    182: ("ಕರ್ನಾಟಕ", "ಬೆಂಗಳೂರ", "ಮೈಸೂರ", "ಹುಬ್ಬಳ್ಳಿ", "ಧಾರವಾಡ", "ಮಂಗಳೂರ", "ಬೆಳಗಾವಿ", "ಕಲಬುರಗಿ", "ಜಿಲ್ಲೆ", "ಸಿದ್ದರಾಮಯ್ಯ",
          "ಕೆಪಿಎಸ್‌ಸಿ", "karnataka", "bengaluru", "bangalore", "mysuru", "hubballi", "dharwad", "mangaluru", "belagavi",
          "kalaburagi", "kpsc", "siddaramaiah"),
    18: ("ಭಾರತ", "ಕೇಂದ್ರ ಸರ್ಕಾರ", "ಸುಪ್ರೀಂ", "ಎಲ್‌ಪಿಜಿ", "ಆಧಾರ್", "ರೈಲ್ವೆ", "ಜಿಎಸ್‌ಟಿ", "ತೆರಿಗೆ", "ಮೋದಿ", "india", "centre",
         "central government", "supreme court", "lpg", "aadhaar", "railway", "gst", "income tax", "modi"),
    # English site
    1355: ("immigration", "immigrant", "visa", "h-1b", "h1b", "deportation", "deported", "asylum", "border", "migrant",
           "green card", "citizenship"),
    1331: ("job", "layoff", "wage", "hiring", "union", "worker", "employee", "workplace", "gig", "burnout", "severance",
           "labor", "labour", "career", "salary", "fired", "firing", "payroll", "overtime"),
    1336: ("price", "cost of living", "debt", "housing", "rent", "mortgage", "healthcare cost", "insurance", "market",
           "stock", "401(k)", "retirement", "wealth", "inflation", "finance", "loan", "credit", "private equity", "economy",
           "healthcare", "health insurance", "insurer", "medical bill"),
    186: ("world", "global", "war", "china", "russia", "ukraine", "europe", "gaza", "israel", "iran", "geopolitics",
          "geopolitical"),
    97: ("congress", "federal", "supreme court", "white house", "senate", "president", "trump", "u.s.", "american",
         "united states", "state law", "governor"),
}


def _norm(value) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip().casefold()


def menu_ids(site_key: str) -> set[int]:
    return {item["id"] for item in (MENUS.get(site_key) or {}).get("items", [])}


def item(site_key: str, term_id: int) -> dict | None:
    return next((i for i in (MENUS.get(site_key) or {}).get("items", []) if i["id"] == term_id), None)


def seo_key(site_key: str) -> str:
    """The SEO prompt's "menu_categories" key (the list itself follows in `seo_list`)."""
    config = MENUS.get(site_key)
    if not config:
        return ""
    count = "exactly 1 name" if config["max"] == 1 else "1 name, or 2 when the article clearly spans two, main one first"
    return f'"menu_categories" (array with {count}, copied exactly from MENU CATEGORIES below),\n'


def seo_list(site_key: str) -> str:
    """The site's menu categories with the owner's descriptions, for the SEO prompt."""
    config = MENUS.get(site_key)
    if not config:
        return ""
    lines = "\n".join(f"- {i['name']}: {i['about']}" for i in config["items"])
    return f"MENU CATEGORIES (the site's header menu). {config['rules']}\n{lines}\n"


def _from_answer(site_key: str, answer) -> list[int]:
    config = MENUS[site_key]
    names = {_norm(name): i["id"] for i in config["items"] for name in (i["name"], *i.get("aliases", ()))}
    chosen: list[int] = []
    for value in (answer if isinstance(answer, list) else [answer] if answer else []):
        term = names.get(_norm(value))
        if term and term not in chosen:
            chosen.append(term)
    return chosen[: config["max"]]


def _hits(word: str, hay: str) -> int:
    if word.isascii():  # whole words (a plural is fine): "war" must not match "software" or "award"
        return len(re.findall(rf"(?<![a-z0-9]){re.escape(word.casefold())}(?:s|es)?(?![a-z0-9])", hay))
    return hay.count(word)  # Kannada words carry suffixes (ಕರ್ನಾಟಕದ, ಬೆಂಗಳೂರಿನಲ್ಲಿ)


def _by_keywords(site_key: str, text: str) -> list[int]:
    ids = [i["id"] for i in MENUS[site_key]["items"]]
    hay = _norm(text)
    scores = {term: sum(_hits(word, hay) for word in KEYWORDS.get(term, ())) for term in ids}
    best = max(scores.values(), default=0)
    if not best:
        return []
    order = [term for term in KEYWORDS if term in scores]  # KEYWORDS order breaks ties (most specific first)
    return [next(term for term in order if scores[term] == best)]


def choose(site_key: str, answer=None, article: dict | None = None, topic: dict | None = None) -> tuple[list[dict], str]:
    """(menu categories as [{"id", "name"}], how they were chosen). Empty for a site without a menu."""
    config = MENUS.get(site_key)
    if not config:
        return [], "no menu configured"
    how = "ChatGPT's choice"
    ids = _from_answer(site_key, answer)
    if not ids:
        article, topic = article or {}, topic or {}
        text = " ".join(str(v) for v in (
            article.get("category"), article.get("headline"), article.get("seo_title"), article.get("excerpt"),
            " ".join(article.get("tags") or []), topic.get("category"), topic.get("topic"), topic.get("geography")) if v)
        ids, how = _by_keywords(site_key, text), "keyword rules"
        if not ids:
            ids, how = [config["default"]], "site default"
    return [{"id": term, "name": item(site_key, term)["name"]} for term in ids], how

