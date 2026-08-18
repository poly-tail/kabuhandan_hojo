"""AI stock review service backed by the OpenAI Responses API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, get_settings
from app.prompts.stock_analysis import (
    build_prompt_only_text,
    build_stock_analysis_prompt,
    estimate_openai_cost,
    get_mode_profile,
    get_output_schema_for_mode,
    validate_stock_analysis_response,
)
from app.schemas.portfolio_ai import (
    AiReviewMode,
    HoldingsSource,
    LongTermCarryCheck,
    LongTermCarryMonitoringIntervalView,
    PortfolioAiCandidate,
    PortfolioAiHolding,
    PortfolioAiReviewError,
    PortfolioAiReviewRequest,
    PortfolioAiReviewResponse,
    PortfolioAiReviewSource,
    PortfolioAiStockAnalysis,
    PortfolioAiSummary,
    PortfolioAiUsage,
    PortfolioMarketSnapshot,
    ReasoningEffort,
)
from app.services.ai_usage import get_legacy_ai_usage_ledger
from app.services.mock_watchlist import mock_watchlist_service
from app.services.portfolio import portfolio_service
from app.services.watchlist import WatchlistService
from kabuhandan_hojo.services.securities import SecurityService


logger = logging.getLogger(__name__)

TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")
DATA_DIR = REPO_ROOT / "data"
AI_REVIEW_HISTORY_PATH = DATA_DIR / "ai_review_history.json"
AI_REVIEW_CACHE_PATH = DATA_DIR / "ai_review_cache.json"

JUDGEMENT_LABELS = {
    "hold": "保有継続",
    "buy_more_candidate": "買増し候補",
    "take_profit_candidate": "一部利確候補",
    "reduce_risk": "リスク低減",
    "watch": "様子見",
    "avoid_new_buy": "新規買い見送り",
    "urgent_review": "緊急確認",
}

MODE_LABELS = {
    "scanner": "軽量スキャン",
    "analyst": "個別詳細分析",
    "judge": "全体売買判断",
    "critical": "重要局面分析",
    "prompt_only": "ChatGPT投入用プロンプト生成",
}

STOCK_REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "generated_at": {"type": "string"},
        "mode": {"type": "string", "enum": ["scanner", "analyst", "judge", "critical", "prompt_only"]},
        "portfolio_summary": {
            "type": "object",
            "properties": {
                "overall_view": {"type": "string"},
                "portfolio_summary": {"type": "string"},
                "market_temperature": {"type": "string"},
                "overall_risk": {"type": "string", "enum": ["low", "medium", "high"]},
                "buy_candidates": {"type": "array", "items": {"type": "string"}},
                "sell_or_reduce_candidates": {"type": "array", "items": {"type": "string"}},
                "hold_priority": {"type": "array", "items": {"type": "string"}},
                "cash_allocation_view": {"type": "string"},
                "concentration_risk": {"type": "string"},
                "theme_exposure": {"type": "array", "items": {"type": "string"}},
                "action_plan_today": {"type": "array", "items": {"type": "string"}},
                "invalidation_for_portfolio": {"type": "string"},
                "top_risks": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "overall_view",
                "portfolio_summary",
                "market_temperature",
                "overall_risk",
                "buy_candidates",
                "sell_or_reduce_candidates",
                "hold_priority",
                "cash_allocation_view",
                "concentration_risk",
                "theme_exposure",
                "action_plan_today",
                "invalidation_for_portfolio",
                "top_risks",
            ],
            "additionalProperties": False,
        },
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "name": {"type": "string"},
                    "judgement": {"type": "string", "enum": list(JUDGEMENT_LABELS.keys())},
                    "judgement_label": {"type": "string"},
                    "confidence": {"type": "number"},
                    "short_reason": {"type": "string"},
                    "watch_points": {"type": "array", "items": {"type": "string"}},
                    "risk_flags": {"type": "array", "items": {"type": "string"}},
                    "needs_detail_analysis": {"type": "boolean"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "technical_view": {"type": "string"},
                    "news_view": {"type": "string"},
                    "market_context_view": {"type": "string"},
                    "supply_demand_view": {"type": "string"},
                    "holder_action": {"type": "string"},
                    "buy_more_condition": {"type": "string"},
                    "take_profit_condition": {"type": "string"},
                    "stop_or_reduce_condition": {"type": "string"},
                    "invalidation": {"type": "string"},
                    "next_price_levels": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "bullish_case": {"type": "string"},
                    "bearish_case": {"type": "string"},
                    "base_case": {"type": "string"},
                    "expected_value_view": {"type": "string"},
                    "position_size_risk": {"type": "string"},
                    "event_risk": {"type": "string"},
                    "gap_risk": {"type": "string"},
                    "decision_deadline": {"type": "string"},
                    "what_would_change_my_mind": {"type": "string"},
                    "final_recommendation_for_holder": {"type": "string"},
                    "uncertainty_notes": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                            "required": ["title", "url"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "ticker",
                    "name",
                    "judgement",
                    "judgement_label",
                    "confidence",
                    "short_reason",
                    "watch_points",
                    "risk_flags",
                    "needs_detail_analysis",
                    "key_points",
                    "technical_view",
                    "news_view",
                    "market_context_view",
                    "supply_demand_view",
                    "holder_action",
                    "buy_more_condition",
                    "take_profit_condition",
                    "stop_or_reduce_condition",
                    "invalidation",
                    "next_price_levels",
                    "risks",
                    "bullish_case",
                    "bearish_case",
                    "base_case",
                    "expected_value_view",
                    "position_size_risk",
                    "event_risk",
                    "gap_risk",
                    "decision_deadline",
                    "what_would_change_my_mind",
                    "final_recommendation_for_holder",
                    "uncertainty_notes",
                    "sources",
                ],
                "additionalProperties": False,
            },
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
        "raw_model_output": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["generated_at", "mode", "portfolio_summary", "stocks", "sources", "warnings", "raw_model_output"],
    "additionalProperties": False,
}

# Keep the legacy exported schema aligned with the active Prompt Builder schema.
STOCK_REVIEW_JSON_SCHEMA = get_output_schema_for_mode("judge")


class PortfolioAiReviewService:
    """Resolve targets, build prompt context, and call OpenAI safely."""

    def __init__(self) -> None:
        self.security_service = SecurityService()
        self.watchlist_service = WatchlistService()

    def review(
        self,
        payload: PortfolioAiReviewRequest,
        *,
        session: Session | None,
    ) -> PortfolioAiReviewResponse:
        holdings, holdings_source = self._resolve_holdings(payload, session=session)
        candidates = self._resolve_candidates(payload, session=session)
        target_count = len(holdings) + len(candidates)
        settings = get_settings()
        max_stocks = settings.openai_max_stocks_per_request
        if target_count > max_stocks:
            return self._error_response(
                status="target_limit_exceeded",
                message=f"1回あたりのAI分析対象は最大 {max_stocks} 銘柄です。対象を絞ってください。",
                options=payload,
                holdings=holdings,
                candidates=candidates,
                market_snapshots=[],
                holdings_source=holdings_source,
            )

        target_tickers = [holding.ticker for holding in holdings] + [candidate.ticker for candidate in candidates]
        market_snapshots = [self.get_market_snapshot(ticker, session=session) for ticker in dict.fromkeys(target_tickers)]
        return self.analyze_portfolio_with_openai(
            holdings=holdings,
            candidates=candidates,
            market_snapshots=market_snapshots,
            options=payload,
            holdings_source=holdings_source,
        )

    def get_holdings(self, session: Session | None) -> list[PortfolioAiHolding]:
        """Return active DB holdings when the portfolio DB is available."""

        if session is None:
            return []
        return [
            PortfolioAiHolding(
                ticker=item.ticker_code,
                name=item.name,
                market=item.market,
                quantity=float(item.quantity),
                average_price=float(item.average_cost) if item.average_cost is not None else None,
            )
            for item in portfolio_service.list_items(session)
        ]

    def get_watchlist(self, session: Session | None) -> list[PortfolioAiHolding]:
        """Return active watchlist entries as zero-quantity review targets."""

        if get_settings().app_use_mock:
            return [
                PortfolioAiHolding(
                    ticker=item.ticker_code,
                    name=item.name,
                    market=item.market,
                    quantity=0,
                    average_price=None,
                )
                for item in mock_watchlist_service.list_items()
            ]
        if session is None:
            return []
        return [
            PortfolioAiHolding(
                ticker=item.ticker_code,
                name=item.name,
                market=item.market,
                quantity=0,
                average_price=None,
            )
            for item in self.watchlist_service.list_items(session)
        ]

    def get_mock_holdings(self) -> list[PortfolioAiHolding]:
        """Return deterministic test holdings for local UI verification."""

        return [
            PortfolioAiHolding(
                ticker="7011",
                name="三菱重工業",
                market="TSE",
                quantity=100,
                average_price=2900,
                position_type="core_and_short",
            ),
            PortfolioAiHolding(
                ticker="6758",
                name="ソニーグループ",
                market="TSE",
                quantity=100,
                average_price=13500,
                position_type="mid",
            ),
            PortfolioAiHolding(
                ticker="9984",
                name="ソフトバンクグループ",
                market="TSE",
                quantity=100,
                average_price=8500,
                position_type="short",
            ),
            PortfolioAiHolding(ticker="7974", name="任天堂", market="TSE", quantity=100, average_price=7200),
            PortfolioAiHolding(ticker="4063", name="信越化学工業", market="TSE", quantity=100, average_price=7400),
            PortfolioAiHolding(ticker="6857", name="アドバンテスト", market="TSE", quantity=100, average_price=8500),
            PortfolioAiHolding(
                ticker="3397",
                name="トリドールではなく、必要なら実際の監視銘柄に差し替え",
                market="TSE",
                quantity=0,
                average_price=None,
            ),
        ]

    def get_mock_candidates(self) -> list[PortfolioAiCandidate]:
        """Return deterministic candidate stocks for local AI review checks."""

        return [
            PortfolioAiCandidate(
                ticker="6857",
                name="アドバンテスト",
                market="TSE",
                candidate_reason="半導体テーマの主力候補",
                watch_condition="出来高を伴う上抜け、または押し目形成",
            ),
            PortfolioAiCandidate(
                ticker="4063",
                name="信越化学工業",
                market="TSE",
                candidate_reason="半導体・素材関連の押し目候補",
                watch_condition="25日線回復または決算材料確認",
            ),
        ]

    def get_market_snapshot(self, ticker: str, *, session: Session | None = None) -> PortfolioMarketSnapshot:
        """Return a replaceable market snapshot backed by stored local data when available."""

        snapshot = PortfolioMarketSnapshot(ticker=ticker)
        if session is None:
            return snapshot

        prices = self.security_service.latest_prices(session, ticker, limit=80)
        if prices:
            latest = prices[-1]
            previous = prices[-2] if len(prices) >= 2 else None
            snapshot.price = self._to_float(latest.close_price)
            snapshot.volume = int(latest.volume) if latest.volume is not None else None
            if previous is not None and previous.close_price not in {None, Decimal("0")}:
                snapshot.change_rate = self._to_float(
                    ((latest.close_price - previous.close_price) / previous.close_price * Decimal("100")).quantize(Decimal("0.01"))
                )
            lows = [self._to_float(price.low_price) for price in prices[-25:] if price.low_price is not None]
            highs = [self._to_float(price.high_price) for price in prices[-25:] if price.high_price is not None]
            snapshot.support_levels = sorted(set(lows))[:3]
            snapshot.resistance_levels = sorted(set(highs), reverse=True)[:3]

        feature = self.security_service.latest_feature(session, ticker)
        if feature is not None:
            snapshot.ma_5 = self._to_float(feature.sma_5)
            snapshot.ma_25 = self._to_float(feature.sma_25)
            snapshot.ma_75 = self._to_float(feature.sma_75)
            snapshot.rsi = self._to_float(feature.rsi_14)
            snapshot.macd = self._to_float(feature.macd_line)
            snapshot.upper_wick_ratio = self._to_float(feature.upper_wick_ratio)
            snapshot.lower_wick_ratio = self._to_float(feature.lower_wick_ratio)
            snapshot.body_ratio = self._to_float(feature.body_ratio)
            snapshot.close_position_ratio = self._to_float(feature.close_position_ratio)

        flow = self.security_service.latest_flow(session, ticker)
        if flow is not None:
            snapshot.credit_ratio = self._to_float(flow.credit_ratio)

        events = self.security_service.recent_events(session, ticker, limit=3)
        snapshot.recent_news = [event.summary_text for event in events]
        return snapshot

    def get_technical_snapshot(self, ticker: str, *, session: Session | None = None) -> PortfolioMarketSnapshot:
        """Return technical fields through the same snapshot contract."""

        return self.get_market_snapshot(ticker, session=session)

    def get_news_snapshot(self, ticker: str, *, session: Session | None = None) -> list[str]:
        """Return recent locally stored event summaries."""

        if session is None:
            return []
        return [event.summary_text for event in self.security_service.recent_events(session, ticker, limit=5)]

    def build_ai_review_payload(
        self,
        *,
        holdings: list[PortfolioAiHolding],
        market_snapshots: list[PortfolioMarketSnapshot],
        options: PortfolioAiReviewRequest,
        model: str,
        reasoning_effort: ReasoningEffort,
        include_web_search: bool,
        max_web_search_calls: int,
    ) -> dict[str, Any]:
        """Build the compact JSON payload sent to OpenAI or manual prompt generation."""

        return {
            "generated_at": self._tokyo_now().isoformat(),
            "mode": options.mode,
            "mode_label": MODE_LABELS[options.mode],
            "target": options.target,
            "analysis_mode": options.analysis_mode,
            "risk_preference": options.risk_preference,
            "verbosity": options.verbosity,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "include_web_search": include_web_search,
            "max_web_search_calls": max_web_search_calls,
            "holdings": [holding.model_dump(mode="json") for holding in holdings],
            "market_snapshots": [snapshot.model_dump(mode="json") for snapshot in market_snapshots],
            "judgement_labels": JUDGEMENT_LABELS,
        }

    def analyze_portfolio_with_openai(
        self,
        *,
        holdings: list[PortfolioAiHolding],
        market_snapshots: list[PortfolioMarketSnapshot],
        options: PortfolioAiReviewRequest,
        candidates: list[PortfolioAiCandidate] | None = None,
        holdings_source: HoldingsSource = "none",
    ) -> PortfolioAiReviewResponse:
        """Analyze targets through OpenAI, prompt generation, mock response, or cache."""

        candidates = candidates or []
        settings = get_settings()
        model = self._model_for_mode(options.mode)
        reasoning_effort = options.reasoning_effort or self._reasoning_for_mode(options.mode)
        include_web_search, web_warnings = self._resolve_web_search(options)
        max_web_search_calls = self._resolve_max_web_search_calls(options)
        builder_options = options.model_copy(
            update={
                "include_web_search": include_web_search,
                "max_web_search_calls": max_web_search_calls,
            }
        )
        prompt_bundle = build_stock_analysis_prompt(
            builder_options,
            holdings=holdings,
            candidates=candidates,
            market_snapshots=market_snapshots,
            news_snapshots={},
            technical_snapshots={snapshot.ticker: snapshot.model_dump(mode="json") for snapshot in market_snapshots},
            portfolio_snapshot={},
        )
        warnings = self._cost_warnings(options, holdings, candidates) + web_warnings + list(prompt_bundle["warnings"])
        estimated_cost_usd = estimate_openai_cost(
            options.mode,
            len(holdings) + len(candidates),
            include_web_search,
            max_web_search_calls,
        )
        request_payload = {
            **prompt_bundle["prompt_payload"],
            "model": model,
            "reasoning_effort": reasoning_effort,
            "mode_label": MODE_LABELS[options.mode],
            "judgement_labels": JUDGEMENT_LABELS,
            "include_web_search": include_web_search,
            "max_web_search_calls": max_web_search_calls,
        }
        prompt_bundle["prompt_payload"] = request_payload

        if not holdings and not candidates:
            return self._error_response(
                status="no_holdings",
                message="AI分析対象の銘柄がありません。",
                options=options,
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                holdings_source=holdings_source,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )

        if options.mode == "prompt_only":
            response = self._prompt_only_response(
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                options=options,
                holdings_source=holdings_source,
                model=model,
                reasoning_effort=reasoning_effort,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )
            if options.save_result:
                self.save_ai_review_result(response)
            return response

        if self._should_force_mock_response(options, holdings_source):
            mock_warnings = [
                *warnings,
                "mock対象のためOpenAI APIは呼びません。実APIで分析する場合は対象を保有銘柄/監視銘柄/選択銘柄に切り替えてください。",
            ]
            response = self._mock_response(
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                options=options,
                holdings_source=holdings_source,
                include_web_search=False,
                model=model,
                reasoning_effort=reasoning_effort,
                estimated_cost_usd=0,
                warnings=mock_warnings,
                request_payload={**request_payload, "include_web_search": False, "mock_forced_no_api": True},
            )
            if options.save_result:
                self.save_ai_review_result(response)
            return response

        cache_key = self._cache_key(request_payload)
        if options.use_cache and not options.mock_response:
            cached = self._load_cached_response(cache_key)
            if cached is not None:
                cached.cache_hit = True
                cached.warnings = [*cached.warnings, "同一入力の前回分析結果をキャッシュから再表示しています。"]
                return cached

        if options.mock_response:
            response = self._mock_response(
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                options=options,
                holdings_source=holdings_source,
                include_web_search=include_web_search,
                model=model,
                reasoning_effort=reasoning_effort,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )
            if options.save_result:
                self.save_ai_review_result(response)
            return response

        if not settings.openai_api_key:
            return self._error_response(
                status="missing_api_key",
                message="OPENAI_API_KEY が未設定です。.env または起動環境に設定してください。",
                options=options,
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                holdings_source=holdings_source,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )

        if not self._can_run_today(settings.openai_daily_request_limit):
            return self._error_response(
                status="daily_limit_exceeded",
                message=f"1日あたりのAI実行回数上限 {settings.openai_daily_request_limit} 回に達しています。",
                options=options,
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                holdings_source=holdings_source,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )

        try:
            openai_result = self._call_openai(
                prompt_payload=request_payload,
                system_prompt=prompt_bundle["system_prompt"],
                user_prompt=prompt_bundle["user_prompt"],
                output_schema=prompt_bundle["output_schema"],
                options=options,
                api_key=settings.openai_api_key,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                max_web_search_calls=max_web_search_calls,
            )
        except ImportError:
            return self._error_response(
                status="openai_sdk_missing",
                message="openai Python SDK が未導入です。requirements を更新して依存関係をインストールしてください。",
                options=options,
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                holdings_source=holdings_source,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )
        except Exception as exc:  # pragma: no cover - real API failure path
            logger.warning("OpenAI stock review failed: %s", exc.__class__.__name__)
            return self._error_response(
                status="openai_api_error",
                message=self._openai_error_message(exc),
                options=options,
                holdings=holdings,
                candidates=candidates,
                market_snapshots=market_snapshots,
                holdings_source=holdings_source,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                estimated_cost_usd=estimated_cost_usd,
                warnings=warnings,
                request_payload=request_payload,
            )

        if isinstance(openai_result, tuple):
            raw_output, usage = openai_result
        else:
            raw_output = openai_result
            usage = PortfolioAiUsage(api_calls=1)
        usage = self._with_minimum_api_calls(usage)
        self._record_provider_usage(model=model, usage=usage)

        try:
            response = self.parse_ai_review_result(raw_output, options=options)
        except ValueError:
            if len(raw_output.strip()) >= 200:
                try:
                    repaired_output, repair_usage = self._repair_model_output_json(
                        raw_output=raw_output,
                        options=options,
                        api_key=settings.openai_api_key,
                        model=model,
                        output_schema=prompt_bundle["output_schema"],
                    )
                    repair_usage = self._with_minimum_api_calls(repair_usage)
                    self._record_provider_usage(model=model, usage=repair_usage)
                    usage = self._merge_usage(usage, repair_usage)
                    response = self.parse_ai_review_result(repaired_output, options=options)
                    warnings.extend(
                        [
                            "OpenAI応答がJSONとして解析できなかったため、Web検索を追加しないJSON整形リトライを実行しました。",
                            "整形リトライ結果です。重要判断はsourcesと検証ラベルを確認してください。",
                        ]
                    )
                except Exception:
                    if self._should_display_raw_fallback(raw_output):
                        response = self._raw_output_fallback_response(
                            raw_output=raw_output,
                            options=options,
                            holdings=holdings,
                            candidates=candidates,
                            market_snapshots=market_snapshots,
                            holdings_source=holdings_source,
                            model=model,
                            reasoning_effort=reasoning_effort,
                            include_web_search=include_web_search,
                            web_search_policy=prompt_bundle["web_search_policy"],
                            estimated_cost_usd=estimated_cost_usd,
                            warnings=[
                                *warnings,
                                "OpenAI応答をJSONとして解析できず、JSON整形リトライにも失敗しました。生応答をそのまま表示します。",
                            ],
                            request_payload=request_payload,
                            usage=usage,
                        )
                    else:
                        return self._error_response(
                            status="json_parse_failed",
                            message="OpenAI応答を指定JSONとして解析できませんでした。",
                            options=options,
                            holdings=holdings,
                            candidates=candidates,
                            market_snapshots=market_snapshots,
                            holdings_source=holdings_source,
                            model=model,
                            reasoning_effort=reasoning_effort,
                            include_web_search=include_web_search,
                            estimated_cost_usd=estimated_cost_usd,
                            warnings=warnings,
                            request_payload=request_payload,
                            raw_model_output=raw_output,
                            usage=usage,
                        )
            else:
                if self._should_display_raw_fallback(raw_output):
                    response = self._raw_output_fallback_response(
                        raw_output=raw_output,
                        options=options,
                        holdings=holdings,
                        candidates=candidates,
                        market_snapshots=market_snapshots,
                        holdings_source=holdings_source,
                        model=model,
                        reasoning_effort=reasoning_effort,
                        include_web_search=include_web_search,
                        web_search_policy=prompt_bundle["web_search_policy"],
                        estimated_cost_usd=estimated_cost_usd,
                        warnings=[
                            *warnings,
                            "OpenAI応答をJSONとして解析できませんでした。生応答をそのまま表示します。",
                        ],
                        request_payload=request_payload,
                        usage=usage,
                    )
                else:
                    return self._error_response(
                        status="json_parse_failed",
                        message="OpenAI応答を指定JSONとして解析できませんでした。",
                        options=options,
                        holdings=holdings,
                        candidates=candidates,
                        market_snapshots=market_snapshots,
                        holdings_source=holdings_source,
                        model=model,
                        reasoning_effort=reasoning_effort,
                        include_web_search=include_web_search,
                        estimated_cost_usd=estimated_cost_usd,
                        warnings=warnings,
                        request_payload=request_payload,
                        raw_model_output=raw_output,
                        usage=usage,
                    )

        response.status = "success"
        response.error = None
        response.mode = options.mode
        response.analysis_mode = options.analysis_mode
        response.holdings_source = holdings_source
        response.web_search_used = include_web_search
        response.include_web_search = include_web_search
        response.web_search_policy = prompt_bundle["web_search_policy"]
        response.mock_response = False
        response.model = model
        response.reasoning_effort = reasoning_effort
        response.estimated_cost_usd = estimated_cost_usd
        response.actual_usage = usage
        if not response.raw_model_output:
            response.raw_model_output = None
        validation_warnings = validate_stock_analysis_response(
            response.model_dump(mode="json"),
            options.mode,
        )
        response.warnings = [*warnings, *validation_warnings, *response.warnings]
        response.holdings_snapshot = holdings
        response.candidates_snapshot = candidates
        response.market_snapshot = market_snapshots
        response.request_payload = request_payload
        self._increment_daily_usage()
        if options.save_result:
            self.save_ai_review_result(response)
            self._save_cached_response(cache_key, response)
        return response

    def call_open_ai_for_stock_review(
        self,
        *,
        prompt_payload: dict[str, Any],
        options: PortfolioAiReviewRequest,
        api_key: str,
        model: str,
        reasoning_effort: ReasoningEffort,
        include_web_search: bool,
        max_web_search_calls: int,
    ) -> tuple[str, PortfolioAiUsage]:
        """Call OpenAI Responses API and return raw text plus usage."""

        return self._call_openai(
            prompt_payload=prompt_payload,
            options=options,
            api_key=api_key,
            model=model,
            reasoning_effort=reasoning_effort,
            include_web_search=include_web_search,
            max_web_search_calls=max_web_search_calls,
        )

    def parse_ai_review_result(
        self,
        raw_output: str,
        *,
        options: PortfolioAiReviewRequest | None = None,
    ) -> PortfolioAiReviewResponse:
        """Parse and validate JSON returned by the model."""

        text = self._extract_json_text(self._strip_json_fence(raw_output))
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("model output was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("model output root was not an object")
        normalized = self._normalize_model_payload(payload, options=options)
        return PortfolioAiReviewResponse.model_validate(normalized)

    def save_ai_review_result(self, response: PortfolioAiReviewResponse) -> None:
        """Append AI analysis result to local JSON history."""

        self._append_json_list(AI_REVIEW_HISTORY_PATH, response.model_dump(mode="json"), limit=100)

    def _resolve_holdings(
        self,
        payload: PortfolioAiReviewRequest,
        *,
        session: Session | None,
    ) -> tuple[list[PortfolioAiHolding], HoldingsSource]:
        if payload.holdings:
            return self._filter_tickers(payload.holdings, payload.tickers), "request"
        if payload.target == "candidates":
            return [], "candidates"
        if payload.use_mock_holdings or payload.target == "mock":
            return self._filter_tickers(self.get_mock_holdings(), payload.tickers), "mock"
        if payload.target == "watchlist":
            watchlist = self.get_watchlist(session)
            if watchlist:
                return self._filter_tickers(watchlist, payload.tickers), "watchlist"
            return self._filter_tickers(self.get_mock_holdings(), payload.tickers), "mock"
        if payload.target == "selected":
            selected = self._resolve_selected_tickers(payload.tickers, session=session)
            return selected, "request" if selected else "none"

        db_holdings = self.get_holdings(session)
        if db_holdings:
            return self._filter_tickers(db_holdings, payload.tickers), "database"
        return self._filter_tickers(self.get_mock_holdings(), payload.tickers), "mock"

    def _resolve_candidates(
        self,
        payload: PortfolioAiReviewRequest,
        *,
        session: Session | None,
    ) -> list[PortfolioAiCandidate]:
        if payload.candidates:
            return self._filter_candidate_tickers(payload.candidates, payload.tickers)
        if payload.target in {"candidates", "mock"}:
            return self._filter_candidate_tickers(self.get_mock_candidates(), payload.tickers)
        if payload.target == "selected":
            candidate_lookup = {candidate.ticker: candidate for candidate in self.get_mock_candidates()}
            selected = [candidate_lookup[ticker] for ticker in payload.tickers if ticker in candidate_lookup]
            return self._filter_candidate_tickers(selected, payload.tickers)
        return []

    def _resolve_selected_tickers(self, tickers: list[str], *, session: Session | None) -> list[PortfolioAiHolding]:
        if not tickers:
            return []
        known: dict[str, PortfolioAiHolding] = {}
        for holding in [*self.get_holdings(session), *self.get_watchlist(session), *self.get_mock_holdings()]:
            known.setdefault(holding.ticker, holding)
        for candidate in self.get_mock_candidates():
            known.setdefault(
                candidate.ticker,
                PortfolioAiHolding(
                    ticker=candidate.ticker,
                    name=candidate.name,
                    market=candidate.market,
                    quantity=0,
                    average_price=None,
                ),
            )
        return [
            known.get(ticker)
            or PortfolioAiHolding(ticker=ticker, name=ticker, market="TSE", quantity=0, average_price=None)
            for ticker in tickers
        ]

    def _filter_tickers(self, holdings: list[PortfolioAiHolding], tickers: list[str]) -> list[PortfolioAiHolding]:
        if not tickers:
            return holdings
        wanted = {ticker.strip() for ticker in tickers if ticker.strip()}
        return [holding for holding in holdings if holding.ticker in wanted]

    def _filter_candidate_tickers(
        self,
        candidates: list[PortfolioAiCandidate],
        tickers: list[str],
    ) -> list[PortfolioAiCandidate]:
        if not tickers:
            return candidates
        wanted = {ticker.strip() for ticker in tickers if ticker.strip()}
        return [candidate for candidate in candidates if candidate.ticker in wanted]

    def _call_openai(
        self,
        *,
        prompt_payload: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
        holdings: list[PortfolioAiHolding] | None = None,
        market_snapshots: list[PortfolioMarketSnapshot] | None = None,
        options: PortfolioAiReviewRequest,
        api_key: str,
        model: str,
        reasoning_effort: ReasoningEffort,
        include_web_search: bool | None = None,
        max_web_search_calls: int | None = None,
    ) -> tuple[str, PortfolioAiUsage]:
        from openai import OpenAI

        if include_web_search is None:
            include_web_search, _ = self._resolve_web_search(options)
        if max_web_search_calls is None:
            max_web_search_calls = options.max_web_search_calls
        if prompt_payload is None:
            prompt_payload = self.build_ai_review_payload(
                holdings=holdings or [],
                market_snapshots=market_snapshots or [],
                options=options,
                model=model,
                reasoning_effort=reasoning_effort,
                include_web_search=include_web_search,
                max_web_search_calls=max_web_search_calls,
            )
        if system_prompt is None or user_prompt is None:
            prompt_bundle = build_stock_analysis_prompt(
                options,
                holdings=holdings or [],
                candidates=[],
                market_snapshots=market_snapshots or [],
                news_snapshots={},
                technical_snapshots={},
                portfolio_snapshot={},
            )
            system_prompt = system_prompt or prompt_bundle["system_prompt"]
            user_prompt = user_prompt or prompt_bundle["user_prompt"]
            output_schema = output_schema or prompt_bundle["output_schema"]
        output_schema = output_schema or get_output_schema_for_mode(options.mode)

        client = OpenAI(api_key=api_key)
        request_kwargs: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "reasoning": {"effort": reasoning_effort},
        }
        if include_web_search and max_web_search_calls > 0:
            request_kwargs["tools"] = [{"type": "web_search"}]
            request_kwargs["include"] = ["web_search_call.action.sources"]
        request_kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": "stock_ai_review",
                "schema": output_schema,
                "strict": False,
            }
        }

        response = client.responses.create(**request_kwargs)
        usage = self._extract_usage(response, include_web_search=include_web_search, max_web_search_calls=max_web_search_calls)
        return self._extract_response_text(response), usage

    def _repair_model_output_json(
        self,
        *,
        raw_output: str,
        options: PortfolioAiReviewRequest,
        api_key: str,
        model: str,
        output_schema: dict[str, Any],
    ) -> tuple[str, PortfolioAiUsage]:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "あなたはJSON整形専用の変換器です。新しい事実、株価、ニュース、投資判断は追加せず、"
                        "直前のOpenAI応答に含まれる内容だけを、指定JSON Schemaに合うJSONへ変換してください。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "次の応答をJSONへ変換してください。JSON以外の文章は返さないでください。\n\n"
                        + raw_output[:20000]
                    ),
                },
            ],
            reasoning={"effort": "low"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "stock_ai_review_repair",
                    "schema": output_schema,
                    "strict": False,
                }
            },
        )
        usage = self._extract_usage(response, include_web_search=False, max_web_search_calls=0)
        return self._extract_response_text(response), usage

    def _prompt_only_response(
        self,
        *,
        holdings: list[PortfolioAiHolding],
        candidates: list[PortfolioAiCandidate],
        market_snapshots: list[PortfolioMarketSnapshot],
        options: PortfolioAiReviewRequest,
        holdings_source: HoldingsSource,
        model: str,
        reasoning_effort: ReasoningEffort,
        estimated_cost_usd: float,
        warnings: list[str],
        request_payload: dict[str, Any],
    ) -> PortfolioAiReviewResponse:
        manual_prompt = build_prompt_only_text(
            options,
            holdings=holdings,
            candidates=candidates,
            market_snapshots=market_snapshots,
            news_snapshots={},
            technical_snapshots={snapshot.ticker: snapshot.model_dump(mode="json") for snapshot in market_snapshots},
            portfolio_snapshot={},
        )
        prompt_stocks = [
            PortfolioAiStockAnalysis(
                ticker=holding.ticker,
                name=holding.name,
                judgement="watch",
                judgement_label=JUDGEMENT_LABELS["watch"],
                confidence=0,
                short_reason="prompt_onlyのためAI分析は未実行です。",
                key_points=["ChatGPT投入用プロンプトを生成済みです。"],
            )
            for holding in holdings
        ]
        prompt_stocks.extend(
            PortfolioAiStockAnalysis(
                ticker=candidate.ticker,
                name=candidate.name,
                judgement="watch",
                judgement_label=JUDGEMENT_LABELS["watch"],
                confidence=0,
                short_reason="prompt_onlyのためAI分析は未実行です。",
                key_points=[candidate.candidate_reason or "狙い中銘柄としてプロンプトに含めました。"],
            )
            for candidate in candidates
        )
        return PortfolioAiReviewResponse(
            generated_at=self._tokyo_now(),
            mode=options.mode,
            analysis_mode=options.analysis_mode,
            model=model,
            reasoning_effort=reasoning_effort,
            include_web_search=False,
            web_search_policy="manual_only",
            estimated_cost_usd=estimated_cost_usd,
            actual_usage=PortfolioAiUsage(),
            portfolio_summary=PortfolioAiSummary(
                overall_view="OpenAI APIを呼ばず、ChatGPTへ手動投入するためのプロンプトを生成しました。",
                portfolio_summary="生成したプロンプトをコピーして、ChatGPTへ手動で貼り付けてください。自動投稿や回答取得は行いません。",
                overall_risk="medium",
                market_temperature="prompt_only",
            ),
            stocks=prompt_stocks,
            action_plan=["生成したプロンプトをコピーしてChatGPTへ手動投入する。"],
            warnings=warnings,
            manual_prompt=manual_prompt,
            status="success",
            holdings_source=holdings_source,
            web_search_used=False,
            mock_response=False,
            holdings_snapshot=holdings,
            candidates_snapshot=candidates,
            market_snapshot=market_snapshots,
            request_payload=request_payload,
        )

    def _build_mock_long_term_carry_check(self, index: int) -> LongTermCarryCheck:
        decisions = [
            "long_term_hold_ok",
            "hold_if_reduced",
            "hold_with_alerts",
            "reduce_before_event",
            "not_suitable_without_daily_monitoring",
            "exit_or_rotate_candidate",
        ]
        decision = decisions[index % len(decisions)]
        risk_by_decision = {
            "long_term_hold_ok": "low",
            "hold_if_reduced": "medium",
            "hold_with_alerts": "medium",
            "reduce_before_event": "high",
            "not_suitable_without_daily_monitoring": "high",
            "exit_or_rotate_candidate": "high",
        }
        can_hold_by_decision = {
            "long_term_hold_ok": "yes",
            "hold_if_reduced": "with_reduction",
            "hold_with_alerts": "with_alerts",
            "reduce_before_event": "before_event_reduce",
            "not_suitable_without_daily_monitoring": "no",
            "exit_or_rotate_candidate": "no",
        }
        core_by_decision = {
            "long_term_hold_ok": "high",
            "hold_if_reduced": "medium",
            "hold_with_alerts": "medium",
            "reduce_before_event": "medium",
            "not_suitable_without_daily_monitoring": "low",
            "exit_or_rotate_candidate": "low",
        }
        risk = risk_by_decision[decision]
        return LongTermCarryCheck(
            can_hold_without_daily_monitoring=can_hold_by_decision[decision],  # type: ignore[arg-type]
            non_monitoring_hold_risk=risk,  # type: ignore[arg-type]
            business_thesis_strength="normal" if risk != "high" else "weak",
            event_risk_while_unmonitored="high" if decision in {"reduce_before_event", "not_suitable_without_daily_monitoring"} else "medium",
            liquidity_risk="medium",
            volatility_risk=risk,  # type: ignore[arg-type]
            position_size_view="mock表示です。毎日見られない場合は短期玉を外し、コア玉だけ残せるかを確認します。",
            core_position_suitability=core_by_decision[decision],  # type: ignore[arg-type]
            short_term_position_should_be_removed=decision != "long_term_hold_ok",
            required_alerts=["25日線割れ", "決算予定日", "出来高急減"],
            must_check_dates_or_events=["次回決算", "重要IR", "月次発表"],
            reduce_before_events=["決算発表"] if decision in {"reduce_before_event", "not_suitable_without_daily_monitoring"} else [],
            stop_or_reduce_conditions=["25日線明確割れ", "信用需給悪化", "想定材料の否定"],
            long_term_thesis_break_conditions=["売上成長鈍化", "利益率悪化", "テーマが業績に落ちない"],
            monitoring_interval_view=[
                LongTermCarryMonitoringIntervalView(
                    interval="1_business_day",
                    holdability="ok" if risk == "low" else "with_alerts",
                    required_conditions=["逆指値または価格アラート"],
                    pre_actions=["短期玉のサイズ確認"],
                ),
                LongTermCarryMonitoringIntervalView(
                    interval="3_business_days",
                    holdability="with_alerts" if risk != "high" else "with_reduction",
                    required_conditions=["決算予定なし", "地合い急変アラート"],
                    pre_actions=["保有サイズを確認"],
                ),
                LongTermCarryMonitoringIntervalView(
                    interval="1_week",
                    holdability="with_reduction" if risk == "high" else "with_alerts",
                    required_conditions=["重要イベントを跨がない"],
                    pre_actions=["短期玉を外す"],
                ),
                LongTermCarryMonitoringIntervalView(
                    interval="2_weeks",
                    holdability="not_recommended" if risk == "high" else "with_reduction",
                    required_conditions=["事業仮説が強い", "流動性が保たれている"],
                    pre_actions=["コア玉だけ残す"],
                ),
                LongTermCarryMonitoringIntervalView(
                    interval="1_month_or_more",
                    holdability="ok" if decision == "long_term_hold_ok" else "not_recommended",
                    required_conditions=["中長期仮説が価格勢いだけではない"],
                    pre_actions=["決算前の見直し予定を置く"],
                ),
            ],
            final_long_term_carry_decision=decision,  # type: ignore[arg-type]
            final_note="mockのため実分析ではありません。非監視期間リスク表示の確認用です。",
        )

    def _mock_response(
        self,
        *,
        holdings: list[PortfolioAiHolding],
        candidates: list[PortfolioAiCandidate],
        market_snapshots: list[PortfolioMarketSnapshot],
        options: PortfolioAiReviewRequest,
        holdings_source: HoldingsSource,
        include_web_search: bool,
        model: str,
        reasoning_effort: ReasoningEffort,
        estimated_cost_usd: float,
        warnings: list[str],
        request_payload: dict[str, Any],
    ) -> PortfolioAiReviewResponse:
        judgements = list(JUDGEMENT_LABELS.keys())
        stocks: list[PortfolioAiStockAnalysis] = []
        target_items: list[tuple[str, str, str]] = [
            (holding.ticker, holding.name, holding.position_type or "保有銘柄") for holding in holdings
        ]
        target_items.extend(
            (
                candidate.ticker,
                candidate.name,
                candidate.candidate_reason or "狙い中銘柄",
            )
            for candidate in candidates
        )
        for index, (ticker, name, target_note) in enumerate(target_items):
            judgement = judgements[index % len(judgements)]
            label = JUDGEMENT_LABELS[judgement]
            long_term_carry_check = self._build_mock_long_term_carry_check(index)
            stocks.append(
                PortfolioAiStockAnalysis(
                    ticker=ticker,
                    name=name,
                    judgement=judgement,  # type: ignore[arg-type]
                    judgement_label=label,
                    confidence=round(0.6 + (index % 4) * 0.08, 2),
                    short_reason="mock market snapshotに基づく表示確認用の分類です。",
                    time_horizon_views={
                        "very_short": "様子見",
                        "short": "条件待ち",
                        "mid": "保有/監視",
                        "long": "仮説確認待ち",
                    },
                    key_risks=["最新Web確認なし", "実データ未接続"],
                    watch_points=["25日線との位置", "出来高の増減", "決算・材料の有無"],
                    risk_flags=["地合い悪化", "決算前後のボラティリティ"] if index % 2 else ["根拠弱い"],
                    needs_detail_analysis=options.mode in {"scanner", "critical"} and index % 2 == 0,
                    needs_analyst_mode=options.mode == "scanner" and index % 2 == 0,
                    needs_judge_mode=options.mode == "scanner" and index % 3 == 0,
                    needs_long_term_carry_check=long_term_carry_check.non_monitoring_hold_risk == "high",
                    non_monitoring_hold_risk=long_term_carry_check.non_monitoring_hold_risk,
                    long_term_carry_check=long_term_carry_check,
                    verification_labels=["【U】", "【E】"],
                    key_points=[
                        target_note,
                        "価格API未接続の項目は未取得として扱います。",
                        "材料が確認できない場合は、ニュース要因を断定しません。",
                        "支持線割れ、または上値抵抗突破を次の確認点にします。",
                    ],
                    technical_view="mock snapshotです。実データ接続後はMA、RSI、MACD、髭情報を差し替えます。",
                    news_view=(
                        "Web検索あり設定ですが、mock_responseのためOpenAI APIもWeb検索も呼びません。"
                        if include_web_search
                        else "Web検索なしのmock分析です。材料なしとして扱います。"
                    ),
                    market_context_view="地合いは未取得です。TOPIX/Nikkei225 proxy接続後に市場要因を分離します。",
                    supply_demand_view="信用倍率や出来高比率は未取得です。取得できる項目だけで補助判断します。",
                    holder_action="保有者はポジションサイズを維持し、反証条件に触れたら縮小候補にします。",
                    buy_more_condition="出来高を伴う上抜け、かつ地合い悪化がないこと。",
                    take_profit_condition="短期急騰後に上髭が連続し、材料の追加確認ができないこと。",
                    stop_or_reduce_condition="25日線割れ、または想定材料の否定。",
                    invalidation="直近支持線、または25日移動平均線を明確に割り込むこと。",
                    next_price_levels=["直近高値", "25日移動平均", "直近安値"],
                    risks=["指数反落", "決算前後のギャップ", "出来高不足の上昇"],
                    bullish_case="上昇トレンド継続と出来高増加が確認できる場合。",
                    bearish_case="材料なしの急騰後に出来高減少と上髭が出る場合。",
                    base_case="根拠がそろうまでは様子見を基本にする。",
                    expected_value_view="mockのため期待値は算定しません。",
                    position_size_risk="大型ポジションでは一部利確や逆指値条件を事前に決めます。",
                    event_risk="決算日・開示予定が未取得のため、跨ぎ前に確認が必要です。",
                    gap_risk="材料株化している場合は寄り付きギャップに注意します。",
                    decision_deadline="次の決算または25日線割れまでに再確認。",
                    what_would_change_my_mind="出来高を伴う高値更新、または決算で前提が否定された場合。",
                    final_recommendation_for_holder="断定売買ではなく、反証条件付きで保有判断を整理します。",
                    uncertainty_notes="mock_responseのため実分析ではありません。",
                    execution_plan=["打診、確認、追加の分割を前提にする", "反証条件に触れたら縮小候補にする"],
                    critical_check=["短期反発狙いを中長期保有理由にすり替えない"],
                    sources=[],
                )
            )

        return PortfolioAiReviewResponse(
            generated_at=self._tokyo_now(),
            mode=options.mode,
            analysis_mode=options.analysis_mode,
            model=model,
            reasoning_effort=reasoning_effort,
            include_web_search=include_web_search,
            web_search_policy=get_mode_profile(options.mode).web_search_policy,
            estimated_cost_usd=estimated_cost_usd,
            actual_usage=PortfolioAiUsage(web_search_calls=0),
            input_summary={
                "target": options.target,
                "holdings": len(holdings),
                "candidates": len(candidates),
                "user_hypothesis": options.user_hypothesis or "未入力",
                "position_intent": options.position_intent or "未入力",
            },
            market_summary={"latest_web_check": "mock_responseのため未実行"},
            portfolio_summary=PortfolioAiSummary(
                overall_view=f"{MODE_LABELS[options.mode]} のmock結果です。OpenAI APIは呼んでいません。",
                portfolio_summary="実データ接続後にテクニカル、材料、需給、保有損益を差し替えます。",
                overall_risk="medium",
                market_temperature="mock_without_live_market_data",
                buy_candidates=[stock.ticker for stock in stocks if stock.judgement == "buy_more_candidate"],
                sell_or_reduce_candidates=[
                    stock.ticker for stock in stocks if stock.judgement in {"take_profit_candidate", "reduce_risk"}
                ],
                hold_priority=[stock.ticker for stock in stocks if stock.judgement == "hold"],
                cash_allocation_view="mockのため資金配分は参考表示です。",
                concentration_risk="数量が大きい銘柄から確認してください。",
                theme_exposure=["大型株", "半導体", "ゲーム"],
                non_monitoring_reduce_candidates=[
                    stock.ticker
                    for stock in stocks
                    if stock.long_term_carry_check.final_long_term_carry_decision
                    in {"hold_if_reduced", "reduce_before_event", "not_suitable_without_daily_monitoring"}
                ],
                core_position_candidates=[
                    stock.ticker
                    for stock in stocks
                    if stock.long_term_carry_check.final_long_term_carry_decision == "long_term_hold_ok"
                ],
                exit_or_rotate_candidates=[
                    stock.ticker
                    for stock in stocks
                    if stock.long_term_carry_check.final_long_term_carry_decision == "exit_or_rotate_candidate"
                ],
                action_plan_today=["軽量スキャンで要詳細銘柄を絞る", "重要局面はcritical modeで再確認する"],
                invalidation_for_portfolio="指数急落、主要保有の25日線割れ、決算前提の否定。",
                top_risks=["指数反落", "決算前ボラティリティ", "AI応答ではなくmock結果"],
            ),
            stocks=stocks,
            action_plan=["軽量スキャンで要詳細銘柄を絞る", "重要局面はcritical modeで再確認する"],
            critical_warnings=["mock_responseのため投資判断には使わないでください。"] if options.mode == "critical" else [],
            warnings=warnings,
            status="success",
            holdings_source=holdings_source,
            web_search_used=False,
            mock_response=True,
            holdings_snapshot=holdings,
            candidates_snapshot=candidates,
            market_snapshot=market_snapshots,
            request_payload=request_payload,
        )

    def _raw_output_fallback_response(
        self,
        *,
        raw_output: str,
        options: PortfolioAiReviewRequest,
        holdings: list[PortfolioAiHolding],
        candidates: list[PortfolioAiCandidate],
        market_snapshots: list[PortfolioMarketSnapshot],
        holdings_source: HoldingsSource,
        model: str,
        reasoning_effort: ReasoningEffort,
        include_web_search: bool,
        web_search_policy: str,
        estimated_cost_usd: float,
        warnings: list[str],
        request_payload: dict[str, Any],
        usage: PortfolioAiUsage,
    ) -> PortfolioAiReviewResponse:
        stocks: list[PortfolioAiStockAnalysis] = []
        for holding in holdings:
            stocks.append(
                PortfolioAiStockAnalysis(
                    ticker=holding.ticker,
                    name=holding.name,
                    judgement="watch",
                    judgement_label=JUDGEMENT_LABELS["watch"],
                    confidence=0,
                    short_reason="OpenAI応答は返りましたが、JSON parseできませんでした。下のOpenAI生応答を確認してください。",
                    key_risks=["構造化JSONではないため、カード項目への分解は未実行です。"],
                    verification_labels=["【U】"],
                )
            )
        for candidate in candidates:
            stocks.append(
                PortfolioAiStockAnalysis(
                    ticker=candidate.ticker,
                    name=candidate.name,
                    judgement="watch",
                    judgement_label=JUDGEMENT_LABELS["watch"],
                    confidence=0,
                    short_reason="OpenAI応答は返りましたが、JSON parseできませんでした。下のOpenAI生応答を確認してください。",
                    key_risks=["構造化JSONではないため、カード項目への分解は未実行です。"],
                    verification_labels=["【U】"],
                )
            )
        return PortfolioAiReviewResponse(
            generated_at=self._tokyo_now(),
            mode=options.mode,
            analysis_mode=options.analysis_mode,
            model=model,
            reasoning_effort=reasoning_effort,
            include_web_search=include_web_search,
            web_search_policy=web_search_policy,  # type: ignore[arg-type]
            estimated_cost_usd=estimated_cost_usd,
            actual_usage=usage,
            input_summary={
                "target": options.target,
                "user_hypothesis": options.user_hypothesis or "未入力",
                "position_intent": options.position_intent or "未入力",
                "raw_output_fallback": True,
            },
            market_summary={"structured_parse": "failed"},
            portfolio_summary=PortfolioAiSummary(
                overall_view="OpenAI応答は返りましたが、JSONとして解析できませんでした。生応答をそのまま表示します。",
                portfolio_summary="カード分解は行わず、raw_model_outputを確認してください。再実行する場合はWeb検索回数を減らすか、軽量スキャン/個別詳細分析で対象を絞ってください。",
                overall_risk="medium",
                market_temperature="raw_output_fallback",
            ),
            stocks=stocks,
            action_plan=["OpenAI生応答を確認する", "必要なら対象銘柄を絞って再実行する"],
            critical_warnings=["構造化JSONではないため、判断は生応答の内容とsourcesを手動確認してください。"],
            warnings=warnings,
            raw_model_output=raw_output,
            status="success",
            holdings_source=holdings_source,
            web_search_used=include_web_search,
            mock_response=False,
            holdings_snapshot=holdings,
            candidates_snapshot=candidates,
            market_snapshot=market_snapshots,
            request_payload=request_payload,
        )

    def _should_display_raw_fallback(self, raw_output: str) -> bool:
        stripped = raw_output.strip()
        return len(stripped) >= 500 or stripped.startswith("{") or stripped.startswith("[")

    def _should_force_mock_response(self, options: PortfolioAiReviewRequest, holdings_source: HoldingsSource) -> bool:
        return options.target == "mock" or options.use_mock_holdings or holdings_source == "mock"

    def _error_response(
        self,
        *,
        status: str,
        message: str,
        options: PortfolioAiReviewRequest,
        holdings: list[PortfolioAiHolding],
        candidates: list[PortfolioAiCandidate] | None = None,
        market_snapshots: list[PortfolioMarketSnapshot],
        holdings_source: HoldingsSource,
        model: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        include_web_search: bool = False,
        estimated_cost_usd: float = 0,
        warnings: list[str] | None = None,
        request_payload: dict[str, Any] | None = None,
        raw_model_output: str | None = None,
        usage: PortfolioAiUsage | None = None,
    ) -> PortfolioAiReviewResponse:
        return PortfolioAiReviewResponse(
            generated_at=self._tokyo_now(),
            mode=options.mode,
            analysis_mode=options.analysis_mode,
            model=model,
            reasoning_effort=reasoning_effort,
            include_web_search=include_web_search,
            web_search_policy=get_mode_profile(options.mode).web_search_policy,
            estimated_cost_usd=estimated_cost_usd,
            actual_usage=usage or PortfolioAiUsage(),
            input_summary={
                "target": options.target,
                "user_hypothesis": options.user_hypothesis or "未入力",
                "position_intent": options.position_intent or "未入力",
            },
            portfolio_summary=PortfolioAiSummary(
                overall_view=message,
                portfolio_summary=message,
                overall_risk="medium",
                market_temperature="unknown",
            ),
            stocks=[],
            warnings=warnings or [],
            raw_model_output=raw_model_output,
            status=status,  # type: ignore[arg-type]
            error=PortfolioAiReviewError(code=status, message=message),  # type: ignore[arg-type]
            holdings_source=holdings_source,
            web_search_used=include_web_search,
            mock_response=options.mock_response,
            holdings_snapshot=holdings,
            candidates_snapshot=candidates or [],
            market_snapshot=market_snapshots,
            request_payload=request_payload or options.model_dump(mode="json"),
        )

    def _normalize_model_payload(
        self,
        payload: dict[str, Any],
        *,
        options: PortfolioAiReviewRequest | None,
    ) -> dict[str, Any]:
        now = self._tokyo_now()
        payload = dict(payload)
        payload.setdefault("generated_at", now.isoformat())
        payload.setdefault("mode", options.mode if options else "judge")
        payload.setdefault("analysis_mode", options.analysis_mode if options else "daily")
        payload.setdefault("web_search_policy", get_mode_profile(options.mode).web_search_policy if options else "optional")
        payload.setdefault("input_summary", {})
        payload.setdefault("market_summary", {})
        payload.setdefault("portfolio_summary", {})
        payload.setdefault("stocks", [])
        payload.setdefault("action_plan", [])
        payload.setdefault("critical_warnings", [])
        payload.setdefault("sources", [])
        payload.setdefault("warnings", [])
        payload.setdefault("raw_model_output", None)
        payload.setdefault("status", "success")
        payload.setdefault("holdings_source", "none")
        payload.setdefault("web_search_used", False)
        payload.setdefault("mock_response", False)
        payload.setdefault("include_web_search", False)
        payload.setdefault("estimated_cost_usd", 0)
        payload.setdefault("actual_usage", {})
        payload.setdefault("holdings_snapshot", [])
        payload.setdefault("candidates_snapshot", [])
        payload.setdefault("market_snapshot", [])
        payload.setdefault("request_payload", {})

        summary = dict(payload.get("portfolio_summary") or {})
        if "overall_view" not in summary and "summary" in summary:
            summary["overall_view"] = summary["summary"]
        summary.setdefault("overall_view", summary.get("portfolio_summary", ""))
        summary.setdefault("portfolio_summary", summary.get("overall_view", ""))
        payload["portfolio_summary"] = summary

        normalized_stocks: list[dict[str, Any]] = []
        for stock in payload.get("stocks") or []:
            if not isinstance(stock, dict):
                continue
            stock = dict(stock)
            judgement = stock.get("judgement") or "watch"
            stock["judgement"] = judgement if judgement in JUDGEMENT_LABELS else "watch"
            stock.setdefault("judgement_label", JUDGEMENT_LABELS.get(stock["judgement"], "様子見"))
            stock.setdefault("confidence", 0)
            stock.setdefault("time_horizon_views", {})
            stock.setdefault("key_risks", [])
            stock.setdefault("needs_analyst_mode", False)
            stock.setdefault("needs_judge_mode", False)
            if not isinstance(stock.get("long_term_carry_check"), dict):
                stock["long_term_carry_check"] = LongTermCarryCheck().model_dump(mode="json")
            stock.setdefault("non_monitoring_hold_risk", stock["long_term_carry_check"].get("non_monitoring_hold_risk", "unknown"))
            stock.setdefault(
                "needs_long_term_carry_check",
                stock.get("non_monitoring_hold_risk") == "high",
            )
            stock.setdefault("verification_labels", [])
            stock.setdefault("execution_plan", [])
            stock.setdefault("critical_check", [])
            normalized_stocks.append(stock)
        payload["stocks"] = normalized_stocks
        return payload

    def _system_prompt(self, mode: AiReviewMode) -> str:
        return (
            "あなたは日本株の短期〜中期の保有判断を補助するアナリストである。"
            "この機能は自動売買や投資助言の断定ではなく、判断材料、反証条件、リスクを整理する。"
            "ただし無難な一般論だけで逃げず、保有者向けの実践的な行動候補を出す。"
            "テクニカル、材料、地合い、需給、保有損益、資金拘束を分けて考える。"
            "根拠が弱い場合は「根拠弱い」と明記する。材料が確認できない場合は憶測で断定しない。"
            "反証条件と次に見るべき価格帯を必ず出す。"
            "基幹ソースはJ-Quants、EDINET API、YouTube Data API、明示allowlist化したIRサイトである。"
            "Web検索が有効な場合も無制限に探索せず、入力JSONのmax_web_search_callsを上限として扱う。"
            f"今回のmodeは {mode} / {MODE_LABELS[mode]} である。出力は指定JSON Schemaに従う。"
        )

    def _user_prompt(self, prompt_payload: dict[str, Any], mode: AiReviewMode) -> str:
        instructions = {
            "scanner": "短く、銘柄ごとの分類、警戒フラグ、詳細分析が必要かを返す。",
            "analyst": "選択銘柄を詳細に、材料・テクニカル・需給・保有者向け行動・反証条件を返す。",
            "judge": "全銘柄を横比較し、買い候補、売り候補、減らす候補、資金配分、集中リスク、今日の行動計画を返す。",
            "critical": "強気・弱気・中立シナリオ、期待値、ポジションサイズ、イベントリスク、ギャップリスク、判断期限、見立て変更条件を返す。",
            "prompt_only": "手動投入用プロンプト生成モードのため通常はAPI呼び出ししない。",
        }
        return (
            f"{instructions[mode]}\n"
            "JSON Schemaの全フィールドを返し、該当しない項目は空文字または空配列にしてください。\n"
            "judgement は hold / buy_more_candidate / take_profit_candidate / reduce_risk / watch / "
            "avoid_new_buy / urgent_review のいずれかにしてください。\n"
            "入力データ:\n"
            + json.dumps(prompt_payload, ensure_ascii=False)
        )

    def _manual_chatgpt_prompt(self, prompt_payload: dict[str, Any]) -> str:
        return (
            "以下は日本株の判断補助用プロンプトです。自動売買や断定的な投資助言ではなく、"
            "判断材料、反証条件、リスク、保有者向け行動候補を整理してください。\n\n"
            f"今日の日付: {self._tokyo_now().date().isoformat()} JST\n"
            f"分析モード: {prompt_payload['mode']} / {prompt_payload['mode_label']}\n"
            f"投資スタンス: {prompt_payload['risk_preference']}\n"
            "次のJSONには、保有銘柄、監視銘柄、現在値、前日比、出来高、移動平均、RSI、MACD、"
            "髭情報、支持線・抵抗線、直近ニュース、出力形式が含まれます。\n\n"
            + json.dumps(prompt_payload, ensure_ascii=False, indent=2)
            + "\n\n出力は stocks と portfolio_summary を持つJSONで返してください。"
        )

    def _model_for_mode(self, mode: AiReviewMode) -> str:
        settings = get_settings()
        if mode == "scanner":
            return settings.openai_model_scanner or settings.openai_model
        if mode == "analyst":
            return settings.openai_model_analyst or settings.openai_model
        if mode == "critical":
            return settings.openai_model_critical or settings.openai_model
        return settings.openai_model_judge or settings.openai_model

    def _reasoning_for_mode(self, mode: AiReviewMode) -> ReasoningEffort:
        settings = get_settings()
        if mode == "scanner":
            return settings.openai_reasoning_scanner
        if mode == "analyst":
            return settings.openai_reasoning_analyst
        if mode == "critical":
            return settings.openai_reasoning_critical
        return settings.openai_reasoning_judge or settings.openai_reasoning_effort

    def _resolve_web_search(self, options: PortfolioAiReviewRequest) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        profile = get_mode_profile(options.mode)
        if options.mode == "prompt_only":
            return False, warnings
        include_web_search = (
            profile.default_include_web_search if options.include_web_search is None else bool(options.include_web_search)
        )
        if not include_web_search:
            return False, warnings
        if not get_settings().openai_enable_web_search:
            warnings.append("OPENAI_ENABLE_WEB_SEARCH=false のため、Web検索は実行しません。")
            return False, warnings
        if options.max_web_search_calls <= 0:
            warnings.append("max_web_search_calls=0 のため、Web検索は実行しません。")
            return False, warnings
        return True, warnings

    def _resolve_max_web_search_calls(self, options: PortfolioAiReviewRequest) -> int:
        settings = get_settings()
        return max(0, min(options.max_web_search_calls, settings.openai_max_web_search_calls))

    def _cost_warnings(
        self,
        options: PortfolioAiReviewRequest,
        holdings: list[PortfolioAiHolding],
        candidates: list[PortfolioAiCandidate] | None = None,
    ) -> list[str]:
        warnings: list[str] = []
        candidates = candidates or []
        if options.mode in {"judge", "critical"}:
            warnings.append("高コストモードです。実行前に対象銘柄とWeb検索設定を確認してください。")
        include_web_search, _ = self._resolve_web_search(options)
        if include_web_search:
            warnings.append("Web検索ONのため通常より時間とAPI利用量が増えます。")
        if len(holdings) + len(candidates) > 10:
            warnings.append("対象銘柄が10件を超えています。軽量スキャンまたは対象絞り込みを推奨します。")
        return warnings

    def _estimate_cost(self, mode: AiReviewMode, stock_count: int, include_web_search: bool, max_web_search_calls: int) -> float:
        return estimate_openai_cost(mode, stock_count, include_web_search, max_web_search_calls)

    def _can_run_today(self, daily_limit: int) -> bool:
        return get_legacy_ai_usage_ledger().can_run_today(daily_limit)

    def _increment_daily_usage(self) -> None:
        get_legacy_ai_usage_ledger().record_review_success()

    def _record_provider_usage(self, *, model: str, usage: PortfolioAiUsage) -> None:
        get_legacy_ai_usage_ledger().record_provider_response(model=model, usage=usage)

    def _cache_key(self, request_payload: dict[str, Any]) -> str:
        raw = json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_cached_response(self, cache_key: str) -> PortfolioAiReviewResponse | None:
        cache = self._read_json_object(AI_REVIEW_CACHE_PATH)
        cached = cache.get(cache_key)
        if not isinstance(cached, dict):
            return None
        try:
            return PortfolioAiReviewResponse.model_validate(cached)
        except Exception:
            return None

    def _save_cached_response(self, cache_key: str, response: PortfolioAiReviewResponse) -> None:
        cache = self._read_json_object(AI_REVIEW_CACHE_PATH)
        cache[cache_key] = response.model_dump(mode="json")
        if len(cache) > 50:
            cache = dict(list(cache.items())[-50:])
        self._write_json(AI_REVIEW_CACHE_PATH, cache)

    def _append_json_list(self, path: Path, item: dict[str, Any], *, limit: int) -> None:
        data = self._read_json_list(path)
        data.append(item)
        self._write_json(path, data[-limit:])

    def _read_json_object(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _read_json_list(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _write_json(self, path: Path, data: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("Failed to write AI review local JSON %s: %s", path, exc.__class__.__name__)

    def _extract_usage(
        self,
        response: Any,
        *,
        include_web_search: bool,
        max_web_search_calls: int,
    ) -> PortfolioAiUsage:
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
        input_details = getattr(usage, "input_tokens_details", None) if usage is not None else None
        cached_input_tokens = getattr(input_details, "cached_tokens", None) if input_details is not None else None
        output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
        reasoning_tokens = None
        output_details = getattr(usage, "output_tokens_details", None) if usage is not None else None
        if output_details is not None:
            reasoning_tokens = getattr(output_details, "reasoning_tokens", None)
        output_items = getattr(response, "output", None)
        web_search_calls = 0
        if isinstance(output_items, list):
            web_search_calls = sum(1 for item in output_items if getattr(item, "type", None) == "web_search_call")
        return PortfolioAiUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            web_search_calls=web_search_calls,
            api_calls=1,
        )

    def _merge_usage(self, primary: PortfolioAiUsage, secondary: PortfolioAiUsage) -> PortfolioAiUsage:
        return PortfolioAiUsage(
            input_tokens=self._sum_optional_int(primary.input_tokens, secondary.input_tokens),
            cached_input_tokens=self._sum_optional_int(primary.cached_input_tokens, secondary.cached_input_tokens),
            output_tokens=self._sum_optional_int(primary.output_tokens, secondary.output_tokens),
            reasoning_tokens=self._sum_optional_int(primary.reasoning_tokens, secondary.reasoning_tokens),
            web_search_calls=primary.web_search_calls + secondary.web_search_calls,
            api_calls=primary.api_calls + secondary.api_calls,
        )

    @staticmethod
    def _with_minimum_api_calls(usage: PortfolioAiUsage) -> PortfolioAiUsage:
        if usage.api_calls >= 1:
            return usage
        return usage.model_copy(update={"api_calls": 1})

    def _sum_optional_int(self, left: int | None, right: int | None) -> int | None:
        if left is None and right is None:
            return None
        return int(left or 0) + int(right or 0)

    def _extract_response_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)

        output_parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    output_parts.append(str(text))
        return "\n".join(output_parts)

    def _openai_error_message(self, exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        code = getattr(exc, "code", None)
        message = str(exc)
        if status_code == 429 or code == "insufficient_quota" or "insufficient_quota" in message:
            return "OpenAI API の利用上限または請求設定により実行できませんでした。OpenAI Platform の billing / usage / quota を確認してください。"
        if status_code == 401:
            return "OpenAI API キーが無効、または認証に失敗しました。OPENAI_API_KEY を確認してください。"
        if status_code == 404 or code == "model_not_found":
            return "指定された OpenAI モデルを利用できません。用途別 OPENAI_MODEL_* の値とモデル利用権限を確認してください。"
        if status_code == 400:
            return "OpenAI API のリクエスト形式が拒否されました。モデル、web_search、reasoning 設定の組み合わせを確認してください。"
        return "OpenAI API 呼び出しに失敗しました。APIキー、モデル名、利用上限を確認してください。"

    def _extract_json_text(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return stripped
        return stripped[start : end + 1]

    def _strip_json_fence(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return stripped

    def _to_float(self, value: Decimal | int | float | None) -> float | None:
        if value is None:
            return None
        return float(value)

    def _tokyo_now(self) -> datetime:
        return datetime.now(TOKYO_TIMEZONE)


portfolio_ai_review_service = PortfolioAiReviewService()


def get_holdings(session: Session | None) -> list[PortfolioAiHolding]:
    return portfolio_ai_review_service.get_holdings(session)


def get_watchlist(session: Session | None) -> list[PortfolioAiHolding]:
    return portfolio_ai_review_service.get_watchlist(session)


def get_mock_holdings() -> list[PortfolioAiHolding]:
    return portfolio_ai_review_service.get_mock_holdings()


def get_mock_candidates() -> list[PortfolioAiCandidate]:
    return portfolio_ai_review_service.get_mock_candidates()


def get_market_snapshot(ticker: str, session: Session | None = None) -> PortfolioMarketSnapshot:
    return portfolio_ai_review_service.get_market_snapshot(ticker, session=session)


def get_technical_snapshot(ticker: str, session: Session | None = None) -> PortfolioMarketSnapshot:
    return portfolio_ai_review_service.get_technical_snapshot(ticker, session=session)


def get_news_snapshot(ticker: str, session: Session | None = None) -> list[str]:
    return portfolio_ai_review_service.get_news_snapshot(ticker, session=session)


def build_ai_review_payload(
    holdings: list[PortfolioAiHolding],
    market_snapshots: list[PortfolioMarketSnapshot],
    options: PortfolioAiReviewRequest,
) -> dict[str, Any]:
    model = portfolio_ai_review_service._model_for_mode(options.mode)
    reasoning_effort = options.reasoning_effort or portfolio_ai_review_service._reasoning_for_mode(options.mode)
    include_web_search, _ = portfolio_ai_review_service._resolve_web_search(options)
    max_web_search_calls = portfolio_ai_review_service._resolve_max_web_search_calls(options)
    return portfolio_ai_review_service.build_ai_review_payload(
        holdings=holdings,
        market_snapshots=market_snapshots,
        options=options,
        model=model,
        reasoning_effort=reasoning_effort,
        include_web_search=include_web_search,
        max_web_search_calls=max_web_search_calls,
    )


def call_open_ai_for_stock_review(
    prompt_payload: dict[str, Any],
    options: PortfolioAiReviewRequest,
    api_key: str,
) -> tuple[str, PortfolioAiUsage]:
    model = portfolio_ai_review_service._model_for_mode(options.mode)
    reasoning_effort = options.reasoning_effort or portfolio_ai_review_service._reasoning_for_mode(options.mode)
    include_web_search, _ = portfolio_ai_review_service._resolve_web_search(options)
    max_web_search_calls = portfolio_ai_review_service._resolve_max_web_search_calls(options)
    return portfolio_ai_review_service.call_open_ai_for_stock_review(
        prompt_payload=prompt_payload,
        options=options,
        api_key=api_key,
        model=model,
        reasoning_effort=reasoning_effort,
        include_web_search=include_web_search,
        max_web_search_calls=max_web_search_calls,
    )


def parse_ai_review_result(raw_output: str, options: PortfolioAiReviewRequest | None = None) -> PortfolioAiReviewResponse:
    return portfolio_ai_review_service.parse_ai_review_result(raw_output, options=options)


def save_ai_review_result(response: PortfolioAiReviewResponse) -> None:
    portfolio_ai_review_service.save_ai_review_result(response)


def analyze_portfolio_with_openai(
    holdings: list[PortfolioAiHolding],
    market_snapshots: list[PortfolioMarketSnapshot],
    options: PortfolioAiReviewRequest,
    candidates: list[PortfolioAiCandidate] | None = None,
) -> PortfolioAiReviewResponse:
    return portfolio_ai_review_service.analyze_portfolio_with_openai(
        holdings=holdings,
        candidates=candidates or [],
        market_snapshots=market_snapshots,
        options=options,
    )
