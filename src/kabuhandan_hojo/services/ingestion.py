"""Manual and connector-backed ingestion services."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from math import ceil
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import func, inspect as sa_inspect, select, text
from sqlalchemy.orm import Session

from kabuhandan_hojo.connectors.base import (
    ConnectorError,
    DailyBarRecord,
    DocumentRecord,
    ListedIssueRecord,
    MarginSnapshotRecord,
)
from kabuhandan_hojo.core.container import ServiceContainer
from kabuhandan_hojo.models.entities import (
    EventFact,
    FinancialSnapshot,
    FlowSnapshot,
    PriceDaily,
    RawDocument,
    ScoreDaily,
    SecurityMaster,
    SecurityMasterSyncRun,
    SourceRegistry,
    TechnicalFeatureDaily,
    VideoItem,
)
from kabuhandan_hojo.normalizers.events import NormalizedEvent
from kabuhandan_hojo.scoring.engine import ScoreComputation
from kabuhandan_hojo.schemas.events import AllowlistedIrDocumentCreate, RawDocumentCreate
from kabuhandan_hojo.schemas.securities import FinancialSnapshotCreate, FlowSnapshotCreate, PriceBarCreate, SecurityCreate


JQUANTS_MASTER_SOURCE = "jquants"
JQUANTS_MASTER_SCOPE = "tse_listed_issues"
DEFAULT_MIN_COMPLETE_MASTER_RECORDS = 4_000
MAX_COMPLETE_MASTER_SHRINK_RATIO = 0.05


@dataclass(frozen=True, slots=True)
class SecurityMasterSyncResult:
    fetched_count: int
    inserted_count: int
    updated_count: int
    reactivated_count: int
    deactivated_count: int
    active_total: int
    jquants_active_count: int
    source: str
    source_scope: str
    source_as_of: date | None
    sync_id: str
    synced_at: datetime
    complete: bool
    is_current_snapshot: bool
    adopted_legacy_count: int = 0

    @property
    def upserted_count(self) -> int:
        return self.inserted_count + self.updated_count


@dataclass(frozen=True, slots=True)
class SecurityMasterSyncStatus:
    active_total: int
    jquants_active_count: int
    source: str
    source_scope: str
    source_as_of: date | None
    sync_id: str | None
    synced_at: datetime | None
    complete: bool


class IngestionService:
    """Persist raw data, derived features, and scores."""

    def __init__(
        self,
        container: ServiceContainer,
        *,
        minimum_complete_master_records: int = DEFAULT_MIN_COMPLETE_MASTER_RECORDS,
        maximum_complete_master_shrink_ratio: float = MAX_COMPLETE_MASTER_SHRINK_RATIO,
    ) -> None:
        self.container = container
        self.minimum_complete_master_records = max(1, minimum_complete_master_records)
        self.maximum_complete_master_shrink_ratio = min(
            max(maximum_complete_master_shrink_ratio, 0.0),
            1.0,
        )

    def bootstrap_source_registry(self, session: Session, *, ir_allowlist_domains: list[str]) -> None:
        sources = [
            {
                "source_name": "jquants",
                "source_type": "api",
                "base_url": self.container.jquants_connector.base_url,
                "is_primary": True,
                "automation_allowed": True,
                "allowlisted_domains": [],
                "notes": "JPX/J-Quants official API source.",
            },
            {
                "source_name": "edinet",
                "source_type": "api",
                "base_url": self.container.edinet_connector.base_url,
                "is_primary": True,
                "automation_allowed": True,
                "allowlisted_domains": [],
                "notes": "EDINET filing API source.",
            },
            {
                "source_name": "tdnet_api",
                "source_type": "api",
                "base_url": self.container.tdnet_connector.base_url,
                "is_primary": False,
                "automation_allowed": True,
                "allowlisted_domains": [],
                "notes": "JPX official paid TDnet API source.",
            },
            {
                "source_name": "youtube_data_api",
                "source_type": "api",
                "base_url": "https://www.googleapis.com/youtube/v3",
                "is_primary": False,
                "automation_allowed": True,
                "allowlisted_domains": [],
                "notes": "For monitored channel updates only.",
            },
            {
                "source_name": "ir_allowlist",
                "source_type": "website",
                "base_url": None,
                "is_primary": False,
                "automation_allowed": True,
                "allowlisted_domains": ir_allowlist_domains,
                "notes": "Only domains explicitly allowed by policy and robots checks.",
            },
        ]
        for source in sources:
            existing = session.scalar(select(SourceRegistry).where(SourceRegistry.source_name == source["source_name"]))
            if existing is None:
                session.add(SourceRegistry(**source))
            else:
                existing.source_type = source["source_type"]
                existing.base_url = source["base_url"]
                existing.is_primary = source["is_primary"]
                existing.automation_allowed = source["automation_allowed"]
                existing.allowlisted_domains = source["allowlisted_domains"]
                existing.notes = source["notes"]
        session.flush()

    def upsert_security(self, session: Session, payload: SecurityCreate) -> SecurityMaster:
        security = session.get(SecurityMaster, payload.ticker_code)
        if security is None:
            security = SecurityMaster(
                ticker_code=payload.ticker_code,
                local_code=payload.ticker_code,
                name=payload.name,
                name_english=payload.name_english,
                market=payload.market,
                industry_17=payload.industry_17,
                industry_33=payload.industry_33,
                master_source="manual",
            )
            session.add(security)
        else:
            security.name = payload.name
            security.name_english = payload.name_english
            security.market = payload.market
            security.industry_17 = payload.industry_17
            security.industry_33 = payload.industry_33
            security.master_source = "manual"
            security.source_as_of = None
            security.last_seen_sync_id = None
        session.flush()
        return security

    def upsert_price_bars(self, session: Session, ticker_code: str, bars: list[PriceBarCreate | DailyBarRecord]) -> list[PriceDaily]:
        self._ensure_security(session, ticker_code)
        entities: list[PriceDaily] = []
        for bar in bars:
            mapped = self._coerce_bar(ticker_code, bar)
            existing = session.scalar(
                select(PriceDaily).where(
                    PriceDaily.ticker_code == ticker_code,
                    PriceDaily.target_date == mapped.target_date,
                )
            )
            if existing is None:
                existing = PriceDaily(
                    ticker_code=ticker_code,
                    target_date=mapped.target_date,
                    open_price=mapped.open_price,
                    high_price=mapped.high_price,
                    low_price=mapped.low_price,
                    close_price=mapped.close_price,
                    adjusted_close=mapped.adjusted_close,
                    volume=mapped.volume,
                    turnover_value=mapped.turnover_value,
                    source_name=mapped.source_name,
                )
                session.add(existing)
            else:
                existing.open_price = mapped.open_price
                existing.high_price = mapped.high_price
                existing.low_price = mapped.low_price
                existing.close_price = mapped.close_price
                existing.adjusted_close = mapped.adjusted_close
                existing.volume = mapped.volume
                existing.turnover_value = mapped.turnover_value
                existing.source_name = mapped.source_name
            entities.append(existing)
        session.flush()
        return entities

    def upsert_financial_snapshot(
        self,
        session: Session,
        ticker_code: str,
        payload: FinancialSnapshotCreate,
    ) -> FinancialSnapshot:
        self._ensure_security(session, ticker_code)
        snapshot = session.scalar(
            select(FinancialSnapshot).where(
                FinancialSnapshot.ticker_code == ticker_code,
                FinancialSnapshot.target_date == payload.target_date,
            )
        )
        if snapshot is None:
            snapshot = FinancialSnapshot(ticker_code=ticker_code, **payload.model_dump())
            session.add(snapshot)
        else:
            for key, value in payload.model_dump().items():
                setattr(snapshot, key, value)
        session.flush()
        return snapshot

    def upsert_flow_snapshot(self, session: Session, ticker_code: str, payload: FlowSnapshotCreate) -> FlowSnapshot:
        self._ensure_security(session, ticker_code)
        previous_snapshot = session.scalar(
            select(FlowSnapshot)
            .where(
                FlowSnapshot.ticker_code == ticker_code,
                FlowSnapshot.target_date < payload.target_date,
            )
            .order_by(FlowSnapshot.target_date.desc())
            .limit(1)
        )
        values = self._coerce_flow_payload(payload, previous_snapshot)
        snapshot = session.scalar(
            select(FlowSnapshot).where(
                FlowSnapshot.ticker_code == ticker_code,
                FlowSnapshot.target_date == payload.target_date,
            )
        )
        if snapshot is None:
            snapshot = FlowSnapshot(ticker_code=ticker_code, **values)
            session.add(snapshot)
        else:
            for key, value in values.items():
                setattr(snapshot, key, value)
        session.flush()
        return snapshot

    async def sync_prices_from_jquants(
        self,
        session: Session,
        ticker_code: str,
        *,
        lookback_days: int = 120,
    ) -> int:
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days)
        bars = await self.container.jquants_connector.fetch_daily_bars(
            ticker_code=ticker_code,
            start_date=start_date,
            end_date=end_date,
        )
        self.upsert_price_bars(session, ticker_code, bars)
        return len(bars)

    async def sync_security_master_from_jquants(
        self,
        session: Session,
        *,
        as_of: date | None = None,
        adopt_legacy: bool = False,
    ) -> SecurityMasterSyncResult:
        """Apply one fully fetched J-Quants snapshot without guessing legacy ownership."""

        listed_issues = await self.container.jquants_connector.fetch_listed_issues(as_of=as_of)
        sync_id = str(uuid4())
        synced_at = datetime.now(timezone.utc)
        fetched_count = len(listed_issues)
        source_dates = {issue.source_as_of for issue in listed_issues if issue.source_as_of is not None}
        source_as_of = next(iter(source_dates)) if len(source_dates) == 1 else None
        current_snapshot = as_of is None
        complete = (
            fetched_count >= self.minimum_complete_master_records
            and len(source_dates) == 1
            and all(issue.source_as_of == source_as_of for issue in listed_issues)
            and (as_of is None or source_as_of == as_of)
        )

        if fetched_count and len(source_dates) > 1:
            raise ConnectorError("J-Quants listed master returned inconsistent source dates.")
        if current_snapshot and not complete:
            raise ConnectorError(
                "J-Quants current listed master was incomplete; no local master changes were applied."
            )

        existing_by_ticker = {
            security.ticker_code: security
            for security in session.scalars(select(SecurityMaster)).all()
        }
        legacy_snapshot_date, legacy_snapshot_count = self._dominant_legacy_snapshot_cohort(
            existing_by_ticker.values()
        )
        if complete and current_snapshot:
            explicit_jquants_active_count = sum(
                1
                for security in existing_by_ticker.values()
                if security.master_source == JQUANTS_MASTER_SOURCE and security.is_active
            )
            previous_provider_count = explicit_jquants_active_count + legacy_snapshot_count
            minimum_safe_count = ceil(
                previous_provider_count * (1.0 - self.maximum_complete_master_shrink_ratio)
            )
            if previous_provider_count and fetched_count < minimum_safe_count:
                raise ConnectorError(
                    "J-Quants current listed master shrank beyond the safe threshold; "
                    "no local master changes were applied."
                )
            if legacy_snapshot_date is not None and not adopt_legacy:
                raise ConnectorError(
                    "A legacy J-Quants snapshot-date cohort requires explicit reconciliation; "
                    "run scripts/sync_security_master.py --adopt-legacy first."
                )
            self._assert_no_referenced_code_collisions(
                session,
                existing_by_ticker=existing_by_ticker,
                listed_issues=listed_issues,
            )
        inserted_count = 0
        updated_count = 0
        reactivated_count = 0
        fetched_tickers: set[str] = set()
        for issue in listed_issues:
            fetched_tickers.add(issue.ticker_code)
            existing = existing_by_ticker.get(issue.ticker_code)
            if existing is None:
                existing = self._upsert_listed_issue(
                    session,
                    issue,
                    sync_id=sync_id,
                    activate=current_snapshot,
                )
                existing_by_ticker[issue.ticker_code] = existing
                inserted_count += 1
                continue

            was_active = existing.is_active
            if (
                legacy_snapshot_date is not None
                and existing.master_source == "legacy"
                and existing.listed_date == legacy_snapshot_date
                and issue.listed_date is None
            ):
                existing.listed_date = None
            self._upsert_listed_issue(
                session,
                issue,
                sync_id=sync_id,
                activate=current_snapshot,
            )
            updated_count += 1
            if current_snapshot and not was_active and existing.is_active:
                reactivated_count += 1

        adopted_legacy_count = 0
        if complete and current_snapshot and adopt_legacy and legacy_snapshot_date is not None:
            for security in existing_by_ticker.values():
                if security.master_source != "legacy":
                    continue
                if security.listed_date != legacy_snapshot_date:
                    continue
                security.listed_date = None
                security.master_source = JQUANTS_MASTER_SOURCE
                adopted_legacy_count += 1

        deactivated_count = 0
        if complete and current_snapshot:
            for security in existing_by_ticker.values():
                if security.master_source != JQUANTS_MASTER_SOURCE:
                    continue
                if security.ticker_code in fetched_tickers or not security.is_active:
                    continue
                security.is_active = False
                deactivated_count += 1

        session.flush()
        active_total, jquants_active_count = self._security_master_counts(session)
        run = SecurityMasterSyncRun(
            sync_id=sync_id,
            source=JQUANTS_MASTER_SOURCE,
            source_scope=JQUANTS_MASTER_SCOPE,
            source_as_of=source_as_of or as_of,
            synced_at=synced_at,
            complete=complete,
            is_current_snapshot=current_snapshot,
            fetched_count=fetched_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            reactivated_count=reactivated_count,
            deactivated_count=deactivated_count,
            active_total=active_total,
            jquants_active_count=jquants_active_count,
            adopted_legacy_count=adopted_legacy_count,
        )
        session.add(run)
        session.flush()
        return SecurityMasterSyncResult(
            fetched_count=fetched_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            reactivated_count=reactivated_count,
            deactivated_count=deactivated_count,
            active_total=active_total,
            jquants_active_count=jquants_active_count,
            source=JQUANTS_MASTER_SOURCE,
            source_scope=JQUANTS_MASTER_SCOPE,
            source_as_of=source_as_of or as_of,
            sync_id=sync_id,
            synced_at=synced_at,
            complete=complete,
            is_current_snapshot=current_snapshot,
            adopted_legacy_count=adopted_legacy_count,
        )

    def get_security_master_status(self, session: Session) -> SecurityMasterSyncStatus:
        """Return persisted sync provenance plus current active counts."""

        active_total, jquants_active_count = self._security_master_counts(session)
        run = session.scalar(
            select(SecurityMasterSyncRun)
            .where(
                SecurityMasterSyncRun.source == JQUANTS_MASTER_SOURCE,
                SecurityMasterSyncRun.complete.is_(True),
                SecurityMasterSyncRun.is_current_snapshot.is_(True),
            )
            .order_by(SecurityMasterSyncRun.synced_at.desc())
            .limit(1)
        )
        if run is None:
            return SecurityMasterSyncStatus(
                active_total=active_total,
                jquants_active_count=jquants_active_count,
                source=JQUANTS_MASTER_SOURCE,
                source_scope=JQUANTS_MASTER_SCOPE,
                source_as_of=None,
                sync_id=None,
                synced_at=None,
                complete=False,
            )
        return SecurityMasterSyncStatus(
            active_total=active_total,
            jquants_active_count=jquants_active_count,
            source=run.source,
            source_scope=run.source_scope,
            source_as_of=run.source_as_of,
            sync_id=run.sync_id,
            synced_at=run.synced_at,
            complete=run.complete,
        )

    async def sync_flow_from_jquants(
        self,
        session: Session,
        ticker_code: str,
        *,
        as_of: date | None = None,
    ) -> int:
        record = await self.container.jquants_connector.fetch_margin_snapshot(ticker_code, as_of=as_of)
        if record is None:
            return 0
        self._upsert_margin_snapshot(session, ticker_code, record)
        session.flush()
        return 1

    def import_raw_document(self, session: Session, payload: RawDocumentCreate) -> tuple[RawDocument, EventFact, str]:
        record = DocumentRecord(
            source_name=payload.source_name,
            external_id=payload.external_id,
            document_type=payload.document_type,
            title=payload.title,
            ticker_code=payload.ticker_code,
            published_at=payload.published_at,
            storage_uri=payload.storage_uri,
            raw_payload=payload.raw_payload,
            content_text=payload.content_text,
            hash_digest=payload.hash_digest,
        )
        raw_document = session.scalar(
            select(RawDocument).where(
                RawDocument.source_name == payload.source_name,
                RawDocument.external_id == payload.external_id,
            )
        )
        if raw_document is None:
            raw_document = RawDocument(**payload.model_dump())
            session.add(raw_document)
        else:
            for key, value in payload.model_dump().items():
                setattr(raw_document, key, value)

        normalized = self.container.event_normalizer.normalize(record)
        self._ensure_security(session, normalized.ticker_code, allow_placeholder=True)
        summary_text = self.container.summary_generator.summarize_document(
            title=payload.title,
            metadata={**payload.raw_payload, "ticker_code": normalized.ticker_code},
            content_text=payload.content_text,
        )
        event = self._upsert_event(session, normalized, payload.published_at, summary_text)
        session.flush()
        return raw_document, event, summary_text

    async def sync_edinet_documents(self, session: Session, target_date: date) -> int:
        documents = await self.container.edinet_connector.fetch_documents(target_date)
        count = 0
        for document in documents:
            raw_payload = RawDocumentCreate(
                source_name=document.source_name,
                external_id=document.external_id,
                document_type=document.document_type,
                title=document.title,
                ticker_code=document.ticker_code,
                published_at=document.published_at,
                storage_uri=document.storage_uri,
                raw_payload=document.raw_payload,
                content_text=document.content_text,
                hash_digest=document.hash_digest,
            )
            self.import_raw_document(session, raw_payload)
            count += 1
        return count

    async def sync_tdnet_documents(
        self,
        session: Session,
        target_date: date,
        *,
        ticker_code: str | None = None,
    ) -> int:
        documents = await self.container.tdnet_connector.fetch_documents(target_date, ticker_code=ticker_code)
        count = 0
        for document in documents:
            raw_payload = RawDocumentCreate(
                source_name=document.source_name,
                external_id=document.external_id,
                document_type=document.document_type,
                title=document.title,
                ticker_code=document.ticker_code,
                published_at=document.published_at,
                storage_uri=document.storage_uri,
                raw_payload=document.raw_payload,
                content_text=document.content_text,
                hash_digest=document.hash_digest,
            )
            self.import_raw_document(session, raw_payload)
            count += 1
        return count

    async def sync_youtube_documents(
        self,
        session: Session,
        *,
        ticker_code: str,
        channel_ids: list[str],
        published_after: datetime | None = None,
        max_results: int = 10,
    ) -> int:
        count = 0
        for channel_id in channel_ids:
            documents = await self.container.youtube_connector.fetch_channel_videos(
                channel_id,
                ticker_code=ticker_code,
                published_after=published_after,
                max_results=max_results,
            )
            for document in documents:
                self._upsert_video_item(session, channel_id, document)
                raw_payload = RawDocumentCreate(
                    source_name=document.source_name,
                    external_id=document.external_id,
                    document_type=document.document_type,
                    title=document.title,
                    ticker_code=document.ticker_code,
                    published_at=document.published_at,
                    storage_uri=document.storage_uri,
                    raw_payload=document.raw_payload,
                    content_text=document.content_text,
                    hash_digest=document.hash_digest,
                )
                self.import_raw_document(session, raw_payload)
                count += 1
        return count

    def import_allowlisted_ir_document(
        self,
        session: Session,
        payload: AllowlistedIrDocumentCreate,
        *,
        allowed_domains: list[str],
    ) -> tuple[RawDocument, EventFact, str]:
        self._validate_allowlisted_url(payload.url, allowed_domains)
        raw_payload = dict(payload.raw_payload)
        raw_payload["source_url"] = payload.url
        if payload.event_type_hint:
            raw_payload["event_type_hint"] = payload.event_type_hint
        external_id = payload.external_id or self._derive_ir_external_id(payload.url)
        return self.import_raw_document(
            session,
            RawDocumentCreate(
                source_name="ir_allowlist",
                external_id=external_id,
                document_type=payload.document_type,
                title=payload.title,
                ticker_code=payload.ticker_code,
                published_at=payload.published_at,
                storage_uri=payload.url,
                raw_payload=raw_payload,
                content_text=payload.content_text,
                hash_digest=None,
            ),
        )

    def recalculate_score(self, session: Session, ticker_code: str, target_date: date | None = None) -> tuple[ScoreDaily, list]:
        target_date = target_date or date.today()
        feature = session.scalar(
            select(TechnicalFeatureDaily)
            .where(TechnicalFeatureDaily.ticker_code == ticker_code)
            .order_by(TechnicalFeatureDaily.target_date.desc())
            .limit(1)
        )
        financial = session.scalar(
            select(FinancialSnapshot)
            .where(FinancialSnapshot.ticker_code == ticker_code)
            .order_by(FinancialSnapshot.target_date.desc())
            .limit(1)
        )
        flow = session.scalar(
            select(FlowSnapshot)
            .where(FlowSnapshot.ticker_code == ticker_code)
            .order_by(FlowSnapshot.target_date.desc())
            .limit(1)
        )
        events = list(
            session.scalars(
                select(EventFact)
                .where(EventFact.ticker_code == ticker_code)
                .order_by(EventFact.event_time.desc())
                .limit(20)
            ).all()
        )
        computation = self.container.score_engine.compute(
            target_date=target_date,
            events=events,
            financial_snapshot=financial,
            flow_snapshot=flow,
            technical_feature=feature,
        )
        score = self._upsert_score(session, ticker_code, computation)
        previous_score = session.scalar(
            select(ScoreDaily)
            .where(ScoreDaily.ticker_code == ticker_code, ScoreDaily.id != score.id)
            .order_by(ScoreDaily.target_date.desc())
            .limit(1)
        )
        alerts = self.container.alert_service.generate_alerts(
            ticker_code=ticker_code,
            current_score=score,
            previous_score=previous_score,
            technical_feature=feature,
            recent_events=events,
        )
        session.flush()
        return score, alerts

    def rebuild_latest_technical_feature(self, session: Session, ticker_code: str) -> TechnicalFeatureDaily:
        prices = list(
            session.scalars(
                select(PriceDaily).where(PriceDaily.ticker_code == ticker_code).order_by(PriceDaily.target_date.asc())
            ).all()
        )
        if len(prices) < 20:
            raise ValueError("At least 20 price bars are required.")
        bars = [
            DailyBarRecord(
                ticker_code=ticker_code,
                target_date=price.target_date,
                open_price=price.open_price,
                high_price=price.high_price,
                low_price=price.low_price,
                close_price=price.close_price,
                adjusted_close=price.adjusted_close,
                volume=price.volume,
                turnover_value=price.turnover_value,
                source_name=price.source_name,
            )
            for price in prices
        ]
        snapshot = self.container.technical_feature_calculator.calculate_latest(ticker_code=ticker_code, bars=bars)
        entity = session.scalar(
            select(TechnicalFeatureDaily).where(
                TechnicalFeatureDaily.ticker_code == ticker_code,
                TechnicalFeatureDaily.target_date == snapshot.target_date,
            )
        )
        values = asdict(snapshot)
        if entity is None:
            entity = TechnicalFeatureDaily(**values)
            session.add(entity)
        else:
            for key, value in values.items():
                setattr(entity, key, value)
        session.flush()
        return entity

    def _upsert_event(
        self,
        session: Session,
        normalized: NormalizedEvent,
        published_at: datetime,
        summary_text: str,
    ) -> EventFact:
        event = session.get(EventFact, normalized.event_id)
        if event is None:
            event = EventFact(
                event_id=normalized.event_id,
                ticker_code=normalized.ticker_code,
                event_type=normalized.event_type,
                event_time=published_at,
                source_name=normalized.metadata_json["source_name"],
                importance_hint=normalized.importance_hint,
                summary_text=summary_text,
                raw_reference=normalized.raw_reference,
                metadata_json=normalized.metadata_json,
            )
            session.add(event)
        else:
            event.ticker_code = normalized.ticker_code
            event.event_type = normalized.event_type
            event.event_time = published_at
            event.importance_hint = normalized.importance_hint
            event.summary_text = summary_text
            event.raw_reference = normalized.raw_reference
            event.metadata_json = normalized.metadata_json
        return event

    def _upsert_score(self, session: Session, ticker_code: str, computation: ScoreComputation) -> ScoreDaily:
        score = session.scalar(
            select(ScoreDaily).where(
                ScoreDaily.ticker_code == ticker_code,
                ScoreDaily.target_date == computation.target_date,
            )
        )
        payload = {
            "ticker_code": ticker_code,
            "target_date": computation.target_date,
            "event_score": computation.event_score,
            "fundamental_score": computation.fundamental_score,
            "technical_score": computation.technical_score,
            "flow_score": computation.flow_score,
            "risk_penalty": computation.risk_penalty,
            "total_score": computation.total_score,
            "explanation_summary": computation.explanation_summary,
            "calculation_version": computation.calculation_version,
            "score_breakdown": computation.score_breakdown,
            "missing_data_flags": computation.missing_data_flags,
        }
        if score is None:
            score = ScoreDaily(**payload)
            session.add(score)
        else:
            for key, value in payload.items():
                setattr(score, key, value)
        session.flush()
        return score

    def _upsert_video_item(self, session: Session, channel_id: str, document: DocumentRecord) -> VideoItem:
        item = session.scalar(
            select(VideoItem).where(
                VideoItem.source_channel == channel_id,
                VideoItem.external_id == document.external_id,
            )
        )
        payload = {
            "source_channel": channel_id,
            "external_id": document.external_id,
            "published_at": document.published_at,
            "title": document.title,
            "description": document.content_text,
            "url": document.storage_uri or f"https://www.youtube.com/watch?v={document.external_id}",
            "metadata_json": document.raw_payload,
        }
        if item is None:
            item = VideoItem(**payload)
            session.add(item)
        else:
            for key, value in payload.items():
                setattr(item, key, value)
        session.flush()
        return item

    def _ensure_security(self, session: Session, ticker_code: str | None, allow_placeholder: bool = True) -> None:
        if not ticker_code:
            return
        security = session.get(SecurityMaster, ticker_code)
        if security is None and allow_placeholder:
            session.add(
                SecurityMaster(
                    ticker_code=ticker_code,
                    local_code=ticker_code,
                    name=ticker_code,
                    market=None,
                    industry_17=None,
                    industry_33=None,
                    master_source="manual",
                )
            )
            session.flush()
        elif security is None:
            raise ValueError(f"Security {ticker_code} is not registered.")

    def _coerce_bar(self, ticker_code: str, bar: PriceBarCreate | DailyBarRecord) -> DailyBarRecord:
        if isinstance(bar, DailyBarRecord):
            return bar
        payload = bar.model_dump()
        return DailyBarRecord(
            ticker_code=ticker_code,
            target_date=payload["target_date"],
            open_price=Decimal(str(payload["open_price"])),
            high_price=Decimal(str(payload["high_price"])),
            low_price=Decimal(str(payload["low_price"])),
            close_price=Decimal(str(payload["close_price"])),
            adjusted_close=Decimal(str(payload["adjusted_close"])) if payload["adjusted_close"] is not None else None,
            volume=payload["volume"],
            turnover_value=Decimal(str(payload["turnover_value"])) if payload["turnover_value"] is not None else None,
            source_name=payload["source_name"],
        )

    def _upsert_listed_issue(
        self,
        session: Session,
        issue: ListedIssueRecord,
        *,
        sync_id: str,
        activate: bool,
    ) -> SecurityMaster:
        security = session.get(SecurityMaster, issue.ticker_code)
        if security is None:
            security = SecurityMaster(
                ticker_code=issue.ticker_code,
                local_code=issue.local_code or issue.ticker_code,
                name=issue.name,
                name_english=issue.name_english,
                market=issue.market,
                industry_17=issue.industry_17,
                industry_33=issue.industry_33,
                listed_date=issue.listed_date,
                is_active=issue.is_active if activate else False,
                master_source=JQUANTS_MASTER_SOURCE,
                source_as_of=issue.source_as_of,
                last_seen_sync_id=sync_id,
            )
            session.add(security)
            return security

        security.local_code = issue.local_code or security.local_code or issue.ticker_code
        security.name = issue.name or security.name
        if issue.name_english is not None:
            security.name_english = issue.name_english
        security.market = issue.market or security.market
        security.industry_17 = issue.industry_17 or security.industry_17
        security.industry_33 = issue.industry_33 or security.industry_33
        security.listed_date = issue.listed_date or security.listed_date
        if activate:
            security.is_active = issue.is_active
        security.master_source = JQUANTS_MASTER_SOURCE
        security.source_as_of = issue.source_as_of
        security.last_seen_sync_id = sync_id
        return security

    def _security_master_counts(self, session: Session) -> tuple[int, int]:
        active_total = int(
            session.scalar(
                select(func.count()).select_from(SecurityMaster).where(SecurityMaster.is_active.is_(True))
            )
            or 0
        )
        jquants_active_count = int(
            session.scalar(
                select(func.count())
                .select_from(SecurityMaster)
                .where(
                    SecurityMaster.is_active.is_(True),
                    SecurityMaster.master_source == JQUANTS_MASTER_SOURCE,
                )
            )
            or 0
        )
        return active_total, jquants_active_count

    def _dominant_legacy_snapshot_cohort(self, securities) -> tuple[date | None, int]:
        """Identify the old importer bug only when explicitly reconciling legacy rows.

        A real listing date cannot plausibly be shared by a full-market-sized
        cohort.  The former importer copied the J-Quants snapshot ``Date`` into
        ``listed_date`` for thousands of rows.  Requiring at least the same
        completeness threshold makes this repair conservative and keeps genuine
        dates on manual/local-seed rows untouched.
        """

        counts = Counter(
            security.listed_date
            for security in securities
            if (
                security.master_source == "legacy"
                and security.is_active
                and security.listed_date is not None
            )
        )
        if not counts:
            return None, 0
        candidate, count = counts.most_common(1)[0]
        if count < self.minimum_complete_master_records:
            return None, 0
        return candidate, count

    def _assert_no_referenced_code_collisions(
        self,
        session: Session,
        *,
        existing_by_ticker: dict[str, SecurityMaster],
        listed_issues: list[ListedIssueRecord],
    ) -> None:
        """Fail before changing a row whose old issue identity is referenced.

        A previous partial synchronization may already have relabelled the
        legacy row as J-Quants-owned, so provenance is deliberately not used as
        a safety condition here.
        """

        fetched_by_ticker = {issue.ticker_code: issue for issue in listed_issues}
        collision_tickers: list[str] = []
        for issue in listed_issues:
            existing = existing_by_ticker.get(issue.ticker_code)
            if existing is None:
                continue
            old_local_code = (existing.local_code or "").strip().upper()
            new_local_code = (issue.local_code or issue.ticker_code).strip().upper()
            if not old_local_code or old_local_code == new_local_code:
                continue
            displaced_issue = fetched_by_ticker.get(old_local_code)
            if displaced_issue is None:
                continue
            displaced_local_code = (displaced_issue.local_code or displaced_issue.ticker_code).strip().upper()
            if displaced_local_code != old_local_code:
                continue
            collision_tickers.append(issue.ticker_code)

        for ticker_code in collision_tickers:
            dependent_count = self._security_master_reference_count(session, ticker_code)
            if dependent_count:
                raise ConnectorError(
                    "A normalized-code collision has dependent records and requires "
                    "explicit identity reconciliation before the master can be synchronized."
                )

    @staticmethod
    def _security_master_reference_count(session: Session, ticker_code: str) -> int:
        # Reflect through the session's live connection.  Inspecting the
        # Engine can open/close a second connection; with SQLite StaticPool that
        # can roll back the transaction currently owned by this Session.
        connection = session.connection()
        inspector = sa_inspect(connection)
        preparer = connection.dialect.identifier_preparer
        schema = inspector.default_schema_name
        total = 0
        for table_name in inspector.get_table_names(schema=schema):
            for foreign_key in inspector.get_foreign_keys(table_name, schema=schema):
                if foreign_key.get("referred_table") != SecurityMaster.__tablename__:
                    continue
                constrained_columns = foreign_key.get("constrained_columns") or []
                referred_columns = foreign_key.get("referred_columns") or []
                for constrained_column, referred_column in zip(constrained_columns, referred_columns):
                    if referred_column != "ticker_code":
                        continue
                    quoted_table = preparer.quote(table_name)
                    if schema:
                        quoted_table = f"{preparer.quote(schema)}.{quoted_table}"
                    quoted_column = preparer.quote(constrained_column)
                    statement = text(
                        f"SELECT COUNT(*) FROM {quoted_table} WHERE {quoted_column} = :ticker_code"
                    )
                    total += int(session.execute(statement, {"ticker_code": ticker_code}).scalar_one())
        return total

    def _coerce_flow_payload(
        self,
        payload: FlowSnapshotCreate,
        previous_snapshot: FlowSnapshot | None,
    ) -> dict[str, object]:
        values = payload.model_dump()

        margin_buy_balance = self._decimal_or_none(values.get("margin_buy_balance"))
        margin_sell_balance = self._decimal_or_none(values.get("margin_sell_balance"))
        average_daily_volume_20 = values.get("average_daily_volume_20")

        if values.get("credit_ratio") is None:
            values["credit_ratio"] = self._safe_ratio(margin_buy_balance, margin_sell_balance)

        if previous_snapshot is not None:
            if values.get("buy_balance_change_wow") is None:
                values["buy_balance_change_wow"] = self._safe_pct_change(
                    previous_snapshot.margin_buy_balance,
                    margin_buy_balance,
                )
            if values.get("sell_balance_change_wow") is None:
                values["sell_balance_change_wow"] = self._safe_pct_change(
                    previous_snapshot.margin_sell_balance,
                    margin_sell_balance,
                )

        volume_decimal = Decimal(str(average_daily_volume_20)) if average_daily_volume_20 else None
        if values.get("buy_balance_to_volume") is None:
            values["buy_balance_to_volume"] = self._safe_ratio(margin_buy_balance, volume_decimal)
        if values.get("sell_balance_to_volume") is None:
            values["sell_balance_to_volume"] = self._safe_ratio(margin_sell_balance, volume_decimal)
        if values.get("squeeze_potential_subscore") is None:
            values["squeeze_potential_subscore"] = self._derive_squeeze_potential_subscore(values)
        return values

    def _derive_squeeze_potential_subscore(self, values: dict[str, object]) -> Decimal:
        score = Decimal("50")
        credit_ratio = self._decimal_or_none(values.get("credit_ratio"))
        buy_balance_change_wow = self._decimal_or_none(values.get("buy_balance_change_wow"))
        sell_balance_change_wow = self._decimal_or_none(values.get("sell_balance_change_wow"))
        sell_balance_to_volume = self._decimal_or_none(values.get("sell_balance_to_volume"))
        buy_balance_to_volume = self._decimal_or_none(values.get("buy_balance_to_volume"))
        volume_ratio_20 = self._decimal_or_none(values.get("volume_ratio_20"))

        if sell_balance_to_volume is not None and sell_balance_to_volume >= Decimal("1.5"):
            score += Decimal("12")
        if credit_ratio is not None and credit_ratio <= Decimal("1.5"):
            score += Decimal("8")
        if sell_balance_change_wow is not None and sell_balance_change_wow >= Decimal("5"):
            score += Decimal("6")
        if volume_ratio_20 is not None and volume_ratio_20 >= Decimal("1.2"):
            score += Decimal("6")
        if buy_balance_change_wow is not None and buy_balance_change_wow >= Decimal("10"):
            score -= Decimal("8")
        if buy_balance_to_volume is not None and buy_balance_to_volume >= Decimal("3"):
            score -= Decimal("8")
        return max(min(score, Decimal("100")), Decimal("0"))

    def _safe_ratio(self, numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or denominator in (None, Decimal("0")):
            return None
        return (numerator / denominator).quantize(Decimal("0.0001"))

    def _safe_pct_change(self, base: Decimal | None, current: Decimal | None) -> Decimal | None:
        if base in (None, Decimal("0")) or current is None:
            return None
        return (((current - base) / base) * Decimal("100")).quantize(Decimal("0.0001"))

    def _decimal_or_none(self, value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _validate_allowlisted_url(self, url: str, allowed_domains: list[str]) -> None:
        parsed = urlparse(url.strip())
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not hostname:
            raise ValueError("Allowlisted IR URL must be an absolute http(s) URL.")
        normalized_domains = [domain.strip().lower() for domain in allowed_domains if domain.strip()]
        if not any(hostname == domain or hostname.endswith(f".{domain}") for domain in normalized_domains):
            raise ValueError("IR URL domain is not included in IR_ALLOWLIST_DOMAINS.")

    def _derive_ir_external_id(self, url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return f"ir-{digest[:16]}"

    def _upsert_margin_snapshot(
        self,
        session: Session,
        ticker_code: str,
        record: MarginSnapshotRecord,
    ) -> FlowSnapshot:
        prices = list(
            session.scalars(
                select(PriceDaily)
                .where(PriceDaily.ticker_code == ticker_code)
                .order_by(PriceDaily.target_date.asc())
            ).all()
        )
        recent_prices = prices[-20:]
        average_daily_volume_20 = None
        volume_ratio_20 = None
        if recent_prices:
            total_volume = sum(price.volume for price in recent_prices)
            average_daily_volume_20 = max(1, round(total_volume / len(recent_prices)))
            latest_volume = recent_prices[-1].volume
            volume_ratio_20 = (
                Decimal(str(latest_volume)) / Decimal(str(average_daily_volume_20))
            ).quantize(Decimal("0.0001"))

        payload = FlowSnapshotCreate(
            target_date=record.target_date,
            average_daily_volume_20=average_daily_volume_20,
            volume_ratio_20=volume_ratio_20,
            margin_buy_balance=record.margin_buy_balance,
            margin_sell_balance=record.margin_sell_balance,
            source_name=record.source_name,
        )
        return self.upsert_flow_snapshot(session, ticker_code, payload)
