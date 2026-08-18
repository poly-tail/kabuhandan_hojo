"""Local usage and estimated-cost ledger for the legacy stock-review path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.core.config import REPO_ROOT
from app.schemas.portfolio_ai import (
    PortfolioAiPricingInfo,
    PortfolioAiPricingModel,
    PortfolioAiUsage,
    PortfolioAiUsagePeriod,
    PortfolioAiUsageSummary,
)


logger = logging.getLogger(__name__)

TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")
AI_REVIEW_USAGE_V2_PATH = REPO_ROOT / "data" / "ai_review_usage_v2.json"
LEDGER_VERSION = 2
PRICING_VERSION = "openai-standard-2026-08-17"
PRICING_AS_OF = "2026-08-17"
WEB_SEARCH_USD_PER_CALL = Decimal("0.01")
PRICING_SOURCE_URLS = [
    "https://developers.openai.com/api/docs/models/gpt-5.4",
    "https://developers.openai.com/api/docs/models/gpt-5.5",
    "https://developers.openai.com/api/docs/models/gpt-5.6-terra",
    "https://developers.openai.com/api/docs/pricing",
]


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Standard-processing price used to estimate one completed response."""

    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    long_context_threshold_tokens: int | None = None
    long_context_input_multiplier: Decimal | None = None
    long_context_output_multiplier: Decimal | None = None


MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-5.4": ModelPrice(
        input_usd_per_million=Decimal("2.50"),
        cached_input_usd_per_million=Decimal("0.25"),
        output_usd_per_million=Decimal("15.00"),
        long_context_threshold_tokens=272_000,
        long_context_input_multiplier=Decimal("2"),
        long_context_output_multiplier=Decimal("1.5"),
    ),
    "gpt-5.5": ModelPrice(
        input_usd_per_million=Decimal("5.00"),
        cached_input_usd_per_million=Decimal("0.50"),
        output_usd_per_million=Decimal("30.00"),
        long_context_threshold_tokens=272_000,
        long_context_input_multiplier=Decimal("2"),
        long_context_output_multiplier=Decimal("1.5"),
    ),
    "gpt-5.6-terra": ModelPrice(
        input_usd_per_million=Decimal("2.00"),
        cached_input_usd_per_million=Decimal("0.20"),
        output_usd_per_million=Decimal("12.00"),
        long_context_threshold_tokens=272_000,
        long_context_input_multiplier=Decimal("2"),
        long_context_output_multiplier=Decimal("1.5"),
    ),
}

_LEDGER_LOCK = threading.RLock()
_ZERO = Decimal("0")
_ONE_MILLION = Decimal("1000000")


def estimate_usage_cost_usd(model: str, usage: PortfolioAiUsage) -> Decimal | None:
    """Estimate cost from reported usage, returning ``None`` rather than guessing."""

    price = MODEL_PRICES.get(model)
    if price is None:
        return None
    if usage.input_tokens is None or usage.cached_input_tokens is None or usage.output_tokens is None:
        return None
    if usage.input_tokens < 0 or usage.cached_input_tokens < 0 or usage.output_tokens < 0:
        return None
    if usage.cached_input_tokens > usage.input_tokens:
        return None

    uncached_input_tokens = usage.input_tokens - usage.cached_input_tokens
    input_multiplier = Decimal("1")
    output_multiplier = Decimal("1")
    if (
        price.long_context_threshold_tokens is not None
        and usage.input_tokens > price.long_context_threshold_tokens
    ):
        input_multiplier = price.long_context_input_multiplier or Decimal("1")
        output_multiplier = price.long_context_output_multiplier or Decimal("1")

    token_cost = (
        Decimal(uncached_input_tokens) * price.input_usd_per_million * input_multiplier
        + Decimal(usage.cached_input_tokens) * price.cached_input_usd_per_million * input_multiplier
        + Decimal(usage.output_tokens) * price.output_usd_per_million * output_multiplier
    ) / _ONE_MILLION
    tool_cost = Decimal(max(0, usage.web_search_calls)) * WEB_SEARCH_USD_PER_CALL
    # reasoning_tokens is an output_tokens detail and is intentionally not added again.
    return token_cost + tool_cost


class LegacyAiUsageLedger:
    """Thread-safe, atomically replaced JSON ledger for legacy AI stock reviews."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def can_run_today(self, daily_limit: int, *, now: datetime | None = None) -> bool:
        return self.summary(daily_limit=daily_limit, now=now).today.review_runs < daily_limit

    def record_provider_response(
        self,
        *,
        model: str,
        usage: PortfolioAiUsage,
        now: datetime | None = None,
    ) -> None:
        """Record one or more completed provider responses and their reported usage."""

        local_now = self._local_now(now)
        day_key = local_now.date().isoformat()
        api_calls = max(1, int(usage.api_calls or 0))
        cost = estimate_usage_cost_usd(model, usage)

        def mutate(data: dict[str, Any]) -> None:
            bucket = self._day_bucket(data, day_key)
            bucket["api_calls"] += api_calls
            bucket["input_tokens"] += max(0, int(usage.input_tokens or 0))
            bucket["cached_input_tokens"] += max(0, int(usage.cached_input_tokens or 0))
            bucket["output_tokens"] += max(0, int(usage.output_tokens or 0))
            bucket["reasoning_tokens"] += max(0, int(usage.reasoning_tokens or 0))
            bucket["web_search_calls"] += max(0, int(usage.web_search_calls or 0))
            if cost is None:
                bucket["unpriced_api_calls"] += api_calls
            else:
                bucket["estimated_cost_usd"] = self._decimal_text(
                    self._decimal(bucket.get("estimated_cost_usd")) + cost
                )
            versions = bucket.setdefault("pricing_versions", [])
            if PRICING_VERSION not in versions:
                versions.append(PRICING_VERSION)

        self._mutate(mutate)

    def record_review_success(self, *, now: datetime | None = None) -> None:
        """Increment quota usage once for a successful top-level live review."""

        day_key = self._local_now(now).date().isoformat()

        def mutate(data: dict[str, Any]) -> None:
            self._day_bucket(data, day_key)["review_runs"] += 1

        self._mutate(mutate)

    def summary(self, *, daily_limit: int, now: datetime | None = None) -> PortfolioAiUsageSummary:
        local_now = self._local_now(now)
        day_key = local_now.date().isoformat()
        month_key = day_key[:7]
        with _LEDGER_LOCK:
            data = self._read()
        today = self._period(day_key, [data.get("days", {}).get(day_key, {})])
        month_buckets = [
            bucket
            for key, bucket in data.get("days", {}).items()
            if isinstance(key, str) and key.startswith(f"{month_key}-") and isinstance(bucket, dict)
        ]
        month = self._period(month_key, month_buckets)
        return PortfolioAiUsageSummary(
            daily_limit=daily_limit,
            remaining_today=max(0, daily_limit - today.review_runs),
            today=today,
            month=month,
            pricing=self._pricing_info(),
        )

    def _mutate(self, mutate: Callable[[dict[str, Any]], None]) -> None:
        with _LEDGER_LOCK:
            data = self._read()
            mutate(data)
            self._write(data)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_ledger()
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read legacy AI usage v2 ledger exception_type=read_error")
            return self._empty_ledger()
        if not isinstance(data, dict) or data.get("version") != LEDGER_VERSION:
            logger.warning("Ignored incompatible legacy AI usage v2 ledger")
            return self._empty_ledger()
        if not isinstance(data.get("days"), dict):
            data["days"] = {}
        catalogs = data.setdefault("pricing_catalog", {})
        catalogs.setdefault(PRICING_VERSION, self._pricing_metadata())
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            self._replace_with_retry(temporary_path, self.path)
            temporary_path = None
        except OSError as exc:
            logger.warning(
                "Failed to write legacy AI usage v2 ledger exception_type=%s",
                exc.__class__.__name__,
            )
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _replace_with_retry(source: Path, destination: Path) -> None:
        """Retry transient Windows sharing/permission failures during atomic replace."""

        delays = (0.01, 0.02, 0.04, 0.08)
        for attempt in range(len(delays) + 1):
            try:
                os.replace(source, destination)
                return
            except PermissionError:
                if attempt == len(delays):
                    raise
                time.sleep(delays[attempt])

    def _empty_ledger(self) -> dict[str, Any]:
        return {
            "version": LEDGER_VERSION,
            "timezone": "Asia/Tokyo",
            "scope": "legacy_stock_review",
            "pricing_catalog": {PRICING_VERSION: self._pricing_metadata()},
            "days": {},
        }

    def _day_bucket(self, data: dict[str, Any], day_key: str) -> dict[str, Any]:
        days = data.setdefault("days", {})
        raw_bucket = days.get(day_key)
        if not isinstance(raw_bucket, dict):
            raw_bucket = {}
            days[day_key] = raw_bucket
        defaults: dict[str, Any] = {
            "review_runs": 0,
            "api_calls": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "web_search_calls": 0,
            "estimated_cost_usd": "0",
            "unpriced_api_calls": 0,
            "pricing_versions": [],
        }
        for key, value in defaults.items():
            raw_bucket.setdefault(key, value)
        return raw_bucket

    def _period(self, period: str, buckets: list[Any]) -> PortfolioAiUsagePeriod:
        totals = {
            "review_runs": 0,
            "api_calls": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "web_search_calls": 0,
            "unpriced_api_calls": 0,
        }
        total_cost = _ZERO
        for raw_bucket in buckets:
            if not isinstance(raw_bucket, dict):
                continue
            for key in totals:
                try:
                    totals[key] += max(0, int(raw_bucket.get(key) or 0))
                except (TypeError, ValueError):
                    continue
            total_cost += self._decimal(raw_bucket.get("estimated_cost_usd"))
        return PortfolioAiUsagePeriod(
            period=period,
            estimated_cost_usd=float(total_cost),
            **totals,
        )

    def _pricing_info(self) -> PortfolioAiPricingInfo:
        return PortfolioAiPricingInfo(
            version=PRICING_VERSION,
            as_of=PRICING_AS_OF,
            web_search_usd_per_call=float(WEB_SEARCH_USD_PER_CALL),
            models={
                model: PortfolioAiPricingModel(
                    input_usd_per_million=float(price.input_usd_per_million),
                    cached_input_usd_per_million=float(price.cached_input_usd_per_million),
                    output_usd_per_million=float(price.output_usd_per_million),
                    long_context_threshold_tokens=price.long_context_threshold_tokens,
                    long_context_input_multiplier=(
                        float(price.long_context_input_multiplier)
                        if price.long_context_input_multiplier is not None
                        else None
                    ),
                    long_context_output_multiplier=(
                        float(price.long_context_output_multiplier)
                        if price.long_context_output_multiplier is not None
                        else None
                    ),
                )
                for model, price in MODEL_PRICES.items()
            },
            source_urls=PRICING_SOURCE_URLS,
        )

    def _pricing_metadata(self) -> dict[str, Any]:
        return self._pricing_info().model_dump(mode="json")

    @staticmethod
    def _local_now(now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(TOKYO_TIMEZONE)
        if now.tzinfo is None:
            return now.replace(tzinfo=TOKYO_TIMEZONE)
        return now.astimezone(TOKYO_TIMEZONE)

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value or "0"))
        except (InvalidOperation, ValueError):
            return _ZERO

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.000000000001")), "f")


def get_legacy_ai_usage_ledger() -> LegacyAiUsageLedger:
    """Build a ledger using the current path so tests can safely replace it."""

    return LegacyAiUsageLedger(AI_REVIEW_USAGE_V2_PATH)
