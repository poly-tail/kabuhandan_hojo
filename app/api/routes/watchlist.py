"""Named watchlist endpoints and legacy default-list compatibility routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.watchlist import (
    SecuritySearchResult,
    WatchlistCollectionCreate,
    WatchlistCollectionRead,
    WatchlistCollectionUpdate,
    WatchlistCreate,
    WatchlistItem,
)
from app.services.mock_watchlist import mock_watchlist_service
from app.services.watchlist import (
    DefaultWatchlistDeletionError,
    DuplicateWatchlistNameError,
    WatchlistCollectionNotFoundError,
    WatchlistItemNotFoundError,
    WatchlistService,
)

router = APIRouter(tags=["watchlist"])
service = WatchlistService()
mock_service = mock_watchlist_service


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")
    return db


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/securities/search", response_model=list[SecuritySearchResult], tags=["securities"])
def search_securities(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    watchlist_id: int | None = Query(default=None, ge=1),
    db: Session | None = Depends(get_db),
) -> list[SecuritySearchResult]:
    """Search securities with membership scoped to one named watchlist."""

    try:
        if get_settings().app_use_mock:
            return mock_service.search_candidates(
                query=q,
                limit=limit,
                collection_id=watchlist_id,
            )
        return service.search_candidates(
            _require_db(db),
            query=q,
            limit=limit,
            collection_id=watchlist_id,
        )
    except WatchlistCollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/watchlists", response_model=list[WatchlistCollectionRead])
def list_watchlists(db: Session | None = Depends(get_db)) -> list[WatchlistCollectionRead]:
    if get_settings().app_use_mock:
        return mock_service.list_collections()
    return service.list_collections(_require_db(db))


@router.post(
    "/watchlists",
    response_model=WatchlistCollectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_watchlist(
    payload: WatchlistCollectionCreate,
    db: Session | None = Depends(get_db),
) -> WatchlistCollectionRead:
    try:
        if get_settings().app_use_mock:
            return mock_service.create_collection(payload)
        return service.create_collection(_require_db(db), payload)
    except DuplicateWatchlistNameError as exc:
        raise _conflict(exc) from exc


@router.patch("/watchlists/{collection_id}", response_model=WatchlistCollectionRead)
def update_watchlist(
    collection_id: int,
    payload: WatchlistCollectionUpdate,
    db: Session | None = Depends(get_db),
) -> WatchlistCollectionRead:
    try:
        if get_settings().app_use_mock:
            return mock_service.update_collection(collection_id, payload)
        return service.update_collection(_require_db(db), collection_id, payload)
    except WatchlistCollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    except DuplicateWatchlistNameError as exc:
        raise _conflict(exc) from exc


@router.delete("/watchlists/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(
    collection_id: int,
    db: Session | None = Depends(get_db),
) -> Response:
    try:
        if get_settings().app_use_mock:
            mock_service.delete_collection(collection_id)
        else:
            service.delete_collection(_require_db(db), collection_id)
    except WatchlistCollectionNotFoundError as exc:
        raise _not_found(exc) from exc
    except DefaultWatchlistDeletionError as exc:
        raise _conflict(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watchlists/{collection_id}/items", response_model=list[WatchlistItem])
def list_watchlist_items(
    collection_id: int,
    db: Session | None = Depends(get_db),
) -> list[WatchlistItem]:
    try:
        if get_settings().app_use_mock:
            return mock_service.list_items(collection_id=collection_id)
        return service.list_items(_require_db(db), collection_id=collection_id)
    except WatchlistCollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/watchlists/{collection_id}/items",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
)
def create_watchlist_item_in_collection(
    collection_id: int,
    payload: WatchlistCreate,
    db: Session | None = Depends(get_db),
) -> WatchlistItem:
    try:
        if get_settings().app_use_mock:
            return mock_service.create_item(payload, collection_id=collection_id)
        return service.create_item(_require_db(db), payload, collection_id=collection_id)
    except WatchlistCollectionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete(
    "/watchlists/{collection_id}/items/{ticker_code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_watchlist_item(
    collection_id: int,
    ticker_code: str,
    db: Session | None = Depends(get_db),
) -> Response:
    try:
        if get_settings().app_use_mock:
            mock_service.remove_item(collection_id, ticker_code)
        else:
            service.remove_item(_require_db(db), collection_id, ticker_code)
    except (WatchlistCollectionNotFoundError, WatchlistItemNotFoundError) as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watchlist", response_model=list[WatchlistItem])
def list_legacy_default_watchlist(db: Session | None = Depends(get_db)) -> list[WatchlistItem]:
    """List the default collection through the original endpoint."""

    if get_settings().app_use_mock:
        return mock_service.list_items()
    return service.list_items(_require_db(db))


@router.post("/watchlist", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
def create_legacy_default_watchlist_item(
    payload: WatchlistCreate,
    db: Session | None = Depends(get_db),
) -> WatchlistItem:
    """Add or reactivate an item in the default collection."""

    if get_settings().app_use_mock:
        return mock_service.create_item(payload)
    return service.create_item(_require_db(db), payload)
