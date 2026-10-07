"""What each site covers, turned into topic discovery. SAMPLE VALUES — edit for your own sites.

Discovery reads each site's news feeds and focused news searches (last two days), drops the kinds of story the
site never covers, and an AI editor scores the rest 0-100 against the site's brief (lib/discovery). A topic scoring
AUTO_QUEUE_SCORE or more is a strong fit: it moves to the Editorial Workbench by itself, up to the site's daily quota
(lib/scheduler._auto_queue); the rest stay in Topic Intelligence.

Keys: `kannadiga` is the Kannada-language site, `human` the English-language site.
"""
import re
from urllib.parse import quote_plus

AUTO_QUEUE_SCORE = 70

_GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
_EDITION = {"kannadiga": ("en-IN", "IN", "IN:en"), "human": ("en-US", "US", "US:en")}

# RSS feeds read for each site. Add your preferred publishers; a feed that fails is skipped.
FEEDS = {
    "kannadiga": ["https://tv9kannada.com/feed", "https://www.prajavani.net/stories.rss"],
    "human": [],
}

# Google News searches (last two days) for each site. Replace with the beats you cover.
QUERIES = {
    "kannadiga": [
        "Karnataka government decision",
        "Karnataka farmers prices",
        "Karnataka exam recruitment",
        "Karnataka hospital school fees",
        "Bengaluru civic issue",
        "(Hubballi OR Mysuru OR Mangaluru OR Belagavi OR Kalaburagi)",
    ],
    "human": [
        "(layoffs OR job cuts) profits",
        "(housing affordability OR rent increase) families",
        "(grocery prices OR cost of living) families",
        "(health insurance OR medical debt)",
        "AI (jobs OR workers)",
        "(gig workers OR delivery drivers) pay",
    ],
}

_ZERO_WIDTH = re.compile("[​‌‍]")
# Kinds of story a site never covers; the AI editor judges the finer points of each brief.
EXCLUDE = {
    "kannadiga": re.compile(r"bigg\s*boss|ಬಿಗ್\s*ಬಾಸ್|^video\s*:", re.I),
    "human": re.compile(r"^how to\b|^\d+\s+(?:ways|tips|tricks|things|best)\b"
                        r"|\b(?:product|gadget|phone|laptop|headphones?)\s+review\b|\bunboxing\b|\bhands-on\b", re.I),
}


def source_urls(site_key: str) -> list[str]:
    """Every source discovery reads for the site: its feeds, then its searches limited to the last two days."""
    hl, gl, ceid = _EDITION.get(site_key, _EDITION["human"])
    return FEEDS.get(site_key, []) + [_GOOGLE_NEWS.format(q=quote_plus(f"{q} when:2d"), hl=hl, gl=gl, ceid=ceid)
                                      for q in QUERIES.get(site_key, [])]


def excluded(site_key: str, title: str) -> bool:
    """A kind of story the site never covers."""
    pattern = EXCLUDE.get(site_key)
    return bool(pattern and pattern.search(_ZERO_WIDTH.sub("", title)))


CATEGORIES = {
    "kannadiga": ["Agriculture", "Jobs & Exams", "Education", "Health", "Civic Issues", "Prices & Money",
                  "Governance", "Environment", "Karnataka"],
    "human": ["Economy", "Housing", "Health Care", "Consumer", "Tech & Society", "Labor", "Inequality"],
}

# The editorial brief the AI editor scores every candidate against. Write your own: who the readers are, what a
# strong story looks like, and what must score low.
BRIEFS = {
    "kannadiga": """SAMPLE BRIEF for the Kannada-language site: Kannada news for readers across Karnataka.
Strong stories (score high):
- Directly affect ordinary people's money, work, health, education or safety, with a concrete paper trail
  (official orders, court records, audit reports, documented price changes).
- Come from districts and towns beyond the capital as well as from Bengaluru.
- Expose a systemic failure or an unfair power dynamic that readers can recognise in daily life.
Weak stories (score below 40): party-political mud-slinging without policy impact, celebrity gossip, social-media
outrage without substance, raw press releases without ground-level evidence, recurring columns such as horoscopes.""",
    "human": """SAMPLE BRIEF for the English-language site: analysis of the human consequences of policy, the economy
and technology, written for working and middle-class readers.
Litmus test: does the story expose a hidden corporate reality, an economic injustice or a systemic failure that is
actively squeezing ordinary households? General information, generic advice or a sanitised press release fails it.
Pillars: work and the workplace (layoffs, pay, surveillance, benefits); household economics (housing, debt, prices,
health costs); technology and society (automation, algorithmic pricing, the gig economy, attention and loneliness).
Angle: never a plain summary; name who gains and who pays.
Score below 40: how-to articles and listicles, motivational fluff, neutral product reviews, and stories outside the
site's audience.""",
}
