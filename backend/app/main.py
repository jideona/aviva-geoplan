import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import classify, envelope
from app.core.logging import configure_logging, get_logger, request_id_var

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger()

app = FastAPI(
    title="Aviva GeoPlan API",
    version="0.1.0",
    description=(
        "AI-assisted GIS survey and fibre network planning platform. "
        "Phase 1 vertical slice: authentication, projects, boundary upload."
    ),
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlate(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["x-request-id"] = rid
    return response


@app.exception_handler(HTTPException)
async def classified_http(request: Request, exc: HTTPException):
    # Preserve the message the raiser gave, but attach audience + remedy so the
    # frontend can route it to the user or to an admin alert.
    if exc.status_code >= 500:
        log.error("http_error", path=str(request.url.path),
                  status=exc.status_code, detail=str(exc.detail))
    body = envelope(exc.status_code,
                    exc.detail if isinstance(exc.detail, str) else "Request failed.")
    return JSONResponse(status_code=exc.status_code, content=body,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Never leak internals to the caller (SRD NFR-USE-007). Full detail logged.
    log.error("unhandled_error", path=str(request.url.path),
              error=str(exc), error_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content=envelope(500,
            "An unexpected system error occurred. The incident has been logged "
            "with a reference id."),
    )


@app.on_event("startup")
def _check_schema() -> None:
    """Warn at boot if the DB schema is behind the code — migrations run at
    container start, so a mismatch means someone forgot `make migrate`."""
    from pathlib import Path
    from sqlalchemy import text
    from app.db.session import engine
    try:
        versions = Path(__file__).resolve().parent / "migrations" / "versions"
        on_disk = sorted(p.name.split("_")[0] for p in versions.glob("[0-9]*.py"))
        with engine.connect() as conn:
            applied = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        latest = on_disk[-1] if on_disk else None
        if latest and applied != latest:
            log.error("schema_behind", applied=applied, latest=latest,
                      action="run `make migrate`")
        else:
            log.info("schema_current", version=applied)
    except Exception as exc:                       # never block startup on this
        log.warning("schema_check_failed", error=str(exc))


app.include_router(api_router)
