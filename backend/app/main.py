import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.api import assessments, auth, catalog, materials, notifications, progress, questions, recommendations
from app.api import schedule as schedule_api
from app.core.config import get_settings
from app.core.db import Base, engine
from app.jobs import start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(engine)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    scheduler = start_scheduler() if settings.scheduler_enabled else None
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Sideline", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"] if part not in ("body", "query", "path"))
        message = str(first["msg"]).removeprefix("Value error, ")
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "validation_error", "message": f"{location}: {message}" if location else message}},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=error)
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "server_error", "message": "Something went wrong. Please try again."}},
        )

    api = APIRouter(prefix="/api")
    for module in (auth, catalog, materials, questions, assessments, recommendations, notifications, progress):
        api.include_router(module.router)
    api.include_router(schedule_api.router)

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    dist = get_settings().frontend_dist
    index = dist / "index.html"
    if not index.is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
