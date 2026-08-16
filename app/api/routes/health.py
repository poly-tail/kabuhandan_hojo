"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session | None = Depends(get_db)) -> HealthResponse:
    """Return application and database health."""

    settings = get_settings()
    if settings.app_use_mock:
        return HealthResponse(
            status="ok",
            app_name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env,
            database="mock",
        )

    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")

    db.execute(text("SELECT 1"))
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database="ok",
    )
