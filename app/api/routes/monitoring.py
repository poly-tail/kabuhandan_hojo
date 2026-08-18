"""Phase 2+ monitoring endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.security_master_sync import SecurityMasterStatusResponse, SecurityMasterSyncResponse
from app.services.mock_monitoring import mock_monitoring_service
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from app.services.security_master_catalog import local_security_master_catalog
from kabuhandan_hojo.connectors.base import ConnectorError, MissingCredentialsError
from kabuhandan_hojo.models.entities import EventFact, FlowSnapshot, ScoreDaily, SecurityMaster, TechnicalFeatureDaily
from kabuhandan_hojo.schemas.alerts import AlertRead
from kabuhandan_hojo.schemas.common import JobRunResponse
from kabuhandan_hojo.schemas.dashboard import DashboardResponse, DashboardRow, ScreeningResult
from kabuhandan_hojo.schemas.events import (
    AllowlistedIrDocumentCreate,
    DocumentImportResponse,
    EventRead,
    RawDocumentCreate,
    YouTubeSyncRequest,
)
from kabuhandan_hojo.schemas.scores import ScoreRead, ScoreRecalculateResponse
from kabuhandan_hojo.schemas.screening import FlowScreeningFilters, ScreeningFilterRequest, TechnicalScreeningFilters
from kabuhandan_hojo.schemas.securities import (
    FinancialSnapshotCreate,
    FinancialSnapshotRead,
    FlowSnapshotCreate,
    FlowSnapshotRead,
    PriceBarCreate,
    PriceBarRead,
    SecurityCreate,
    SecurityDetailResponse,
    SecurityRead,
    TechnicalFeatureRead,
)
from kabuhandan_hojo.services.ingestion import IngestionService
from kabuhandan_hojo.services.insights import build_flow_context, build_technical_context, screening_reasons
from kabuhandan_hojo.services.securities import SecurityService
from kabuhandan_hojo.services.watchlists import WatchlistService

router = APIRouter(tags=["monitoring"])

DISCLAIMER_TEXT = (
    "本APIは日本株の判断補助を目的としており、売買の断定や自動執行を行うものではありません。"
)


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database-backed monitoring endpoints are unavailable in mock mode.",
        )
    return db


def _build_ingestion_service() -> IngestionService:
    return IngestionService(get_monitoring_container())


def _build_security_service() -> SecurityService:
    return SecurityService()


def _build_watchlist_service() -> WatchlistService:
    return WatchlistService()


def _security_master_status_payload(status_snapshot: Any) -> dict[str, Any]:
    """Map service status to the public contract without exposing credentials."""

    return {
        "source": status_snapshot.source,
        "source_scope": status_snapshot.source_scope,
        "source_as_of": status_snapshot.source_as_of,
        "sync_id": status_snapshot.sync_id,
        "synced_at": status_snapshot.synced_at,
        "complete": status_snapshot.complete,
        "active_total": status_snapshot.active_total,
        "jquants_active_count": status_snapshot.jquants_active_count,
    }


def _to_alert_reads(alerts: list) -> list[AlertRead]:
    return [
        AlertRead(
            ticker_code=alert.ticker_code,
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
        )
        for alert in alerts
    ]


def _latest_previous_score(session: Session, ticker_code: str, current_score_id: int) -> ScoreDaily | None:
    return session.scalar(
        select(ScoreDaily)
        .where(ScoreDaily.ticker_code == ticker_code, ScoreDaily.id != current_score_id)
        .order_by(ScoreDaily.target_date.desc())
        .limit(1)
    )


def _build_security_detail(session: Session, ticker_code: str) -> SecurityDetailResponse:
    service = _build_security_service()
    security = service.get(session, ticker_code)
    if security is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security was not found.")

    latest_score = service.latest_score(session, ticker_code)
    latest_features = service.latest_feature(session, ticker_code)
    recent_events = service.recent_events(session, ticker_code)
    latest_financials = service.latest_financial(session, ticker_code)
    latest_flow = service.latest_flow(session, ticker_code)
    latest_prices = service.latest_prices(session, ticker_code)

    score_read = ScoreRead.model_validate(latest_score) if latest_score else None
    feature_read = TechnicalFeatureRead.model_validate(latest_features) if latest_features else None
    flow_read = FlowSnapshotRead.model_validate(latest_flow) if latest_flow else None

    updated_at_candidates = [
        security.updated_at,
        getattr(latest_score, "updated_at", None),
        getattr(latest_features, "updated_at", None),
        getattr(latest_financials, "updated_at", None),
        getattr(latest_flow, "updated_at", None),
        *(price.updated_at for price in latest_prices),
    ]
    updated_at = max((item for item in updated_at_candidates if item is not None), default=None)

    return SecurityDetailResponse(
        security=SecurityRead.model_validate(security),
        latest_score=score_read,
        latest_features=feature_read,
        technical_context=build_technical_context(feature_read, score_read),
        recent_events=[EventRead.model_validate(event) for event in recent_events],
        latest_financials=FinancialSnapshotRead.model_validate(latest_financials) if latest_financials else None,
        latest_flow=flow_read,
        flow_context=build_flow_context(flow_read, feature_read, score_read),
        latest_prices=[PriceBarRead.model_validate(price) for price in latest_prices],
        updated_at=updated_at,
    )


def _build_screening_result(
    *,
    security: SecurityMaster | SecurityRead,
    latest_score: ScoreDaily | ScoreRead | None,
    latest_features: TechnicalFeatureDaily | TechnicalFeatureRead | None,
    latest_flow: FlowSnapshot | FlowSnapshotRead | None,
) -> ScreeningResult:
    security_read = security if isinstance(security, SecurityRead) else SecurityRead.model_validate(security)
    score_read = latest_score if isinstance(latest_score, ScoreRead) else (ScoreRead.model_validate(latest_score) if latest_score else None)
    feature_read = (
        latest_features if isinstance(latest_features, TechnicalFeatureRead) else (
            TechnicalFeatureRead.model_validate(latest_features) if latest_features else None
        )
    )
    flow_read = latest_flow if isinstance(latest_flow, FlowSnapshotRead) else (FlowSnapshotRead.model_validate(latest_flow) if latest_flow else None)
    return ScreeningResult(
        security=security_read,
        latest_score=score_read,
        latest_features=feature_read,
        latest_flow=flow_read,
        matched_reasons=screening_reasons(feature_read, flow_read, score_read),
    )


def _matches_technical_filters(feature: Any, filters: TechnicalScreeningFilters | None) -> bool:
    if filters is None:
        return True
    if feature is None:
        return False
    if filters.min_rsi_14 is not None and (feature.rsi_14 is None or feature.rsi_14 < filters.min_rsi_14):
        return False
    if filters.max_rsi_14 is not None and (feature.rsi_14 is None or feature.rsi_14 > filters.max_rsi_14):
        return False
    if filters.macd_cross == "bullish" and not getattr(feature, "macd_bullish_cross_flag", False):
        return False
    if filters.macd_cross == "bearish" and not getattr(feature, "macd_bearish_cross_flag", False):
        return False
    if filters.macd_histogram_positive is True and (feature.macd_histogram is None or feature.macd_histogram <= 0):
        return False
    if filters.macd_histogram_positive is False and (feature.macd_histogram is None or feature.macd_histogram >= 0):
        return False
    if filters.price_above_ma_25 is True and (feature.deviation_from_sma_25_pct is None or feature.deviation_from_sma_25_pct <= 0):
        return False
    if filters.price_above_ma_25 is False and (feature.deviation_from_sma_25_pct is None or feature.deviation_from_sma_25_pct >= 0):
        return False
    if filters.price_above_ma_75 is True and (feature.deviation_from_sma_75_pct is None or feature.deviation_from_sma_75_pct <= 0):
        return False
    if filters.price_above_ma_75 is False and (feature.deviation_from_sma_75_pct is None or feature.deviation_from_sma_75_pct >= 0):
        return False
    if filters.golden_cross_only and not feature.golden_cross_flag:
        return False
    if filters.dead_cross_exclude and feature.dead_cross_flag:
        return False
    if filters.min_volume_surge_ratio is not None and (
        feature.volume_surge_ratio is None or feature.volume_surge_ratio < filters.min_volume_surge_ratio
    ):
        return False
    if filters.min_upper_wick_ratio is not None and (
        feature.upper_wick_ratio is None or feature.upper_wick_ratio < filters.min_upper_wick_ratio
    ):
        return False
    if filters.max_upper_wick_ratio is not None and (
        feature.upper_wick_ratio is None or feature.upper_wick_ratio > filters.max_upper_wick_ratio
    ):
        return False
    if filters.min_lower_wick_ratio is not None and (
        feature.lower_wick_ratio is None or feature.lower_wick_ratio < filters.min_lower_wick_ratio
    ):
        return False
    if filters.gap_up_only and not feature.gap_up_flag:
        return False
    if filters.gap_down_exclude and feature.gap_down_flag:
        return False
    return True


def _matches_flow_filters(flow: Any, filters: FlowScreeningFilters | None) -> bool:
    if filters is None:
        return True
    if flow is None:
        return False
    if filters.min_credit_ratio is not None and (flow.credit_ratio is None or flow.credit_ratio < filters.min_credit_ratio):
        return False
    if filters.max_credit_ratio is not None and (flow.credit_ratio is None or flow.credit_ratio > filters.max_credit_ratio):
        return False
    if filters.min_buy_balance_change_wow is not None and (
        flow.buy_balance_change_wow is None or flow.buy_balance_change_wow < filters.min_buy_balance_change_wow
    ):
        return False
    if filters.max_buy_balance_change_wow is not None and (
        flow.buy_balance_change_wow is None or flow.buy_balance_change_wow > filters.max_buy_balance_change_wow
    ):
        return False
    if filters.min_sell_balance_change_wow is not None and (
        flow.sell_balance_change_wow is None or flow.sell_balance_change_wow < filters.min_sell_balance_change_wow
    ):
        return False
    if filters.min_buy_balance_to_volume is not None and (
        flow.buy_balance_to_volume is None or flow.buy_balance_to_volume < filters.min_buy_balance_to_volume
    ):
        return False
    if filters.max_buy_balance_to_volume is not None and (
        flow.buy_balance_to_volume is None or flow.buy_balance_to_volume > filters.max_buy_balance_to_volume
    ):
        return False
    if filters.min_sell_balance_to_volume is not None and (
        flow.sell_balance_to_volume is None or flow.sell_balance_to_volume < filters.min_sell_balance_to_volume
    ):
        return False
    if filters.min_squeeze_potential_subscore is not None and (
        flow.squeeze_potential_subscore is None or flow.squeeze_potential_subscore < filters.min_squeeze_potential_subscore
    ):
        return False
    return True


def _screening_candidates_from_live(session: Session, request: ScreeningFilterRequest) -> list[ScreeningResult]:
    service = _build_security_service()
    results: list[ScreeningResult] = []
    for security in session.scalars(select(SecurityMaster).where(SecurityMaster.is_active.is_(True))).all():
        latest_score = service.latest_score(session, security.ticker_code)
        if latest_score is None or latest_score.total_score < request.min_total_score:
            continue
        latest_features = service.latest_feature(session, security.ticker_code)
        latest_flow = service.latest_flow(session, security.ticker_code)
        if not _matches_technical_filters(latest_features, request.technical):
            continue
        if not _matches_flow_filters(latest_flow, request.flow):
            continue
        results.append(
            _build_screening_result(
                security=security,
                latest_score=latest_score,
                latest_features=latest_features,
                latest_flow=latest_flow,
            )
        )

    results.sort(key=lambda item: item.latest_score.total_score if item.latest_score else Decimal("0"), reverse=True)
    return results[: request.limit]


@router.post("/sources/bootstrap", response_model=JobRunResponse)
def bootstrap_sources(db: Session | None = Depends(get_db)) -> JobRunResponse:
    session = _require_db(db)
    settings = get_monitoring_settings()
    service = _build_ingestion_service()
    service.bootstrap_source_registry(session, ir_allowlist_domains=settings.ir_allowlist_domains)
    session.commit()
    return JobRunResponse(
        job_name="bootstrap_sources",
        processed_count=5,
        detail="Registered allowed primary sources and IR allowlist domains.",
        executed_at=datetime.now(timezone.utc),
    )


@router.get("/securities/master/status", response_model=SecurityMasterStatusResponse)
def get_security_master_status(db: Session | None = Depends(get_db)) -> SecurityMasterStatusResponse:
    """Return local coverage for the latest complete J-Quants TSE snapshot."""

    session = _require_db(db)
    status_snapshot = _build_ingestion_service().get_security_master_status(session)
    return SecurityMasterStatusResponse(**_security_master_status_payload(status_snapshot))


@router.post("/securities/master/sync", response_model=SecurityMasterSyncResponse)
async def sync_security_master(
    target_date: date | None = Query(default=None),
    require_jquants: bool = Query(default=False),
    db: Session | None = Depends(get_db),
) -> SecurityMasterSyncResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        sync_result = await service.sync_security_master_from_jquants(session, as_of=target_date)
    except MissingCredentialsError as exc:
        if require_jquants:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{exc} Full listed security master sync requires JQUANTS_API_KEY.",
            ) from exc
        sync_result = None
        fallback_note = "J-Quants sync was skipped because JQUANTS_API_KEY is not configured."
    except ConnectorError as exc:
        if require_jquants:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        sync_result = None
        fallback_note = f"J-Quants listed master sync failed: {exc}"

    if sync_result is not None and require_jquants and (
        sync_result.fetched_count == 0 or (target_date is None and not sync_result.complete)
    ):
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="J-Quants listed master sync did not produce a complete, non-empty snapshot.",
        )

    if sync_result is None:
        bundled_count = len(local_security_master_catalog.load())
        inserted_count = local_security_master_catalog.sync_to_db(session)
        session.commit()
        status_snapshot = service.get_security_master_status(session)
        executed_at = datetime.now(timezone.utc)
        return SecurityMasterSyncResponse(
            source="local_seed",
            source_scope="bundled_search_seed_only",
            source_as_of=None,
            sync_id=None,
            synced_at=executed_at,
            complete=False,
            active_total=status_snapshot.active_total,
            jquants_active_count=status_snapshot.jquants_active_count,
            job_name="sync_security_master",
            processed_count=inserted_count,
            fetched_count=bundled_count,
            upserted_count=inserted_count,
            inserted_count=inserted_count,
            updated_count=0,
            reactivated_count=0,
            deactivated_count=0,
            detail=(
                f"Loaded {bundled_count} bundled search-seed records and inserted {inserted_count}; "
                f"this is not a complete TSE snapshot. {fallback_note}"
            ),
            executed_at=executed_at,
        )

    session.commit()
    snapshot_label = (
        f"historical ({target_date.isoformat()})" if target_date is not None else "current"
    )
    coverage_label = "complete" if sync_result.complete else "incomplete"
    detail = (
        f"Synchronized a {coverage_label} {snapshot_label} J-Quants TSE listed-issues snapshot: "
        f"fetched {sync_result.fetched_count}, inserted {sync_result.inserted_count}, "
        f"updated {sync_result.updated_count}, reactivated {sync_result.reactivated_count}, "
        f"deactivated {sync_result.deactivated_count}."
    )
    return SecurityMasterSyncResponse(
        **_security_master_status_payload(sync_result),
        job_name="sync_security_master",
        processed_count=sync_result.upserted_count,
        fetched_count=sync_result.fetched_count,
        upserted_count=sync_result.upserted_count,
        inserted_count=sync_result.inserted_count,
        updated_count=sync_result.updated_count,
        reactivated_count=sync_result.reactivated_count,
        deactivated_count=sync_result.deactivated_count,
        detail=detail,
        executed_at=sync_result.synced_at,
    )


@router.post("/securities", response_model=SecurityRead, status_code=status.HTTP_201_CREATED)
def upsert_security(payload: SecurityCreate, db: Session | None = Depends(get_db)) -> SecurityRead:
    session = _require_db(db)
    service = _build_ingestion_service()
    security = service.upsert_security(session, payload)
    session.commit()
    session.refresh(security)
    return SecurityRead.model_validate(security)


@router.post("/securities/{ticker_code}/prices", response_model=list[PriceBarRead], status_code=status.HTTP_201_CREATED)
def upsert_price_bars(
    ticker_code: str,
    payload: list[PriceBarCreate],
    db: Session | None = Depends(get_db),
) -> list[PriceBarRead]:
    session = _require_db(db)
    service = _build_ingestion_service()
    entities = service.upsert_price_bars(session, ticker_code, payload)
    session.commit()
    for entity in entities:
        session.refresh(entity)
    return [PriceBarRead.model_validate(entity) for entity in entities]


@router.post("/securities/{ticker_code}/prices/sync", response_model=JobRunResponse)
async def sync_price_bars(
    ticker_code: str,
    lookback_days: int = Query(default=120, ge=20, le=3650),
    db: Session | None = Depends(get_db),
) -> JobRunResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        processed_count = await service.sync_prices_from_jquants(session, ticker_code, lookback_days=lookback_days)
    except ConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return JobRunResponse(
        job_name="sync_prices_from_jquants",
        processed_count=processed_count,
        detail=f"Synchronized daily bars for {ticker_code}.",
        executed_at=datetime.now(timezone.utc),
    )


@router.post(
    "/securities/{ticker_code}/financials",
    response_model=FinancialSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def upsert_financial_snapshot(
    ticker_code: str,
    payload: FinancialSnapshotCreate,
    db: Session | None = Depends(get_db),
) -> FinancialSnapshotRead:
    session = _require_db(db)
    service = _build_ingestion_service()
    snapshot = service.upsert_financial_snapshot(session, ticker_code, payload)
    session.commit()
    session.refresh(snapshot)
    return FinancialSnapshotRead.model_validate(snapshot)


@router.post("/securities/{ticker_code}/flow", response_model=FlowSnapshotRead, status_code=status.HTTP_201_CREATED)
def upsert_flow_snapshot(
    ticker_code: str,
    payload: FlowSnapshotCreate,
    db: Session | None = Depends(get_db),
) -> FlowSnapshotRead:
    session = _require_db(db)
    service = _build_ingestion_service()
    snapshot = service.upsert_flow_snapshot(session, ticker_code, payload)
    session.commit()
    session.refresh(snapshot)
    return FlowSnapshotRead.model_validate(snapshot)


@router.post("/securities/{ticker_code}/flow/sync", response_model=JobRunResponse)
async def sync_flow_snapshot(
    ticker_code: str,
    target_date: date | None = Query(default=None),
    db: Session | None = Depends(get_db),
) -> JobRunResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        processed_count = await service.sync_flow_from_jquants(session, ticker_code, as_of=target_date)
    except ConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if processed_count:
        try:
            service.recalculate_score(session, ticker_code, target_date=target_date)
        except ValueError:
            pass
    session.commit()
    detail = f"Synchronized margin flow snapshot for {ticker_code}."
    if target_date is not None:
        detail = f"Synchronized margin flow snapshot for {ticker_code} as of {target_date.isoformat()}."
    return JobRunResponse(
        job_name="sync_flow_from_jquants",
        processed_count=processed_count,
        detail=detail,
        executed_at=datetime.now(timezone.utc),
    )


@router.post("/securities/{ticker_code}/technical/rebuild", response_model=TechnicalFeatureRead)
def rebuild_technical_feature(ticker_code: str, db: Session | None = Depends(get_db)) -> TechnicalFeatureRead:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        feature = service.rebuild_latest_technical_feature(session, ticker_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    session.refresh(feature)
    return TechnicalFeatureRead.model_validate(feature)


@router.post("/securities/{ticker_code}/score/recalculate", response_model=ScoreRecalculateResponse)
def recalculate_score(
    ticker_code: str,
    target_date: date | None = Query(default=None),
    db: Session | None = Depends(get_db),
) -> ScoreRecalculateResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    score, alerts = service.recalculate_score(session, ticker_code, target_date)
    session.commit()
    session.refresh(score)
    return ScoreRecalculateResponse(
        score=ScoreRead.model_validate(score),
        generated_alerts=_to_alert_reads(alerts),
    )


@router.post("/documents/import", response_model=DocumentImportResponse, status_code=status.HTTP_201_CREATED)
def import_document(payload: RawDocumentCreate, db: Session | None = Depends(get_db)) -> DocumentImportResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    raw_document, event, summary_text = service.import_raw_document(session, payload)
    session.commit()
    session.refresh(raw_document)
    session.refresh(event)
    return DocumentImportResponse(
        raw_document=raw_document,
        event=event,
        summary_text=summary_text,
    )


@router.post("/documents/import/ir", response_model=DocumentImportResponse, status_code=status.HTTP_201_CREATED)
def import_allowlisted_ir_document(
    payload: AllowlistedIrDocumentCreate,
    db: Session | None = Depends(get_db),
) -> DocumentImportResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        raw_document, event, summary_text = service.import_allowlisted_ir_document(
            session,
            payload,
            allowed_domains=get_monitoring_settings().ir_allowlist_domains,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    session.refresh(raw_document)
    session.refresh(event)
    return DocumentImportResponse(
        raw_document=raw_document,
        event=event,
        summary_text=summary_text,
    )


@router.post("/documents/sync/edinet", response_model=JobRunResponse)
async def sync_edinet_documents(
    target_date: date = Query(default_factory=date.today),
    db: Session | None = Depends(get_db),
) -> JobRunResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        processed_count = await service.sync_edinet_documents(session, target_date)
    except ConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return JobRunResponse(
        job_name="sync_edinet_documents",
        processed_count=processed_count,
        detail=f"Synchronized EDINET documents for {target_date.isoformat()}.",
        executed_at=datetime.now(timezone.utc),
    )


@router.post("/documents/sync/tdnet", response_model=JobRunResponse)
async def sync_tdnet_documents(
    target_date: date = Query(default_factory=date.today),
    ticker_code: str | None = Query(default=None, min_length=4, max_length=10),
    db: Session | None = Depends(get_db),
) -> JobRunResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        processed_count = await service.sync_tdnet_documents(session, target_date, ticker_code=ticker_code)
    except ConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    detail = f"Synchronized TDnet documents for {target_date.isoformat()}."
    if ticker_code:
        detail = f"Synchronized TDnet documents for {ticker_code} on {target_date.isoformat()}."
    return JobRunResponse(
        job_name="sync_tdnet_documents",
        processed_count=processed_count,
        detail=detail,
        executed_at=datetime.now(timezone.utc),
    )


@router.post("/documents/sync/youtube", response_model=JobRunResponse)
async def sync_youtube_documents(
    payload: YouTubeSyncRequest,
    db: Session | None = Depends(get_db),
) -> JobRunResponse:
    session = _require_db(db)
    service = _build_ingestion_service()
    try:
        processed_count = await service.sync_youtube_documents(
            session,
            ticker_code=payload.ticker_code,
            channel_ids=payload.channel_ids,
            published_after=payload.published_after,
            max_results=payload.max_results,
        )
    except ConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return JobRunResponse(
        job_name="sync_youtube_documents",
        processed_count=processed_count,
        detail=f"Synchronized YouTube observations for {payload.ticker_code}.",
        executed_at=datetime.now(timezone.utc),
    )


@router.post("/documents/sync/youtube/monitored", response_model=JobRunResponse)
async def sync_monitored_youtube_documents(
    ticker_code: str = Query(min_length=4, max_length=10),
    lookback_days: int = Query(default=30, ge=1, le=365),
    db: Session | None = Depends(get_db),
) -> JobRunResponse:
    session = _require_db(db)
    settings = get_monitoring_settings()
    channel_ids = settings.youtube_monitored_channels.get(ticker_code) or []
    if not channel_ids:
        return JobRunResponse(
            job_name="sync_youtube_documents",
            processed_count=0,
            detail=f"No monitored YouTube channels configured for {ticker_code}.",
            executed_at=datetime.now(timezone.utc),
        )

    service = _build_ingestion_service()
    published_after = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    try:
        processed_count = await service.sync_youtube_documents(
            session,
            ticker_code=ticker_code,
            channel_ids=channel_ids,
            published_after=published_after,
            max_results=10,
        )
    except ConnectorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return JobRunResponse(
        job_name="sync_youtube_documents",
        processed_count=processed_count,
        detail=f"Synchronized monitored YouTube observations for {ticker_code}.",
        executed_at=datetime.now(timezone.utc),
    )


@router.get("/securities/{ticker_code}", response_model=SecurityDetailResponse)
def get_security_detail(ticker_code: str, db: Session | None = Depends(get_db)) -> SecurityDetailResponse:
    if get_settings().app_use_mock:
        detail = mock_monitoring_service.get_security_detail(ticker_code)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security was not found.")
        return detail
    session = _require_db(db)
    return _build_security_detail(session, ticker_code)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    recent_event_limit: int = Query(default=10, ge=1, le=50),
    db: Session | None = Depends(get_db),
) -> DashboardResponse:
    if get_settings().app_use_mock:
        return mock_monitoring_service.get_dashboard()

    session = _require_db(db)
    settings = get_monitoring_settings()
    container = get_monitoring_container()
    watchlist_service = _build_watchlist_service()
    security_service = _build_security_service()

    active_watchlist = watchlist_service.list(session)
    rows: list[DashboardRow] = []
    aggregated_alerts: list[AlertRead] = []
    watchlist_tickers = [item.ticker_code for item in active_watchlist]

    for item in active_watchlist:
        latest_score = watchlist_service.latest_score(session, item.ticker_code)
        latest_event = watchlist_service.latest_event(session, item.ticker_code)
        feature = security_service.latest_feature(session, item.ticker_code)
        recent_events = security_service.recent_events(session, item.ticker_code, limit=5)
        alerts = []
        if latest_score is not None:
            previous_score = _latest_previous_score(session, item.ticker_code, latest_score.id)
            alerts = container.alert_service.generate_alerts(
                ticker_code=item.ticker_code,
                current_score=latest_score,
                previous_score=previous_score,
                technical_feature=feature,
                recent_events=recent_events,
            )
        alert_reads = _to_alert_reads(alerts)
        aggregated_alerts.extend(alert_reads)
        if latest_score and latest_score.total_score >= Decimal(str(settings.high_priority_threshold)):
            rows.append(
                DashboardRow(
                    security=SecurityRead.model_validate(item.security),
                    latest_score=ScoreRead.model_validate(latest_score),
                    alerts=alert_reads,
                    latest_event=EventRead.model_validate(latest_event) if latest_event else None,
                )
            )

    event_statement = select(EventFact).order_by(EventFact.event_time.desc()).limit(recent_event_limit)
    if watchlist_tickers:
        event_statement = (
            select(EventFact)
            .where(EventFact.ticker_code.in_(watchlist_tickers))
            .order_by(EventFact.event_time.desc())
            .limit(recent_event_limit)
        )
    recent_events = [EventRead.model_validate(event) for event in session.scalars(event_statement).all()]

    rows.sort(key=lambda row: row.latest_score.total_score if row.latest_score else Decimal("0"), reverse=True)
    return DashboardResponse(
        target_date=date.today(),
        disclaimer=DISCLAIMER_TEXT,
        high_priority=rows,
        recent_events=recent_events,
        alerts=aggregated_alerts,
    )


@router.get("/screening", response_model=list[ScreeningResult])
def get_screening(
    min_total_score: Decimal = Query(default=Decimal("60"), ge=Decimal("0"), le=Decimal("100")),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session | None = Depends(get_db),
) -> list[ScreeningResult]:
    request = ScreeningFilterRequest(min_total_score=min_total_score, limit=limit)
    if get_settings().app_use_mock:
        return mock_monitoring_service.get_screening_query(request)

    session = _require_db(db)
    return _screening_candidates_from_live(session, request)


@router.post("/screening/query", response_model=list[ScreeningResult])
def query_screening(
    payload: ScreeningFilterRequest,
    db: Session | None = Depends(get_db),
) -> list[ScreeningResult]:
    if get_settings().app_use_mock:
        return mock_monitoring_service.get_screening_query(payload)

    session = _require_db(db)
    return _screening_candidates_from_live(session, payload)
