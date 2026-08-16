"""FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

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
    init_db()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        description=(
            "Japanese equity monitoring support API. "
            "This service organizes watchlist data and does not execute trades or provide definitive investment advice."
        ),
    )
    app.include_router(api_router)
    return app


app = create_app()
