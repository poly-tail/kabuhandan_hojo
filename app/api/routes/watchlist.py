"""Watchlist endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.watchlist import SecuritySearchResult, WatchlistCreate, WatchlistItem
from app.services.mock_watchlist import mock_watchlist_service
from app.services.watchlist import WatchlistService

router = APIRouter(tags=["watchlist"])
service = WatchlistService()
mock_service = mock_watchlist_service


@router.get("/securities/search", response_model=list[SecuritySearchResult], tags=["securities"])
def search_securities(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session | None = Depends(get_db),
) -> list[SecuritySearchResult]:
    """Search known securities so they can be added to the watchlist."""

    if get_settings().app_use_mock:
        return mock_service.search_candidates(query=q, limit=limit)

    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")

    return service.search_candidates(db, query=q, limit=limit)


@router.get("/watchlist", response_model=list[WatchlistItem])
def list_watchlist(db: Session | None = Depends(get_db)) -> list[WatchlistItem]:
    """List active watchlist items."""

    if get_settings().app_use_mock:
        return mock_service.list_items()

    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")

    return service.list_items(db)


@router.post("/watchlist", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
def create_watchlist_item(payload: WatchlistCreate, db: Session | None = Depends(get_db)) -> WatchlistItem:
    """Create or reactivate a watchlist item."""

    if get_settings().app_use_mock:
        return mock_service.create_item(payload)

    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")

    return service.create_item(db, payload)
