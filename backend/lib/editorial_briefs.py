"""What each site covers: sample editorial guidelines turned into topic discovery. Edit FEEDS, QUERIES,
EXCLUDE, CATEGORIES and BRIEFS to describe your own two sites.

Discovery reads each site's own news feeds and focused news searches (last two days), drops the kinds of story the
site never covers, and an AI editor scores the rest 0-100 against the site's brief (lib/discovery). A topic scoring
AUTO_QUEUE_SCORE or more is a strong fit: it moves to the Editorial Workbench by itself, up to the site's daily quota
(lib/scheduler._auto_queue); the rest stay in Topic Intelligence.
"""
import re
from urllib.parse import quote_plus

AUTO_QUEUE_SCORE = 70

_GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
_EDITION = {"kannadiga": ("en-IN", "IN", "IN:en"), "human": ("en-US", "US", "US:en")}

# Sample Kannada publishers with public RSS feeds (checked 28 Sep 2026).
FEEDS = {
    "kannadiga": ["https://tv9kannada.com/feed", "https://www.prajavani.net/stories.rss", "https://publictv.in/feed",
                  "https://kannada.oneindia.com/rss/feeds/kannada-news-fb.xml"],
    "human": [],
}

# Sample focused searches: Karnataka regions paired with systemic issues (Kannada site) and three topic pillars
# (English site).
QUERIES = {
    "kannadiga": [
        "Karnataka farmers (seeds OR fertilizer OR crop OR prices)",
        "Karnataka (recruitment OR exam) (scam OR irregularities OR leak)",
        "Karnataka (private school OR private hospital) (fees OR charges OR overcharging)",
        "Karnataka (toll OR tariff OR fare OR tax) hike",
        "Karnataka (tax devolution OR central funds OR railway project)",
        "(Kalaburagi OR Belagavi OR Raichur OR Vijayapura OR Ballari OR Bidar OR Koppal OR Yadgir)",
        "(Hubballi OR Dharwad OR Shivamogga OR Mysuru OR Davanagere OR Tumakuru OR Hassan OR Chitradurga)",
        "(Mangaluru OR Udupi OR Karwar OR Dakshina Kannada OR Uttara Kannada)",
        "Karnataka (layout OR land OR real estate) (illegal OR unapproved OR fraud)",
        "Karnataka (SIT OR Lokayukta OR CID OR ED) probe",
        "Karnataka (drinking water OR government hospital OR road OR school) villagers",
        "Karnataka (APMC OR vegetable prices OR onion OR tomato OR milk price)",
    ],
    "human": [
        # A. Corporate & HR reality
        "(layoffs OR job cuts) profits",
        "(return to office OR RTO) mandate employees",
        "(employee monitoring OR workplace surveillance OR bossware)",
        "(CEO pay OR executive compensation) workers",
        "(severance OR performance improvement plan OR quiet firing)",
        "(employee benefits OR 401k OR health plan) cuts",
        "(NLRB OR labor law OR union) workers ruling",
        "AI (replacing OR replaces OR eliminates) (jobs OR managers OR workers)",
        # B. Macro-economics & the middle-class squeeze
        "(housing affordability OR rent increase OR mortgage rates) families",
        "(credit card debt OR buy now pay later OR consumer debt) record",
        "(grocery prices OR food prices OR cost of living) families",
        "(child care OR daycare) costs parents",
        "(medical debt OR health insurance premiums OR GoFundMe medical)",
        "private equity (buyout OR takeover) (prices OR workers OR patients)",
        "(junk fees OR hidden fees OR surprise fees) consumers",
        "(car insurance OR auto loans) (costs OR premiums OR delinquencies)",
        # C. Tech & societal decline
        "(dynamic pricing OR surge pricing OR algorithmic pricing)",
        "(gig workers OR delivery drivers OR rideshare drivers) pay",
        "(loneliness epidemic OR AI companion OR AI girlfriend)",
        "(screen time OR social media addiction OR smartphone addiction)",
        "(subscription economy OR subscription prices OR you own nothing)",
        "(data brokers OR personal data OR privacy) consumers",
    ],
}

_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d]")
# Kinds of story a site never covers; the AI editor judges the finer points of each brief.
EXCLUDE = {
    "kannadiga": re.compile(r"bigg\s*boss|ಬಿಗ್\s*ಬಾಸ್|silk\s*board|ಸಿಲ್ಕ್\s*ಬೋರ್ಡ್|\btechies?\b|ಟೆಕ್ಕಿ|^video\s*:", re.I),
    "human": re.compile(r"\bindia(?:n|'s)?\b|karnataka|bengaluru|bangalore|bollywood|tollywood|kannada|\bdelhi\b|\bmumbai\b"
                        r"|^how to\b|^\d+\s+(?:ways|tips|tricks|things|best)\b"
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
                  "Scams & Probes", "Governance", "Environment", "Karnataka"],
    "human": ["Corporate & HR", "Economy", "Housing", "Health Care", "Consumer", "Tech & Society", "Labor", "Inequality"],
}

BRIEFS = {
    "kannadiga": """The Kannada edition: Kannada news for common citizens across Karnataka.
Core editorial criteria:
- Common citizen first (no tech cliches): skip repetitive Bengaluru IT-bubble angles (Silk Board traffic, techies,
  corporate managers, layoffs) unless the issue strictly concerns tech policy. Target farmers, tier-2 city residents,
  small business owners, exam aspirants and middle-class families across Karnataka.
- Beyond the capital: prioritise stories affecting North Karnataka, the coastal districts and tier-2/tier-3 hubs
  (Hubballi-Dharwad, Kalaburagi, Belagavi, Raichur, Mysuru, Shivamogga).
- Direct pocket and livelihood impact: systemic failures that hit ordinary finances: artificial price rigging
  (fertilizers, vegetables), fee extortion (private schools, hospitals), toll charges on broken roads, unfair tariff hikes.
- Systemic injustice and policy failures: verifiable administrative lapses: government recruitment irregularities,
  exam paper leaks, agricultural mafia operations, state-federal fiscal disputes (tax devolution, railway neglect).
Filters every topic must pass:
- Lived reality: a common person in a district headquarters or taluk experiences this problem directly in daily life.
- Data and paper trail: concrete data points (FIRs, court orders, government notifications, audit reports, documented
  price disparities), not vague social-media gossip.
- Emotional resonance (anger and curiosity): it exposes an unfair power dynamic (corrupt officials vs unemployed
  youth, corporate cartels vs unorganised consumers, middlemen vs farmers).
Cover all kinds of news, as long as they fit these criteria. Excluded (score below 40): partisan mud-slinging and
daily party spats without systemic policy impact; melodramatic gossip, celebrity rumours and generic social-media
outrage without investigative substance; raw government press releases unless paired with ground-level
counter-evidence of implementation gaps; recurring columns such as horoscopes.""",
    "human": """The English edition: it does not report the news; it exposes the mechanics behind the news.
The litmus test: "Does this story expose a hidden corporate reality, an economic injustice, or a systemic failure that
is actively squeezing the working or middle class?" General information, generic advice or a sanitised corporate press
release fails it.
Audience: the United States (and US-led global corporate trends); the American middle class, working professionals
and people surviving the modern corporate machine. Pain points: inflation, job insecurity, unaffordable housing, toxic
HR policies, the death of ownership, the monetisation of human behaviour (loneliness, sleep, attention).
Topic pillars:
A. Corporate & HR reality (insider perspective): mass layoffs, labour-law changes, return-to-office mandates, corporate
   tracking software, CEO compensation, changes to employee benefits. Explain why it happens from an HR insider's view,
   e.g. how Performance Improvement Plans are used to avoid paying severance.
B. Macro-economics & the middle-class squeeze: housing data, credit card debt, the cost of groceries, cars, daycare and
   healthcare, private-equity buyouts, hidden consumer fees, framed by the human toll (e.g. GoFundMe as the default US
   healthcare system; a subscription economy in which the middle class owns nothing).
C. Tech & societal decline: AI replacing middle management, algorithmic (surge) pricing, gig-economy exploitation,
   screen addiction, the death of third spaces, remote-work isolation: how technology monetises human vulnerability.
The site's angle, never a plain summary: "Tech Giant X announces 10,000 layoffs but reports record profits" becomes
"The Record Profit Paradox: Why Wall Street Rewards CEOs for Destroying 10,000 Families"; "Wendy's to test dynamic
pricing menus" becomes "Surge Pricing Your Lunch: How Algorithmic Greed is Starving the Working Class".
Cover all kinds of news, as long as they pass the litmus test. Blacklist (score below 40): basic how-to information
and listicles; regional or Indian content (Karnataka politics, regional cinema, local travel belong to the Kannada
edition); motivational hustle-culture fluff; neutral product reviews (unless they expose data harvesting or consumer
exploitation).""",
}
