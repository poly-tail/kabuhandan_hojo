"""UI-facing dashboard schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.portfolio import PortfolioHoldingRead
from kabuhandan_hojo.schemas.securities import InterpretedMetricRead, PriceBarRead


class DashboardMetric(BaseModel):
    label: str
    value: str
    note: str


class SourceLink(BaseModel):
    label: str
    url: str
    note: str | None = None


class StatusCount(BaseModel):
    status: str
    count: int
    note: str


class LabeledScore(BaseModel):
    score: int = Field(ge=0, le=100)
    label: str
    note: str


class MarketSectorPulse(BaseModel):
    name: str
    label: str
    note: str


class MarketOverview(BaseModel):
    label: str
    score: int = Field(ge=0, le=100)
    breadth: str
    breadth_ratio: str
    separation_hint: str
    comment: str
    sector_pulse: list[MarketSectorPulse] = Field(default_factory=list)
    caution_tags: list[str] = Field(default_factory=list)


class PriorityItem(BaseModel):
    ticker_code: str
    name: str
    market: str | None = None
    status: str
    status_note: str
    priority_rank: int
    attention: LabeledScore
    hypothesis: LabeledScore
    market_headwind: LabeledScore
    risk: LabeledScore
    why_now_tags: list[str] = Field(default_factory=list)
    alert_tags: list[str] = Field(default_factory=list)
    material_summary: str
    factor_summary: str
    rebuttal_summary: str
    updated_at: datetime | None = None


class EventFeedItem(BaseModel):
    event_id: str
    ticker_code: str | None = None
    security_name: str | None = None
    category: str
    importance: str
    stance: str
    summary: str
    what_changed: str
    published_at: datetime
    source_name: str
    raw_reference: str | None = None
    source_links: list[SourceLink] = Field(default_factory=list)


class AlertCard(BaseModel):
    ticker_code: str
    security_name: str
    severity: str
    title: str
    message: str
    action_hint: str
    source_links: list[SourceLink] = Field(default_factory=list)


class WatchlistOverviewItem(BaseModel):
    ticker_code: str
    name: str
    market: str | None = None
    status: str
    next_action: str
    memo: str | None = None
    updated_at: datetime | None = None
    thesis_state: str


class ScreeningOverviewItem(BaseModel):
    ticker_code: str
    name: str
    market: str | None = None
    total_score: LabeledScore
    reason_summary: str
    caution: str


class HypothesisCard(BaseModel):
    primary: str
    secondary: str | None = None
    catalyst: str | None = None
    time_horizon: str
    invalidation: str
    exit_condition: str
    note: str | None = None
    updated_at: datetime | None = None
    source_label: str


class FactorSplit(BaseModel):
    market: int = Field(ge=0, le=100)
    sector: int = Field(ge=0, le=100)
    company: int = Field(ge=0, le=100)
    summary: str
    note: str


class MaterialHistoryItem(BaseModel):
    event_id: str
    category: str
    importance: str
    stance: str
    summary: str
    what_changed: str
    event_time: datetime
    source_name: str
    raw_reference: str | None = None
    source_links: list[SourceLink] = Field(default_factory=list)


class WarningItem(BaseModel):
    severity: str
    title: str
    detail: str


class HistoryItem(BaseModel):
    occurred_at: datetime
    kind: str
    title: str
    detail: str


class SecurityDetailPanel(BaseModel):
    ticker_code: str
    name: str
    market: str | None = None
    status: str
    attention: LabeledScore
    hypothesis_strength: LabeledScore
    market_headwind: LabeledScore
    risk: LabeledScore
    summary_comment: str
    is_in_watchlist: bool
    sort_order: int | None = None
    draft_primary: str | None = None
    draft_invalidation: str | None = None
    draft_memo: str | None = None
    hypothesis: HypothesisCard
    factor_split: FactorSplit
    reference_links: list[SourceLink] = Field(default_factory=list)
    price_chart: list[PriceBarRead] = Field(default_factory=list)
    technical_summary: str | None = None
    technical_interpretations: list[str] = Field(default_factory=list)
    technical_metrics: list[InterpretedMetricRead] = Field(default_factory=list)
    technical_source_links: list[SourceLink] = Field(default_factory=list)
    flow_summary: str | None = None
    flow_interpretations: list[str] = Field(default_factory=list)
    flow_metrics: list[InterpretedMetricRead] = Field(default_factory=list)
    flow_source_links: list[SourceLink] = Field(default_factory=list)
    materials: list[MaterialHistoryItem] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    history: list[HistoryItem] = Field(default_factory=list)


class DashboardExperienceResponse(BaseModel):
    generated_at: datetime
    target_date: date
    mode: str
    disclaimer: str
    market_overview: MarketOverview
    metrics: list[DashboardMetric] = Field(default_factory=list)
    status_counts: list[StatusCount] = Field(default_factory=list)
    priority_items: list[PriorityItem] = Field(default_factory=list)
    important_alerts: list[AlertCard] = Field(default_factory=list)
    event_feed: list[EventFeedItem] = Field(default_factory=list)
    portfolio_items: list[PortfolioHoldingRead] = Field(default_factory=list)
    watchlist_items: list[WatchlistOverviewItem] = Field(default_factory=list)
    screening_items: list[ScreeningOverviewItem] = Field(default_factory=list)
    selected_ticker_code: str | None = None
    detail: SecurityDetailPanel | None = None
