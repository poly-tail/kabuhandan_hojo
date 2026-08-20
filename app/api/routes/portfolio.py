"""Portfolio holding endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioHoldingRead,
    PortfolioHoldingUpsert,
    PortfolioImportCsvRequest,
    PortfolioImportCsvResponse,
)
from app.schemas.portfolio_ai import (
    AiReviewHistoryTarget,
    AiReviewMode,
    PortfolioAiReviewHistoryDetail,
    PortfolioAiReviewHistoryListResponse,
    PortfolioAiReviewRequest,
    PortfolioAiReviewResponse,
    PortfolioAiUsageSummary,
    ReviewStatus,
)
from app.services.ai_usage import get_legacy_ai_usage_ledger
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


@router.get("/api/ai/stock-review/usage", response_model=PortfolioAiUsageSummary)
def get_stock_review_usage(response: Response) -> PortfolioAiUsageSummary:
    """Return local usage for the legacy stock-review path only."""

    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    return get_legacy_ai_usage_ledger().summary(daily_limit=settings.openai_daily_request_limit)


@router.get("/api/ai/stock-review/history", response_model=PortfolioAiReviewHistoryListResponse)
def list_stock_review_history(
    response: Response,
    mode: AiReviewMode | None = Query(default=None),
    target: AiReviewHistoryTarget | None = Query(default=None),
    review_status: ReviewStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PortfolioAiReviewHistoryListResponse:
    """Return safe metadata for locally saved legacy stock reviews."""

    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return portfolio_ai_review_service.list_ai_review_history(
        mode=mode,
        target=target,
        status=review_status,
        limit=limit,
        offset=offset,
    )


@router.get("/api/ai/stock-review/history/{history_id}", response_model=PortfolioAiReviewHistoryDetail)
def get_stock_review_history(
    history_id: str,
    response: Response,
) -> PortfolioAiReviewHistoryDetail | JSONResponse:
    """Return one local legacy review without its internal request payload."""

    review = portfolio_ai_review_service.get_ai_review_history(history_id)
    if review is None:
        return _history_not_found_response()
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return review


@router.get("/api/ai/stock-review/history/{history_id}/export.md", response_class=Response)
def export_stock_review_history_markdown(history_id: str) -> Response:
    """Download one local legacy review as semantic UTF-8 Markdown."""

    exported = portfolio_ai_review_service.export_ai_review_history_markdown(history_id)
    if exported is None:
        return _history_not_found_response()
    filename, markdown = exported
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _history_not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "保存済みのAIレビューが見つかりません。"},
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/portfolio/{ticker_code}", status_code=status.HTTP_204_NO_CONTENT)
def archive_portfolio_item(ticker_code: str, db: Session | None = Depends(get_db)) -> None:
    if get_settings().app_use_mock:
        raise RuntimeError("Portfolio endpoints are unavailable in mock mode.")
    if db is None:
        raise RuntimeError("Database session is required when mock mode is disabled.")
    portfolio_service.archive_item(db, ticker_code)
