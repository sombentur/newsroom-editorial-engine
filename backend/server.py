# MAINTAINER NOTE (2026-09-27): ENTRY POINT: FastAPI startup initializes Mongo indexes, seed/config safety, approved-research recovery, then the scheduler. See docs/MAINTAINER_HANDOFF.md before changing startup or recovery; restarting can interrupt in-memory tasks.
"""Local and self-hosted entry point with a safety-gated background scheduler."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
from lib.configuration import validate_environment
validate_environment()
from lib.db import client, db, ensure_indexes
from lib.auth import allowed_origins, require_admin, router as auth_router
from lib.safety import initialize_safety
from lib.scheduler import scheduler_loop
from lib.runtime import ConfigurationError
from seed import seed
from routers.config import router as config_router
from routers.pipeline import router as pipeline_router
from routers.manual_research import router as manual_research_router
from lib.browser_bridge import admin as browser_admin, worker as browser_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler_task = None
    try:
        await db.command("ping")
        await ensure_indexes()
        await seed()
        await initialize_safety()
        from routers.pipeline import recover_approved_research
        await recover_approved_research()
        scheduler_task = asyncio.create_task(scheduler_loop())
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
        client.close()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
api = APIRouter(prefix="/api")

@api.get("/ready")
async def ready():
    await db.command("ping")
    return {"status": "ok", "service": "editorial-local"}

api.include_router(auth_router)
api.include_router(browser_admin)
api.include_router(browser_worker)
api.include_router(config_router, dependencies=[Depends(require_admin)])
api.include_router(pipeline_router, dependencies=[Depends(require_admin)])
api.include_router(manual_research_router, dependencies=[Depends(require_admin)])
app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=list(allowed_origins()),
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])
from urllib.parse import urlsplit
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list({urlsplit(x).hostname for x in allowed_origins()}))

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Invalid request. Check the field formats and required values."})

@app.exception_handler(ConfigurationError)
async def configuration_error(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

DIST = ROOT_DIR.parent / "frontend" / "dist"
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

@app.get("/{path:path}")
async def frontend(path: str):
    if path.startswith("api/") or path == "api":
        return JSONResponse(status_code=404, content={"detail": "API route not found"})
    candidate = (DIST / path).resolve()
    if candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    if (DIST / "index.html").is_file():
        return FileResponse(DIST / "index.html")
    return JSONResponse(status_code=503, content={"detail": "Frontend build missing. Run Setup Local.cmd."})

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
