"""Build a UI-focused dashboard view model from existing monitoring APIs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.ui_dashboard import (
    AlertCard,
    DashboardExperienceResponse,
    DashboardMetric,
    EventFeedItem,
    FactorSplit,
    HistoryItem,
    HypothesisCard,
    LabeledScore,
    MarketOverview,
    MarketSectorPulse,
    MaterialHistoryItem,
    PriorityItem,
    ScreeningOverviewItem,
    SecurityDetailPanel,
    SourceLink,
    StatusCount,
    WarningItem,
    WatchlistOverviewItem,
)
from app.schemas.watchlist import WatchlistCollectionRead, WatchlistItem
from app.services.mock_monitoring import mock_monitoring_service
from app.services.mock_watchlist import mock_watchlist_service
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from app.services.portfolio import portfolio_service
from app.services.security_profile import security_profile_service
from app.services.watchlist import WatchlistService
from kabuhandan_hojo.connectors.base import ConnectorError
from kabuhandan_hojo.models.entities import EventFact, PriceDaily, ScoreDaily, SecurityMaster
from kabuhandan_hojo.schemas.alerts import AlertRead
from kabuhandan_hojo.schemas.dashboard import DashboardResponse, DashboardRow, ScreeningResult
from kabuhandan_hojo.schemas.events import EventRead
from kabuhandan_hojo.schemas.scores import ScoreRead
from kabuhandan_hojo.schemas.screening import ScreeningFilterRequest
from kabuhandan_hojo.schemas.securities import (
    FinancialSnapshotRead,
    FlowSnapshotRead,
    PriceBarRead,
    SecurityDetailResponse,
    SecurityRead,
    TechnicalFeatureRead,
)
from kabuhandan_hojo.services.insights import build_flow_context, build_technical_context, screening_reasons
from kabuhandan_hojo.services.ingestion import IngestionService
from kabuhandan_hojo.services.securities import SecurityService


ZERO = Decimal("0")
HUNDRED = Decimal("100")
TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")
JQUANTS_AUTO_SYNC_LOOKBACK_DAYS = 180
MARKET_PROXY_MANUAL_SYNC_LOOKBACK_DAYS = 60
TECHNICAL_REBUILD_MIN_BARS = 20
MARKET_PROXY_TICKERS = (
    ("topix", "1306", "TOPIX"),
    ("nikkei225", "1321", "Nikkei225"),
)
MARKET_PROXY_MIN_BARS = 25
MARKET_PROXY_STALE_AFTER_DAYS = 5

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SecurityBundle:
    security: SecurityRead
    detail: SecurityDetailResponse
    alerts: list[AlertRead]
    watchlist_item: WatchlistItem | None


@dataclass(slots=True)
class MarketProxySnapshot:
    key: str
    ticker_code: str
    label: str
    latest_date: date | None
    change_1d_pct: Decimal | None
    change_5d_pct: Decimal | None
    change_20d_pct: Decimal | None
    above_sma_20: bool | None


@dataclass(slots=True)
class LiveMarketSignal:
    score: int
    breadth: str
    breadth_ratio: str
    separation_hint: str
    comment: str
    caution_tags: list[str]
    average_5d_change_pct: Decimal | None
    average_20d_change_pct: Decimal | None
    latest_market_date: date | None
    is_stale: bool


@dataclass(slots=True)
class SectorBreadthSnapshot:
    name: str
    sample_count: int
    advancers: int
    decliners: int
    average_change_5d_pct: Decimal | None


class DashboardExperienceService:
    """Compose a judgment-support view model without changing primary routes."""

    def __init__(self) -> None:
        self.security_service = SecurityService()
        self.watchlist_service = WatchlistService()
        self.portfolio_service = portfolio_service

    def build(
        self,
        *,
        session: Session | None,
        selected_ticker_code: str | None = None,
        selected_watchlist_id: int | None = None,
        screening_limit: int = 6,
        event_limit: int = 8,
    ) -> DashboardExperienceResponse:
        if get_settings().app_use_mock:
            return self._build_mock(
                selected_ticker_code=selected_ticker_code,
                selected_watchlist_id=selected_watchlist_id,
                screening_limit=screening_limit,
                event_limit=event_limit,
            )
        if session is None:
            raise RuntimeError("Database session is required when mock mode is disabled.")
        return self._build_live(
            session=session,
            selected_ticker_code=selected_ticker_code,
            selected_watchlist_id=selected_watchlist_id,
            screening_limit=screening_limit,
            event_limit=event_limit,
        )

    def _build_mock(
        self,
        *,
        selected_ticker_code: str | None,
        selected_watchlist_id: int | None,
        screening_limit: int,
        event_limit: int,
    ) -> DashboardExperienceResponse:
        dashboard = mock_monitoring_service.get_dashboard()
        watchlist_collections = mock_watchlist_service.list_collections()
        active_watchlist_id = self._resolve_watchlist_collection_id(
            watchlist_collections,
            selected_watchlist_id,
        )
        watchlist_items = (
            mock_watchlist_service.list_items(collection_id=active_watchlist_id)
            if active_watchlist_id is not None
            else []
        )
        screening = mock_monitoring_service.get_screening_query(
            ScreeningFilterRequest(min_total_score=Decimal("60"), limit=screening_limit)
        )
        bundles = [
            self._bundle_from_mock(
                ticker_code=item.ticker_code,
                watchlist_item=item,
            )
            for item in watchlist_items
        ]
        bundles = [bundle for bundle in bundles if bundle is not None]
        sector_snapshots = self._mock_sector_breadth_snapshots(bundles)
        bundle_map = {bundle.security.ticker_code: bundle for bundle in bundles}
        selected_ticker = self._resolve_selected_ticker(selected_ticker_code, bundle_map, dashboard.high_priority, watchlist_items)
        detail_bundle = bundle_map.get(selected_ticker) if selected_ticker else None
        portfolio_items = self._mock_portfolio_items()
        return self._assemble_response(
            mode="mock",
            dashboard=dashboard,
            screening=screening,
            portfolio_items=portfolio_items,
            watchlist_collections=watchlist_collections,
            selected_watchlist_id=active_watchlist_id,
            watchlist_items=watchlist_items,
            bundles=bundles,
            sector_snapshots=sector_snapshots,
            selected_ticker=selected_ticker,
            detail_bundle=detail_bundle,
            event_limit=event_limit,
            market_signal=None,
        )

    def _build_live(
        self,
        *,
        session: Session,
        selected_ticker_code: str | None,
        selected_watchlist_id: int | None,
        screening_limit: int,
        event_limit: int,
    ) -> DashboardExperienceResponse:
        watchlist_collections = self.watchlist_service.list_collections(session)
        active_watchlist_id = self._resolve_watchlist_collection_id(
            watchlist_collections,
            selected_watchlist_id,
        )
        watchlist_items = (
            self.watchlist_service.list_items(session, collection_id=active_watchlist_id)
            if active_watchlist_id is not None
            else []
        )
        bundles: list[SecurityBundle] = []
        for item in watchlist_items:
            bundle = self._bundle_from_live(session=session, ticker_code=item.ticker_code, watchlist_item=item)
            if bundle is not None:
                bundles.append(bundle)
        sector_snapshots = self._load_sector_breadth_snapshots(session=session, bundles=bundles)

        market_signal = self._build_live_market_signal(session=session)
        dashboard = self._build_live_dashboard(
            session,
            recent_event_limit=event_limit,
            watchlist_items=watchlist_items,
        )
        screening = self._build_live_screening(session, limit=screening_limit)
        if not screening and bundles:
            screening = [self._screening_from_bundle(bundle) for bundle in bundles[:screening_limit]]

        bundle_map = {bundle.security.ticker_code: bundle for bundle in bundles}
        selected_ticker = self._resolve_selected_ticker(selected_ticker_code, bundle_map, dashboard.high_priority, watchlist_items)
        if selected_ticker is None and selected_ticker_code and self.security_service.get(session, selected_ticker_code) is not None:
            selected_ticker = selected_ticker_code
        detail_bundle = bundle_map.get(selected_ticker) if selected_ticker else None
        if detail_bundle is None and selected_ticker:
            detail_bundle = self._bundle_from_live(session=session, ticker_code=selected_ticker, watchlist_item=None)
        portfolio_items = self.portfolio_service.list_items(session)

        return self._assemble_response(
            mode="live",
            dashboard=dashboard,
            screening=screening,
            portfolio_items=portfolio_items,
            watchlist_collections=watchlist_collections,
            selected_watchlist_id=active_watchlist_id,
            watchlist_items=watchlist_items,
            bundles=bundles,
            sector_snapshots=sector_snapshots,
            selected_ticker=selected_ticker,
            detail_bundle=detail_bundle,
            event_limit=event_limit,
            market_signal=market_signal,
        )

    def _assemble_response(
        self,
        *,
        mode: str,
        dashboard: DashboardResponse,
        screening: list[ScreeningResult],
        portfolio_items: list[object],
        watchlist_collections: list[WatchlistCollectionRead],
        selected_watchlist_id: int | None,
        watchlist_items: list[WatchlistItem],
        bundles: list[SecurityBundle],
        sector_snapshots: dict[str, SectorBreadthSnapshot],
        selected_ticker: str | None,
        detail_bundle: SecurityBundle | None,
        event_limit: int,
        market_signal: LiveMarketSignal | None,
    ) -> DashboardExperienceResponse:
        priority_items = self._priority_items(bundles, market_signal=market_signal, sector_snapshots=sector_snapshots)
        important_alerts = self._important_alerts(bundles)
        event_feed = self._event_feed(bundles, dashboard.recent_events, limit=event_limit)
        selected_detail = (
            self._detail_panel(
                detail_bundle,
                bundles=bundles,
                market_signal=market_signal,
                sector_snapshots=sector_snapshots,
            )
            if detail_bundle
            else None
        )
        status_counts = self._status_counts(priority_items)
        market_overview = self._market_overview(
            priority_items,
            bundles=bundles,
            market_signal=market_signal,
            sector_snapshots=sector_snapshots,
        )
        metrics = self._metrics(
            mode=mode,
            watchlist_count=len(watchlist_items),
            priority_items=priority_items,
            important_alerts=important_alerts,
            screening_count=len(screening),
            market_overview=market_overview,
        )
        screening_items = [self._screening_item(item) for item in screening]
        watchlist_overview = [self._watchlist_overview(bundle, market_signal=market_signal) for bundle in bundles]

        return DashboardExperienceResponse(
            generated_at=self._tokyo_now(),
            target_date=dashboard.target_date,
            mode=mode,
            disclaimer=dashboard.disclaimer,
            market_overview=market_overview,
            metrics=metrics,
            status_counts=status_counts,
            priority_items=priority_items,
            important_alerts=important_alerts,
            event_feed=event_feed,
            portfolio_items=portfolio_items,
            watchlist_collections=watchlist_collections,
            selected_watchlist_id=selected_watchlist_id,
            watchlist_items=watchlist_overview,
            screening_items=screening_items,
            selected_ticker_code=selected_ticker,
            detail=selected_detail,
        )

    def _mock_portfolio_items(self) -> list[object]:
        items = []
        for ticker_code, quantity, average_cost in (
            ("7203", Decimal("100"), Decimal("3200")),
            ("7974", Decimal("50"), Decimal("7800")),
        ):
            detail = mock_monitoring_service.get_security_detail(ticker_code)
            if detail is None:
                continue
            last_price = detail.latest_prices[-1].close_price if detail.latest_prices else None
            market_value = (last_price * quantity).quantize(Decimal("0.01")) if last_price is not None else None
            cost_basis = (average_cost * quantity).quantize(Decimal("0.01"))
            pnl = (market_value - cost_basis).quantize(Decimal("0.01")) if market_value is not None else None
            pnl_pct = ((pnl / cost_basis) * Decimal("100")).quantize(Decimal("0.01")) if pnl is not None else None
            items.append(
                {
                    "id": len(items) + 1,
                    "ticker_code": ticker_code,
                    "name": detail.security.name,
                    "market": detail.security.market,
                    "quantity": quantity,
                    "average_cost": average_cost,
                    "last_price": last_price,
                    "market_value": market_value,
                    "cost_basis": cost_basis,
                    "unrealized_pnl": pnl,
                    "unrealized_return_pct": pnl_pct,
                    "note": "mock holding",
                    "sort_order": len(items) + 1,
                    "updated_at": detail.updated_at or self._tokyo_now(),
                }
            )
        return items

    def _mock_sector_breadth_snapshots(self, bundles: list[SecurityBundle]) -> dict[str, SectorBreadthSnapshot]:
        snapshots: dict[str, SectorBreadthSnapshot] = {}
        grouped: dict[str, list[Decimal]] = {}
        for bundle in bundles:
            sector_name = bundle.security.industry_33 or bundle.security.industry_17
            if not sector_name:
                continue
            change_5d = self._price_return_pct(bundle.detail.latest_prices, 5)
            if change_5d is None:
                continue
            grouped.setdefault(sector_name, []).append(change_5d)

        for sector_name, changes in grouped.items():
            advancers = sum(1 for change in changes if change > ZERO)
            decliners = sum(1 for change in changes if change < ZERO)
            snapshots[sector_name] = SectorBreadthSnapshot(
                name=sector_name,
                sample_count=len(changes),
                advancers=advancers,
                decliners=decliners,
                average_change_5d_pct=self._mean_decimal(changes),
            )
        return snapshots

    def _load_sector_breadth_snapshots(
        self,
        *,
        session: Session,
        bundles: list[SecurityBundle],
    ) -> dict[str, SectorBreadthSnapshot]:
        sector_names = {
            bundle.security.industry_33 or bundle.security.industry_17
            for bundle in bundles
            if (bundle.security.industry_33 or bundle.security.industry_17)
        }
        if not sector_names:
            return {}

        cutoff_date = self._tokyo_today() - timedelta(days=40)
        rows = session.execute(
            select(SecurityMaster.ticker_code, SecurityMaster.industry_33, SecurityMaster.industry_17, PriceDaily)
            .join(PriceDaily, PriceDaily.ticker_code == SecurityMaster.ticker_code)
            .where(
                SecurityMaster.is_active.is_(True),
                or_(
                    SecurityMaster.industry_33.in_(sector_names),
                    SecurityMaster.industry_17.in_(sector_names),
                ),
                PriceDaily.target_date >= cutoff_date,
            )
            .order_by(SecurityMaster.ticker_code.asc(), PriceDaily.target_date.asc())
        ).all()

        sector_by_ticker: dict[str, str] = {}
        prices_by_ticker: dict[str, list[PriceDaily]] = {}
        for ticker_code, industry_33, industry_17, price in rows:
            sector_name = industry_33 or industry_17
            if not sector_name:
                continue
            sector_by_ticker[ticker_code] = sector_name
            prices_by_ticker.setdefault(ticker_code, []).append(price)

        aggregated: dict[str, list[Decimal]] = {}
        for ticker_code, prices in prices_by_ticker.items():
            change_5d = self._price_return_pct(prices, 5)
            if change_5d is None:
                continue
            sector_name = sector_by_ticker.get(ticker_code)
            if sector_name is None:
                continue
            aggregated.setdefault(sector_name, []).append(change_5d)

        snapshots: dict[str, SectorBreadthSnapshot] = {}
        for sector_name, changes in aggregated.items():
            advancers = sum(1 for change in changes if change > ZERO)
            decliners = sum(1 for change in changes if change < ZERO)
            snapshots[sector_name] = SectorBreadthSnapshot(
                name=sector_name,
                sample_count=len(changes),
                advancers=advancers,
                decliners=decliners,
                average_change_5d_pct=self._mean_decimal(changes),
            )
        return snapshots

    def _build_live_dashboard(
        self,
        session: Session,
        recent_event_limit: int,
        watchlist_items: list[WatchlistItem],
    ) -> DashboardResponse:
        settings = get_monitoring_settings()
        container = get_monitoring_container()
        rows: list[DashboardRow] = []
        aggregated_alerts: list[AlertRead] = []
        watchlist_tickers = [item.ticker_code for item in watchlist_items]

        for item in watchlist_items:
            security = self.security_service.get(session, item.ticker_code)
            if security is None:
                continue
            latest_score_entity = self.security_service.latest_score(session, item.ticker_code)
            latest_event_entity = self.security_service.recent_events(session, item.ticker_code, limit=1)
            latest_event = latest_event_entity[0] if latest_event_entity else None
            feature = self.security_service.latest_feature(session, item.ticker_code)
            recent_events = self.security_service.recent_events(session, item.ticker_code, limit=5)
            alerts: list[AlertRead] = []
            if latest_score_entity is not None:
                previous_score = self._latest_previous_score(session, item.ticker_code, latest_score_entity.id)
                alerts = self._to_alert_reads(
                    container.alert_service.generate_alerts(
                        ticker_code=item.ticker_code,
                        current_score=latest_score_entity,
                        previous_score=previous_score,
                        technical_feature=feature,
                        recent_events=recent_events,
                    )
                )
            aggregated_alerts.extend(alerts)
            if latest_score_entity is not None and latest_score_entity.total_score >= Decimal(str(settings.high_priority_threshold)):
                rows.append(
                    DashboardRow(
                        security=SecurityRead.model_validate(security),
                        latest_score=ScoreRead.model_validate(latest_score_entity),
                        alerts=alerts,
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
        rows.sort(key=lambda row: self._score_value(row.latest_score), reverse=True)

        disclaimer = (
            "この画面は日本株の判断補助を目的とした整理画面です。"
            "売買の断定ではなく、地合い要因と個別要因を分けて確認するために使います。"
        )
        return DashboardResponse(
            target_date=self._tokyo_today(),
            disclaimer=disclaimer,
            high_priority=rows,
            recent_events=recent_events,
            alerts=aggregated_alerts,
        )

    def _build_live_screening(self, session: Session, limit: int) -> list[ScreeningResult]:
        results: list[ScreeningResult] = []
        for security in session.scalars(select(SecurityMaster).where(SecurityMaster.is_active.is_(True))).all():
            latest_score = self.security_service.latest_score(session, security.ticker_code)
            if latest_score is None or latest_score.total_score < Decimal("60"):
                continue
            latest_features = self.security_service.latest_feature(session, security.ticker_code)
            latest_flow = self.security_service.latest_flow(session, security.ticker_code)
            results.append(
                ScreeningResult(
                    security=SecurityRead.model_validate(security),
                    latest_score=ScoreRead.model_validate(latest_score),
                    latest_features=TechnicalFeatureRead.model_validate(latest_features) if latest_features else None,
                    latest_flow=FlowSnapshotRead.model_validate(latest_flow) if latest_flow else None,
                    matched_reasons=screening_reasons(
                        TechnicalFeatureRead.model_validate(latest_features) if latest_features else None,
                        FlowSnapshotRead.model_validate(latest_flow) if latest_flow else None,
                        ScoreRead.model_validate(latest_score),
                    ),
                )
            )

        results.sort(key=lambda item: self._score_value(item.latest_score), reverse=True)
        return results[:limit]

    def _bundle_from_live(
        self,
        *,
        session: Session,
        ticker_code: str,
        watchlist_item: WatchlistItem | None,
    ) -> SecurityBundle | None:
        security_entity = self.security_service.get(session, ticker_code)
        if security_entity is None:
            return None

        detail = self._build_live_detail(session, ticker_code)
        if detail is None:
            return None
        security = self._merge_security_profile(detail.security, ticker_code, session=session)
        detail = detail.model_copy(update={"security": security})
        alerts = self._live_alerts(session, ticker_code)

        detail = self._merge_with_watchlist(detail, watchlist_item)
        return SecurityBundle(
            security=security,
            detail=detail,
            alerts=alerts,
            watchlist_item=watchlist_item,
        )

    def _bundle_from_mock(self, *, ticker_code: str, watchlist_item: WatchlistItem | None) -> SecurityBundle | None:
        detail = mock_monitoring_service.get_security_detail(ticker_code)
        if detail is None:
            return None
        security = self._merge_security_profile(detail.security, ticker_code, session=None)
        detail = detail.model_copy(update={"security": security})
        detail = self._merge_with_watchlist(detail, watchlist_item)
        return SecurityBundle(
            security=security,
            detail=detail,
            alerts=mock_monitoring_service.get_alerts_for_ticker(ticker_code),
            watchlist_item=watchlist_item,
        )

    def _build_live_detail(self, session: Session, ticker_code: str) -> SecurityDetailResponse | None:
        security = self.security_service.get(session, ticker_code)
        if security is None:
            return None

        latest_features = self.security_service.latest_feature(session, ticker_code)
        latest_score = self.security_service.latest_score(session, ticker_code)
        latest_prices = self.security_service.latest_prices(session, ticker_code)
        latest_prices, latest_features, latest_score = self._ensure_live_market_snapshot(
            session=session,
            ticker_code=ticker_code,
            latest_prices=latest_prices,
            latest_features=latest_features,
            latest_score=latest_score,
        )
        self._ensure_live_tdnet_documents(session=session, ticker_code=ticker_code)
        self._ensure_live_youtube_documents(session=session, ticker_code=ticker_code)
        recent_events = self.security_service.recent_events(session, ticker_code)
        latest_financials = self.security_service.latest_financial(session, ticker_code)
        latest_flow = self.security_service.latest_flow(session, ticker_code)
        latest_flow = self._ensure_live_flow_snapshot(session=session, ticker_code=ticker_code, latest_flow=latest_flow)

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

    def _ensure_live_market_snapshot(
        self,
        *,
        session: Session,
        ticker_code: str,
        latest_prices: list[object],
        latest_features: object | None,
        latest_score: object | None,
    ) -> tuple[list[object], object | None, object | None]:
        prices = latest_prices
        features = latest_features
        score = latest_score

        synced_price_count = 0
        if not prices:
            synced_price_count = self._sync_live_prices_from_jquants(session=session, ticker_code=ticker_code)
            if synced_price_count:
                prices = self.security_service.latest_prices(session, ticker_code)

        needs_feature_rebuild = len(prices) >= TECHNICAL_REBUILD_MIN_BARS and (features is None or synced_price_count > 0)
        needs_score_rebuild = bool((score is None and (features is not None or needs_feature_rebuild)) or needs_feature_rebuild)

        if not needs_feature_rebuild and not needs_score_rebuild:
            return prices, features, score

        container = get_monitoring_container()
        ingestion_service = IngestionService(container)
        try:
            if needs_feature_rebuild:
                ingestion_service.rebuild_latest_technical_feature(session, ticker_code)
            if needs_score_rebuild:
                ingestion_service.recalculate_score(session, ticker_code)
            session.commit()
        except ValueError as exc:
            session.rollback()
            logger.info("Skipping live technical rebuild for %s: %s", ticker_code, exc)
        except Exception:
            session.rollback()
            logger.exception("Failed to refresh live technical snapshot for %s", ticker_code)

        return (
            self.security_service.latest_prices(session, ticker_code),
            self.security_service.latest_feature(session, ticker_code),
            self.security_service.latest_score(session, ticker_code),
        )

    def _sync_live_prices_from_jquants(self, *, session: Session, ticker_code: str) -> int:
        settings = get_monitoring_settings()
        if not settings.jquants_api_key:
            return 0

        container = get_monitoring_container()
        ingestion_service = IngestionService(container)
        try:
            processed_count = asyncio.run(
                ingestion_service.sync_prices_from_jquants(
                    session,
                    ticker_code,
                    lookback_days=JQUANTS_AUTO_SYNC_LOOKBACK_DAYS,
                )
            )
            if processed_count:
                session.commit()
            return processed_count
        except ConnectorError as exc:
            session.rollback()
            logger.info("Skipping J-Quants auto-sync for %s: %s", ticker_code, exc)
            return 0
        except Exception:
            session.rollback()
            logger.exception("Failed to auto-sync prices from J-Quants for %s", ticker_code)
            return 0

    def _ensure_live_flow_snapshot(
        self,
        *,
        session: Session,
        ticker_code: str,
        latest_flow: object | None,
    ) -> object | None:
        if latest_flow is not None:
            return latest_flow
        if not get_monitoring_settings().jquants_api_key:
            return None
        synced_count = self._sync_live_flow_from_jquants(session=session, ticker_code=ticker_code)
        if not synced_count:
            return None
        return self.security_service.latest_flow(session, ticker_code)

    def _sync_live_flow_from_jquants(self, *, session: Session, ticker_code: str) -> int:
        settings = get_monitoring_settings()
        if not settings.jquants_api_key:
            return 0

        container = get_monitoring_container()
        ingestion_service = IngestionService(container)
        try:
            processed_count = asyncio.run(
                ingestion_service.sync_flow_from_jquants(
                    session,
                    ticker_code,
                    as_of=self._tokyo_today(),
                )
            )
            if processed_count:
                try:
                    ingestion_service.recalculate_score(session, ticker_code)
                except ValueError:
                    logger.info("Skipping score recalc after flow sync for %s", ticker_code)
                session.commit()
            return processed_count
        except ConnectorError as exc:
            session.rollback()
            logger.info("Skipping J-Quants flow sync for %s: %s", ticker_code, exc)
            return 0
        except Exception:
            session.rollback()
            logger.exception("Failed to auto-sync flow snapshot from J-Quants for %s", ticker_code)
            return 0

    def _ensure_live_tdnet_documents(self, *, session: Session, ticker_code: str) -> None:
        settings = get_monitoring_settings()
        if not getattr(settings, "tdnet_api_key", None):
            return

        today = self._tokyo_today()
        day_start = datetime.combine(today, datetime.min.time(), tzinfo=TOKYO_TIMEZONE).astimezone(timezone.utc)
        existing = session.scalar(
            select(EventFact)
            .where(
                EventFact.ticker_code == ticker_code,
                EventFact.source_name == "tdnet_api",
                EventFact.event_time >= day_start,
            )
            .limit(1)
        )
        if existing is not None:
            return

        container = get_monitoring_container()
        ingestion_service = IngestionService(container)
        try:
            processed_count = asyncio.run(
                ingestion_service.sync_tdnet_documents(
                    session,
                    today,
                    ticker_code=ticker_code,
                )
            )
            if processed_count:
                session.commit()
        except ConnectorError as exc:
            session.rollback()
            logger.info("Skipping TDnet sync for %s: %s", ticker_code, exc)
        except Exception:
            session.rollback()
            logger.exception("Failed to auto-sync TDnet documents for %s", ticker_code)

    def _ensure_live_youtube_documents(self, *, session: Session, ticker_code: str) -> None:
        settings = get_monitoring_settings()
        if not getattr(settings, "youtube_api_key", None):
            return
        channel_ids = settings.youtube_monitored_channels.get(ticker_code) or []
        if not channel_ids:
            return

        recent_threshold = self._tokyo_now().astimezone(timezone.utc) - timedelta(days=30)
        existing = session.scalar(
            select(EventFact.event_id)
            .where(
                EventFact.ticker_code == ticker_code,
                EventFact.source_name == "youtube_data_api",
                EventFact.event_time >= recent_threshold,
            )
            .limit(1)
        )
        if existing is not None:
            return

        container = get_monitoring_container()
        ingestion_service = IngestionService(container)
        try:
            processed_count = asyncio.run(
                ingestion_service.sync_youtube_documents(
                    session,
                    ticker_code=ticker_code,
                    channel_ids=channel_ids,
                    published_after=recent_threshold,
                    max_results=5,
                )
            )
            if processed_count:
                session.commit()
        except ConnectorError as exc:
            session.rollback()
            logger.info("Skipping YouTube sync for %s: %s", ticker_code, exc)
        except Exception:
            session.rollback()
            logger.exception("Failed to auto-sync YouTube observations for %s", ticker_code)

    def _build_live_market_signal(self, *, session: Session) -> LiveMarketSignal | None:
        proxy_snapshots = self._load_market_proxy_snapshots(session=session)
        if not proxy_snapshots:
            return None

        proxy_scores: list[int] = []
        positive_signals = 0
        total_signals = 0
        average_5d_change_pct = self._mean_decimal(
            [snapshot.change_5d_pct for snapshot in proxy_snapshots if snapshot.change_5d_pct is not None]
        )
        average_20d_change_pct = self._mean_decimal(
            [snapshot.change_20d_pct for snapshot in proxy_snapshots if snapshot.change_20d_pct is not None]
        )
        latest_market_date = max(
            (snapshot.latest_date for snapshot in proxy_snapshots if snapshot.latest_date is not None),
            default=None,
        )
        is_stale = (
            latest_market_date is None
            or (self._tokyo_today() - latest_market_date).days > MARKET_PROXY_STALE_AFTER_DAYS
        )

        for snapshot in proxy_snapshots:
            component = Decimal("50")
            for change_value, weight in (
                (snapshot.change_1d_pct, Decimal("10")),
                (snapshot.change_5d_pct, Decimal("18")),
                (snapshot.change_20d_pct, Decimal("22")),
            ):
                if change_value is None:
                    continue
                total_signals += 1
                if change_value >= ZERO:
                    positive_signals += 1
                    component += weight
                else:
                    component -= weight
            if snapshot.above_sma_20 is not None:
                total_signals += 1
                if snapshot.above_sma_20:
                    positive_signals += 1
                    component += Decimal("10")
                else:
                    component -= Decimal("10")
            proxy_scores.append(int(round(float(self._clamp(component)))))

        if not proxy_scores:
            return None

        breadth_ratio_value = (positive_signals / total_signals) if total_signals else 0.5
        breadth = "全面高寄り" if breadth_ratio_value >= 0.7 else ("全面安寄り" if breadth_ratio_value <= 0.3 else "まちまち")
        breadth_ratio = f"{positive_signals} / {total_signals}" if total_signals else "0 / 0"
        score = round(sum(proxy_scores) / len(proxy_scores))

        date_note = latest_market_date.isoformat() if latest_market_date else "未取得"
        if score >= 68:
            separation_hint = "市場proxyが上向きです。個別銘柄の5日騰落が市場に負けていないかを先に見ます。"
            comment = (
                "J-Quants公式価格のTOPIX(1306) / Nikkei225(1321) proxyでは追い風寄りです。"
                f" 最新反映日は {date_note} です。"
            )
        elif score <= 35:
            separation_hint = "市場proxyが弱いので、まず地合い要因を切り分けてから個別材料を確認します。"
            comment = (
                "J-Quants公式価格のTOPIX(1306) / Nikkei225(1321) proxyでは逆風寄りです。"
                f" 最新反映日は {date_note} です。"
            )
        else:
            separation_hint = "市場proxyは中立圏です。市場より強い銘柄だけを個別材料とセットで見ます。"
            comment = (
                "J-Quants公式価格のTOPIX(1306) / Nikkei225(1321) proxyでは方向感が割れています。"
                f" 最新反映日は {date_note} です。"
            )

        caution_tags: list[str] = []
        if len(proxy_snapshots) < len(MARKET_PROXY_TICKERS):
            caution_tags.append("市場proxyは一部のみ")
        if is_stale:
            caution_tags.append(f"市場proxy最新 {date_note}")
        if not caution_tags:
            caution_tags.append("J-Quants公式価格")

        return LiveMarketSignal(
            score=score,
            breadth=breadth,
            breadth_ratio=breadth_ratio,
            separation_hint=separation_hint,
            comment=comment,
            caution_tags=caution_tags,
            average_5d_change_pct=average_5d_change_pct,
            average_20d_change_pct=average_20d_change_pct,
            latest_market_date=latest_market_date,
            is_stale=is_stale,
        )

    def _load_market_proxy_snapshots(self, *, session: Session) -> list[MarketProxySnapshot]:
        self._sync_market_proxy_prices_if_needed(session=session)

        snapshots: list[MarketProxySnapshot] = []
        for key, ticker_code, label in MARKET_PROXY_TICKERS:
            prices = self.security_service.latest_prices(session, ticker_code)
            snapshot = self._market_proxy_snapshot(
                key=key,
                ticker_code=ticker_code,
                label=label,
                prices=prices,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    def _sync_market_proxy_prices_if_needed(self, *, session: Session) -> None:
        for _, ticker_code, label in MARKET_PROXY_TICKERS:
            prices = self.security_service.latest_prices(session, ticker_code)
            if prices:
                self._seed_market_proxy_security(session=session, ticker_code=ticker_code, label=label)

    def _seed_market_proxy_security(self, *, session: Session, ticker_code: str, label: str) -> None:
        security = self.security_service.get(session, ticker_code)
        if security is None:
            session.add(
                SecurityMaster(
                    ticker_code=ticker_code,
                    local_code=ticker_code,
                    name=label,
                    market="ETF",
                    industry_17=None,
                    industry_33=None,
                    master_source="local_seed",
                )
            )
            session.flush()
            return

        changed = False
        if security.name in {"", ticker_code}:
            security.name = label
            changed = True
        if security.market is None:
            security.market = "ETF"
            changed = True
        if changed:
            session.flush()

    def _market_proxy_snapshot(
        self,
        *,
        key: str,
        ticker_code: str,
        label: str,
        prices: list[object],
    ) -> MarketProxySnapshot | None:
        if len(prices) < MARKET_PROXY_MIN_BARS:
            return None

        latest_close = self._price_close(prices[-1])
        sma_20 = self._simple_moving_average(prices, 20)
        return MarketProxySnapshot(
            key=key,
            ticker_code=ticker_code,
            label=label,
            latest_date=getattr(prices[-1], "target_date", None),
            change_1d_pct=self._price_return_pct(prices, 1),
            change_5d_pct=self._price_return_pct(prices, 5),
            change_20d_pct=self._price_return_pct(prices, 20),
            above_sma_20=(latest_close >= sma_20) if latest_close is not None and sma_20 is not None else None,
        )

    def _merge_with_watchlist(
        self,
        detail: SecurityDetailResponse,
        watchlist_item: WatchlistItem | None,
    ) -> SecurityDetailResponse:
        if watchlist_item is None:
            return detail
        security = detail.security.model_copy(
            update={
                "name": watchlist_item.name or detail.security.name,
                "market": watchlist_item.market if watchlist_item.market is not None else detail.security.market,
            }
        )
        return detail.model_copy(update={"security": security})

    def _merge_security_profile(
        self,
        security: SecurityRead,
        ticker_code: str,
        *,
        session: Session | None,
    ) -> SecurityRead:
        profile = security_profile_service.resolve(ticker_code, session=session)
        if profile is None:
            return security

        update: dict[str, object] = {}
        if security_profile_service.prefers_profile_name(security.name, ticker_code, profile.name):
            update["name"] = profile.name
        if security.market is None and profile.market is not None:
            update["market"] = profile.market
        if security.local_code is None and profile.local_code is not None:
            update["local_code"] = profile.local_code
        if security.industry_17 is None and profile.industry_17 is not None:
            update["industry_17"] = profile.industry_17
        if security.industry_33 is None and profile.industry_33 is not None:
            update["industry_33"] = profile.industry_33
        if security.listed_date is None and profile.listed_date is not None:
            update["listed_date"] = profile.listed_date
        if not update:
            return security
        return security.model_copy(update=update)

    def _live_alerts(self, session: Session, ticker_code: str) -> list[AlertRead]:
        latest_score_entity = self.security_service.latest_score(session, ticker_code)
        if latest_score_entity is None:
            return []
        previous_score = self._latest_previous_score(session, ticker_code, latest_score_entity.id)
        feature = self.security_service.latest_feature(session, ticker_code)
        recent_events = self.security_service.recent_events(session, ticker_code, limit=5)
        raw_alerts = get_monitoring_container().alert_service.generate_alerts(
            ticker_code=ticker_code,
            current_score=latest_score_entity,
            previous_score=previous_score,
            technical_feature=feature,
            recent_events=recent_events,
        )
        return self._to_alert_reads(raw_alerts)

    def _priority_items(
        self,
        bundles: list[SecurityBundle],
        *,
        market_signal: LiveMarketSignal | None,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
    ) -> list[PriorityItem]:
        rows = []
        for bundle in bundles:
            attention_value = self._score_value(bundle.detail.latest_score)
            hypothesis_value = self._hypothesis_strength(bundle)
            headwind_value = self._market_headwind(bundle, market_signal=market_signal)
            risk_value = self._risk_level(bundle)
            status, status_note = self._priority_status(
                attention=attention_value,
                hypothesis=hypothesis_value,
                headwind=headwind_value,
                risk=risk_value,
            )
            materials = self._material_history(bundle.detail.recent_events)[:2]
            material_summary = materials[0].what_changed if materials else "新しい材料はありません。直近の仮説と地合いの変化を確認してください。"
            factor_split = self._factor_split(
                bundle,
                headwind_value,
                market_signal=market_signal,
                sector_snapshots=sector_snapshots,
            )
            why_now_tags = self._why_now_tags(bundle)
            rebuttal_summary = self._rebuttal_summary(bundle, risk_value)

            rows.append(
                PriorityItem(
                    ticker_code=bundle.security.ticker_code,
                    name=bundle.security.name,
                    market=bundle.security.market,
                    status=status,
                    status_note=status_note,
                    priority_rank=0,
                    attention=self._labeled_score(attention_value, kind="attention"),
                    hypothesis=self._labeled_score(hypothesis_value, kind="hypothesis"),
                    market_headwind=self._labeled_score(headwind_value, kind="headwind"),
                    risk=self._labeled_score(risk_value, kind="risk"),
                    why_now_tags=why_now_tags,
                    alert_tags=[self._alert_tag(alert) for alert in bundle.alerts[:3]],
                    material_summary=material_summary,
                    factor_summary=factor_split.summary,
                    rebuttal_summary=rebuttal_summary,
                    updated_at=bundle.detail.updated_at,
                )
            )

        rows.sort(
            key=lambda item: (item.attention.score, -item.risk.score, item.hypothesis.score),
            reverse=True,
        )
        for index, row in enumerate(rows, start=1):
            row.priority_rank = index
        return rows

    def _important_alerts(self, bundles: list[SecurityBundle]) -> list[AlertCard]:
        cards: list[AlertCard] = []
        for bundle in bundles:
            for alert in bundle.alerts:
                cards.append(
                    AlertCard(
                        ticker_code=bundle.security.ticker_code,
                        security_name=bundle.security.name,
                        severity=alert.severity,
                        title=self._alert_title(alert),
                        message=alert.message,
                        action_hint=self._alert_action_hint(alert),
                        source_links=self._alert_source_links(bundle, alert),
                    )
                )
        severity_rank = {"high": 0, "medium": 1, "low": 2}
        cards.sort(key=lambda item: (severity_rank.get(item.severity, 3), item.ticker_code))
        return cards[:6]

    def _event_feed(
        self,
        bundles: list[SecurityBundle],
        dashboard_events: list[EventRead],
        *,
        limit: int,
    ) -> list[EventFeedItem]:
        security_names = {bundle.security.ticker_code: bundle.security.name for bundle in bundles}
        combined = list(dashboard_events)
        if not combined:
            for bundle in bundles:
                combined.extend(bundle.detail.recent_events)

        deduped: dict[str, EventRead] = {}
        for event in combined:
            deduped[event.event_id] = event

        items = [self._event_feed_item(event, security_names.get(event.ticker_code or "")) for event in deduped.values()]
        importance_rank = {"最重要": 0, "重要": 1, "通常": 2, "参考": 3}
        items.sort(key=lambda item: (importance_rank.get(item.importance, 3), -item.published_at.timestamp()))
        return items[:limit]

    def _watchlist_overview(
        self,
        bundle: SecurityBundle,
        *,
        market_signal: LiveMarketSignal | None,
    ) -> WatchlistOverviewItem:
        attention_value = self._score_value(bundle.detail.latest_score)
        hypothesis_value = self._hypothesis_strength(bundle)
        headwind_value = self._market_headwind(bundle, market_signal=market_signal)
        risk_value = self._risk_level(bundle)
        status, _ = self._priority_status(
            attention=attention_value,
            hypothesis=hypothesis_value,
            headwind=headwind_value,
            risk=risk_value,
        )
        next_action = self._next_action(status=status, bundle=bundle, risk_value=risk_value)
        thesis_state = "仮説あり" if bundle.watchlist_item and bundle.watchlist_item.thesis_bull else "仮説未入力"
        return WatchlistOverviewItem(
            ticker_code=bundle.security.ticker_code,
            name=bundle.security.name,
            market=bundle.security.market,
            status=status,
            next_action=next_action,
            memo=bundle.watchlist_item.memo if bundle.watchlist_item else None,
            updated_at=bundle.watchlist_item.updated_at if bundle.watchlist_item else bundle.detail.updated_at,
            thesis_state=thesis_state,
        )

    def _screening_item(self, item: ScreeningResult) -> ScreeningOverviewItem:
        reasons = [self._screening_reason_label(reason) for reason in item.matched_reasons[:3]]
        caution = "反証条件の確認を優先" if self._score_value(item.latest_score, fallback=Decimal("0")) < Decimal("70") else "材料の鮮度を確認"
        return ScreeningOverviewItem(
            ticker_code=item.security.ticker_code,
            name=item.security.name,
            market=item.security.market,
            total_score=self._labeled_score(self._score_value(item.latest_score), kind="attention"),
            reason_summary=" / ".join(reasons) if reasons else "条件一致の根拠は詳細を確認",
            caution=caution,
        )

    def _detail_panel(
        self,
        bundle: SecurityBundle,
        *,
        bundles: list[SecurityBundle],
        market_signal: LiveMarketSignal | None,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
    ) -> SecurityDetailPanel:
        attention_value = self._score_value(bundle.detail.latest_score)
        hypothesis_value = self._hypothesis_strength(bundle)
        headwind_value = self._market_headwind(bundle, market_signal=market_signal)
        risk_value = self._risk_level(bundle)
        status, _ = self._priority_status(
            attention=attention_value,
            hypothesis=hypothesis_value,
            headwind=headwind_value,
            risk=risk_value,
        )
        detail_status = self._detail_status_label(status)
        factor_split = self._factor_split(
            bundle,
            headwind_value,
            market_signal=market_signal,
            sector_snapshots=sector_snapshots,
        )
        hypothesis = self._hypothesis_card(bundle)
        materials = self._material_history(bundle.detail.recent_events)
        warnings = self._warnings(bundle, headwind_value, risk_value)
        history = self._history(bundle, materials, warnings)
        technical_context = bundle.detail.technical_context
        flow_context = bundle.detail.flow_context
        summary_comment = self._summary_comment(bundle, status, factor_split)
        watchlist_item = bundle.watchlist_item

        return SecurityDetailPanel(
            ticker_code=bundle.security.ticker_code,
            name=bundle.security.name,
            market=bundle.security.market,
            status=detail_status,
            attention=self._labeled_score(attention_value, kind="attention"),
            hypothesis_strength=self._labeled_score(hypothesis_value, kind="hypothesis"),
            market_headwind=self._labeled_score(headwind_value, kind="headwind"),
            risk=self._labeled_score(risk_value, kind="risk"),
            summary_comment=summary_comment,
            is_in_watchlist=watchlist_item is not None and watchlist_item.is_active,
            sort_order=watchlist_item.sort_order if watchlist_item else None,
            draft_primary=watchlist_item.thesis_bull if watchlist_item else None,
            draft_invalidation=watchlist_item.thesis_bear if watchlist_item else None,
            draft_memo=watchlist_item.memo if watchlist_item else None,
            hypothesis=hypothesis,
            factor_split=factor_split,
            reference_links=self._detail_reference_links(bundle),
            price_chart=bundle.detail.latest_prices,
            technical_summary=technical_context.moving_average_state if technical_context else "テクニカル情報は未取得です。",
            technical_interpretations=technical_context.interpretations if technical_context else [],
            technical_metrics=technical_context.metrics if technical_context else [],
            technical_source_links=self._analysis_source_links(bundle, section="technical"),
            flow_summary=flow_context.state_summary if flow_context else "信用需給データは未取得です。",
            flow_interpretations=flow_context.interpretations if flow_context else [],
            flow_metrics=flow_context.metrics if flow_context else [],
            flow_source_links=self._analysis_source_links(bundle, section="flow"),
            materials=materials,
            warnings=warnings,
            history=history,
        )

    def _market_overview(
        self,
        priority_items: list[PriorityItem],
        *,
        bundles: list[SecurityBundle],
        market_signal: LiveMarketSignal | None,
    ) -> MarketOverview:
        if market_signal is None:
            return MarketOverview(
                label="未取得",
                score=50,
                breadth="未取得",
                breadth_ratio="0 / 0",
                separation_hint="J-Quants の市場proxy価格が未取得のため、地合い分離はまだ確定できません。",
                comment="TOPIX(1306) / Nikkei225(1321) の公式価格を取得できていないため、市場地合いは未取得として扱っています。",
                sector_pulse=[],
                caution_tags=["J-Quants市場proxy未取得"],
            )

        caution_tags = list(market_signal.caution_tags)
        if any(item.risk.score >= 70 for item in priority_items):
            caution_tags.append("個別リスク高め")
        return MarketOverview(
            label=self._market_label(market_signal.score),
            score=market_signal.score,
            breadth=market_signal.breadth,
            breadth_ratio=market_signal.breadth_ratio,
            separation_hint=market_signal.separation_hint,
            comment=market_signal.comment,
            sector_pulse=self._sector_pulse(bundles, market_signal=market_signal),
            caution_tags=caution_tags,
        )
        if not priority_items:
            return MarketOverview(
                label="中立",
                score=50,
                breadth="様子見",
                breadth_ratio="0 / 0",
                separation_hint="監視対象がまだ少ないため、地合いと個別要因の切り分けは未判定です。",
                comment="watchlist を登録すると、地合いの温度感と今日見る順番をここに集約します。",
                sector_pulse=[],
                caution_tags=["watchlist登録待ち"],
            )

        strong_count = sum(1 for item in priority_items if item.market_headwind.score <= 40)
        weak_count = sum(1 for item in priority_items if item.market_headwind.score >= 65)
        score = round(sum(100 - item.market_headwind.score for item in priority_items) / len(priority_items))
        label = self._market_label(score)
        breadth = "全面高寄り" if strong_count > weak_count else ("全面安寄り" if weak_count > strong_count else "まちまち")
        breadth_ratio = f"{strong_count} / {len(priority_items)}"
        if weak_count >= max(2, len(priority_items) // 2):
            separation_hint = "今日は地合い要因の影響がやや強く、個別材料だけで判断しにくい状態です。"
        else:
            separation_hint = "個別材料の差が出やすく、地合いと個別要因を分けて見やすい状態です。"
        comment = (
            "市場全体の逆風が強い日は、上位銘柄でも個別材料だけでなく指数連動の下げを切り分けて確認します。"
            if weak_count >= strong_count
            else "地合いは大崩れしておらず、個別材料と仮説の維持状況を優先して確認できる状態です。"
        )
        caution_tags = []
        if weak_count:
            caution_tags.append("地合い要因を優先確認")
        if any(item.risk.score >= 70 for item in priority_items):
            caution_tags.append("反証条件に接近")
        if not caution_tags:
            caution_tags.append("個別材料優先")

        sector_pulse = self._sector_pulse(priority_items)
        return MarketOverview(
            label=label,
            score=score,
            breadth=breadth,
            breadth_ratio=breadth_ratio,
            separation_hint=separation_hint,
            comment=comment,
            sector_pulse=sector_pulse,
            caution_tags=caution_tags,
        )

    def _metrics(
        self,
        *,
        mode: str,
        watchlist_count: int,
        priority_items: list[PriorityItem],
        important_alerts: list[AlertCard],
        screening_count: int,
        market_overview: MarketOverview,
    ) -> list[DashboardMetric]:
        return [
            DashboardMetric(label="動作モード", value="モック" if mode == "mock" else "ライブ", note="画面表示の元データ"),
            DashboardMetric(label="市場温度感", value=market_overview.label, note=market_overview.comment),
            DashboardMetric(label="監視銘柄数", value=str(watchlist_count), note="優先順位づけの対象"),
            DashboardMetric(label="重要アラート", value=str(len(important_alerts)), note="反証条件や警告の件数"),
            DashboardMetric(label="今日見る候補", value=str(len(priority_items)), note="優先度の高い銘柄"),
            DashboardMetric(label="条件一致", value=str(screening_count), note="テクニカル/需給条件に合う銘柄"),
        ]

    def _status_counts(self, priority_items: list[PriorityItem]) -> list[StatusCount]:
        labels = [
            "今日見るべき銘柄",
            "監視継続",
            "地合い改善待ち",
            "要注意",
        ]
        counts = {label: 0 for label in labels}
        for item in priority_items:
            counts[item.status] = counts.get(item.status, 0) + 1
        notes = {
            "今日見るべき銘柄": "材料か警告が新しく、優先確認が必要です。",
            "監視継続": "仮説は維持。日次確認を継続します。",
            "地合い改善待ち": "個別要因より市場逆風の影響を強く受けています。",
            "要注意": "反証条件や悪材料を先に確認する状態です。",
        }
        return [StatusCount(status=label, count=counts.get(label, 0), note=notes[label]) for label in labels]

    def _sector_pulse(
        self,
        bundles: list[SecurityBundle],
        *,
        market_signal: LiveMarketSignal | None,
    ) -> list[MarketSectorPulse]:
        market_change_5d = market_signal.average_5d_change_pct if market_signal is not None else None
        grouped: dict[str, list[Decimal]] = {}
        for bundle in bundles:
            sector_name = bundle.security.industry_33 or bundle.security.industry_17
            if not sector_name:
                continue
            change_5d = self._price_return_pct(bundle.detail.latest_prices, 5)
            if change_5d is None:
                continue
            grouped.setdefault(sector_name, []).append(change_5d)

        pulses: list[MarketSectorPulse] = []
        for name, changes in grouped.items():
            average_change = self._mean_decimal(changes)
            if average_change is None:
                continue
            relative_change = average_change - market_change_5d if market_change_5d is not None else None
            if relative_change is None:
                label = "中立"
                note = f"5日騰落 {self._format_pct(average_change)} / {len(changes)}銘柄"
            elif relative_change >= Decimal("2"):
                label = "強い"
                note = f"市場比 {self._format_signed_pct(relative_change)}pt / {len(changes)}銘柄"
            elif relative_change >= Decimal("0.5"):
                label = "やや強い"
                note = f"市場比 {self._format_signed_pct(relative_change)}pt / {len(changes)}銘柄"
            elif relative_change <= Decimal("-2"):
                label = "弱い"
                note = f"市場比 {self._format_signed_pct(relative_change)}pt / {len(changes)}銘柄"
            elif relative_change <= Decimal("-0.5"):
                label = "やや弱い"
                note = f"市場比 {self._format_signed_pct(relative_change)}pt / {len(changes)}銘柄"
            else:
                label = "中立"
                note = f"市場比 {self._format_signed_pct(relative_change)}pt / {len(changes)}銘柄"
            pulses.append(MarketSectorPulse(name=name, label=label, note=note))

        label_rank = {"強い": 4, "やや強い": 3, "中立": 2, "やや弱い": 1, "弱い": 0}
        pulses.sort(key=lambda item: (label_rank.get(item.label, -1), item.note), reverse=True)
        return pulses[:3]
        grouped: dict[str, list[PriorityItem]] = {}
        for item in priority_items:
            key = item.market or "市場横断"
            grouped.setdefault(key, []).append(item)

        pulses: list[MarketSectorPulse] = []
        for name, items in grouped.items():
            avg_attention = sum(item.attention.score for item in items) / len(items)
            avg_headwind = sum(item.market_headwind.score for item in items) / len(items)
            state_score = round((avg_attention + (100 - avg_headwind)) / 2)
            label = "強い" if state_score >= 70 else ("やや強い" if state_score >= 58 else ("中立" if state_score >= 45 else "弱い"))
            note = "上位に残る銘柄が多い" if avg_headwind <= 45 else "地合い影響の切り分けが必要"
            pulses.append(MarketSectorPulse(name=name, label=label, note=note))
        pulses.sort(key=lambda item: item.label, reverse=True)
        return pulses[:3]

    def _hypothesis_card(self, bundle: SecurityBundle) -> HypothesisCard:
        watch = bundle.watchlist_item
        materials = self._material_history(bundle.detail.recent_events)
        first_material = materials[0] if materials else None
        primary = (
            watch.thesis_bull
            if watch and watch.thesis_bull
            else "主仮説が未入力です。なぜ今見るのかを短く固定してください。"
        )
        invalidation = (
            watch.thesis_bear
            if watch and watch.thesis_bear
            else "何が崩れたら見送りにするかを明文化してください。"
        )
        catalyst = first_material.what_changed if first_material else "次の材料待ち"
        return HypothesisCard(
            primary=primary,
            secondary=first_material.summary if first_material else None,
            catalyst=catalyst,
            time_horizon="1〜3か月",
            invalidation=invalidation,
            exit_condition=invalidation,
            note=watch.memo if watch else None,
            updated_at=watch.updated_at if watch else bundle.detail.updated_at,
            source_label="watchlist",
        )

    def _factor_split(
        self,
        bundle: SecurityBundle,
        headwind_value: Decimal,
        *,
        bundles: list[SecurityBundle],
        market_signal: LiveMarketSignal | None,
    ) -> FactorSplit:
        latest_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        sector_relative, sector_sample_count, sector_name = self._sector_relative_strength(
            bundle,
            bundles=bundles,
            market_signal=market_signal,
        )

        if market_signal is None:
            market = 25
        elif market_signal.is_stale:
            market = 35
        elif market_signal.score >= 72 or market_signal.score <= 30:
            market = 55
        elif market_signal.score >= 60 or market_signal.score <= 40:
            market = 45
        else:
            market = 30

        sector = 15
        if sector_relative is not None:
            if abs(sector_relative) >= Decimal("2"):
                sector += 15 if sector_sample_count >= 2 else 10
            elif abs(sector_relative) >= Decimal("0.8"):
                sector += 8
        elif sector_sample_count >= 1:
            sector += 5

        company = 100 - market - sector
        if latest_event and latest_event.event_type in {"upward_revision", "shareholder_return", "dilution_risk", "product_cycle"}:
            company += 20
            market -= 10
            sector -= 10
        if latest_event and latest_event.event_type == "sector_strength":
            sector += 15
            company -= 10
            market -= 5

        market = max(10, min(80, market))
        sector = max(10, min(60, sector))
        company = max(10, 100 - market - sector)
        total = market + sector + company
        if total != 100:
            company += 100 - total

        if company >= market and company >= sector:
            summary = "個別要因が主体です。材料とリスクイベントの確認を先に進めてください。"
        elif market >= company and market >= sector:
            summary = "市場要因が主体です。TOPIX / Nikkei225 proxy の方向感を先に切り分けてください。"
        else:
            summary = "セクター要因が主体です。同業の強弱と個別材料をセットで確認してください。"

        note_parts: list[str] = []
        if market_signal is None:
            note_parts.append("市場要因は J-Quants 市場proxy未取得のため保守的に計上")
        else:
            note_parts.append("市場要因は J-Quants 公式価格の TOPIX(1306) / Nikkei225(1321) proxy で算出")
            if market_signal.is_stale and market_signal.latest_market_date is not None:
                note_parts.append(f"市場proxy最新日は {market_signal.latest_market_date.isoformat()}")
        if sector_name and sector_sample_count:
            if sector_relative is None:
                note_parts.append(f"セクター比較は {sector_name} {sector_sample_count} 銘柄で参考表示")
            else:
                note_parts.append(f"セクター比較は {sector_name} {sector_sample_count} 銘柄の5日騰落差")
        else:
            note_parts.append("セクター比較は未取得")

        return FactorSplit(
            market=market,
            sector=sector,
            company=company,
            summary=summary,
            note=" / ".join(note_parts),
        )
        latest_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        market = 35
        sector = 20
        company = 45
        if headwind_value >= Decimal("65"):
            market += 20
            company -= 10
            sector -= 10
        if latest_event and latest_event.event_type in {"upward_revision", "shareholder_return", "dilution_risk", "product_cycle"}:
            company += 20
            market -= 10
            sector -= 10
        if latest_event and latest_event.event_type == "sector_strength":
            sector += 20
            company -= 10
            market -= 10

        market = max(10, min(80, market))
        sector = max(10, min(60, sector))
        company = max(10, 100 - market - sector)
        total = market + sector + company
        if total != 100:
            company += 100 - total

        if company >= market and company >= sector:
            summary = "個別要因寄りです。材料と反証条件の変化を優先してください。"
        elif market >= company and market >= sector:
            summary = "地合い要因寄りです。指数や市場逆風の影響を先に切り分けてください。"
        else:
            summary = "セクター要因が混ざっています。業界全体の強弱も併せて確認してください。"
        note = "推定。市場/セクター/個別要因を分離して見るための補助表示です。"
        return FactorSplit(market=market, sector=sector, company=company, summary=summary, note=note)

    def _material_history(self, events: list[EventRead]) -> list[MaterialHistoryItem]:
        items = []
        for event in events:
            items.append(
                MaterialHistoryItem(
                    event_id=event.event_id,
                    category=self._event_category(event.event_type),
                    importance=self._importance_label(event.importance_hint),
                    stance=self._event_stance(event.event_type),
                    summary=event.summary_text,
                    what_changed=self._what_changed(event),
                    event_time=event.event_time,
                    source_name=event.source_name,
                    raw_reference=event.raw_reference,
                    source_links=self._event_source_links(event),
                )
            )
        return items[:8]

    def _warnings(self, bundle: SecurityBundle, headwind_value: Decimal, risk_value: Decimal) -> list[WarningItem]:
        warnings: list[WarningItem] = []
        if risk_value >= Decimal("70"):
            warnings.append(
                WarningItem(
                    severity="high",
                    title="反証条件に接近",
                    detail="リスク警戒が高く、買い理由よりも崩れた条件の確認を優先してください。",
                )
            )
        if headwind_value >= Decimal("65"):
            warnings.append(
                WarningItem(
                    severity="medium",
                    title="地合い悪化注意",
                    detail="指数や市場全体の逆風が強く、個別材料だけでは説明しにくい下げの可能性があります。",
                )
            )
        latest_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        if latest_event and latest_event.event_type in {"dilution_risk", "downward_revision"}:
            warnings.append(
                WarningItem(
                    severity="high",
                    title="ネガティブ材料",
                    detail=self._what_changed(latest_event),
                )
            )
        if bundle.detail.latest_features and bundle.detail.latest_features.upper_wick_ratio and bundle.detail.latest_features.upper_wick_ratio >= Decimal("0.35"):
            warnings.append(
                WarningItem(
                    severity="medium",
                    title="上ヒゲ警戒",
                    detail="戻り売りが出やすい形です。出来高と終値位置も併せて確認してください。",
                )
            )
        if bundle.detail.latest_flow and bundle.detail.latest_flow.credit_ratio and bundle.detail.latest_flow.credit_ratio >= Decimal("5"):
            warnings.append(
                WarningItem(
                    severity="medium",
                    title="信用需給の偏り",
                    detail="信用倍率が高く、価格上昇に対して需給の重さが残る可能性があります。",
                )
            )
        return warnings[:5]

    def _history(self, bundle: SecurityBundle, materials: list[MaterialHistoryItem], warnings: list[WarningItem]) -> list[HistoryItem]:
        rows: list[HistoryItem] = []
        hypothesis = self._hypothesis_card(bundle)
        if hypothesis.updated_at:
            rows.append(
                HistoryItem(
                    occurred_at=hypothesis.updated_at,
                    kind="仮説更新",
                    title="仮説カードの基準",
                    detail=hypothesis.primary,
                )
            )
        for warning in warnings[:2]:
            rows.append(
                HistoryItem(
                    occurred_at=bundle.detail.updated_at or datetime.now(timezone.utc),
                    kind="警告",
                    title=warning.title,
                    detail=warning.detail,
                )
            )
        for material in materials[:3]:
            rows.append(
                HistoryItem(
                    occurred_at=material.event_time,
                    kind=material.category,
                    title=material.summary,
                    detail=material.what_changed,
                )
            )
        rows.sort(key=lambda item: self._coerce_utc(item.occurred_at), reverse=True)
        return rows[:6]

    def _analysis_source_links(self, bundle: SecurityBundle, *, section: str) -> list[SourceLink]:
        ticker_code = bundle.security.ticker_code
        links = [
            SourceLink(
                label="分析明細JSON",
                url=f"/securities/{quote(ticker_code)}",
                note="最新の分析スナップショットを確認できます。",
            )
        ]

        if section == "technical":
            source_name = bundle.detail.latest_prices[0].source_name if bundle.detail.latest_prices else None
            source_url = self._source_catalog_url(source_name, ticker_code=ticker_code)
            if source_name and source_url:
                links.append(
                    SourceLink(
                        label="価格ソース",
                        url=source_url,
                        note=f"{self._source_display_name(source_name)} を参照します。",
                    )
                )
        elif section == "flow":
            source_name = bundle.detail.latest_flow.source_name if bundle.detail.latest_flow else None
            source_url = self._source_catalog_url(source_name, ticker_code=ticker_code)
            if source_name and source_url:
                links.append(
                    SourceLink(
                        label="需給ソース",
                        url=source_url,
                        note=f"{self._source_display_name(source_name)} を参照します。",
                    )
                )

        recent_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        if recent_event is not None:
            raw_source_url = self._raw_reference_url(
                recent_event.source_name,
                recent_event.raw_reference,
                ticker_code=recent_event.ticker_code,
            )
            if raw_source_url:
                links.append(
                    SourceLink(
                        label="直近材料",
                        url=raw_source_url,
                        note=f"{self._source_display_name(recent_event.source_name)} の原典です。",
                    )
                )
        self._append_official_ir_link(links, ticker_code, note="許可済みの公式IRページを開きます。")
        return self._dedupe_source_links(links)

    def _detail_reference_links(self, bundle: SecurityBundle) -> list[SourceLink]:
        ticker_code = bundle.security.ticker_code
        local_code = self._quote_code(bundle.security)
        links: list[SourceLink] = []

        yahoo_url = self._yahoo_finance_url(local_code)
        if yahoo_url:
            links.append(
                SourceLink(
                    label="Yahoo!ファイナンス",
                    url=yahoo_url,
                    note="株価、ニュース、信用残の確認に使う参照先です。",
                )
            )

        # The major-reference block should open human-readable Japanese pages first.
        jquants_url = None
        if jquants_url:
            links.append(
                SourceLink(
                    label="J-Quants",
                    url=jquants_url,
                    note="日足データの一次ソースです。",
                )
            )

        ir_url = self._official_ir_url(ticker_code)
        if ir_url:
            links.append(
                SourceLink(
                    label="公式IR",
                    url=ir_url,
                    note="決算短信や説明資料の確認に使う公式ページです。",
                )
            )

        recent_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        if recent_event is not None:
            raw_source_url = self._raw_reference_url(
                recent_event.source_name,
                recent_event.raw_reference,
                ticker_code=recent_event.ticker_code,
            )
            if raw_source_url:
                links.append(
                    SourceLink(
                        label="最新開示",
                        url=raw_source_url,
                        note=f"{self._source_display_name(recent_event.source_name)} の原文です。",
                    )
                )

        return self._dedupe_source_links(links, limit=4)

    def _alert_source_links(self, bundle: SecurityBundle, alert: AlertRead) -> list[SourceLink]:
        links: list[SourceLink] = []
        related_event = self._related_event_for_alert(bundle, alert)
        if related_event is not None:
            links.extend(self._event_source_links(related_event))

        ticker_code = bundle.security.ticker_code
        self._append_official_ir_link(links, ticker_code, note="許可済みの公式IRページを開きます。")
        links.append(
            SourceLink(
                label="銘柄詳細",
                url=self._detail_page_url(ticker_code),
                note="この銘柄の判断補助画面を開きます。",
            )
        )
        links.append(
            SourceLink(
                label="分析明細JSON",
                url=f"/securities/{quote(ticker_code)}",
                note="アラートの根拠になった分析スナップショットです。",
            )
        )
        return self._dedupe_source_links(links)

    def _event_source_links(self, event: EventRead) -> list[SourceLink]:
        links: list[SourceLink] = []
        raw_source_url = self._raw_reference_url(event.source_name, event.raw_reference, ticker_code=event.ticker_code)
        if raw_source_url:
            links.append(
                SourceLink(
                    label="原典",
                    url=raw_source_url,
                    note=f"{self._source_display_name(event.source_name)} を開きます。",
                )
            )
        else:
            source_url = self._source_catalog_url(event.source_name, ticker_code=event.ticker_code)
            if source_url:
                links.append(
                    SourceLink(
                        label="情報源",
                        url=source_url,
                        note=f"{self._source_display_name(event.source_name)} の参照先です。",
                    )
                )
            elif event.raw_reference:
                links.append(
                    SourceLink(
                        label="参照ID",
                        url=self._detail_page_url(event.ticker_code) if event.ticker_code else "/ui/dashboard",
                        note=event.raw_reference,
                    )
                )

        self._append_official_ir_link(links, event.ticker_code, note="許可済みの公式IRページを開きます。")
        if event.ticker_code:
            links.append(
                SourceLink(
                    label="銘柄詳細",
                    url=self._detail_page_url(event.ticker_code),
                    note="この銘柄の詳細画面を開きます。",
                )
            )
        return self._dedupe_source_links(links)

    def _related_event_for_alert(self, bundle: SecurityBundle, alert: AlertRead) -> EventRead | None:
        events = bundle.detail.recent_events
        if not events:
            return None
        if alert.alert_type == "risk_event":
            for event in events:
                if event.event_type in {"dilution_risk", "downward_revision"}:
                    return event
        return events[0]

    def _raw_reference_url(
        self,
        source_name: str | None,
        raw_reference: str | None,
        *,
        ticker_code: str | None,
    ) -> str | None:
        if raw_reference:
            normalized = raw_reference.strip()
            if normalized.startswith(("http://", "https://")):
                return normalized
            if source_name == "edinet":
                doc_id = normalized.removeprefix("edinet://").strip("/")
                if doc_id:
                    return f"{get_monitoring_settings().edinet_base_url.rstrip('/')}/documents/{quote(doc_id)}"
        return self._source_catalog_url(source_name, ticker_code=ticker_code)

    def _source_catalog_url(self, source_name: str | None, *, ticker_code: str | None) -> str | None:
        if not source_name:
            return None
        normalized_source = source_name.strip().lower()
        settings = get_monitoring_settings()
        if normalized_source == "jquants":
            if ticker_code:
                return f"{settings.jquants_base_url.rstrip('/')}/v2/equities/bars/daily?code={quote(ticker_code)}"
            return settings.jquants_base_url
        if normalized_source == "edinet":
            return settings.edinet_base_url
        if normalized_source == "youtube_data_api":
            return "https://www.googleapis.com/youtube/v3"
        if normalized_source in {"timely_disclosure", "ir_allowlist"}:
            return self._official_ir_url(ticker_code)
        manual_reference_urls = {
            "tdnet": "https://www.jpx.co.jp/equities/listing/disclosure/tdnet/index.html",
            "tdnet_api": "https://www.jpx.co.jp/markets/paid-info-listing/tdnet/02.html",
            "nikkei": "https://www.nikkei.com/",
            "nikkei_news": "https://www.nikkei.com/",
            "reuters": "https://jp.reuters.com/",
            "reuters_japan": "https://jp.reuters.com/",
            "bloomberg": "https://www.bloomberg.co.jp/",
            "bloomberg_japan": "https://www.bloomberg.co.jp/",
            "kabutan": "https://kabutan.jp/",
            "minkabu": "https://minkabu.jp/",
            "sbi": "https://www.sbisec.co.jp/",
            "sbi_sec": "https://www.sbisec.co.jp/",
            "rakuten": "https://www.rakuten-sec.co.jp/",
            "rakuten_sec": "https://www.rakuten-sec.co.jp/",
            "x": "https://x.com/",
            "twitter": "https://x.com/",
            "stocktwits": "https://stocktwits.com/",
        }
        return manual_reference_urls.get(normalized_source)

    def _source_display_name(self, source_name: str | None) -> str:
        normalized_source = (source_name or "").strip().lower()
        mapping = {
            "jquants": "J-Quants",
            "edinet": "EDINET",
            "youtube_data_api": "YouTube Data API",
            "timely_disclosure": "適時開示",
            "tdnet": "TDnet",
            "tdnet_api": "TDnet API",
            "nikkei": "日経新聞",
            "nikkei_news": "日経新聞",
            "reuters": "ロイター",
            "reuters_japan": "ロイター",
            "bloomberg": "Bloomberg",
            "bloomberg_japan": "Bloomberg",
            "kabutan": "株探",
            "minkabu": "みんかぶ",
            "sbi": "SBI証券",
            "sbi_sec": "SBI証券",
            "rakuten": "楽天証券",
            "rakuten_sec": "楽天証券",
            "x": "X",
            "twitter": "X",
            "stocktwits": "StockTwits",
            "analysis": "アプリ内分析",
            "manual": "手入力",
            "mock": "モック",
        }
        return mapping.get(normalized_source, source_name or "情報源")

    def _official_ir_url(self, ticker_code: str | None) -> str | None:
        if not ticker_code:
            return None
        profile = security_profile_service.resolve(ticker_code)
        if profile is None:
            return None
        return profile.ir_url

    def _detail_page_url(self, ticker_code: str) -> str:
        return f"/ui/security/{quote(ticker_code)}"

    def _quote_code(self, security: SecurityRead) -> str | None:
        raw_code = (security.local_code or security.ticker_code or "").strip()
        if not raw_code:
            return None
        return raw_code.split(".", 1)[0]

    def _yahoo_finance_url(self, local_code: str | None) -> str | None:
        if not local_code:
            return None
        return f"https://finance.yahoo.co.jp/quote/{quote(local_code)}.T"

    def _append_official_ir_link(self, links: list[SourceLink], ticker_code: str | None, *, note: str) -> None:
        if self._has_external_source_link(links):
            return
        ir_url = self._official_ir_url(ticker_code)
        if ir_url:
            links.append(SourceLink(label="公式IR", url=ir_url, note=note))

    def _has_external_source_link(self, links: list[SourceLink]) -> bool:
        return any(self._is_external_url(link.url) for link in links)

    def _is_external_url(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    def _dedupe_source_links(self, links: list[SourceLink], *, limit: int = 3) -> list[SourceLink]:
        deduped: list[SourceLink] = []
        seen: set[tuple[str, str]] = set()
        for link in links:
            key = (link.label, link.url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(link)
        return deduped[:limit]

    def _summary_comment(self, bundle: SecurityBundle, status: str, factor_split: FactorSplit) -> str:
        materials = self._material_history(bundle.detail.recent_events)
        latest_change = materials[0].what_changed if materials else "新材料は確認されていません。"
        return f"{status}。{factor_split.summary} 直近では「{latest_change}」を先に確認してください。"

    def _priority_status(
        self,
        *,
        attention: Decimal,
        hypothesis: Decimal,
        headwind: Decimal,
        risk: Decimal,
    ) -> tuple[str, str]:
        if risk >= Decimal("75"):
            return "要注意", "反証条件や悪材料の確認を優先します。"
        if attention >= Decimal("72") and headwind <= Decimal("55"):
            return "今日見るべき銘柄", "材料と警告が集中しており、初動確認の優先度が高い状態です。"
        if headwind >= Decimal("65") and hypothesis >= Decimal("55"):
            return "地合い改善待ち", "仮説は残る一方で、市場逆風の影響が強い状態です。"
        return "監視継続", "仮説と警告を毎日点検する通常監視の状態です。"

    def _detail_status_label(self, status: str) -> str:
        mapping = {
            "今日見るべき銘柄": "監視強化",
            "監視継続": "通常監視",
            "地合い改善待ち": "保留",
            "要注意": "要注意",
        }
        return mapping.get(status, "通常監視")

    def _next_action(self, *, status: str, bundle: SecurityBundle, risk_value: Decimal) -> str:
        if status == "今日見るべき銘柄":
            return "寄り前に材料と反証条件を再確認"
        if status == "地合い改善待ち":
            return "指数連動の逆風が和らぐかを見る"
        if risk_value >= Decimal("70"):
            return "ネガティブ材料と撤退条件を先に確認"
        if bundle.detail.latest_flow is None:
            return "信用需給データを補完"
        return "日次レビューを継続"

    def _hypothesis_strength(self, bundle: SecurityBundle) -> Decimal:
        score = bundle.detail.latest_score
        if score is None:
            base = Decimal("45")
        else:
            base = score.event_score * Decimal("0.35") + score.fundamental_score * Decimal("0.40") + (HUNDRED - score.risk_penalty) * Decimal("0.25")
        if bundle.watchlist_item and bundle.watchlist_item.thesis_bull:
            base += Decimal("8")
        if bundle.watchlist_item and bundle.watchlist_item.thesis_bear:
            base += Decimal("5")
        return self._clamp(base)

    def _market_headwind(
        self,
        bundle: SecurityBundle,
        *,
        market_signal: LiveMarketSignal | None,
    ) -> Decimal:
        if market_signal is None:
            value = Decimal("45")
        else:
            value = Decimal(str(100 - market_signal.score))
            if market_signal.is_stale:
                value = (value + Decimal("45")) / Decimal("2")

        security_change_5d = self._price_return_pct(bundle.detail.latest_prices, 5)
        market_change_5d = market_signal.average_5d_change_pct if market_signal is not None else None
        if security_change_5d is not None and market_change_5d is not None:
            relative_change = security_change_5d - market_change_5d
            if relative_change <= Decimal("-3"):
                value += Decimal("10")
            elif relative_change <= Decimal("-1"):
                value += Decimal("5")
            elif relative_change >= Decimal("3"):
                value -= Decimal("8")
            elif relative_change >= Decimal("1"):
                value -= Decimal("4")

        feature = bundle.detail.latest_features
        flow = bundle.detail.latest_flow
        if feature is not None:
            if feature.price_vs_ma_25 is not None and feature.price_vs_ma_25 < 0:
                value += Decimal("12")
            if feature.price_vs_ma_75 is not None and feature.price_vs_ma_75 < 0:
                value += Decimal("12")
            if feature.macd_histogram is not None and feature.macd_histogram < 0:
                value += Decimal("8")
            if feature.gap_down_flag:
                value += Decimal("6")
            if feature.golden_cross_flag:
                value -= Decimal("8")
            if feature.breakout_20d:
                value -= Decimal("6")
        if flow is not None:
            if flow.sell_balance_to_volume is not None and flow.sell_balance_to_volume >= Decimal("1.5"):
                value += Decimal("7")
            if flow.credit_ratio is not None and flow.credit_ratio <= Decimal("1.5"):
                value -= Decimal("4")
        return self._clamp(value)

    def _risk_level(self, bundle: SecurityBundle) -> Decimal:
        score = bundle.detail.latest_score
        if score is None:
            value = Decimal("55")
        else:
            value = score.risk_penalty
        latest_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        if latest_event and latest_event.event_type in {"dilution_risk", "downward_revision"}:
            value += Decimal("15")
        if bundle.detail.latest_features and bundle.detail.latest_features.upper_wick_ratio and bundle.detail.latest_features.upper_wick_ratio >= Decimal("0.35"):
            value += Decimal("8")
        return self._clamp(value)

    def _why_now_tags(self, bundle: SecurityBundle) -> list[str]:
        reasons = screening_reasons(bundle.detail.latest_features, bundle.detail.latest_flow, bundle.detail.latest_score)
        labels = [self._screening_reason_label(reason) for reason in reasons[:4]]
        return labels or ["根拠整理待ち"]

    def _rebuttal_summary(self, bundle: SecurityBundle, risk_value: Decimal) -> str:
        if bundle.watchlist_item and bundle.watchlist_item.thesis_bear:
            return bundle.watchlist_item.thesis_bear
        if risk_value >= Decimal("70"):
            return "悪材料か仮説崩れの兆候を優先確認してください。"
        return "反証条件が未入力です。撤退条件を先に固定してください。"

    def _event_feed_item(self, event: EventRead, security_name: str | None) -> EventFeedItem:
        return EventFeedItem(
            event_id=event.event_id,
            ticker_code=event.ticker_code,
            security_name=security_name,
            category=self._event_category(event.event_type),
            importance=self._importance_label(event.importance_hint),
            stance=self._event_stance(event.event_type),
            summary=event.summary_text,
            what_changed=self._what_changed(event),
            published_at=event.event_time,
            source_name=event.source_name,
            raw_reference=event.raw_reference,
            source_links=self._event_source_links(event),
        )

    def _screening_from_bundle(self, bundle: SecurityBundle) -> ScreeningResult:
        return ScreeningResult(
            security=bundle.security,
            latest_score=bundle.detail.latest_score,
            latest_features=bundle.detail.latest_features,
            latest_flow=bundle.detail.latest_flow,
            matched_reasons=screening_reasons(bundle.detail.latest_features, bundle.detail.latest_flow, bundle.detail.latest_score),
        )

    def _resolve_selected_ticker(
        self,
        selected_ticker_code: str | None,
        bundle_map: dict[str, SecurityBundle],
        high_priority: list[DashboardRow],
        watchlist_items: list[WatchlistItem],
    ) -> str | None:
        if selected_ticker_code and selected_ticker_code in bundle_map:
            return selected_ticker_code
        if selected_ticker_code and get_settings().app_use_mock and mock_monitoring_service.has_security(selected_ticker_code):
            return selected_ticker_code
        if selected_ticker_code:
            return selected_ticker_code
        if high_priority:
            return high_priority[0].security.ticker_code
        if watchlist_items:
            return watchlist_items[0].ticker_code
        if bundle_map:
            return next(iter(bundle_map))
        return None

    @staticmethod
    def _resolve_watchlist_collection_id(
        collections: list[WatchlistCollectionRead],
        requested_id: int | None,
    ) -> int | None:
        """Resolve an active collection, falling back to the durable default."""

        if requested_id is not None and any(item.id == requested_id for item in collections):
            return requested_id
        default = next((item for item in collections if item.is_default), None)
        if default is not None:
            return default.id
        return collections[0].id if collections else None

    def _event_category(self, event_type: str) -> str:
        mapping = {
            "upward_revision": "上方修正",
            "downward_revision": "下方修正",
            "shareholder_return": "還元",
            "dilution_risk": "増資",
            "product_cycle": "製品サイクル",
            "sector_strength": "セクター",
            "volume_expansion": "出来高",
        }
        return mapping.get(event_type, "その他IR")

    def _event_stance(self, event_type: str) -> str:
        positive = {"upward_revision", "shareholder_return", "product_cycle", "sector_strength", "volume_expansion"}
        negative = {"downward_revision", "dilution_risk"}
        if event_type in positive:
            return "ポジティブ"
        if event_type in negative:
            return "ネガティブ"
        return "要確認"

    def _what_changed(self, event: EventRead) -> str:
        mapping = {
            "upward_revision": "業績前提が上向き、仮説補強の材料が増えました。",
            "downward_revision": "業績前提が悪化し、仮説崩れの確認が必要です。",
            "shareholder_return": "還元姿勢の変化が出ており、株主還元の評価が変わりました。",
            "dilution_risk": "希薄化や資本政策の変化が示唆され、需給悪化に注意が必要です。",
            "product_cycle": "新製品やサイクル更新が近づき、需要再加速の見方が変わりました。",
            "sector_strength": "セクター全体の強弱が変化し、個別要因との切り分けが必要です。",
            "volume_expansion": "出来高が増え、需給の変化が値動きに反映され始めています。",
        }
        return mapping.get(event.event_type, event.summary_text)

    def _importance_label(self, importance_hint: Decimal) -> str:
        if importance_hint >= Decimal("0.85"):
            return "最重要"
        if importance_hint >= Decimal("0.70"):
            return "重要"
        if importance_hint >= Decimal("0.50"):
            return "通常"
        return "参考"

    def _alert_title(self, alert: AlertRead) -> str:
        mapping = {
            "high_priority": "優先確認",
            "risk_event": "悪材料注意",
            "thesis_check": "仮説点検",
            "trend_follow": "地合い確認",
            "breakout_volume": "出来高確認",
            "screening_candidate": "候補浮上",
        }
        return mapping.get(alert.alert_type, "警告")

    def _alert_action_hint(self, alert: AlertRead) -> str:
        if alert.severity == "high":
            return "反証条件と最新材料を先に確認"
        if alert.alert_type in {"trend_follow", "screening_candidate"}:
            return "地合いと個別要因を分けて確認"
        return "材料の変化を短く確認"

    def _alert_tag(self, alert: AlertRead) -> str:
        return f"{self._alert_title(alert)}: {alert.message}"

    def _screening_reason_label(self, reason: str) -> str:
        mapping = {
            "20d_breakout": "20日高値更新",
            "60d_breakout": "60日高値更新",
            "golden_cross": "ゴールデンクロス",
            "macd_bullish_cross": "MACD強気転換",
            "rsi_55_75": "RSI中強気",
            "volume_surge>=1.5": "出来高急増",
            "credit_ratio<=1.5": "信用倍率軽め",
            "squeeze_potential>=65": "踏み上げ余地",
        }
        if reason.startswith("total_score="):
            return f"総合スコア {reason.split('=', 1)[1]}"
        return mapping.get(reason, reason)

    def _market_label(self, score: int) -> str:
        if score >= 72:
            return "強い"
        if score >= 60:
            return "やや強い"
        if score >= 45:
            return "中立"
        if score >= 30:
            return "やや弱い"
        return "弱い"

    def _labeled_score(self, value: Decimal, *, kind: str) -> LabeledScore:
        rounded = int(round(float(value)))
        if kind == "headwind":
            if rounded >= 70:
                label = "強い"
                note = "市場逆風の影響が強い可能性"
            elif rounded >= 50:
                label = "中立"
                note = "市場と個別要因が混在"
            else:
                label = "弱い"
                note = "個別要因の比重が高い可能性"
        elif kind == "risk":
            if rounded >= 70:
                label = "高"
                note = "反証条件や悪材料の優先確認が必要"
            elif rounded >= 50:
                label = "中"
                note = "警告はあるが直ちに崩れてはいない"
            else:
                label = "低"
                note = "今のところ大きな警告は少ない"
        else:
            if rounded >= 72:
                label = "高"
                note = "今日見る優先度が高い状態"
            elif rounded >= 55:
                label = "中"
                note = "継続監視で十分"
            else:
                label = "低"
                note = "急ぎの確認は不要"
        return LabeledScore(score=rounded, label=label, note=note)

    def _sector_relative_strength(
        self,
        bundle: SecurityBundle,
        *,
        bundles: list[SecurityBundle],
        market_signal: LiveMarketSignal | None,
    ) -> tuple[Decimal | None, int, str | None]:
        sector_name = bundle.security.industry_33 or bundle.security.industry_17
        if not sector_name:
            return None, 0, None

        sector_changes: list[Decimal] = []
        for candidate in bundles:
            candidate_sector = candidate.security.industry_33 or candidate.security.industry_17
            if candidate_sector != sector_name:
                continue
            change_5d = self._price_return_pct(candidate.detail.latest_prices, 5)
            if change_5d is not None:
                sector_changes.append(change_5d)

        if not sector_changes:
            return None, 0, sector_name

        sector_average = self._mean_decimal(sector_changes)
        market_average = market_signal.average_5d_change_pct if market_signal is not None else None
        if sector_average is None or market_average is None:
            return None, len(sector_changes), sector_name
        return sector_average - market_average, len(sector_changes), sector_name

    def _priority_items(
        self,
        bundles: list[SecurityBundle],
        *,
        market_signal: LiveMarketSignal | None,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
    ) -> list[PriorityItem]:
        rows: list[PriorityItem] = []
        for bundle in bundles:
            attention_value = self._score_value(bundle.detail.latest_score)
            hypothesis_value = self._hypothesis_strength(bundle)
            headwind_value = self._market_headwind(bundle, market_signal=market_signal)
            risk_value = self._risk_level(bundle)
            status, status_note = self._priority_status(
                attention=attention_value,
                hypothesis=hypothesis_value,
                headwind=headwind_value,
                risk=risk_value,
            )
            materials = self._material_history(bundle.detail.recent_events)[:2]
            material_summary = materials[0].what_changed if materials else "新しい材料は未取得です。"
            factor_split = self._factor_split(
                bundle,
                headwind_value,
                market_signal=market_signal,
                sector_snapshots=sector_snapshots,
            )
            rows.append(
                PriorityItem(
                    ticker_code=bundle.security.ticker_code,
                    name=bundle.security.name,
                    market=bundle.security.market,
                    status=status,
                    status_note=status_note,
                    priority_rank=0,
                    attention=self._labeled_score(attention_value, kind="attention"),
                    hypothesis=self._labeled_score(hypothesis_value, kind="hypothesis"),
                    market_headwind=self._labeled_score(headwind_value, kind="headwind"),
                    risk=self._labeled_score(risk_value, kind="risk"),
                    why_now_tags=self._why_now_tags(bundle),
                    alert_tags=[self._alert_tag(alert) for alert in bundle.alerts[:3]],
                    material_summary=material_summary,
                    factor_summary=factor_split.summary,
                    rebuttal_summary=self._rebuttal_summary(bundle, risk_value),
                    updated_at=bundle.detail.updated_at,
                )
            )

        rows.sort(
            key=lambda item: (item.attention.score, -item.risk.score, item.hypothesis.score),
            reverse=True,
        )
        for index, row in enumerate(rows, start=1):
            row.priority_rank = index
        return rows

    def _detail_panel(
        self,
        bundle: SecurityBundle,
        *,
        bundles: list[SecurityBundle],
        market_signal: LiveMarketSignal | None,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
    ) -> SecurityDetailPanel:
        attention_value = self._score_value(bundle.detail.latest_score)
        hypothesis_value = self._hypothesis_strength(bundle)
        headwind_value = self._market_headwind(bundle, market_signal=market_signal)
        risk_value = self._risk_level(bundle)
        status, _ = self._priority_status(
            attention=attention_value,
            hypothesis=hypothesis_value,
            headwind=headwind_value,
            risk=risk_value,
        )
        technical_context = bundle.detail.technical_context
        flow_context = bundle.detail.flow_context
        factor_split = self._factor_split(
            bundle,
            headwind_value,
            market_signal=market_signal,
            sector_snapshots=sector_snapshots,
        )
        materials = self._material_history(bundle.detail.recent_events)
        warnings = self._warnings(bundle, headwind_value, risk_value)
        history = self._history(bundle, materials, warnings)
        watchlist_item = bundle.watchlist_item
        return SecurityDetailPanel(
            ticker_code=bundle.security.ticker_code,
            name=bundle.security.name,
            market=bundle.security.market,
            status=self._detail_status_label(status),
            attention=self._labeled_score(attention_value, kind="attention"),
            hypothesis_strength=self._labeled_score(hypothesis_value, kind="hypothesis"),
            market_headwind=self._labeled_score(headwind_value, kind="headwind"),
            risk=self._labeled_score(risk_value, kind="risk"),
            summary_comment=self._summary_comment(bundle, status, factor_split),
            is_in_watchlist=watchlist_item is not None and watchlist_item.is_active,
            sort_order=watchlist_item.sort_order if watchlist_item else None,
            draft_primary=watchlist_item.thesis_bull if watchlist_item else None,
            draft_invalidation=watchlist_item.thesis_bear if watchlist_item else None,
            draft_memo=watchlist_item.memo if watchlist_item else None,
            hypothesis=self._hypothesis_card(bundle),
            factor_split=factor_split,
            reference_links=self._detail_reference_links(bundle),
            price_chart=bundle.detail.latest_prices,
            technical_summary=technical_context.moving_average_state if technical_context else "テクニカル情報は未取得です。",
            technical_interpretations=technical_context.interpretations if technical_context else [],
            technical_metrics=technical_context.metrics if technical_context else [],
            technical_source_links=self._analysis_source_links(bundle, section="technical"),
            flow_summary=flow_context.state_summary if flow_context else "信用需給データは未取得です。",
            flow_interpretations=flow_context.interpretations if flow_context else [],
            flow_metrics=flow_context.metrics if flow_context else [],
            flow_source_links=self._analysis_source_links(bundle, section="flow"),
            materials=materials,
            warnings=warnings,
            history=history,
        )

    def _market_overview(
        self,
        priority_items: list[PriorityItem],
        *,
        bundles: list[SecurityBundle],
        market_signal: LiveMarketSignal | None,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
    ) -> MarketOverview:
        sector_pulse = self._sector_pulse(sector_snapshots, market_signal=market_signal)
        if market_signal is None:
            return MarketOverview(
                label="未取得",
                score=50,
                breadth="未取得",
                breadth_ratio="0 / 0",
                separation_hint="J-Quants の市場proxy価格が未取得のため、地合い分離はまだ確定できません。必要なときだけ市場価格更新を実行します。",
                comment="TOPIX(1306) / Nikkei225(1321) の公式価格をまだ保持していないため、市場地合いは未取得です。Market Overview の市場価格更新ボタンで取得してください。",
                sector_pulse=sector_pulse,
                caution_tags=["J-Quants市場proxy未取得"],
            )

        caution_tags = list(market_signal.caution_tags)
        if any(item.risk.score >= 70 for item in priority_items):
            caution_tags.append("個別リスク警戒")
        return MarketOverview(
            label=self._market_label(market_signal.score),
            score=market_signal.score,
            breadth=market_signal.breadth,
            breadth_ratio=market_signal.breadth_ratio,
            separation_hint=market_signal.separation_hint,
            comment=market_signal.comment,
            sector_pulse=sector_pulse,
            caution_tags=caution_tags,
        )

    def _sector_pulse(
        self,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
        *,
        market_signal: LiveMarketSignal | None,
    ) -> list[MarketSectorPulse]:
        if not sector_snapshots:
            return []

        market_change_5d = market_signal.average_5d_change_pct if market_signal is not None else None
        pulses: list[MarketSectorPulse] = []
        for snapshot in sector_snapshots.values():
            average_change = snapshot.average_change_5d_pct
            breadth_note = f"{snapshot.advancers}/{snapshot.sample_count}銘柄が上昇"
            relative_change = (
                average_change - market_change_5d
                if average_change is not None and market_change_5d is not None
                else None
            )
            if relative_change is None:
                label = "中立"
                base_note = (
                    f"5日騰落 {self._format_pct(average_change)}"
                    if average_change is not None
                    else "5日騰落は未取得"
                )
            elif relative_change >= Decimal("2"):
                label = "強い"
                base_note = f"市場比 {self._format_signed_pct(relative_change)}pt"
            elif relative_change >= Decimal("0.5"):
                label = "やや強い"
                base_note = f"市場比 {self._format_signed_pct(relative_change)}pt"
            elif relative_change <= Decimal("-2"):
                label = "弱い"
                base_note = f"市場比 {self._format_signed_pct(relative_change)}pt"
            elif relative_change <= Decimal("-0.5"):
                label = "やや弱い"
                base_note = f"市場比 {self._format_signed_pct(relative_change)}pt"
            else:
                label = "中立"
                base_note = f"市場比 {self._format_signed_pct(relative_change)}pt"
            pulses.append(
                MarketSectorPulse(
                    name=snapshot.name,
                    label=label,
                    note=f"{base_note} / {breadth_note}",
                )
            )

        label_rank = {"強い": 4, "やや強い": 3, "中立": 2, "やや弱い": 1, "弱い": 0}
        pulses.sort(
            key=lambda item: (
                label_rank.get(item.label, -1),
                next(
                    (
                        snapshot.sample_count
                        for snapshot in sector_snapshots.values()
                        if snapshot.name == item.name
                    ),
                    0,
                ),
            ),
            reverse=True,
        )
        return pulses[:3]

    def _factor_split(
        self,
        bundle: SecurityBundle,
        headwind_value: Decimal,
        *,
        market_signal: LiveMarketSignal | None,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
    ) -> FactorSplit:
        latest_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        sector_relative, sector_sample_count, sector_name = self._sector_relative_strength(
            bundle,
            sector_snapshots=sector_snapshots,
            market_signal=market_signal,
        )

        if market_signal is None:
            market = 25
        elif market_signal.is_stale:
            market = 35
        elif market_signal.score >= 72 or market_signal.score <= 30:
            market = 55
        elif market_signal.score >= 60 or market_signal.score <= 40:
            market = 45
        else:
            market = 30

        sector = 15
        if sector_relative is not None:
            if abs(sector_relative) >= Decimal("2"):
                sector += 15 if sector_sample_count >= 5 else 10
            elif abs(sector_relative) >= Decimal("0.8"):
                sector += 8
        elif sector_sample_count >= 3:
            sector += 5

        company = 100 - market - sector
        if latest_event and latest_event.event_type in {"upward_revision", "shareholder_return", "dilution_risk", "product_cycle"}:
            company += 20
            market -= 10
            sector -= 10
        if latest_event and latest_event.event_type == "sector_strength":
            sector += 15
            company -= 10
            market -= 5
        if headwind_value >= Decimal("65"):
            market += 10
            company -= 5
            sector -= 5

        market = max(10, min(80, market))
        sector = max(10, min(60, sector))
        company = max(10, 100 - market - sector)
        total = market + sector + company
        if total != 100:
            company += 100 - total

        if company >= market and company >= sector:
            summary = "会社要因が主体です。材料とリスクイベントを優先して見てください。"
        elif market >= company and market >= sector:
            summary = "市場要因が主体です。TOPIX / Nikkei225 proxy の方向感を先に切り分けてください。"
        else:
            summary = "セクター要因が主体です。同業の強弱と市場比を並べて見てください。"

        note_parts: list[str] = []
        if market_signal is None:
            note_parts.append("市場要因は J-Quants 市場proxy未取得のため保守的に計上")
        else:
            note_parts.append("市場要因は J-Quants 公式価格の TOPIX(1306) / Nikkei225(1321) proxy で算出")
            if market_signal.is_stale and market_signal.latest_market_date is not None:
                note_parts.append(f"市場proxy最新日は {market_signal.latest_market_date.isoformat()}")
        if sector_name and sector_sample_count:
            if sector_relative is None:
                note_parts.append(f"セクター比較は {sector_name} {sector_sample_count} 銘柄で参考表示")
            else:
                note_parts.append(
                    f"セクター比較は {sector_name} {sector_sample_count} 銘柄で市場比 {self._format_signed_pct(sector_relative)}pt"
                )
        else:
            note_parts.append("セクター比較は未取得")

        return FactorSplit(
            market=market,
            sector=sector,
            company=company,
            summary=summary,
            note=" / ".join(note_parts),
        )

    def _sector_relative_strength(
        self,
        bundle: SecurityBundle,
        *,
        sector_snapshots: dict[str, SectorBreadthSnapshot],
        market_signal: LiveMarketSignal | None,
    ) -> tuple[Decimal | None, int, str | None]:
        sector_name = bundle.security.industry_33 or bundle.security.industry_17
        if not sector_name:
            return None, 0, None
        snapshot = sector_snapshots.get(sector_name)
        if snapshot is None:
            return None, 0, sector_name
        market_average = market_signal.average_5d_change_pct if market_signal is not None else None
        if snapshot.average_change_5d_pct is None or market_average is None:
            return None, snapshot.sample_count, sector_name
        return snapshot.average_change_5d_pct - market_average, snapshot.sample_count, sector_name

    def _price_return_pct(self, prices: list[object], lookback_sessions: int) -> Decimal | None:
        if len(prices) <= lookback_sessions:
            return None
        current = self._price_close(prices[-1])
        base = self._price_close(prices[-1 - lookback_sessions])
        if current is None or base in (None, ZERO):
            return None
        return ((current - base) / base * Decimal("100")).quantize(Decimal("0.01"))

    def _simple_moving_average(self, prices: list[object], window: int) -> Decimal | None:
        if len(prices) < window:
            return None
        closes = [self._price_close(price) for price in prices[-window:]]
        if any(close is None for close in closes):
            return None
        return (sum(closes, ZERO) / Decimal(str(window))).quantize(Decimal("0.0001"))

    def _price_close(self, price: object) -> Decimal | None:
        raw_value = getattr(price, "close_price", None)
        if raw_value is None:
            return None
        if isinstance(raw_value, Decimal):
            return raw_value
        return Decimal(str(raw_value))

    def _mean_decimal(self, values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        return (sum(values, ZERO) / Decimal(str(len(values)))).quantize(Decimal("0.01"))

    def _format_pct(self, value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.1'))}%"

    def _format_signed_pct(self, value: Decimal) -> str:
        quantized = value.quantize(Decimal("0.1"))
        prefix = "+" if quantized > ZERO else ""
        return f"{prefix}{quantized}"

    def _score_value(self, score: ScoreRead | None, *, fallback: Decimal = Decimal("50")) -> Decimal:
        if score is None:
            return fallback
        return Decimal(str(score.total_score))

    def _clamp(self, value: Decimal) -> Decimal:
        return min(max(value, ZERO), HUNDRED)

    def _latest_previous_score(self, session: Session, ticker_code: str, current_score_id: int) -> ScoreDaily | None:
        return session.scalar(
            select(ScoreDaily)
            .where(ScoreDaily.ticker_code == ticker_code, ScoreDaily.id != current_score_id)
            .order_by(ScoreDaily.target_date.desc())
            .limit(1)
        )

    def _to_alert_reads(self, alerts: list[object]) -> list[AlertRead]:
        return [
            AlertRead(
                ticker_code=alert.ticker_code,
                alert_type=alert.alert_type,
                severity=alert.severity,
                message=alert.message,
            )
            for alert in alerts
        ]

    def _coerce_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _tokyo_now(self) -> datetime:
        return datetime.now(TOKYO_TIMEZONE)

    def _tokyo_today(self) -> date:
        return self._tokyo_now().date()

    def _detail_reference_links(self, bundle: SecurityBundle) -> list[SourceLink]:
        ticker_code = bundle.security.ticker_code
        links: list[SourceLink] = [
            SourceLink(
                label="銘柄JSON",
                url=f"/securities/{quote(ticker_code)}",
                note="登録済みデータと導出コンテキストの元データを確認します。",
            )
        ]

        yahoo_url = self._yahoo_finance_url(self._quote_code(bundle.security))
        if yahoo_url:
            links.append(
                SourceLink(
                    label="Yahoo!ファイナンス",
                    url=yahoo_url,
                    note="株価、ニュース、信用残の手動確認用リンクです。自動取得ソースには使いません。",
                )
            )

        ir_url = self._official_ir_url(ticker_code)
        if ir_url:
            links.append(
                SourceLink(
                    label="公式IR",
                    url=ir_url,
                    note="許可済みの公式IRページを開きます。",
                )
            )

        if bundle.detail.latest_prices:
            source_name = bundle.detail.latest_prices[0].source_name
            source_url = self._source_catalog_url(source_name, ticker_code=ticker_code)
            if source_name and source_url and source_name.strip().lower() != "jquants":
                links.append(
                    SourceLink(
                        label="価格ソース",
                        url=source_url,
                        note=f"{self._source_display_name(source_name)} を開きます。",
                    )
                )

        recent_event = bundle.detail.recent_events[0] if bundle.detail.recent_events else None
        if recent_event is not None:
            raw_source_url = self._raw_reference_url(
                recent_event.source_name,
                recent_event.raw_reference,
                ticker_code=recent_event.ticker_code,
            )
            if raw_source_url:
                links.append(
                    SourceLink(
                        label="最新開示ソース",
                        url=raw_source_url,
                        note=f"{self._source_display_name(recent_event.source_name)} の元ソースを開きます。",
                    )
                )

        return self._dedupe_source_links(links, limit=5)


dashboard_experience_service = DashboardExperienceService()
