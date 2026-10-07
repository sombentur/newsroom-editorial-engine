"""Manual Editorial Workbench API (owner request, 28 Sep 2026): the research workbook (download/upload) and the
imports of the owner's research reports, one Topic ID at a time. See lib/manual_research.py."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from lib import manual_research as manual
from lib.util import now_utc

router = APIRouter(prefix="/manual-research")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class UploadBody(BaseModel):
    filename: str = Field(default="", max_length=200)
    content_b64: str = Field(min_length=1, max_length=14_000_000)


class ProceedBody(BaseModel):
    url: str | None = Field(default=None, max_length=2000)  # the research link pasted in the row (optional)


class FetchBody(BaseModel):
    replace: bool = False  # Replace Existing Research / Re-import: overwrite research the topic already has


def _actor(request: Request) -> str:
    return getattr(request.state, "admin", None) or "owner"


@router.get("")
async def manual_rows():
    return {"rows": await manual.list_rows(), "statuses": manual.STATUS_LABELS}


@router.get("/export")
async def download_workbook(request: Request):
    content, count = await manual.export_workbook(_actor(request))
    name = f"research-topics-{now_utc():%Y-%m-%d-%H%M}.xlsx"
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                       "X-Topic-Count": str(count)})


@router.post("/import")
async def upload_workbook(body: UploadBody, request: Request):
    try:
        content = manual.decode_upload(body.content_b64)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return await manual.import_workbook(content, body.filename, _actor(request))


@router.get("/imports/{batch_id}")
async def upload_summary(batch_id: str):
    if not (summary := await manual.batch_summary(batch_id)):
        raise HTTPException(404, "Import not found.")
    return summary


@router.post("/{article_id}/fetch")
async def fetch_research(article_id: str, body: FetchBody | None = None):
    try:
        return await manual.fetch_again(article_id, bool(body and body.replace))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{article_id}/proceed")
async def proceed_with_research(article_id: str, body: ProceedBody | None = None):
    try:
        return await manual.proceed(article_id, body.url if body else None)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{article_id}/release")
async def research_automatically(article_id: str):
    try:
        await manual.release(article_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"ok": True}


@router.get("/{article_id}/report")
async def view_imported_research(article_id: str):
    if not (report := await manual.imported_report(article_id)):
        raise HTTPException(404, "Topic not found.")
    return report



class PasteContentBody(BaseModel):
    html: str = Field(min_length=1, max_length=2_000_000)
    replace: bool = False


class UploadDocumentBody(BaseModel):
    filename: str = Field(default="", max_length=200)
    content_b64: str = Field(min_length=1, max_length=14_000_000)
    replace: bool = False


@router.post("/{article_id}/paste-content")
async def paste_research_content(article_id: str, body: PasteContentBody):
    try:
        return await manual.import_pasted(article_id, body.html, body.replace)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/{article_id}/upload-document")
async def upload_research_document(article_id: str, body: UploadDocumentBody):
    try:
        return await manual.import_uploaded(article_id, body.filename, body.content_b64, body.replace)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None



@router.get("/today-stats")
async def today_published_stats():
    """Count articles that reached published/scheduled/wordpress_draft today (IST calendar day) per site."""
    return await manual.today_stats()


# Declared last: "/{article_id}" must not shadow /export or /imports/… above.
@router.get("/{article_id}")
async def research_row(article_id: str):
    if not (row := await manual.row_for(article_id)):
        raise HTTPException(404, "Topic not found.")
    return row
