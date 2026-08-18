"""Tests for the isolated legacy stock-review usage ledger."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.core.config import Settings
from app.schemas.portfolio_ai import PortfolioAiUsage
from app.services.ai_usage import LegacyAiUsageLedger, estimate_usage_cost_usd


TOKYO = ZoneInfo("Asia/Tokyo")


def _at(day: int, *, month: int = 8) -> datetime:
    return datetime(2026, month, day, 12, 0, tzinfo=TOKYO)


def test_daily_limit_default_is_300(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_DAILY_REQUEST_LIMIT", raising=False)

    assert Settings(_env_file=None).openai_daily_request_limit == 300


def test_cost_uses_reported_cached_tokens_and_does_not_double_count_reasoning() -> None:
    usage = PortfolioAiUsage(
        input_tokens=100_000,
        cached_input_tokens=20_000,
        output_tokens=10_000,
        reasoning_tokens=9_000,
        web_search_calls=2,
        api_calls=1,
    )

    cost = estimate_usage_cost_usd("gpt-5.4", usage)

    assert cost is not None
    assert float(cost) == pytest.approx(0.375)


@pytest.mark.parametrize(
    ("model", "expected_cost"),
    [
        ("gpt-5.4", 3.75),
        ("gpt-5.5", 7.5),
        ("gpt-5.6-terra", 3.0),
    ],
)
def test_cost_applies_long_context_multipliers(model: str, expected_cost: float) -> None:
    usage = PortfolioAiUsage(
        input_tokens=300_000,
        cached_input_tokens=0,
        output_tokens=100_000,
        reasoning_tokens=50_000,
        api_calls=1,
    )

    cost = estimate_usage_cost_usd(model, usage)

    assert cost is not None
    assert float(cost) == pytest.approx(expected_cost)


@pytest.mark.parametrize(
    ("model", "expected_cost"),
    [
        ("gpt-5.5", 0.8),
        ("gpt-5.6-terra", 0.32),
    ],
)
def test_supported_model_rates_are_pinned(model: str, expected_cost: float) -> None:
    usage = PortfolioAiUsage(
        input_tokens=100_000,
        cached_input_tokens=0,
        output_tokens=10_000,
        api_calls=1,
    )

    cost = estimate_usage_cost_usd(model, usage)

    assert cost is not None
    assert float(cost) == pytest.approx(expected_cost)


@pytest.mark.parametrize(
    ("model", "usage"),
    [
        (
            "unknown-model",
            PortfolioAiUsage(input_tokens=10, cached_input_tokens=0, output_tokens=20, api_calls=1),
        ),
        (
            "gpt-5.4",
            PortfolioAiUsage(input_tokens=10, cached_input_tokens=None, output_tokens=20, api_calls=1),
        ),
    ],
)
def test_unknown_model_or_missing_usage_is_never_priced(model: str, usage: PortfolioAiUsage) -> None:
    assert estimate_usage_cost_usd(model, usage) is None


def test_ledger_separates_provider_calls_from_successful_review_runs(tmp_path: Path) -> None:
    ledger = LegacyAiUsageLedger(tmp_path / "usage.json")
    usage = PortfolioAiUsage(
        input_tokens=1_000,
        cached_input_tokens=100,
        output_tokens=200,
        reasoning_tokens=50,
        api_calls=1,
    )

    ledger.record_provider_response(model="gpt-5.4", usage=usage, now=_at(17))
    before_success = ledger.summary(daily_limit=300, now=_at(17))
    ledger.record_review_success(now=_at(17))
    after_success = ledger.summary(daily_limit=300, now=_at(17))

    assert before_success.today.api_calls == 1
    assert before_success.today.review_runs == 0
    assert after_success.today.api_calls == 1
    assert after_success.today.review_runs == 1
    assert after_success.remaining_today == 299


def test_day_and_month_buckets_use_asia_tokyo_calendar(tmp_path: Path) -> None:
    ledger = LegacyAiUsageLedger(tmp_path / "usage.json")
    usage = PortfolioAiUsage(
        input_tokens=100,
        cached_input_tokens=0,
        output_tokens=50,
        api_calls=1,
    )
    for when in (_at(31, month=7), _at(1), _at(17)):
        ledger.record_provider_response(model="gpt-5.5", usage=usage, now=when)
        ledger.record_review_success(now=when)

    summary = ledger.summary(daily_limit=300, now=_at(17))

    assert summary.today.period == "2026-08-17"
    assert summary.today.review_runs == 1
    assert summary.today.api_calls == 1
    assert summary.month.period == "2026-08"
    assert summary.month.review_runs == 2
    assert summary.month.api_calls == 2


def test_unpriced_provider_calls_are_counted_without_inventing_cost(tmp_path: Path) -> None:
    ledger = LegacyAiUsageLedger(tmp_path / "usage.json")

    ledger.record_provider_response(
        model="not-in-pricing-catalog",
        usage=PortfolioAiUsage(api_calls=1),
        now=_at(17),
    )

    summary = ledger.summary(daily_limit=300, now=_at(17))
    assert summary.today.api_calls == 1
    assert summary.today.unpriced_api_calls == 1
    assert summary.today.estimated_cost_usd == 0
    assert summary.today.review_runs == 0


def test_daily_quota_boundary_is_300_successful_reviews(tmp_path: Path) -> None:
    ledger = LegacyAiUsageLedger(tmp_path / "usage.json")

    for _ in range(300):
        ledger.record_review_success(now=_at(17))

    summary = ledger.summary(daily_limit=300, now=_at(17))
    assert summary.today.review_runs == 300
    assert summary.remaining_today == 0
    assert ledger.can_run_today(300, now=_at(17)) is False


def test_ledger_uses_versioned_pricing_metadata_and_atomic_temp_cleanup(tmp_path: Path) -> None:
    path = tmp_path / "usage.json"
    ledger = LegacyAiUsageLedger(path)

    ledger.record_review_success(now=_at(17))
    summary = ledger.summary(daily_limit=300, now=_at(17))

    assert summary.pricing.version == "openai-standard-2026-08-17"
    assert summary.pricing.as_of == "2026-08-17"
    assert summary.pricing.models["gpt-5.4"].input_usd_per_million == 2.5
    assert summary.pricing.web_search_usd_per_call == 0.01
    assert summary.incomplete_pre_v2_history is True
    assert summary.official_billing_is_authoritative is True
    assert path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_ledger_retries_a_transient_permission_error_during_atomic_replace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "usage.json"
    ledger = LegacyAiUsageLedger(path)
    real_replace = os.replace
    attempts = 0

    def flaky_replace(source: Path, destination: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("transient sharing violation")
        real_replace(source, destination)

    monkeypatch.setattr("app.services.ai_usage.os.replace", flaky_replace)

    ledger.record_review_success(now=_at(17))

    assert attempts == 2
    assert ledger.summary(daily_limit=300, now=_at(17)).today.review_runs == 1
