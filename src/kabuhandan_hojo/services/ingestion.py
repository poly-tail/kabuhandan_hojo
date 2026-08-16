"""Manual and connector-backed ingestion services."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from kabuhandan_hojo.connectors.base import DailyBarRecord, DocumentRecord, ListedIssueRecord, MarginSnapshotRecord
from kabuhandan_hojo.core.container import ServiceContainer
from kabuhandan_hojo.models.entities import (
    EventFact,
    FinancialSnapshot,
    FlowSnapshot,
    PriceDaily,
    RawDocument,
    ScoreDaily,
    SecurityMaster,
    SourceRegistry,
    TechnicalFeatureDaily,
    VideoItem,
)
from kabuhandan_hojo.normalizers.events import NormalizedEvent
from kabuhandan_hojo.scoring.engine import ScoreComputation
from kabuhandan_hojo.schemas.events import AllowlistedIrDocumentCreate, RawDocumentCreate
from kabuhandan_hojo.schemas.securities import FinancialSnapshotCreate, FlowSnapshotCreate, PriceBarCreate, SecurityCreate


class IngestionService:
    """Persist raw data, derived features, and scores."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container

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
            )
            session.add(security)
        else:
            security.name = payload.name
            security.name_english = payload.name_english
            security.market = payload.market
            security.industry_17 = payload.industry_17
            security.industry_33 = payload.industry_33
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
    ) -> int:
        listed_issues = await self.container.jquants_connector.fetch_listed_issues(as_of=as_of)
        processed_count = 0
        for issue in listed_issues:
            self._upsert_listed_issue(session, issue)
            processed_count += 1
        session.flush()
        return processed_count

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

    def _upsert_listed_issue(self, session: Session, issue: ListedIssueRecord) -> SecurityMaster:
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
                is_active=issue.is_active,
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
        security.is_active = issue.is_active
        return security

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
