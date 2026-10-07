# MAINTAINER NOTE (2026-09-27): PERSISTENT RESEARCH: Resume the stored provider job instead of resubmitting a paid request. Browser-generated research and direct API research have different failure paths; investigate the selected provider and stored job before retrying. See docs/MAINTAINER_HANDOFF.md.
"""Persistent provider research jobs; retry polls the same paid job."""
import asyncio
import time

import httpx

from lib.ai import AIError, _retry, _safe, provider_json
from lib.db import db
from lib.manual_ai import block_reason
from lib.secrets import get_model, get_provider, get_secret
from lib.util import now_utc

BASE = "https://generativelanguage.googleapis.com/v1beta/interactions"


def report_text(result: dict) -> str:
    blocks, citations = [], {}
    for step in result.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for item in step.get("content", []):
            if item.get("type") != "text":
                continue
            body = str(item.get("text", ""))
            if body:
                blocks.append(body)
            for annotation in item.get("annotations", []):
                if annotation.get("type") != "url_citation":
                    continue
                url = str(annotation.get("url") or annotation.get("uri") or "")
                if not url.startswith("https://"):
                    continue
                start, end = annotation.get("start_index"), annotation.get("end_index")
                label = body[start:end].replace("\n", " ").strip() if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(body) else ""
                citations.setdefault(url, label[:100])
    report = "\n\n".join(blocks).strip()
    if citations:
        report += "\n\nPROVIDER CITATION LINKS — use only these exact URLs for sources and claim_evidence; do not invent links:\n"
        report += "\n".join(f"- {label or 'Source'}: {url}" for url, label in citations.items())
    return report


async def research(prompt: str, topic: dict, report_only: bool = False) -> tuple[dict | str, str]:
    art_id, site_key = topic["article_id"], topic["site_key"]
    doc = await db.articles.find_one({"id": art_id})
    meta = dict(doc.get("dossier_meta") or {})
    prompt = meta.get("prompt") or prompt
    provider = get_provider("research")
    saved_provider = meta.get("provider") or ("gemini" if meta.get("interaction_id") else "openai" if meta.get("response_id") else None)
    if saved_provider and saved_provider != provider and (meta.get("interaction_id") or meta.get("response_id")):
        raise AIError("A research job is already saved with another provider. Resume or review that job before switching providers.", "review")
    model = (meta.get("model") if saved_provider == provider and
             (meta.get("interaction_id") or meta.get("response_id") or meta.get("report")) else None) or get_model("research")

    async def save(**patch):
        meta.update(patch)
        await db.articles.update_one({"id": art_id}, {"$set": {"dossier_meta": meta, "updated_at": now_utc()}})

    async def stopped_by_editor() -> bool:
        current = await db.articles.find_one({"id": art_id}, {"stage": 1, "held_reason": 1})
        return bool(current and current.get("stage") == "held_review" and current.get("held_reason") == "Stopped by editor.")

    if reason := await block_reason(site_key):
        raise AIError(reason, "safety")
    try:
        from lib.browser_bridge import enabled, run_job
        if await enabled("research"):
            model = "gemini-browser-deep-research"
            if not meta.get("report"):
                suffix = "" if report_only else "\nPrepare a complete Deep Research report with clickable source URLs. Preserve uncertainties and distinguish allegations from established facts."
                report = await run_job("research", art_id, prompt + suffix, 3600)
                await save(report=report, provider="gemini-browser", model=model, status="formatting")
                from lib.browser_bridge import consumed
                await consumed("research", art_id)
        elif provider == "openai":
            if not get_secret("openai_api_key"):
                raise AIError("OpenAI API key is missing.", "auth")
            from openai import OpenAI
            client = OpenAI(api_key=get_secret("openai_api_key"), max_retries=0, timeout=90)
            response_id = meta.get("response_id")
            if not response_id and meta.get("status") == "submitting":
                raise AIError("The earlier OpenAI submission has an unknown outcome. Check provider activity before starting another paid job.", "review")
            if not response_id and meta.get("status") in {"failed", "cancelled"}:
                raise AIError("The saved Deep Research job ended without a report. Review its provider status before starting a new paid job.", "review")
            if not response_id and not meta.get("report"):
                await save(model=model, prompt=prompt, status="submitting", started=now_utc(), provider="openai")
                try:
                    response = await _retry(lambda: client.responses.create(
                        model=model, input=prompt + ("" if report_only else "\nPrepare a complete research report with source URLs and citations."),
                        tools=[{"type": "web_search_preview"}], background=True), "OpenAI Deep Research submit")
                except AIError as exc:
                    if exc.kind in {"model_unavailable", "auth", "rate_limit"}:
                        await save(status="rejected")
                    raise
                response_id = response.id
                if not response_id:
                    raise AIError("OpenAI did not return a job ID. Check provider activity before resubmitting.", "review")
                await save(response_id=response_id, status=response.status)
            deadline = time.monotonic() + 3600
            while not meta.get("report"):
                if await stopped_by_editor():
                    raise AIError("Stopped by editor.", "cancelled")
                if reason := await block_reason(site_key):
                    raise AIError(reason, "safety")
                response = await _retry(lambda: client.responses.retrieve(response_id), "OpenAI Deep Research poll")
                await save(status=response.status)
                if response.status == "completed":
                    report = response.output_text or ""
                    if not report:
                        raise AIError("OpenAI Deep Research completed without a readable report.", "error")
                    await save(report=report, status="formatting")
                    break
                if response.status in {"failed", "cancelled", "incomplete", "expired"}:
                    raise AIError(f"OpenAI Deep Research {response.status}; no replacement job was submitted.", "error")
                if time.monotonic() >= deadline:
                    raise AIError("Research is still running. Retry will reconnect to the same job.", "network")
                await asyncio.sleep(10)
        else:
            if not model.startswith("deep-research-"):
                raise AIError("Configure a Gemini Deep Research agent.", "configuration")
            if not get_secret("gemini_api_key"):
                raise AIError("Gemini API key is missing.", "auth")
            async with httpx.AsyncClient(timeout=90, headers={"x-goog-api-key": get_secret("gemini_api_key")}) as client:
                interaction_id = meta.get("interaction_id")
                if not interaction_id and meta.get("status") == "submitting":
                    raise AIError("The earlier submission has an unknown outcome. Check Gemini activity before starting another paid job.", "review")
                if meta.get("status") in {"failed", "cancelled"}:
                    raise AIError("The saved Deep Research job ended without a report. Review its provider status before starting a new paid job.", "review")
                if not interaction_id:
                    await save(model=model, prompt=prompt, status="submitting", started=now_utc(), provider="gemini")
                    response = await client.post(BASE, json={"agent": model, "background": True, "store": True, "input": prompt + ("" if report_only else "\nPrepare a complete research report with source URLs and citations. The app will format it separately; prioritize evidence over JSON formatting.")})
                    if 400 <= response.status_code < 500 and response.status_code != 408:
                        await save(status="rejected")
                    response.raise_for_status()
                    result = response.json()
                    interaction_id = result.get("id")
                    if not interaction_id:
                        raise AIError("Gemini did not return a job ID. Check provider activity before resubmitting.", "review")
                    await save(interaction_id=interaction_id, status=result.get("status", "in_progress"))
                deadline = time.monotonic() + 3600
                while not meta.get("report"):
                    if await stopped_by_editor():
                        raise AIError("Stopped by editor.", "cancelled")
                    if reason := await block_reason(site_key):
                        cancelled = await client.post(f"{BASE}/{interaction_id}/cancel")
                        cancelled.raise_for_status()
                        await save(status="cancelled")
                        raise AIError(reason + " The research cancellation was requested.", "safety")
                    response = await client.get(f"{BASE}/{interaction_id}")
                    response.raise_for_status()
                    result = response.json()
                    status = result.get("status")
                    await save(status=status)
                    if status == "completed":
                        report = report_text(result)
                        if not report:
                            raise AIError("Deep Research completed without a readable report.", "error")
                        await save(report=report, status="formatting", citations_included=True)
                        break
                    if status in {"failed", "cancelled"}:
                        raise AIError(f"Deep Research {status}; no replacement job was submitted.", "error")
                    if time.monotonic() >= deadline:
                        raise AIError("Research is still running. Retry will reconnect to the same job.", "network")
                    await asyncio.sleep(10)
        if await stopped_by_editor():
            raise AIError("Stopped by editor.", "cancelled")
        if reason := await block_reason(site_key):
            raise AIError(reason, "safety")
        if report_only:
            await save(status="completed", completed=now_utc())
            return meta["report"], model
        if (provider == "gemini" and meta.get("interaction_id") and meta.get("report")
                and meta.get("citation_reformat_attempted") and not meta.get("citations_included")):
            async with httpx.AsyncClient(timeout=30, headers={"x-goog-api-key": get_secret("gemini_api_key")}) as client:
                response = await client.get(f"{BASE}/{meta['interaction_id']}")
                response.raise_for_status()
                result = response.json()
            if result.get("status") == "completed":
                enriched = report_text(result)
                if enriched:
                    await save(report=enriched, citations_included=True, status="formatting")
        system = (
            "Format the supplied research report as the requested JSON. Preserve source URLs and uncertainty. "
            "When PROVIDER CITATION LINKS are supplied, use only those exact URLs as sources. "
            "Every claim_evidence.source_url must exactly equal a URL in sources[].url. "
            "Set verified=true only for claims explicitly supported in the report; omit unsupported claims. "
            "Never add facts, sources, URLs, or claim verification absent from the report. "
            "If source corroboration is insufficient, set publication_ready=false and explain why."
        )
        formatted_prompt = prompt + "\n\nCOMPLETED DEEP RESEARCH REPORT:\n" + meta["report"]
        dossier, formatter = await provider_json("writing_research", system, formatted_prompt)
        await save(status="completed", completed=now_utc(), formatting_model=formatter)
        return dossier, model
    except AIError:
        raise
    except Exception as exc:
        raise AIError(_safe(exc), "network" if isinstance(exc, httpx.TransportError) else "error") from None
