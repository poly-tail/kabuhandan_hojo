"""Schemas for AI-assisted stock and portfolio review."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AiReviewMode = Literal["scanner", "analyst", "judge", "critical", "prompt_only"]
AiReviewTarget = Literal["holdings", "watchlist", "candidates", "selected", "mock"]
AnalysisMode = Literal["daily", "swing", "weekly"]
RiskPreference = Literal["conservative", "balanced", "aggressive"]
WebSearchPolicy = Literal["optional", "required", "strongly_recommended", "manual_only"]
Judgement = Literal[
    "hold",
    "buy_more_candidate",
    "take_profit_candidate",
    "reduce_risk",
    "watch",
    "avoid_new_buy",
    "urgent_review",
]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
ReviewStatus = Literal[
    "success",
    "missing_api_key",
    "json_parse_failed",
    "openai_api_error",
    "openai_sdk_missing",
    "no_holdings",
    "target_limit_exceeded",
    "daily_limit_exceeded",
]
ParseFailureKind = Literal["json_syntax", "root_shape", "schema_validation"]
HoldingsSource = Literal["request", "database", "watchlist", "candidates", "mock", "none"]
Verbosity = Literal["short", "normal", "detailed"]
RiskLevel = Literal["low", "medium", "high", "unknown"]
BusinessThesisStrength = Literal["strong", "normal", "weak", "unknown"]
HoldWithoutDailyMonitoringDecision = Literal["yes", "with_reduction", "with_alerts", "before_event_reduce", "no", "unknown"]
CorePositionSuitability = Literal["high", "medium", "low", "unknown"]
MonitoringInterval = Literal["1_business_day", "3_business_days", "1_week", "2_weeks", "1_month_or_more"]
MonitoringHoldability = Literal["ok", "with_alerts", "with_reduction", "not_recommended", "unknown"]
FinalLongTermCarryDecision = Literal[
    "long_term_hold_ok",
    "hold_if_reduced",
    "hold_with_alerts",
    "reduce_before_event",
    "not_suitable_without_daily_monitoring",
    "exit_or_rotate_candidate",
    "unknown",
]


class PortfolioAiHolding(BaseModel):
    """Holding or watchlist item normalized for AI review prompts."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=4, max_length=10)
    name: str = Field(min_length=1)
    market: str | None = None
    quantity: float = Field(default=0, ge=0)
    average_price: float | None = Field(default=None, gt=0)
    position_type: str | None = None


class PortfolioAiCandidate(BaseModel):
    """Candidate or watch target normalized for AI review prompts."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=4, max_length=10)
    name: str = Field(min_length=1)
    market: str | None = None
    candidate_reason: str | None = None
    watch_condition: str | None = None


class PortfolioAiReviewRequest(BaseModel):
    """Request body for multi-mode AI stock review.

    ``analysis_mode`` and ``mock_response`` are retained for older dashboard callers.
    ``mock_response`` means "return deterministic sample output"; ``prompt_only`` means
    "build a manual ChatGPT prompt without calling OpenAI".
    """

    model_config = ConfigDict(extra="forbid")

    mode: AiReviewMode = "judge"
    target: AiReviewTarget = "holdings"
    watchlist_id: int | None = Field(default=None, ge=1)
    tickers: list[str] = Field(default_factory=list)
    use_mock_holdings: bool = False
    holdings: list[PortfolioAiHolding] = Field(default_factory=list)
    candidates: list[PortfolioAiCandidate] = Field(default_factory=list)
    analysis_mode: AnalysisMode = "daily"
    risk_preference: RiskPreference = "balanced"
    include_web_search: bool | None = None
    max_web_search_calls: int = Field(default=5, ge=0, le=10)
    save_result: bool = True
    use_cache: bool = True
    mock_response: bool = False
    reasoning_effort: ReasoningEffort | None = None
    verbosity: Verbosity = "normal"
    user_hypothesis: str | None = None
    position_intent: str | None = None


class PortfolioMarketSnapshot(BaseModel):
    """Market data snapshot that can be backed by real price APIs later."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    price: float | None = None
    change_rate: float | None = None
    volume: int | None = None
    ma_5: float | None = None
    ma_25: float | None = None
    ma_75: float | None = None
    rsi: float | None = None
    macd: float | None = None
    upper_wick_ratio: float | None = None
    lower_wick_ratio: float | None = None
    body_ratio: float | None = None
    close_position_ratio: float | None = None
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    credit_ratio: float | None = None
    earnings_date: str | None = None
    recent_news: list[str] = Field(default_factory=list)


class PortfolioAiReviewSource(BaseModel):
    """Source link returned by the model."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str


class PortfolioAiUsage(BaseModel):
    """Token and tool usage returned or estimated for a review."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    web_search_calls: int = 0
    api_calls: int = 0


class PortfolioAiUsagePeriod(BaseModel):
    """Locally aggregated usage for one calendar period in Asia/Tokyo."""

    model_config = ConfigDict(extra="forbid")

    period: str
    review_runs: int = 0
    api_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    web_search_calls: int = 0
    estimated_cost_usd: float = 0
    unpriced_api_calls: int = 0


class PortfolioAiPricingModel(BaseModel):
    """Versioned standard-processing token prices in USD per one million tokens."""

    model_config = ConfigDict(extra="forbid")

    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float
    long_context_threshold_tokens: int | None = None
    long_context_input_multiplier: float | None = None
    long_context_output_multiplier: float | None = None


class PortfolioAiPricingInfo(BaseModel):
    """Pricing provenance used for local cost estimates."""

    model_config = ConfigDict(extra="forbid")

    version: str
    as_of: str
    currency: Literal["USD"] = "USD"
    estimate_only: bool = True
    web_search_usd_per_call: float
    models: dict[str, PortfolioAiPricingModel]
    source_urls: list[str]


class PortfolioAiUsageSummary(BaseModel):
    """Usage and cost summary for the legacy stock-review path only."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["legacy_stock_review"] = "legacy_stock_review"
    timezone: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    daily_limit: int
    remaining_today: int
    today: PortfolioAiUsagePeriod
    month: PortfolioAiUsagePeriod
    pricing: PortfolioAiPricingInfo
    incomplete_pre_v2_history: bool = True
    official_billing_is_authoritative: bool = True


class LongTermCarryMonitoringIntervalView(BaseModel):
    """Holdability by non-monitoring interval."""

    model_config = ConfigDict(extra="forbid")

    interval: MonitoringInterval
    holdability: MonitoringHoldability = "unknown"
    required_conditions: list[str] = Field(default_factory=list)
    pre_actions: list[str] = Field(default_factory=list)


class LongTermCarryCheck(BaseModel):
    """Long-term carry suitability when the user cannot monitor daily."""

    model_config = ConfigDict(extra="forbid")

    can_hold_without_daily_monitoring: HoldWithoutDailyMonitoringDecision = "unknown"
    non_monitoring_hold_risk: RiskLevel = "unknown"
    business_thesis_strength: BusinessThesisStrength = "unknown"
    event_risk_while_unmonitored: RiskLevel = "unknown"
    liquidity_risk: RiskLevel = "unknown"
    volatility_risk: RiskLevel = "unknown"
    position_size_view: str = ""
    core_position_suitability: CorePositionSuitability = "unknown"
    short_term_position_should_be_removed: bool | None = None
    required_alerts: list[str] = Field(default_factory=list)
    must_check_dates_or_events: list[str] = Field(default_factory=list)
    reduce_before_events: list[str] = Field(default_factory=list)
    stop_or_reduce_conditions: list[str] = Field(default_factory=list)
    long_term_thesis_break_conditions: list[str] = Field(default_factory=list)
    monitoring_interval_view: list[LongTermCarryMonitoringIntervalView] = Field(default_factory=list)
    final_long_term_carry_decision: FinalLongTermCarryDecision = "unknown"
    final_note: str = ""


class PortfolioAiStockAnalysis(BaseModel):
    """Per-stock AI review result.

    Most fields default to an empty value so every mode can share one UI renderer.
    The prompt asks the model to fill the fields relevant to the selected mode.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    judgement: Judgement = "watch"
    judgement_label: str = "様子見"
    confidence: float = Field(default=0, ge=0, le=1)
    time_horizon_views: dict[str, str] = Field(default_factory=dict)
    short_reason: str = ""
    key_risks: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    needs_detail_analysis: bool = False
    needs_analyst_mode: bool = False
    needs_judge_mode: bool = False
    needs_long_term_carry_check: bool = False
    non_monitoring_hold_risk: RiskLevel = "unknown"
    long_term_carry_check: LongTermCarryCheck = Field(default_factory=LongTermCarryCheck)
    verification_labels: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    technical_view: str = ""
    news_view: str = ""
    market_context_view: str = ""
    supply_demand_view: str = ""
    holder_action: str = ""
    buy_more_condition: str = ""
    take_profit_condition: str = ""
    stop_or_reduce_condition: str = ""
    invalidation: str = ""
    next_price_levels: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    bullish_case: str = ""
    bearish_case: str = ""
    base_case: str = ""
    expected_value_view: str = ""
    position_size_risk: str = ""
    event_risk: str = ""
    gap_risk: str = ""
    decision_deadline: str = ""
    what_would_change_my_mind: str = ""
    final_recommendation_for_holder: str = ""
    uncertainty_notes: str = ""
    execution_plan: list[str] = Field(default_factory=list)
    critical_check: list[str] = Field(default_factory=list)
    sources: list[PortfolioAiReviewSource] = Field(default_factory=list)


class PortfolioAiSummary(BaseModel):
    """Portfolio-level AI review summary."""

    model_config = ConfigDict(extra="forbid")

    overall_view: str = ""
    portfolio_summary: str = ""
    market_temperature: str = "unknown"
    overall_risk: Literal["low", "medium", "high"] = "medium"
    buy_candidates: list[str] = Field(default_factory=list)
    sell_or_reduce_candidates: list[str] = Field(default_factory=list)
    hold_priority: list[str] = Field(default_factory=list)
    cash_allocation_view: str = ""
    concentration_risk: str = ""
    theme_exposure: list[str] = Field(default_factory=list)
    non_monitoring_reduce_candidates: list[str] = Field(default_factory=list)
    core_position_candidates: list[str] = Field(default_factory=list)
    exit_or_rotate_candidates: list[str] = Field(default_factory=list)
    action_plan_today: list[str] = Field(default_factory=list)
    invalidation_for_portfolio: str = ""
    top_risks: list[str] = Field(default_factory=list)


class PortfolioAiReviewError(BaseModel):
    """Sanitized error payload for UI state handling."""

    model_config = ConfigDict(extra="forbid")

    code: ReviewStatus
    message: str


class PortfolioAiReviewResponse(BaseModel):
    """UI-friendly AI review response."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    mode: AiReviewMode = "judge"
    analysis_mode: AnalysisMode = "daily"
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    include_web_search: bool = False
    web_search_policy: WebSearchPolicy = "optional"
    estimated_cost_usd: float = 0
    actual_usage: PortfolioAiUsage = Field(default_factory=PortfolioAiUsage)
    input_summary: dict[str, Any] = Field(default_factory=dict)
    market_summary: dict[str, Any] = Field(default_factory=dict)
    portfolio_summary: PortfolioAiSummary = Field(default_factory=PortfolioAiSummary)
    stocks: list[PortfolioAiStockAnalysis] = Field(default_factory=list)
    action_plan: list[str] = Field(default_factory=list)
    critical_warnings: list[str] = Field(default_factory=list)
    sources: list[PortfolioAiReviewSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_model_output: str | None = None
    parse_failure_kind: ParseFailureKind | None = None
    manual_prompt: str | None = None
    status: ReviewStatus = "success"
    error: PortfolioAiReviewError | None = None
    holdings_source: HoldingsSource = "none"
    web_search_used: bool = False
    mock_response: bool = False
    cache_hit: bool = False
    holdings_snapshot: list[PortfolioAiHolding] = Field(default_factory=list)
    candidates_snapshot: list[PortfolioAiCandidate] = Field(default_factory=list)
    market_snapshot: list[PortfolioMarketSnapshot] = Field(default_factory=list)
    request_payload: dict[str, Any] = Field(default_factory=dict)
