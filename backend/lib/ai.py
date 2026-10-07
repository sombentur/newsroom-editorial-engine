# MAINTAINER NOTE (2026-09-27): PROVIDER FAILURES: _retry records the provider/task label without storing SDK exception bodies or secrets. HTTP 429 alone does not prove exhausted credits; _classify separates explicit quota evidence from ambiguous rate/quota limits. No silent provider fallback.
"""Production AI layer — the owner's OWN Google Gemini + OpenAI keys via the official SDKs.

No automatic fallback to any other provider and no mock/placeholder
content: every failure raises AIError so the workflow can stop the article safely, surface the
exact non-sensitive error, and allow a controlled retry after the problem is fixed.

Deep Research uses persistent Gemini Interactions jobs; manual requests are explicitly gated.
"""

import asyncio
import base64
import io
import json
import logging
import re

from lib.secrets import get_model, get_provider, get_secret

logger = logging.getLogger(__name__)

# Keep provider calls below the workflow's 120-second wall-clock limit so there
# is time to decode, typeset and save the thumbnail before the deadline.
IMAGE_PROVIDER_TIMEOUT_SECONDS = 110

RESEARCH_JSON_SCHEMA = {
    "type": "object",
    "required": ["executive_summary", "verified_facts", "claim_evidence", "sources", "publication_ready", "not_ready_reasons"],
    "properties": {
        "executive_summary": {"type": "string"},
        "verified_facts": {"type": "array", "items": {"type": "string"}},
        "newest_development": {"type": "string"},
        "timeline": {"type": "array", "items": {"type": "object", "properties": {"date": {"type": "string"}, "event": {"type": "string"}}}},
        "stakeholders": {"type": "array", "items": {"type": "string"}},
        "human_impact": {"type": "string"},
        "key_statistics": {"type": "array", "items": {"type": "object", "properties": {"metric": {"type": "string"}, "value": {"type": "string"}, "period": {"type": "string"}, "source": {"type": "string"}}}},
        "competing_claims": {"type": "array", "items": {"type": "string"}},
        "unresolved_questions": {"type": "array", "items": {"type": "string"}},
        "risk_review": {"type": "object", "properties": {"level": {"type": "string", "enum": ["low", "medium", "high"]}, "flags": {"type": "array", "items": {"type": "string"}}, "explanation": {"type": "string"}}},
        "recommended_angle": {"type": "string"},
        "outline": {"type": "array", "items": {"type": "string"}},
        "seo": {"type": "object", "properties": {"search_intent": {"type": "string"}, "focus_keyword": {"type": "string"}, "related_terms": {"type": "array", "items": {"type": "string"}}}},
        "claim_evidence": {"type": "array", "items": {"type": "object", "required": ["claim", "source_url", "verified"], "properties": {"claim": {"type": "string"}, "source_url": {"type": "string"}, "verified": {"type": "boolean"}, "note": {"type": "string"}}}},
        "sources": {"type": "array", "items": {"type": "object", "required": ["title", "url"], "properties": {"title": {"type": "string"}, "publisher": {"type": "string"}, "author": {"type": "string"}, "published": {"type": "string"}, "url": {"type": "string"}, "type": {"type": "string", "enum": ["primary", "secondary", "official"]}, "reliability": {"type": "string"}}}},
        "publication_ready": {"type": "boolean"},
        "not_ready_reasons": {"type": "array", "items": {"type": "string"}},
    },
}

ARTICLE_JSON_SCHEMA = {
    "type": "object",
    "required": ["headline", "short_headline", "thumbnail_headlines", "dek", "excerpt", "content_html",
                 "key_takeaways", "focus_keyword", "secondary_keywords", "seo_title", "meta_description",
                 "slug", "category", "tags", "og_title", "og_description", "suggested_internal_links",
                 "approved_external_sources", "featured_image_brief", "featured_image_alt_text",
                 "featured_image_caption", "schema_type", "article_section", "review_flags"],
    "properties": {
        "headline": {"type": "string"}, "short_headline": {"type": "string"},
        "thumbnail_headlines": {"type": "array", "items": {"type": "string"}},
        "dek": {"type": "string"}, "excerpt": {"type": "string"}, "content_html": {"type": "string"},
        "key_takeaways": {"type": "array", "items": {"type": "string"}},
        "focus_keyword": {"type": "string"}, "secondary_keywords": {"type": "array", "items": {"type": "string"}},
        "seo_title": {"type": "string"}, "meta_description": {"type": "string"}, "slug": {"type": "string"},
        "category": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
        "og_title": {"type": "string"}, "og_description": {"type": "string"},
        "suggested_internal_links": {"type": "array", "items": {"type": "string"}},
        "approved_external_sources": {"type": "array", "items": {"type": "string"}},
        "featured_image_brief": {"type": "string"}, "featured_image_alt_text": {"type": "string"},
        "featured_image_caption": {"type": "string"}, "schema_type": {"type": "string"},
        "article_section": {"type": "string"}, "review_flags": {"type": "array", "items": {"type": "string"}},
    },
}

KANNADA_AUDIT_SCHEMA = {
    "type": "object",
    "required": ["language_ok", "readability_ok", "grounding_ok", "issues"],
    "properties": {
        "language_ok": {"type": "boolean"},
        "readability_ok": {"type": "boolean"},
        "grounding_ok": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
}


class AIError(RuntimeError):
    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind  # auth | quota | rate_limit | moderation | invalid | network | error


def _classify(exc: Exception) -> str:
    if getattr(exc, "code", None) == "model_not_found":
        return "model_unavailable"
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 500 <= status <= 599:
        return "network"
    if status == 400:
        return "invalid"
    s = str(exc).lower()
    if any(k in s for k in ("api key", "api_key", "unauthenticated", "permission", "401", "403", "invalid authentication")):
        return "auth"
    if any(k in s for k in ("insufficient_quota", "billing_hard_limit", "credit balance", "quota exhausted")):
        return "quota"
    if any(k in s for k in ("429", "quota", "rate limit", "rate_limit", "resource_exhausted", "insufficient_quota", "billing")):
        return "rate_limit"
    if any(k in s for k in ("safety", "blocked", "moderation", "content_policy", "responsible ai")):
        return "moderation"
    if any(k in s for k in ("timeout", "connection", "network", "temporar", "503", "unavailable", "overloaded", "high demand", "try again")):
        return "network"
    return "error"


def _safe(exc: Exception) -> str:
    # SDK exceptions can include headers, URLs, submitted prompts or credentials.
    # Never return their original text, even when a provider changes key formats.
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    if status == 400:
        safe_code = str(code)[:60] if isinstance(code, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,60}", code) else "invalid_request"
        return f"Provider rejected the request (HTTP 400, {safe_code}). Check the selected model and report size."
    return {"auth": "Provider authentication failed; check server configuration.",
            "model_unavailable": "The selected AI model is unavailable to this API key. Choose an accessible model in Settings → AI Providers.",
            "quota": "Provider API credits or quota exhausted. Check billing and usage limits.",
            "rate_limit": "Provider rate or quota limit reached; the response did not confirm exhausted credits.",
            "network": "Provider request failed due to a network or transient service error."}.get(
                _classify(exc), "Provider request failed; inspect the provider dashboard using the request time.")


def _parse_json(raw: str) -> dict:
    if not raw:
        raise AIError("model returned an empty response", "error")
    text = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", raw.strip()).strip()).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise AIError("model did not return valid JSON", "error")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIError(f"could not parse model JSON: {exc}", "error") from exc


async def _retry(call, label: str, tries: int = 1):
    """Run a blocking SDK call in a thread; retry transient (network/503) errors with backoff."""
    delay = 1.0
    for attempt in range(tries):
        from lib.manual_ai import block_reason
        if reason := await block_reason():
            raise AIError(reason, "safety")
        try:
            return await asyncio.to_thread(call)
        except AIError as exc:
            err, kind = exc, exc.kind
        except Exception as exc:
            kind = _classify(exc)
            err = AIError(_safe(exc), kind)
        if kind == "network" and attempt < tries - 1:
            logger.warning("%s transient (%s) — retry %d/%d in %.0fs", label, kind, attempt + 1, tries - 1, delay)
            await asyncio.sleep(delay)
            delay *= 2
            continue
        err.provider_label = label
        logger.error("%s failed: %s", label, err)
        raise err


# ── Gemini ────────────────────────────────────────────────────────────────
def _gemini_call(model: str, system: str, prompt: str, grounding: bool, json_schema: dict | None = None) -> str:
    from lib.manual_ai import environment_reason
    if reason := environment_reason():
        raise AIError(reason, "safety")
    if not model:
        raise AIError("Configure the Gemini model in the server environment.", "configuration")
    key = get_secret("gemini_api_key")
    if not key:
        raise AIError("Gemini API key is not configured — add it in Settings → AI Providers.", "auth")
    from google import genai
    from google.genai import types

    # Deep/grounded work can be long-running. Structured article formatting should
    # fail clearly instead of leaving the editor waiting for ten minutes.
    timeout_ms = 600000 if grounding else 180000
    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)))
    if grounding:
        cfg = types.GenerateContentConfig(
            system_instruction=system, temperature=0.6,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        )
        resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
        return resp.text or ""
    # Google's current standard endpoint for Gemini 3.x structured output.
    # It avoids the recurring generateContent capacity failures seen on full articles.
    interaction = client.interactions.create(
        model=model,
        input=system + "\n\n" + prompt,
        response_format={"type": "text", "mime_type": "application/json", "schema": json_schema},
    )
    return interaction.output_text or ""


async def _gemini_json(kind: str, system: str, prompt: str, grounding: bool) -> tuple[dict, str]:
    schema = (RESEARCH_JSON_SCHEMA if kind == "writing_research" else
              KANNADA_AUDIT_SCHEMA if kind == "kannada_audit" else ARTICLE_JSON_SCHEMA if kind == "writing" else None)
    model_kind = "writing" if kind == "writing_research" else kind
    model = get_model(model_kind)
    text = await _retry(lambda: _gemini_call(model, system, prompt, grounding, schema), f"Gemini {kind}")
    return _parse_json(text), model


def _openai_json_call(model: str, system: str, prompt: str, schema: dict) -> str:
    from lib.manual_ai import environment_reason
    if reason := environment_reason():
        raise AIError(reason, "safety")
    key = get_secret("openai_api_key")
    if not key:
        raise AIError("OpenAI API key is not configured — add it in Settings → AI Providers.", "auth")
    from openai import OpenAI
    client = OpenAI(api_key=key, max_retries=0, timeout=180)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": {"name": "editorial_result", "strict": False, "schema": schema}},
    )
    return response.choices[0].message.content or ""


async def provider_json(kind: str, system: str, prompt: str) -> tuple[dict, str]:
    if get_provider("writing") == "openai":
        model = get_model("writing")
        schema = (RESEARCH_JSON_SCHEMA if kind == "writing_research" else
                  KANNADA_AUDIT_SCHEMA if kind == "kannada_audit" else ARTICLE_JSON_SCHEMA)
        text = await _retry(lambda: _openai_json_call(model, system, prompt, schema), f"OpenAI {kind}", tries=2)
        return _parse_json(text), model
    return await _gemini_json(kind, system, prompt, False)


async def run_research(prompt: str, topic: dict) -> tuple[dict, str]:
    from lib.manual_ai import environment_reason
    if reason := environment_reason():
        raise AIError(reason, "configuration")
    from lib.deep_research import research
    return await research(prompt, topic)


async def run_article(prompt: str, topic: dict, dossier: dict, language: str) -> tuple[dict, str]:
    """Article generation via the selected research provider. Raises AIError on failure."""
    return await provider_json(
        "writing",
        "You are a senior editor writing original, publication-ready news analysis. "
        "Return ONLY a valid JSON object matching the requested schema.",
        prompt,
    )


async def gemini_ping(kind: str) -> dict:
    """Configuration inspection only; a health check must never incur charges."""
    return {"ok": False, "configured": bool(get_secret("gemini_api_key") and get_model(kind)),
            "model": get_model(kind), "kind": "not_tested", "paid_request_sent": False,
            "error": "Live provider validation has not run. A paid integration test requires explicit owner approval."}


# ── OpenAI images ───────────────────────────────────────────────────────────
def _openai_image(model: str, prompt: str, size: str) -> str:
    from lib.manual_ai import environment_reason
    if reason := environment_reason():
        raise AIError(reason, "safety")
    if not model:
        raise AIError("Configure OPENAI_IMAGE_MODEL in the server environment.", "configuration")
    key = get_secret("openai_api_key")
    if not key:
        raise AIError("OpenAI API key is not configured — add it in Settings → AI Providers.", "auth")
    from openai import OpenAI

    client = OpenAI(api_key=key, max_retries=0, timeout=IMAGE_PROVIDER_TIMEOUT_SECONDS)
    r = client.images.generate(model=model, prompt=prompt, size=size, n=1)
    return r.data[0].b64_json


def _gemini_image(model: str, prompt: str) -> str:
    from lib.manual_ai import environment_reason
    if reason := environment_reason():
        raise AIError(reason, "safety")
    key = get_secret("gemini_api_key")
    if not key:
        raise AIError("Gemini API key is not configured — add it in Settings → AI Providers.", "auth")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=IMAGE_PROVIDER_TIMEOUT_SECONDS * 1000,
        retry_options=types.HttpRetryOptions(attempts=1),
    ))
    response = client.models.generate_images(model=model, prompt=prompt, config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="16:9"))
    return base64.b64encode(response.generated_images[0].image.image_bytes).decode()


def _size_for(model: str) -> str:
    return "1536x864"


async def generate_image(brief: str, site_name: str, brand_style: str, *, template: str,
                         headlines: list[str], language: str) -> tuple[str, str, str]:
    from lib.thumbnails import validate_headlines
    from PIL import Image
    model = get_model("image")
    try:
        # Validate the headlines BEFORE a paid request. The prompt (owner's format) has the model render the whole
        # thumbnail, headline text included; the app adds no text.
        headlines = validate_headlines(headlines, language)
        prompt = template
        for key, value in {"brief": brief, "site_name": site_name, "brand_style": brand_style}.items():
            prompt = prompt.replace("{" + key + "}", value)
        if get_provider("image") == "gemini":
            b64 = await _retry(lambda: _gemini_image(model, prompt), "Google Imagen")
        else:
            b64 = await _retry(lambda: _openai_image(model, prompt, _size_for(model)), "OpenAI image")
        im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=90, method=6)
        return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode(), model, "webp"
    except AIError:
        raise
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise AIError(str(exc), "validation") from None
        raise AIError("Thumbnail processing failed; check font configuration and provider output.", "error") from None


async def openai_ping() -> dict:
    """Configuration inspection only; never generate a chargeable test image."""
    model = get_model("image")
    return {"ok": False, "configured": bool(get_secret("openai_api_key") and model),
            "model": model, "kind": "not_tested", "paid_request_sent": False,
            "error": "Live provider validation has not run. A paid integration test requires explicit owner approval."}
