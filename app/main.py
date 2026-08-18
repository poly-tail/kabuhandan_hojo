"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize the database at startup."""

    init_db()
    yield


def create_app() -> FastAPI:
    """Create the FastAPI application."""

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        description=(
            "Japanese equity monitoring support API. "
            "This service organizes watchlist data and does not execute trades or provide definitive investment advice."
        ),
    )

    @app.middleware("http")
    async def add_canonical_ai_no_store_header(request: Request, call_next) -> Response:
        """Prevent browser/proxy caching, including framework validation errors."""

        response = await call_next(request)
        path = request.url.path
        if path == "/api/ai/analyses" or path.startswith("/api/ai/analyses/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(api_router)
    return app


app = create_app()
