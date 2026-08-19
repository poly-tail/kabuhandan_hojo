"""Application database entities."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kabuhandan_hojo.models.base import Base, TimestampMixin


class SecurityMaster(TimestampMixin, Base):
    __tablename__ = "security_master"

    ticker_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    local_code: Mapped[str | None] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(255))
    name_english: Mapped[str | None] = mapped_column(String(255))
    market: Mapped[str | None] = mapped_column(String(50))
    industry_17: Mapped[str | None] = mapped_column(String(100))
    industry_33: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    listed_date: Mapped[date | None] = mapped_column(Date)
    master_source: Mapped[str] = mapped_column(String(32), default="legacy", server_default="legacy", nullable=False)
    source_as_of: Mapped[date | None] = mapped_column(Date)
    last_seen_sync_id: Mapped[str | None] = mapped_column(String(36))

    watchlist_items: Mapped[list["Watchlist"]] = relationship(back_populates="security")
    prices: Mapped[list["PriceDaily"]] = relationship(back_populates="security")
    events: Mapped[list["EventFact"]] = relationship(back_populates="security")
    scores: Mapped[list["ScoreDaily"]] = relationship(back_populates="security")
    technical_features: Mapped[list["TechnicalFeatureDaily"]] = relationship(back_populates="security")


class SecurityMasterSyncRun(Base):
    """Persist non-secret provenance and counts for one master sync attempt."""

    __tablename__ = "security_master_sync_run"

    sync_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    source_as_of: Mapped[date | None] = mapped_column(Date)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_current_snapshot: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reactivated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deactivated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jquants_active_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    adopted_legacy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Watchlist(TimestampMixin, Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("ticker_code", name="uq_watchlist_ticker_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    memo: Mapped[str | None] = mapped_column(Text)
    thesis_bull: Mapped[str | None] = mapped_column(Text)
    thesis_bear: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    security: Mapped["SecurityMaster"] = relationship(back_populates="watchlist_items")
    memberships: Mapped[list["WatchlistMembership"]] = relationship(back_populates="watchlist_item")


class WatchlistCollection(TimestampMixin, Base):
    __tablename__ = "watchlist_collection"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_watchlist_collection_normalized_name"),
        UniqueConstraint("system_key", name="uq_watchlist_collection_system_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(256), nullable=False)
    system_key: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list["WatchlistMembership"]] = relationship(back_populates="collection")


class WatchlistMembership(TimestampMixin, Base):
    __tablename__ = "watchlist_membership"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "watchlist_item_id",
            name="uq_watchlist_membership_collection_item",
        ),
        Index(
            "ix_watchlist_membership_item_active",
            "watchlist_item_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("watchlist_collection.id"), nullable=False)
    watchlist_item_id: Mapped[int] = mapped_column(ForeignKey("watchlist.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    collection: Mapped["WatchlistCollection"] = relationship(back_populates="memberships")
    watchlist_item: Mapped["Watchlist"] = relationship(back_populates="memberships")


class RawDocument(TimestampMixin, Base):
    __tablename__ = "raw_document"
    __table_args__ = (UniqueConstraint("source_name", "external_id", name="uq_raw_document_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    ticker_code: Mapped[str | None] = mapped_column(String(10))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(500))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_text: Mapped[str | None] = mapped_column(Text)
    hash_digest: Mapped[str | None] = mapped_column(String(128))


class EventFact(TimestampMixin, Base):
    __tablename__ = "event_fact"

    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    ticker_code: Mapped[str | None] = mapped_column(ForeignKey("security_master.ticker_code"))
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_name: Mapped[str] = mapped_column(String(50), nullable=False)
    importance_hint: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_reference: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    security: Mapped["SecurityMaster | None"] = relationship(back_populates="events")


class PriceDaily(TimestampMixin, Base):
    __tablename__ = "price_daily"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_price_daily_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Decimal] = mapped_column("open", Numeric(18, 4), nullable=False)
    high_price: Mapped[Decimal] = mapped_column("high", Numeric(18, 4), nullable=False)
    low_price: Mapped[Decimal] = mapped_column("low", Numeric(18, 4), nullable=False)
    close_price: Mapped[Decimal] = mapped_column("close", Numeric(18, 4), nullable=False)
    adjusted_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    turnover_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    source_name: Mapped[str] = mapped_column(String(50), default="manual")

    security: Mapped["SecurityMaster"] = relationship(back_populates="prices")


class FinancialSnapshot(TimestampMixin, Base):
    __tablename__ = "financial_snapshot"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_financial_snapshot_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    operating_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    ordinary_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    revenue_growth_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    operating_profit_growth_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    operating_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    equity_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    source_name: Mapped[str] = mapped_column(String(50), default="manual")


class FlowSnapshot(TimestampMixin, Base):
    __tablename__ = "flow_snapshot"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_flow_snapshot_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    average_daily_volume_20: Mapped[int | None] = mapped_column(Integer)
    volume_ratio_20: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    margin_buy_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    margin_buy_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    margin_sell_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    credit_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    buy_balance_change_wow: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sell_balance_change_wow: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    buy_balance_to_volume: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    sell_balance_to_volume: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    squeeze_potential_subscore: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    short_interest_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    float_turnover_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    large_holder_activity_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    source_name: Mapped[str] = mapped_column(String(50), default="derived")


class TechnicalFeatureDaily(TimestampMixin, Base):
    __tablename__ = "technical_feature_daily"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_technical_feature_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    sma_5: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sma_25: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sma_75: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sma_200: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sma_5_slope_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sma_25_slope_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sma_75_slope_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    deviation_from_sma_25_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    deviation_from_sma_75_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    ma_gap_5_25_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    ma_gap_25_75_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    golden_cross_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    dead_cross_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    breakout_20d: Mapped[bool] = mapped_column(Boolean, default=False)
    breakout_60d: Mapped[bool] = mapped_column(Boolean, default=False)
    volume_ratio_20: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    volume_surge_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    atr_14: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    atr_pct_14: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    rsi_14: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    roc_20: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    macd_line: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    macd_signal: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    macd_histogram: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    macd_bullish_cross_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    macd_bearish_cross_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    bollinger_mid_20: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    bollinger_upper_20: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    bollinger_lower_20: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    bollinger_width_20: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    upper_wick_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    lower_wick_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    body_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    close_position_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    gap_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    gap_up_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    gap_down_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_up_candles: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_down_candles: Mapped[int] = mapped_column(Integer, default=0)
    range_compression_20: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    security: Mapped["SecurityMaster"] = relationship(back_populates="technical_features")


class ScoreDaily(TimestampMixin, Base):
    __tablename__ = "score_daily"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_score_daily_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    fundamental_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    technical_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    flow_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    explanation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(50), nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    missing_data_flags: Mapped[list[str]] = mapped_column(JSON, default=list)

    security: Mapped["SecurityMaster"] = relationship(back_populates="scores")


class ThesisNote(TimestampMixin, Base):
    __tablename__ = "thesis_note"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    hypothesis_text: Mapped[str] = mapped_column(Text, nullable=False)
    invalidation_condition: Mapped[str | None] = mapped_column(Text)
    caution_note: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))


class AlertRule(TimestampMixin, Base):
    __tablename__ = "alert_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class VideoItem(TimestampMixin, Base):
    __tablename__ = "video_item"
    __table_args__ = (UniqueConstraint("source_channel", "external_id", name="uq_video_item_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_channel: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class SourceRegistry(TimestampMixin, Base):
    __tablename__ = "source_registry"
    __table_args__ = (UniqueConstraint("source_name", name="uq_source_registry_source_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    automation_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    allowlisted_domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
