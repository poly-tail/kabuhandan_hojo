"""Portfolio holding endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioHoldingRead,
    PortfolioHoldingUpsert,
    PortfolioImportCsvRequest,
    PortfolioImportCsvResponse,
)
from app.schemas.portfolio_ai import PortfolioAiReviewRequest, PortfolioAiReviewResponse
from app.services.portfolio import portfolio_service
from app.services.portfolio_ai_review import portfolio_ai_review_service

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=list[PortfolioHoldingRead])
def list_portfolio(db: Session | None = Depends(get_db)) -> list[PortfolioHoldingRead]:
    if get_settings().app_use_mock:
        return []
    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")
    return portfolio_service.list_items(db)


@router.post("/portfolio", response_model=PortfolioHoldingRead, status_code=status.HTTP_201_CREATED)
def upsert_portfolio_item(payload: PortfolioHoldingUpsert, db: Session | None = Depends(get_db)) -> PortfolioHoldingRead:
    if get_settings().app_use_mock:
        raise RuntimeError("Portfolio endpoints are unavailable in mock mode.")
    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")
    return portfolio_service.upsert_item(db, payload)


@router.post("/portfolio/import/csv", response_model=PortfolioImportCsvResponse)
def import_portfolio_csv(
    payload: PortfolioImportCsvRequest,
    db: Session | None = Depends(get_db),
) -> PortfolioImportCsvResponse:
    if get_settings().app_use_mock:
        raise RuntimeError("Portfolio endpoints are unavailable in mock mode.")
    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")
    return portfolio_service.import_csv(db, payload)


@router.post("/portfolio/ai-review", response_model=PortfolioAiReviewResponse)
@router.post("/api/portfolio/ai-review", response_model=PortfolioAiReviewResponse, include_in_schema=False)
@router.post("/api/ai/stock-review", response_model=PortfolioAiReviewResponse)
def review_portfolio_with_ai(
    payload: PortfolioAiReviewRequest,
    db: Session | None = Depends(get_db),
) -> PortfolioAiReviewResponse:
    return portfolio_ai_review_service.review(payload, session=db)


@router.delete("/portfolio/{ticker_code}", status_code=status.HTTP_204_NO_CONTENT)
def archive_portfolio_item(ticker_code: str, db: Session | None = Depends(get_db)) -> None:
    if get_settings().app_use_mock:
        raise RuntimeError("Portfolio endpoints are unavailable in mock mode.")
    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")
    portfolio_service.archive_item(db, ticker_code)
