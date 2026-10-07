"""Editorial constants: prompt templates, scoring model, high-risk detection, sample trend pool."""

# ── Scoring model (Stage C) — configurable weights that sum to 100 ──
SCORE_WEIGHTS = {
    "relevance": 25,  # audience & site relevance
    "impact": 20,     # human / public impact
    "trend": 15,      # trend strength / momentum
    "freshness": 15,  # freshness & news value
    "source": 15,     # source quality & verifiability
    "seo": 10,        # useful SEO / search opportunity
}

# Subjects that force human review even under automatic publishing (§3).
HIGH_RISK_KEYWORDS = [
    "murder", "rape", "sexual", "suicide", "terror", "riot", "communal", "war",
    "election", "vote", "bomb", "attack", "death", "killed", "arrest", "accused",
    "allegation", "fraud", "scam", "corruption", "defamation", "leak", "child",
    "ಕೊಲೆ", "ಅತ್ಯಾಚಾರ", "ಆತ್ಮಹತ್ಯೆ", "ಗಲಭೆ", "ಚುನಾವಣೆ", "ದಾಳಿ", "ಬಂಧನ", "ಆರೋಪ",
]

RESEARCH_PROMPT = """You are a meticulous senior journalist, researcher, fact-checker, and subject-matter analyst preparing a source-grounded research dossier for {site_name}.

Topic: {topic}
Proposed angle: {angle}
Target audience: {audience}
Geographic focus: {geography}
Research cutoff: {current_datetime_with_timezone}
Target article language: {language}

Investigate why this topic is important now and produce a balanced, evidence-based dossier. Prioritize primary and authoritative sources. Verify the central event and its date; do not assume a trending claim is true. Separate established facts from allegations, predictions, opinions, and estimates. Do not fabricate quotations or sources. Flag any defamation, privacy, legal, medical, financial, political, communal, or safety risk requiring human review.

Return ONLY valid JSON (no markdown fences) with this exact shape:
{{
  "executive_summary": "string",
  "verified_facts": ["string"],
  "newest_development": "string",
  "timeline": [{{"date": "string", "event": "string"}}],
  "stakeholders": ["string"],
  "human_impact": "string",
  "key_statistics": [{{"metric": "string", "value": "string", "period": "string", "source": "string"}}],
  "competing_claims": ["string"],
  "unresolved_questions": ["string"],
  "risk_review": {{"level": "low|medium|high", "flags": ["string"], "explanation": "string"}},
  "recommended_angle": "string",
  "outline": ["string"],
  "seo": {{"search_intent": "string", "focus_keyword": "string", "related_terms": ["string"]}},
  "claim_evidence": [{{"claim": "string", "source_url": "string", "verified": true, "note": "string"}}],
  "sources": [{{"title": "string", "publisher": "string", "author": "string", "published": "string", "url": "string", "type": "primary|secondary|official", "reliability": "string"}}],
  "publication_ready": true,
  "not_ready_reasons": ["string"]
}}"""

ARTICLE_PROMPT = """You are the senior editor and original writer for {site_name}. Write a fresh, publication-ready news-analysis article using ONLY the validated research dossier below.

Website profile: {site_profile}
Audience: {audience}
Language: {language}
Tone: {tone}
Target length: {word_count_range} words
Focus keyword: {focus_keyword}
Validated research dossier: {research_dossier}

Rules: Write for humans first. Original analysis only — never copy a source's phrasing. Lead with what happened, why it matters, and whom it affects in two or three short introductory paragraphs. Attribute allegations precisely and distinguish verified facts from claims. Never invent quotations, statistics, or personal anecdotes. {language_rule}

Structure the article for comfortable phone reading:
- Do not add an H1 in the body; WordPress supplies it.
- Use 3 to 6 descriptive H2 sections in a logical narrative order. Use H3 only when a section truly needs a subdivision.
- Keep most paragraphs to 2 to 4 sentences. Avoid walls of text and repetitive summaries.
- Use bullet or numbered lists only for genuinely parallel information.
- Use a compact table only when readers need to compare dates or numbers; keep it to 4 columns or fewer and introduce it in prose.
- Attribute important facts in the prose and link only URLs present in approved_external_sources.
- Include a concise “What happens next” section when the dossier supports it.
- End cleanly without a generic conclusion or call to action.

content_html must be clean semantic WordPress HTML using p, h2, h3, ul, ol, li, blockquote, table, thead, tbody, tr, th, td, strong, em, and safe a tags. Return HTML, never Markdown. Do not include scripts, inline styles, event handlers, forms, embeds, or unsafe HTML.

Return ONLY valid JSON (no markdown fences) with this exact shape:
{{
  "headline": "string",
  "short_headline": "string",
  "dek": "string",
  "excerpt": "string",
  "content_html": "string",
  "key_takeaways": ["string"],
  "focus_keyword": "string",
  "secondary_keywords": ["string"],
  "seo_title": "string",
  "meta_description": "string",
  "slug": "string",
  "category": "string",
  "tags": ["string"],
  "og_title": "string",
  "og_description": "string",
  "suggested_internal_links": ["string"],
  "approved_external_sources": ["string"],
  "featured_image_brief": "string",
  "featured_image_alt_text": "string",
  "featured_image_caption": "string",
  "schema_type": "NewsArticle",
  "article_section": "string",
  "review_flags": ["string"]
}}"""

KANNADA_RULE = ("Write the COMPLETE article in clear, idiomatic contemporary Kannada (ಕನ್ನಡ) for readers across Karnataka. "
                "Use the cadence of a careful Kannada newspaper editor: natural word order, precise verbs, short readable sentences, "
                "correct spelling and inflection, and familiar Kannada words such as ಅಂಕಿಅಂಶ rather than unnecessary English loanwords. "
                "Avoid literal translations from English, awkward sentence fragments, and untranslated English sentences. "
                "Keep a proper noun or technical acronym in English only when translation reduces clarity; explain it in Kannada on first mention. "
                "Use restrained headlines that state only dossier-supported facts. Connect national/global developments to Karnataka only when supported.")
# Appended to every research prompt (API and Chrome Deep Research) after Prompt Studio's template,
# so the report language cannot be left for the provider to guess.
RESEARCH_LANGUAGE_RULES = {
    "kn": """

LANGUAGE INSTRUCTIONS FOR THIS RESEARCH (mandatory):
1. Write the ENTIRE Deep Research report in Kannada (ಕನ್ನಡ script): every heading, summary, fact, timeline entry,
   explanation and every JSON string value. Do not write the report in English or Hindi.
2. When an English word is the term readers actually use or search for (Fake Seeds, Black Market, Urea, Scam),
   write it phonetically in Kannada script (ಫೇಕ್ ಸೀಡ್ಸ್, ಬ್ಲ್ಯಾಕ್ ಮಾರ್ಕೆಟ್, ಯೂರಿಯಾ, ಸ್ಕ್ಯಾಮ್), never in English letters.
   Keep ONLY JSON keys, URLs, and source titles/publisher names in the source list in their original form.
3. Search in BOTH Kannada and English. Use Kannada news outlets (for example Prajavani, Vijay Karnataka, Udayavani,
   Kannada Prabha, TV9 Kannada), national/English outlets, and official Government of Karnataka / Government of India
   sources. Use at least two independent publishers.
4. Translate facts from English sources into natural, contemporary Kannada as a Karnataka newspaper editor would.
   Never paste English sentences. For a quotation, give it in Kannada and state the original language of the source.
5. Spell people, places, districts, departments and schemes in the standard Kannada form used by the Government of
   Karnataka and major Kannada newspapers, with the English form in brackets on first mention, e.g. ಬೆಂಗಳೂರು (Bengaluru).
6. Write amounts with ₹ and Indian units (ಸಾವಿರ, ಲಕ್ಷ, ಕೋಟಿ); write dates as day month year in Kannada.
7. Deliver the completed report, not a research plan.""",
    "en": """

LANGUAGE INSTRUCTIONS FOR THIS RESEARCH (mandatory):
Write the ENTIRE research report and every JSON string value in clear English. Translate any non-English source
material into English and name the original language of quoted material. Deliver the completed report, not a research plan.""",
}

ENGLISH_RULE = "Write in clear English. Center the consequences for ordinary people, workers, families, and communities without inventing anecdotes."

IMAGE_PROMPT = """Create an original, high-quality editorial news thumbnail, 16:9 landscape.
Subject: {brief}
Website: {site_name} ({brand_style})
Style: realistic documentary-style conceptual editorial scene, clear focal point, clean composition, natural lighting, generous negative space, strong mobile readability.
STRICT restrictions: no text, headline, caption, logo, watermark, signature, or garbled letters anywhere in the image; no fabricated documents, charts, seals, flags, currency, or data visualizations that could be mistaken for evidence; no graphic violence, hateful, sexual, or humiliating imagery; do not depict a generated face as a real victim, suspect, or official; use symbolic non-identifiable compositions for sensitive stories."""
