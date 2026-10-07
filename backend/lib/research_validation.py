"""Evidence checks shared by the pipeline and offline tests."""

import asyncio
import re
from urllib.parse import urlsplit

import httpx


def _canonical(url: str) -> str:
    parts = urlsplit(str(url or ""))
    return (parts.scheme.lower() + "://" + parts.netloc.lower() + parts.path.rstrip("/")) if parts.scheme in {"http", "https"} else ""


async def resolve_grounding_redirects(dossier: dict) -> dict:
    """Turn Gemini citation redirects into publisher URLs before checking domains."""
    sources = dossier.get("sources") or []
    claims = dossier.get("claim_evidence") or []
    urls = {str(item.get(field, "")) for rows, field in ((sources, "url"), (claims, "source_url"))
            for item in rows if isinstance(item, dict)}
    redirects = [url for url in urls if urlsplit(url).scheme == "https" and
                 urlsplit(url).netloc.lower() == "vertexaisearch.cloud.google.com" and
                 urlsplit(url).path.startswith("/grounding-api-redirect/")]
    if not redirects:
        return dossier
    limit = asyncio.Semaphore(6)

    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        async def resolve(url: str) -> tuple[str, str]:
            async with limit:
                try:
                    response = await client.get(url)
                    target = response.headers.get("location", "") if response.status_code in {301, 302, 303, 307, 308} else ""
                    parsed = urlsplit(target)
                    host = (parsed.hostname or "").lower()
                    if parsed.scheme == "https" and host and host != "localhost" and not host.endswith(".local"):
                        return url, target
                except httpx.HTTPError:
                    pass
                return url, url

        mapping = dict(await asyncio.gather(*(resolve(url) for url in redirects)))
    for rows, field in ((sources, "url"), (claims, "source_url")):
        for item in rows:
            if isinstance(item, dict) and item.get(field) in mapping:
                item[field] = mapping[item[field]]
    return dossier


async def reconcile_provider_citations(dossier: dict, report: str) -> dict:
    """Add omitted claim sources only when the research provider itself cited the URL."""
    if "PROVIDER CITATION LINKS" not in report:
        return dossier
    appendix = report.split("PROVIDER CITATION LINKS", 1)[1]
    links = list(dict.fromkeys(re.findall(r"https://[^\s]+", appendix)))
    if not links:
        return dossier
    provider_refs = {"sources": [{"url": url} for url in links], "claim_evidence": []}
    await resolve_grounding_redirects(provider_refs)
    allowed = {_canonical(source["url"]) for source in provider_refs["sources"]}
    sources = dossier.setdefault("sources", [])
    present = {_canonical(source.get("url")) for source in sources if isinstance(source, dict)}
    for claim in dossier.get("claim_evidence", []):
        if not isinstance(claim, dict) or claim.get("verified") is not True:
            continue
        url = str(claim.get("source_url") or "")
        key = _canonical(url)
        if not key or key not in allowed or key in present:
            continue
        host = urlsplit(url).hostname or "Source"
        sources.append({"title": str(claim.get("claim") or host)[:160], "publisher": host,
                        "url": url, "type": "secondary", "reliability": "Provider-cited source"})
        present.add(key)
    return dossier


def validate_research(dossier: dict, language: str | None = None) -> dict:
    checks, failed = [], []
    sources = dossier.get("sources", [])
    accessible = [s for s in sources if isinstance(s, dict) and str(s.get("url", "")).startswith(("https://", "http://"))]
    claims = dossier.get("claim_evidence", [])

    cited = {_canonical(s["url"]) for s in accessible}

    def chk(name: str, ok: bool, note: str = ""):
        checks.append({"name": name, "passed": ok, "note": note})
        if not ok:
            failed.append(name)

    chk("has_sources", len(sources) >= 1, f"{len(sources)} source(s)")
    chk("cited_urls_present", len(accessible) >= 1, f"{len(accessible)} with URLs")
    chk("claims_mapped", len(claims) >= 1, f"{len(claims)} claim-to-source rows")
    chk("no_unsupported_material_claim", all(isinstance(c, dict) and c.get("verified") is True for c in claims) if claims else False,
        "every material claim maps to a verified source")
    chk("claim_urls_match_sources", bool(claims) and all(isinstance(c, dict) and _canonical(c.get("source_url")) in cited for c in claims),
        "every claim URL occurs in the source list")
    if language == "kn":
        domains = {urlsplit(s["url"]).netloc.lower().removeprefix("www.") for s in accessible}
        chk("kannada_second_source", len(domains) >= 2,
            f"{len(domains)} independent source domains; at least 2 required")
    chk("publication_ready", bool(dossier.get("publication_ready", False)),
        "; ".join(dossier.get("not_ready_reasons", [])) or "model marked ready")
    return {"passed": len(failed) == 0, "checks": checks, "failed_reasons": failed}
