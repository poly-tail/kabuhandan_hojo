"""AI stock review service backed by the OpenAI Responses API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import html
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, get_settings
from app.models import SecurityMaster
from app.prompts.stock_analysis import (
    build_prompt_only_text,
    build_stock_analysis_prompt,
    estimate_openai_cost,
    get_mode_profile,
    get_output_schema_for_mode,
    validate_stock_analysis_response,
)
from app.schemas.portfolio_ai import (
    AiReviewHistoryTarget,
    AiReviewMode,
    HoldingsSource,
    LongTermCarryCheck,
    LongTermCarryMonitoringIntervalView,
    PortfolioAiCandidate,
    PortfolioAiHolding,
    ParseFailureKind,
    PortfolioAiReviewError,
    PortfolioAiReviewHistoryDetail,
    PortfolioAiReviewHistoryItem,
    PortfolioAiReviewHistoryListResponse,
    PortfolioAiReviewRequest,
    PortfolioAiReviewResponse,
    PortfolioAiReviewSource,
    PortfolioAiStockAnalysis,
    PortfolioAiSummary,
    PortfolioAiUsage,
    PortfolioMarketSnapshot,
    ReasoningEffort,
    ReviewStatus,
)
from app.services.ai_usage import get_legacy_ai_usage_ledger
from app.services.mock_watchlist import mock_watchlist_service
from app.services.portfolio import portfolio_service
from app.services.watchlist import WatchlistCollectionNotFoundError, WatchlistService
from kabuhandan_hojo.services.securities import SecurityService


logger = logging.getLogger(__name__)

TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")
DATA_DIR = REPO_ROOT / "data"
AI_REVIEW_HISTORY_PATH = DATA_DIR / "ai_review_history.json"
AI_REVIEW_CACHE_PATH = DATA_DIR / "ai_review_cache.json"
AI_REVIEW_HISTORY_LIMIT = 100
AI_REVIEW_HISTORY_LOCK = threading.RLock()
AI_REVIEW_HISTORY_SAVE_WARNING = (
    "AI結果は生成されましたが、ローカル履歴の保存に失敗しました。"
    "data保存先の書込み権限または履歴JSONを確認してください。"
)

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

TARGET_LABELS = {
    "holdings": "保有銘柄",
    "watchlist": "ウォッチリスト",
    "candidates": "狙い中銘柄",
    "selected": "選択銘柄",
    "mock": "テスト用仮銘柄",
    "unknown": "対象不明",
}

STATUS_LABELS = {
    "success": "正常完了",
    "missing_api_key": "APIキー未設定",
    "json_parse_failed": "JSON解析失敗",
    "openai_api_error": "OpenAI APIエラー",
    "openai_sdk_missing": "OpenAI SDK未導入",
    "no_holdings": "対象銘柄なし",
    "target_limit_exceeded": "対象銘柄数超過",
    "daily_limit_exceeded": "日次上限到達",
}

SUMMARY_SECURITY_REFERENCE_FIELDS = (
    "buy_candidates",
    "sell_or_reduce_candidates",
    "hold_priority",
    "non_monitoring_reduce_candidates",
    "core_position_candidates",
    "exit_or_rotate_candidates",
)

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


class AiReviewOutputError(ValueError):
    """Base class for sanitized model-output parsing failures."""

    failure_kind: ParseFailureKind


class AiReviewJsonDecodeError(AiReviewOutputError):
    """The provider response was not a JSON object."""

    failure_kind = "json_syntax"


class AiReviewRootShapeError(AiReviewOutputError):
    """The provider returned JSON with an unsupported root shape."""

    failure_kind = "root_shape"


class AiReviewSchemaValidationError(AiReviewOutputError):
    """The provider returned JSON that did not match the application contract."""

    failure_kind = "schema_validation"


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
        holdings = self._hydrate_holding_identities(holdings, session=session)
        candidates = self._hydrate_candidate_identities(candidates, session=session)
        holdings = list({holding.ticker: holding for holding in holdings}.values())
        holding_tickers = {holding.ticker for holding in holdings}
        candidates = list(
            {
                candidate.ticker: candidate
                for candidate in candidates
                if candidate.ticker not in holding_tickers
            }.values()
        )
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

    def get_watchlist(
        self,
        session: Session | None,
        *,
        watchlist_id: int | None = None,
    ) -> list[PortfolioAiHolding]:
        """Return one active watchlist collection as zero-quantity review targets."""

        if get_settings().app_use_mock:
            return [
                PortfolioAiHolding(
                    ticker=item.ticker_code,
                    name=item.name,
                    market=item.market,
                    quantity=0,
                    average_price=None,
                )
                for item in mock_watchlist_service.list_items(collection_id=watchlist_id)
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
            for item in self.watchlist_service.list_items(session, collection_id=watchlist_id)
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
            "watchlist_id": options.watchlist_id,
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
            "watchlist_id": options.watchlist_id,
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
                self._save_ai_review_result_with_warning(response)
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
            response = self._enrich_response_security_references(
                response,
                holdings=holdings,
                candidates=candidates,
            )
            if options.save_result:
                self._save_ai_review_result_with_warning(response)
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
            response = self._enrich_response_security_references(
                response,
                holdings=holdings,
                candidates=candidates,
            )
            if options.save_result:
                self._save_ai_review_result_with_warning(response)
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

        raw_fallback = False
        try:
            response = self.parse_ai_review_result(raw_output, options=options)
        except AiReviewOutputError as parse_error:
            parse_failure_kind = parse_error.failure_kind
            parse_failure_message = (
                "OpenAI応答のJSON項目形式がアプリ仕様と一致しませんでした。"
                if parse_failure_kind == "schema_validation"
                else (
                    "OpenAI応答のJSONルート形式がアプリ仕様と一致しませんでした。"
                    if parse_failure_kind == "root_shape"
                    else "OpenAI応答のJSON構文を解析できませんでした。"
                )
            )
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
                            f"{parse_failure_message} Web検索を追加しないJSON整形リトライを実行しました。",
                            "整形リトライ結果です。重要判断はsourcesと検証ラベルを確認してください。",
                        ]
                    )
                except Exception as repair_error:
                    logger.warning(
                        "OpenAI stock review JSON repair failed: parse_kind=%s error_type=%s",
                        parse_failure_kind,
                        repair_error.__class__.__name__,
                    )
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
                                f"{parse_failure_message} JSON整形リトライにも失敗しました。生応答をそのまま表示します。",
                            ],
                            request_payload=request_payload,
                            usage=usage,
                            failure_kind=parse_failure_kind,
                        )
                        raw_fallback = True
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
                            parse_failure_kind=parse_failure_kind,
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
                            f"{parse_failure_message} 生応答をそのまま表示します。",
                        ],
                        request_payload=request_payload,
                        usage=usage,
                        failure_kind=parse_failure_kind,
                    )
                    raw_fallback = True
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
                        parse_failure_kind=parse_failure_kind,
                    )

        if not raw_fallback:
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
        validation_warnings = (
            []
            if raw_fallback
            else validate_stock_analysis_response(
                response.model_dump(mode="json"),
                options.mode,
            )
        )
        response.warnings = [*warnings, *validation_warnings, *response.warnings]
        response.holdings_snapshot = holdings
        response.candidates_snapshot = candidates
        response.market_snapshot = market_snapshots
        response.request_payload = request_payload
        response = self._enrich_response_security_references(
            response,
            holdings=holdings,
            candidates=candidates,
        )
        if not raw_fallback:
            self._increment_daily_usage()
        if options.save_result:
            history_saved = self._save_ai_review_result_with_warning(response)
            if history_saved and not raw_fallback:
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

        stripped = self._strip_json_fence(raw_output)
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as direct_exc:
            text = self._extract_json_text(stripped)
            if text == stripped:
                raise AiReviewJsonDecodeError("model output was not valid JSON") from direct_exc
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as extracted_exc:
                raise AiReviewJsonDecodeError("model output was not valid JSON") from extracted_exc
        if not isinstance(payload, dict):
            raise AiReviewRootShapeError("model output root was not an object")
        schema_mode = options.mode if options is not None else payload.get("mode")
        if schema_mode not in {"scanner", "analyst", "judge", "critical", "prompt_only"}:
            raise AiReviewSchemaValidationError("model output mode was invalid")
        allowed_root_fields = set(get_output_schema_for_mode(schema_mode)["properties"])
        if set(payload).difference(allowed_root_fields):
            raise AiReviewSchemaValidationError("model output contained unsupported root fields")
        required_fields = {
            "generated_at",
            "mode",
            "portfolio_summary",
            "stocks",
            "sources",
            "warnings",
            "raw_model_output",
        }
        if required_fields.difference(payload):
            raise AiReviewSchemaValidationError("model output was missing required fields")
        for field in ("input_summary", "market_summary", "portfolio_summary"):
            if field in payload and not isinstance(payload[field], dict):
                raise AiReviewSchemaValidationError(f"model output field {field!r} was not an object")
        for field in ("stocks", "action_plan", "critical_warnings", "sources", "warnings"):
            if field in payload and not isinstance(payload[field], list):
                raise AiReviewSchemaValidationError(f"model output field {field!r} was not an array")
        try:
            normalized = self._normalize_model_payload(payload, options=options)
            return PortfolioAiReviewResponse.model_validate(normalized)
        except (TypeError, ValueError, ValidationError) as exc:
            raise AiReviewSchemaValidationError("model output did not match the response schema") from exc

    def save_ai_review_result(self, response: PortfolioAiReviewResponse) -> bool:
        """Append AI analysis result to local JSON history."""

        return self._append_json_list(
            AI_REVIEW_HISTORY_PATH,
            response.model_dump(mode="json"),
            limit=AI_REVIEW_HISTORY_LIMIT,
        )

    def _save_ai_review_result_with_warning(self, response: PortfolioAiReviewResponse) -> bool:
        saved = self.save_ai_review_result(response)
        if not saved and AI_REVIEW_HISTORY_SAVE_WARNING not in response.warnings:
            response.warnings.append(AI_REVIEW_HISTORY_SAVE_WARNING)
        return saved

    def list_ai_review_history(
        self,
        *,
        mode: AiReviewMode | None = None,
        target: AiReviewHistoryTarget | None = None,
        status: ReviewStatus | None = None,
        limit: int = AI_REVIEW_HISTORY_LIMIT,
        offset: int = 0,
    ) -> PortfolioAiReviewHistoryListResponse:
        """Return newest-first, metadata-only history without prompt or position data."""

        entries, stored_count, invalid_count = self._load_valid_ai_review_history()
        mode_counts: dict[AiReviewMode, int] = {
            "scanner": 0,
            "analyst": 0,
            "judge": 0,
            "critical": 0,
            "prompt_only": 0,
        }
        for _, review in entries:
            mode_counts[review.mode] += 1
        items: list[PortfolioAiReviewHistoryItem] = []
        for history_id, review in reversed(entries):
            item = self._history_item(history_id, review)
            if mode is not None and item.mode != mode:
                continue
            if target is not None and item.target != target:
                continue
            if status is not None and item.status != status:
                continue
            items.append(item)

        total = len(items)
        paged_items = items[offset : offset + limit]
        return PortfolioAiReviewHistoryListResponse(
            items=paged_items,
            total=total,
            stored_count=stored_count,
            invalid_count=invalid_count,
            mode_counts=mode_counts,
            retention_limit=AI_REVIEW_HISTORY_LIMIT,
            limit=limit,
            offset=offset,
        )

    def get_ai_review_history(self, history_id: str) -> PortfolioAiReviewHistoryDetail | None:
        """Return one saved review while excluding its internal request payload."""

        entry = self._find_ai_review_history(history_id)
        if entry is None:
            return None
        normalized_id, review = entry
        return PortfolioAiReviewHistoryDetail(
            history_id=normalized_id,
            review=review.model_dump(mode="json", exclude={"request_payload"}),
        )

    def export_ai_review_history_markdown(self, history_id: str) -> tuple[str, str] | None:
        """Render one saved review as a semantic, UTF-8 Markdown attachment."""

        entry = self._find_ai_review_history(history_id)
        if entry is None:
            return None
        normalized_id, review = entry
        generated_at = review.generated_at
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=TOKYO_TIMEZONE)
        generated_at = generated_at.astimezone(TOKYO_TIMEZONE)
        filename = (
            f"ai-review-{generated_at:%Y%m%d-%H%M%S}-{review.mode}-{normalized_id[:8]}.md"
        )
        return filename, self._build_ai_review_markdown(normalized_id, review)

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
            try:
                watchlist = self.get_watchlist(session, watchlist_id=payload.watchlist_id)
            except WatchlistCollectionNotFoundError:
                return [], "watchlist"
            if watchlist:
                return self._filter_tickers(watchlist, payload.tickers), "watchlist"
            if payload.watchlist_id is not None:
                return [], "watchlist"
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

    def _hydrate_holding_identities(
        self,
        holdings: list[PortfolioAiHolding],
        *,
        session: Session | None,
    ) -> list[PortfolioAiHolding]:
        """Replace placeholder names with authoritative local master identities."""

        if session is None:
            return holdings
        hydrated: list[PortfolioAiHolding] = []
        for holding in holdings:
            security = self._find_security_master(session, holding.ticker)
            if security is None:
                hydrated.append(holding)
                continue
            hydrated.append(
                holding.model_copy(
                    update={
                        "ticker": security.ticker_code,
                        "name": security.name,
                        "market": security.market or holding.market,
                    }
                )
            )
        return hydrated

    def _hydrate_candidate_identities(
        self,
        candidates: list[PortfolioAiCandidate],
        *,
        session: Session | None,
    ) -> list[PortfolioAiCandidate]:
        """Resolve candidate names locally without making provider requests."""

        if session is None:
            return candidates
        hydrated: list[PortfolioAiCandidate] = []
        for candidate in candidates:
            security = self._find_security_master(session, candidate.ticker)
            if security is None:
                hydrated.append(candidate)
                continue
            hydrated.append(
                candidate.model_copy(
                    update={
                        "ticker": security.ticker_code,
                        "name": security.name,
                        "market": security.market or candidate.market,
                    }
                )
            )
        return hydrated

    def _find_security_master(self, session: Session, ticker: str) -> SecurityMaster | None:
        normalized = ticker.strip().upper()
        aliases = self._security_code_aliases(normalized)
        matches = session.scalars(
            select(SecurityMaster).where(
                SecurityMaster.is_active.is_(True),
                or_(
                    SecurityMaster.ticker_code.in_(aliases),
                    SecurityMaster.local_code.in_(aliases),
                ),
            )
        ).all()
        if not matches:
            return None

        def rank(security: SecurityMaster) -> tuple[int, str]:
            if security.ticker_code.upper() == normalized:
                return (0, security.ticker_code)
            if (security.local_code or "").upper() == normalized:
                return (1, security.ticker_code)
            return (2, security.ticker_code)

        return min(matches, key=rank)

    @staticmethod
    def _security_code_aliases(ticker: str) -> tuple[str, ...]:
        normalized = ticker.strip().upper()
        aliases = [normalized]
        if re.fullmatch(r"[0-9A-Z]{4}", normalized) and any(character.isalpha() for character in normalized):
            aliases.append(f"{normalized}0")
        if (
            re.fullmatch(r"[0-9A-Z]{4}0", normalized)
            and any(character.isalpha() for character in normalized[:4])
        ):
            aliases.append(normalized[:4])
        return tuple(aliases)

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

    def _enrich_response_security_references(
        self,
        response: PortfolioAiReviewResponse,
        *,
        holdings: list[PortfolioAiHolding],
        candidates: list[PortfolioAiCandidate],
    ) -> PortfolioAiReviewResponse:
        """Use request-side identities for model names and human-facing summary labels."""

        identities: dict[str, tuple[str, str | None]] = {}
        identities_by_name: dict[str, tuple[str, str]] = {}
        for item in [*holdings, *candidates]:
            ticker = item.ticker.strip().upper()
            name = item.name.strip()
            aliases = self._security_code_aliases(ticker)
            trusted_name = None if not name or name.upper() in aliases else name
            identity = (ticker, trusted_name)
            for alias in aliases:
                existing = identities.get(alias)
                if existing is None or (existing[1] is None and trusted_name is not None):
                    identities[alias] = identity
            if trusted_name is not None:
                identities_by_name.setdefault(trusted_name, (ticker, trusted_name))

        for stock in response.stocks:
            identity = self._find_response_identity(stock.ticker, identities)
            if identity is not None:
                stock.name = identity[1] or "名称未登録"

        for field in SUMMARY_SECURITY_REFERENCE_FIELDS:
            values = getattr(response.portfolio_summary, field)
            setattr(
                response.portfolio_summary,
                field,
                [
                    self._format_security_reference(value, identities, identities_by_name)
                    for value in values
                ],
            )
        return response

    def _format_security_reference(
        self,
        value: str,
        identities: dict[str, tuple[str, str | None]],
        identities_by_name: dict[str, tuple[str, str]],
    ) -> str:
        text = value.strip()
        formatted_match = re.fullmatch(r"(.+?)[（(]([0-9A-Za-z]{4,10})[）)]", text)
        if formatted_match is not None:
            code = formatted_match.group(2)
        elif re.fullmatch(r"(?=[0-9A-Za-z]*\d)[0-9A-Za-z]{4,10}", text):
            code = text
        else:
            identity_by_name = identities_by_name.get(text)
            if identity_by_name is None:
                return value
            ticker, name = identity_by_name
            return f"{name}（{self._public_security_code(ticker)}）"

        identity = self._find_response_identity(code, identities)
        if identity is not None:
            ticker, name = identity
            return f"{name or '名称未登録'}（{self._public_security_code(ticker)}）"
        if formatted_match is not None:
            return value
        return f"名称未登録（{self._public_security_code(code)}）"

    def _find_response_identity(
        self,
        ticker: str,
        identities: dict[str, tuple[str, str | None]],
    ) -> tuple[str, str | None] | None:
        normalized = ticker.strip().upper()
        for alias in self._security_code_aliases(normalized):
            identity = identities.get(alias)
            if identity is not None:
                return identity
        return None

    @staticmethod
    def _public_security_code(ticker: str) -> str:
        normalized = ticker.strip().upper()
        if (
            re.fullmatch(r"[0-9A-Z]{4}0", normalized)
            and any(character.isalpha() for character in normalized[:4])
        ):
            return normalized[:4]
        return normalized

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
        failure_kind: ParseFailureKind = "json_syntax",
    ) -> PortfolioAiReviewResponse:
        if failure_kind == "schema_validation":
            failure_summary = "OpenAI応答は有効なJSONでしたが、項目形式がアプリ仕様と一致しませんでした。"
            failure_detail = "項目形式が一致しないため、カード項目への分解は未実行です。"
        elif failure_kind == "root_shape":
            failure_summary = "OpenAI応答は有効なJSONでしたが、ルート形式がアプリ仕様と一致しませんでした。"
            failure_detail = "JSONルート形式が一致しないため、カード項目への分解は未実行です。"
        else:
            failure_summary = "OpenAI応答は返りましたが、JSON構文を解析できませんでした。"
            failure_detail = "JSON構文を解析できないため、カード項目への分解は未実行です。"
        stocks: list[PortfolioAiStockAnalysis] = []
        for holding in holdings:
            stocks.append(
                PortfolioAiStockAnalysis(
                    ticker=holding.ticker,
                    name=holding.name,
                    judgement="watch",
                    judgement_label=JUDGEMENT_LABELS["watch"],
                    confidence=0,
                    short_reason=f"{failure_summary} 下のOpenAI生応答を確認してください。",
                    key_risks=[failure_detail],
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
                    short_reason=f"{failure_summary} 下のOpenAI生応答を確認してください。",
                    key_risks=[failure_detail],
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
                overall_view=f"{failure_summary} 生応答をそのまま表示します。",
                portfolio_summary="カード分解は行わず、raw_model_outputを確認してください。再実行する場合はWeb検索回数を減らすか、軽量スキャン/個別詳細分析で対象を絞ってください。",
                overall_risk="medium",
                market_temperature="raw_output_fallback",
            ),
            stocks=stocks,
            action_plan=["OpenAI生応答を確認する", "必要なら対象銘柄を絞って再実行する"],
            critical_warnings=[f"{failure_detail} 判断は生応答の内容とsourcesを手動確認してください。"],
            warnings=warnings,
            raw_model_output=raw_output,
            parse_failure_kind=failure_kind,
            status="json_parse_failed",
            error=PortfolioAiReviewError(code="json_parse_failed", message=failure_summary),
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
        parse_failure_kind: ParseFailureKind | None = None,
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
            parse_failure_kind=parse_failure_kind,
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
        for alias in (
            "summary",
            "summary_view",
            "overall_assessment",
            "allocation_view",
            "concentration_comment",
        ):
            if alias in summary and not isinstance(summary[alias], str):
                raise TypeError(f"portfolio summary alias {alias!r} was not a string")
        summary_text = summary.pop("summary", None)
        summary_view = summary.pop("summary_view", None)
        overall_assessment = summary.pop("overall_assessment", None)
        if not summary.get("overall_view"):
            for alias_value in (summary_text, summary_view, overall_assessment):
                if isinstance(alias_value, str) and alias_value:
                    summary["overall_view"] = alias_value
                    break
        allocation_view = summary.pop("allocation_view", None)
        if not summary.get("cash_allocation_view") and isinstance(allocation_view, str):
            summary["cash_allocation_view"] = allocation_view
        concentration_comment = summary.pop("concentration_comment", None)
        if not summary.get("concentration_risk") and isinstance(concentration_comment, str):
            summary["concentration_risk"] = concentration_comment
        summary.setdefault("overall_view", summary.get("portfolio_summary", ""))
        summary.setdefault("portfolio_summary", summary.get("overall_view", ""))
        payload["portfolio_summary"] = summary

        normalized_stocks: list[dict[str, Any]] = []
        for stock in payload.get("stocks") or []:
            if not isinstance(stock, dict):
                raise TypeError("stock analysis item was not an object")
            stock = dict(stock)
            if "judgement" in stock and not isinstance(stock["judgement"], str):
                raise TypeError("stock judgement was not a string")
            stock["judgement"] = self._normalize_judgement_code(
                stock.get("judgement"),
                stock.get("judgement_label"),
            )
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

    @staticmethod
    def _normalize_judgement_code(judgement: object, judgement_label: object) -> str:
        if isinstance(judgement, str) and judgement in JUDGEMENT_LABELS:
            return judgement
        label = judgement_label if isinstance(judgement_label, str) else ""
        text = f"{judgement if isinstance(judgement, str) else ''} {label}"
        if "緊急" in text:
            return "urgent_review"
        if "新規" in text and any(marker in text for marker in ("回避", "見送", "避け")):
            return "avoid_new_buy"
        if "利確" in text:
            return "take_profit_candidate"
        if any(marker in text for marker in ("買い増", "買い候補")):
            return "buy_more_candidate"
        if any(marker in text for marker in ("縮小", "減ら", "撤退", "入替")):
            return "reduce_risk"
        if any(marker in text for marker in ("保有", "継続", "コア")):
            return "hold"
        return "watch"

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

    def _load_valid_ai_review_history(
        self,
    ) -> tuple[list[tuple[str, PortfolioAiReviewResponse]], int, int]:
        raw_entries, invalid_root = self._read_json_list_state(AI_REVIEW_HISTORY_PATH)
        valid_entries: list[tuple[str, PortfolioAiReviewResponse]] = []
        invalid_count = 1 if invalid_root else 0
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                invalid_count += 1
                continue
            try:
                review = PortfolioAiReviewResponse.model_validate(raw_entry)
                history_id = self._history_id(raw_entry)
                review = self._enrich_response_security_references(
                    review,
                    holdings=review.holdings_snapshot,
                    candidates=review.candidates_snapshot,
                )
            except (TypeError, ValueError, ValidationError):
                invalid_count += 1
                continue
            valid_entries.append((history_id, review))
        return valid_entries, len(raw_entries), invalid_count

    def _find_ai_review_history(self, history_id: str) -> tuple[str, PortfolioAiReviewResponse] | None:
        normalized_id = history_id.strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", normalized_id) is None:
            return None
        entries, _, _ = self._load_valid_ai_review_history()
        for stored_id, review in entries:
            if stored_id == normalized_id:
                return stored_id, review
        return None

    @staticmethod
    def _history_id(raw_entry: dict[str, Any]) -> str:
        canonical = json.dumps(
            raw_entry,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _history_item(
        self,
        history_id: str,
        review: PortfolioAiReviewResponse,
    ) -> PortfolioAiReviewHistoryItem:
        target = self._history_target(review)
        stock_labels = self._history_stock_labels(review)
        if review.mode == "prompt_only":
            summary = "ChatGPT投入用プロンプト"
        elif review.status == "success":
            summary = f"{len(stock_labels)}銘柄の保存済み結果"
        else:
            summary = STATUS_LABELS[review.status]
        watchlist_id_value = review.request_payload.get("watchlist_id")
        watchlist_id = (
            watchlist_id_value
            if isinstance(watchlist_id_value, int)
            and not isinstance(watchlist_id_value, bool)
            and watchlist_id_value > 0
            else None
        )
        return PortfolioAiReviewHistoryItem(
            history_id=history_id,
            generated_at=review.generated_at,
            mode=review.mode,
            mode_label=MODE_LABELS[review.mode],
            analysis_mode=review.analysis_mode,
            target=target,
            target_label=TARGET_LABELS[target],
            status=review.status,
            status_label=STATUS_LABELS[review.status],
            holdings_source=review.holdings_source,
            stock_count=len(stock_labels),
            stocks_preview=stock_labels[:3],
            summary=summary,
            model=review.model,
            watchlist_id=watchlist_id,
            include_web_search=review.include_web_search,
            web_search_used=review.web_search_used,
            mock_response=review.mock_response,
            cache_hit=review.cache_hit,
            estimated_cost_usd=max(review.estimated_cost_usd, 0),
        )

    @staticmethod
    def _history_target(review: PortfolioAiReviewResponse) -> AiReviewHistoryTarget:
        supported_targets = {"holdings", "watchlist", "candidates", "selected", "mock"}
        for source in (review.request_payload, review.input_summary):
            value = str(source.get("target", "")).strip().lower()
            if value in supported_targets:
                return value  # type: ignore[return-value]
        source_fallbacks: dict[HoldingsSource, AiReviewHistoryTarget] = {
            "request": "selected",
            "database": "holdings",
            "watchlist": "watchlist",
            "candidates": "candidates",
            "mock": "mock",
            "none": "unknown",
        }
        return source_fallbacks.get(review.holdings_source, "unknown")

    @classmethod
    def _history_stock_labels(cls, review: PortfolioAiReviewResponse) -> list[str]:
        trusted_names: dict[str, str] = {}
        for item in (*review.holdings_snapshot, *review.candidates_snapshot):
            ticker = str(item.ticker).strip().upper()
            aliases = cls._security_code_aliases(ticker)
            name = " ".join(str(item.name).split())
            if not name or name.upper() in aliases:
                continue
            for alias in aliases:
                trusted_names.setdefault(alias, name)

        labels: list[str] = []
        seen: set[str] = set()
        for item in (*review.stocks, *review.holdings_snapshot, *review.candidates_snapshot):
            ticker = str(item.ticker).strip().upper()
            public_ticker = cls._public_security_code(ticker)
            if not public_ticker or public_ticker in seen:
                continue
            seen.add(public_ticker)
            trusted_name = next(
                (
                    trusted_names[alias]
                    for alias in cls._security_code_aliases(ticker)
                    if alias in trusted_names
                ),
                public_ticker,
            )
            labels.append(cls._security_label(trusted_name, ticker))
        return labels

    @classmethod
    def _security_label(cls, name: str, ticker: str) -> str:
        normalized_name = " ".join(str(name).split())
        normalized_ticker = str(ticker).strip()
        public_ticker = cls._public_security_code(normalized_ticker)
        if not normalized_name or normalized_name in {normalized_ticker, public_ticker}:
            return public_ticker
        return f"{normalized_name}（{public_ticker}）"

    def _build_ai_review_markdown(self, history_id: str, review: PortfolioAiReviewResponse) -> str:
        target = self._history_target(review)
        mode_label = MODE_LABELS[review.mode]
        status_label = STATUS_LABELS[review.status]
        lines = [
            f"# AIレビュー履歴：{self._markdown_inline(mode_label)}",
            "",
            f"- 履歴ID: `{history_id}`",
            f"- 回答生成日時: {self._markdown_inline(review.generated_at.isoformat())}",
            f"- 分析方法: {self._markdown_inline(mode_label)} (`{review.mode}`)",
            f"- 対象: {self._markdown_inline(TARGET_LABELS[target])}",
            f"- 状態: {self._markdown_inline(status_label)} (`{review.status}`)",
            f"- モデル: {self._markdown_inline(review.model or '未記録')}",
            f"- reasoning: {self._markdown_inline(review.reasoning_effort or '未記録')}",
            f"- Web検索: {'使用済み' if review.web_search_used else ('有効' if review.include_web_search else 'なし')}",
            f"- 実行前概算: ${review.estimated_cost_usd:.4f}",
            "",
        ]

        def add_text(title: str, value: Any, *, level: int = 3) -> None:
            if not str(value or "").strip():
                return
            lines.extend([f"{'#' * level} {title}", "", self._markdown_inline(value), ""])

        def add_list(title: str, values: list[Any], *, level: int = 3) -> None:
            cleaned: list[Any] = []
            seen_values: set[str] = set()
            for value in values:
                normalized = str(value or "").strip()
                if not normalized or normalized in seen_values:
                    continue
                seen_values.add(normalized)
                cleaned.append(value)
            if not cleaned:
                return
            lines.extend([f"{'#' * level} {title}", ""])
            lines.extend(f"- {self._markdown_inline(value)}" for value in cleaned)
            lines.append("")

        portfolio = review.portfolio_summary
        lines.extend(
            [
                "## ポートフォリオ総合判断",
                "",
                f"- 市場温度感: {self._markdown_inline(portfolio.market_temperature)}",
                f"- 総合リスク: {self._markdown_inline(portfolio.overall_risk)}",
                "",
            ]
        )
        add_text("総合見解", portfolio.overall_view)
        add_text("要約", portfolio.portfolio_summary)
        add_text("集中リスク", portfolio.concentration_risk)
        add_text("現金配分", portfolio.cash_allocation_view)
        add_list("テーマ偏り", portfolio.theme_exposure)

        security_labels = {
            stock.ticker: self._security_label(stock.name, stock.ticker)
            for stock in review.stocks
        }

        def resolve_references(values: list[str]) -> list[str]:
            return [security_labels.get(str(value).strip(), str(value)) for value in values]

        add_list("買い候補", resolve_references(portfolio.buy_candidates))
        add_list("売却・縮小候補", resolve_references(portfolio.sell_or_reduce_candidates))
        add_list("保有優先", resolve_references(portfolio.hold_priority))
        add_list("毎日見られない場合の縮小候補", resolve_references(portfolio.non_monitoring_reduce_candidates))
        add_list("コア候補", resolve_references(portfolio.core_position_candidates))
        add_list("入れ替え候補", resolve_references(portfolio.exit_or_rotate_candidates))
        add_list("ポートフォリオの主なリスク", portfolio.top_risks)
        add_list("今日の行動案", portfolio.action_plan_today)
        add_text("ポートフォリオ判断の反証条件", portfolio.invalidation_for_portfolio)

        add_list("具体的な執行案", review.action_plan, level=2)
        add_list("重要警告", review.critical_warnings, level=2)

        if review.stocks:
            lines.extend(["## 銘柄別分析", ""])
        stock_text_fields = (
            ("判断理由", "short_reason"),
            ("テクニカル", "technical_view"),
            ("ニュース", "news_view"),
            ("市場環境", "market_context_view"),
            ("需給", "supply_demand_view"),
            ("保有者の行動", "holder_action"),
            ("買い増し条件", "buy_more_condition"),
            ("利確条件", "take_profit_condition"),
            ("損切り・縮小条件", "stop_or_reduce_condition"),
            ("反証条件", "invalidation"),
            ("強気ケース", "bullish_case"),
            ("弱気ケース", "bearish_case"),
            ("基本ケース", "base_case"),
            ("期待値", "expected_value_view"),
            ("ポジションサイズリスク", "position_size_risk"),
            ("イベントリスク", "event_risk"),
            ("ギャップリスク", "gap_risk"),
            ("判断期限", "decision_deadline"),
            ("判断を変える条件", "what_would_change_my_mind"),
            ("最終判断", "final_recommendation_for_holder"),
            ("不確実性", "uncertainty_notes"),
        )
        stock_list_fields = (
            ("重要点", "key_points"),
            ("主要リスク", "key_risks"),
            ("監視点", "watch_points"),
            ("警戒フラグ", "risk_flags"),
            ("価格水準", "next_price_levels"),
            ("リスク", "risks"),
            ("執行計画", "execution_plan"),
            ("辛口チェック", "critical_check"),
            ("検証ラベル", "verification_labels"),
        )
        for stock in review.stocks:
            label = self._security_label(stock.name, stock.ticker)
            lines.extend(
                [
                    f"### {self._markdown_inline(label)}",
                    "",
                    f"- 判定: {self._markdown_inline(stock.judgement_label or stock.judgement)}",
                    f"- 確信度: {stock.confidence:.0%}",
                    f"- 非監視保有リスク: {self._markdown_inline(stock.non_monitoring_hold_risk)}",
                    "",
                ]
            )
            follow_up_modes: list[str] = []
            if stock.needs_detail_analysis:
                follow_up_modes.append("詳細分析")
            if stock.needs_analyst_mode:
                follow_up_modes.append("個別詳細分析")
            if stock.needs_judge_mode:
                follow_up_modes.append("全体売買判断")
            if stock.needs_long_term_carry_check:
                follow_up_modes.append("長期持越しチェック")
            if follow_up_modes:
                lines.append(
                    "- 推奨フォローアップ: "
                    + self._markdown_inline(" / ".join(follow_up_modes))
                )
                lines.append("")
            for title, field_name in stock_text_fields:
                add_text(title, getattr(stock, field_name), level=4)
            if stock.time_horizon_views:
                lines.extend(["#### 時間軸別見解", ""])
                for horizon, view in stock.time_horizon_views.items():
                    lines.append(
                        f"- {self._markdown_inline(horizon)}: {self._markdown_inline(view)}"
                    )
                lines.append("")
            for title, field_name in stock_list_fields:
                add_list(title, getattr(stock, field_name), level=4)
            carry = stock.long_term_carry_check
            carry_scalar_values = (
                carry.can_hold_without_daily_monitoring,
                carry.non_monitoring_hold_risk,
                carry.business_thesis_strength,
                carry.event_risk_while_unmonitored,
                carry.liquidity_risk,
                carry.volatility_risk,
                carry.position_size_view,
                carry.core_position_suitability,
                carry.final_long_term_carry_decision,
                carry.final_note,
            )
            carry_lists = (
                carry.required_alerts,
                carry.must_check_dates_or_events,
                carry.reduce_before_events,
                carry.stop_or_reduce_conditions,
                carry.long_term_thesis_break_conditions,
            )
            has_carry_detail = (
                any(str(value or "").strip() not in {"", "unknown"} for value in carry_scalar_values)
                or carry.short_term_position_should_be_removed is not None
                or any(carry_lists)
                or bool(carry.monitoring_interval_view)
            )
            if has_carry_detail:
                lines.extend(["#### 長期持越しチェック", ""])
                carry_fields = (
                    ("毎日見られない場合の保有可否", carry.can_hold_without_daily_monitoring),
                    ("非監視保有リスク", carry.non_monitoring_hold_risk),
                    ("事業仮説の強さ", carry.business_thesis_strength),
                    ("非監視中のイベントリスク", carry.event_risk_while_unmonitored),
                    ("流動性リスク", carry.liquidity_risk),
                    ("変動リスク", carry.volatility_risk),
                    ("ポジションサイズ", carry.position_size_view),
                    ("コア適性", carry.core_position_suitability),
                    ("最終持越し判断", carry.final_long_term_carry_decision),
                )
                for field_label, field_value in carry_fields:
                    normalized_value = str(field_value or "").strip()
                    if normalized_value and normalized_value != "unknown":
                        lines.append(
                            f"- {field_label}: {self._markdown_inline(normalized_value)}"
                        )
                if carry.short_term_position_should_be_removed is not None:
                    lines.append(
                        "- 短期玉の除外: "
                        + ("必要" if carry.short_term_position_should_be_removed else "不要")
                    )
                lines.append("")
                carry_list_fields = (
                    ("必要なアラート", carry.required_alerts),
                    ("確認必須日・イベント", carry.must_check_dates_or_events),
                    ("イベント前の縮小", carry.reduce_before_events),
                    ("損切り・縮小条件", carry.stop_or_reduce_conditions),
                    ("長期仮説の崩壊条件", carry.long_term_thesis_break_conditions),
                )
                for field_label, field_values in carry_list_fields:
                    add_list(field_label, field_values, level=5)
                if carry.monitoring_interval_view:
                    lines.extend(["##### 非監視期間別の保有可否", ""])
                    for interval_view in carry.monitoring_interval_view:
                        interval_summary = (
                            f"{interval_view.interval}: {interval_view.holdability}"
                        )
                        lines.append(f"- {self._markdown_inline(interval_summary)}")
                        if interval_view.required_conditions:
                            required = " / ".join(interval_view.required_conditions)
                            lines.append(f"  - 必要条件: {self._markdown_inline(required)}")
                        if interval_view.pre_actions:
                            actions = " / ".join(interval_view.pre_actions)
                            lines.append(f"  - 事前対応: {self._markdown_inline(actions)}")
                    lines.append("")
                add_text("最終補足", carry.final_note, level=5)
            if stock.sources:
                lines.extend(["#### この銘柄の情報源", ""])
                lines.extend(f"- {self._markdown_source(source)}" for source in stock.sources)
                lines.append("")

        if review.sources:
            lines.extend(["## 情報源", ""])
            lines.extend(f"- {self._markdown_source(source)}" for source in review.sources)
            lines.append("")

        add_list("警告", review.warnings, level=2)

        if review.error is not None:
            lines.extend(
                [
                    "## エラー情報",
                    "",
                    f"- code: `{review.error.code}`",
                    f"- message: {self._markdown_inline(review.error.message)}",
                    "",
                ]
            )
        if review.raw_model_output:
            lines.extend(["## OpenAI生応答（調査用）", ""])
            lines.extend(self._markdown_code_block(review.raw_model_output, language="text"))
            lines.append("")
        if review.manual_prompt:
            lines.extend(["## ChatGPT投入用プロンプト", ""])
            lines.extend(self._markdown_code_block(review.manual_prompt, language="text"))
            lines.append("")

        lines.extend(
            [
                "> この出力は日本株の判断補助であり、自動売買や断定的な投資助言ではありません。",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _markdown_inline(value: Any) -> str:
        escaped = html.escape(str(value), quote=False).replace("\\", "\\\\")
        for marker in ("`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|", ">", "~"):
            escaped = escaped.replace(marker, f"\\{marker}")
        return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "  \n")

    @classmethod
    def _markdown_source(cls, source: PortfolioAiReviewSource) -> str:
        title = cls._markdown_inline(source.title or "情報源")
        safe_url = cls._safe_http_url(source.url)
        if safe_url is None:
            return f"{title}（HTTP\\(S\\)以外のURLはリンク省略）"
        return f"[{title}]({safe_url})"

    @staticmethod
    def _safe_http_url(value: str) -> str | None:
        raw_url = str(value).strip()
        if not raw_url or any(ord(character) < 32 for character in raw_url):
            return None
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            return None
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        return quote(raw_url, safe=":/?#[]@!$&'*+,;=%")

    @staticmethod
    def _markdown_code_block(value: str, *, language: str = "") -> list[str]:
        longest_run = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
        fence = "`" * max(3, longest_run + 1)
        return [f"{fence}{language}", value, fence]

    def _cache_key(self, request_payload: dict[str, Any]) -> str:
        raw = json.dumps(request_payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_cached_response(self, cache_key: str) -> PortfolioAiReviewResponse | None:
        cache = self._read_json_object(AI_REVIEW_CACHE_PATH)
        cached = cache.get(cache_key)
        if not isinstance(cached, dict):
            return None
        try:
            response = PortfolioAiReviewResponse.model_validate(cached)
        except Exception:
            return None
        if response.status != "success" or response.raw_model_output is not None:
            return None
        return self._enrich_response_security_references(
            response,
            holdings=response.holdings_snapshot,
            candidates=response.candidates_snapshot,
        )

    def _save_cached_response(self, cache_key: str, response: PortfolioAiReviewResponse) -> None:
        if response.status != "success" or response.raw_model_output is not None:
            return
        cache = self._read_json_object(AI_REVIEW_CACHE_PATH)
        cache[cache_key] = response.model_dump(mode="json")
        if len(cache) > 50:
            cache = dict(list(cache.items())[-50:])
        self._write_json(AI_REVIEW_CACHE_PATH, cache)

    def _append_json_list(self, path: Path, item: dict[str, Any], *, limit: int) -> bool:
        with AI_REVIEW_HISTORY_LOCK:
            data, invalid_root = self._read_json_list_state(path)
            if invalid_root:
                logger.warning(
                    "Refusing to overwrite invalid AI review history JSON path=%s",
                    path,
                )
                return False
            data.append(item)
            return self._write_json(path, data[-limit:])

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
        data, _ = self._read_json_list_state(path)
        return [item for item in data if isinstance(item, dict)]

    def _read_json_list_state(self, path: Path) -> tuple[list[Any], bool]:
        """Return a list plus a root-corruption flag under the history lock."""

        with AI_REVIEW_HISTORY_LOCK:
            if not path.exists():
                return [], False
            try:
                with path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
            except (OSError, json.JSONDecodeError):
                return [], True
            if not isinstance(data, list):
                return [], True
            return data, False

    def _write_json(self, path: Path, data: Any) -> bool:
        temp_path: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temp_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Failed to write AI review local JSON %s: %s", path, exc.__class__.__name__)
            return False
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Failed to clean up AI review temporary JSON: %s", temp_path)

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


def get_watchlist(
    session: Session | None,
    *,
    watchlist_id: int | None = None,
) -> list[PortfolioAiHolding]:
    return portfolio_ai_review_service.get_watchlist(session, watchlist_id=watchlist_id)


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


def save_ai_review_result(response: PortfolioAiReviewResponse) -> bool:
    return portfolio_ai_review_service.save_ai_review_result(response)


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
