"""ASGI application factory; use one API process for the local thread executor."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException

from . import __version__
from .config import Settings
from .database import Database
from .errors import APIError
from .jobs import JobDispatcher, JobRunner
from .middleware import RequestMiddleware
from .repository import Repository
from .routes import router
from .services import ResearchService

logger = logging.getLogger("neuroresect.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings.database_url)
        database.initialize()
        repository = Repository(database)
        service = ResearchService(repository)
        if settings.job_executor == "local":
            recovered = repository.recover_local_jobs()
            if recovered:
                logger.warning("interrupted_local_jobs count=%d", recovered)
        dispatcher = JobDispatcher(settings, repository, JobRunner(repository, service))
        app.state.database = database
        app.state.repository = repository
        app.state.service = service
        app.state.dispatcher = dispatcher
        try:
            yield
        finally:
            dispatcher.shutdown()
            database.close()

    app = FastAPI(
        title="NeuroResect Research API",
        description=(
            "Virtual resection, network analysis, and synthetic outcome experiments. "
            "Anonymous local research prototype; outputs are not clinical recommendations. "
            "Long computations return persisted jobs. Poll until SUCCEEDED or FAILED."
        ),
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(RequestMiddleware, max_request_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.exception_handler(APIError)
    async def api_error(_: Request, exc: APIError):
        return JSONResponse(exc.envelope(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Pydantic's input/ctx fields may contain a whole uploaded matrix or exception object.
        issues = [
            {"location": list(error["loc"]), "type": error["type"], "message": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            APIError(422, "VALIDATION_ERROR", "Request validation failed.", {"issues": issues}).envelope(),
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse(
            APIError(exc.status_code, "HTTP_ERROR", str(exc.detail)).envelope(),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        logger.error("request_failed error_type=%s", type(exc).__name__)
        return JSONResponse(
            APIError(500, "INTERNAL_ERROR", "An internal error occurred.").envelope(),
            status_code=500,
        )

    @app.get("/health", tags=["health"])
    def health(request: Request):
        try:
            with request.app.state.database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise APIError(503, "DATABASE_UNAVAILABLE", "Database is unavailable.") from exc
        return {"status": "ok", "version": __version__, "executor": settings.job_executor}

    app.include_router(router)
    return app


app = create_app()
