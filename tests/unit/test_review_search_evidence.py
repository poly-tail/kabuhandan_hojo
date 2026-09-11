"""Provider evidence, settings, and historical Web search are distinct contracts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.schemas.portfolio_ai import (
    PortfolioAiHolding,
    PortfolioAiReviewRequest,
    PortfolioAiUsage,
    PortfolioMarketSnapshot,
)
from app.services import ai_usage as usage_module
from app.services import portfolio_ai_review as review_module
from app.services.portfolio_ai_review import portfolio_ai_review_service as service


@pytest.fixture(autouse=True)
def isolated_search_review(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ENABLE_WEB_SEARCH", "true")
    monkeypatch.setenv("OPENAI_MAX_WEB_SEARCH_CALLS", "5")
    monkeypatch.setattr(usage_module, "AI_REVIEW_USAGE_V2_PATH", tmp_path / "usage.json")
    monkeypatch.setattr(review_module, "AI_REVIEW_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(review_module, "AI_REVIEW_CACHE_PATH", tmp_path / "cache.json")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def run_review(**overrides):
    options = PortfolioAiReviewRequest(
        **{
            "target": "selected",
            "mode": "analyst",
            "include_web_search": True,
            "save_result": False,
            "use_cache": False,
            **overrides,
        }
    )
    return service.analyze_portfolio_with_openai(
        holdings=[PortfolioAiHolding(ticker="7203", name="トヨタ自動車", quantity=0)],
        candidates=[],
        market_snapshots=[PortfolioMarketSnapshot(ticker="7203")],
        options=options,
        holdings_source="request",
    )


def model_output():
    # The model falsely claims that it searched: provider evidence must override it.
    return json.dumps({
        "generated_at": "2026-08-17T12:00:00+09:00",
        "mode": "analyst",
        "market_summary": {"latest_web_check": "Web検索済みというモデルの自己申告"},
        "portfolio_summary": {},
        "stocks": [],
        "sources": [{"title": "model supplied source", "url": "https://example.com/"}],
        "warnings": [],
        "raw_model_output": None,
    })


@pytest.mark.parametrize("calls,expected", [(0, "not_run"), (2, "executed")])
def test_search_setting_does_not_replace_actual_calls(monkeypatch, calls, expected):
    monkeypatch.setattr(service, "_call_openai", lambda **_: (
        model_output(), PortfolioAiUsage(web_search_calls=calls),
    ))
    review = run_review()
    assert review.status == "success"
    assert review.web_search_used is (calls > 0)
    assert review.model_dump()["web_search_status"] == expected
    assert review.include_web_search is True
    assert review.actual_usage.web_search_calls == calls
    assert review.model_dump()["web_search_requested"] is True
    assert "主張の裏付け" in service._build_ai_review_markdown("a" * 64, review)


def test_missing_provider_metadata_is_unknown_despite_model_self_report(monkeypatch):
    usage = service._extract_usage(
        SimpleNamespace(), include_web_search=True, max_web_search_calls=5,
    )
    monkeypatch.setattr(service, "_call_openai", lambda **_: (model_output(), usage))
    review = run_review()
    assert review.status == "success"
    assert review.web_search_used is False
    assert review.model_dump()["web_search_status"] == "unknown"
    assert "未確認" in service._build_ai_review_markdown("a" * 64, review)


@pytest.mark.parametrize("output,calls", [([], 0), ([{"type": "web_search_call"}], 1)])
def test_provider_tool_metadata_records_zero_and_positive(output, calls):
    usage = service._extract_usage(
        SimpleNamespace(output=output), include_web_search=True, max_web_search_calls=5,
    )
    assert usage.web_search_calls == calls
    assert usage.model_dump()["web_search_calls_known"] is True


def test_default_usage_zero_is_not_an_observed_count(monkeypatch):
    monkeypatch.setattr(service, "_call_openai", lambda **_: (
        model_output(), PortfolioAiUsage(input_tokens=50),
    ))
    review = run_review()
    assert review.web_search_used is False
    assert review.web_search_status == "unknown"


def test_unknown_repair_usage_does_not_turn_unobserved_zero_into_evidence():
    unknown = service._extract_usage(
        SimpleNamespace(), include_web_search=True, max_web_search_calls=5,
    )
    known = PortfolioAiUsage(web_search_calls=0)
    merged = service._merge_usage(unknown, known)
    assert merged.web_search_calls == 0
    assert merged.web_search_calls_known is False
    evidence = service._web_search_evidence(PortfolioAiReviewRequest(), usage=merged)
    assert evidence["web_search_status"] == "unknown"


def test_provider_error_is_unknown_but_preflight_failure_is_not_run(monkeypatch):
    def failed_provider(**_):
        raise RuntimeError("stub provider unavailable")

    monkeypatch.setattr(service, "_call_openai", failed_provider)
    failed = run_review()
    assert failed.status == "openai_api_error"
    assert failed.web_search_status == "unknown"
    assert failed.web_search_used is False
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    preflight = run_review()
    assert preflight.status == "missing_api_key"
    assert preflight.web_search_status == "not_run"
    assert preflight.web_search_used is False


@pytest.mark.parametrize("include,maximum", [(True, 0), (False, 5)])
def test_disabled_or_effective_zero_does_not_enable_tool(monkeypatch, include, maximum):
    monkeypatch.setenv("OPENAI_MAX_WEB_SEARCH_CALLS", str(maximum))
    captured = {}

    def provider(**kwargs):
        captured.update(kwargs)
        return model_output(), PortfolioAiUsage(web_search_calls=0)

    monkeypatch.setattr(service, "_call_openai", provider)
    review = run_review(include_web_search=include)
    assert captured["include_web_search"] is False
    assert review.include_web_search is False
    assert review.web_search_used is False
    assert review.model_dump()["web_search_status"] == "not_run"


@pytest.mark.parametrize("options", [{"mock_response": True}, {"mode": "prompt_only"}])
def test_no_provider_modes_have_known_zero_search(monkeypatch, options):
    monkeypatch.setattr(service, "_call_openai", lambda **_: pytest.fail("provider called"))
    review = run_review(**options)
    assert review.web_search_used is False
    assert review.model_dump()["web_search_status"] == "not_run"
    assert review.actual_usage.api_calls == 0
    assert review.actual_usage.web_search_calls == 0


@pytest.mark.parametrize("raw", ["x", "{" + "解析できない生応答です。" * 8])
def test_parse_failure_keeps_actual_search_evidence(monkeypatch, raw):
    monkeypatch.setattr(service, "_call_openai", lambda **_: (
        raw, PortfolioAiUsage(web_search_calls=0),
    ))
    review = run_review()
    assert review.status == "json_parse_failed"
    assert review.web_search_used is False
    assert review.model_dump()["web_search_status"] == "not_run"


def test_cache_preserves_original_search_and_generation_without_new_usage(monkeypatch):
    monkeypatch.setattr(service, "_call_openai", lambda **_: (
        model_output(), PortfolioAiUsage(web_search_calls=2),
    ))
    original = run_review()
    before = usage_module.AI_REVIEW_USAGE_V2_PATH.read_bytes()
    monkeypatch.setattr(service, "_load_cached_response", lambda *_, **__: original.model_copy(deep=True))
    monkeypatch.setattr(service, "_call_openai", lambda **_: pytest.fail("cached provider call"))
    cached = run_review(use_cache=True)
    assert cached.cache_hit is True
    assert cached.generated_at == original.generated_at
    assert cached.web_search_used is True
    assert cached.model_dump()["web_search_status"] == "executed"
    assert cached.actual_usage.web_search_calls == 2
    assert usage_module.AI_REVIEW_USAGE_V2_PATH.read_bytes() == before
    markdown = service._build_ai_review_markdown("a" * 64, cached)
    assert "前回生成時" in markdown
    assert "今回の新規検索: 0回" in markdown


def test_old_history_search_setting_is_unknown_and_file_is_unchanged(monkeypatch):
    monkeypatch.setattr(service, "_call_openai", lambda **_: (
        model_output(), PortfolioAiUsage(web_search_calls=0),
    ))
    raw = run_review().model_dump(mode="json")
    for key in ("web_search_status", "web_search_requested"):
        raw.pop(key, None)
    raw["actual_usage"].pop("web_search_calls_known", None)
    raw["web_search_used"] = True  # Legacy bug persisted the setting as a fact.
    review_module.AI_REVIEW_HISTORY_PATH.write_text(json.dumps([raw]), encoding="utf-8")
    before = review_module.AI_REVIEW_HISTORY_PATH.read_bytes()
    entries, _, _ = service._load_valid_ai_review_history()
    history_id, review = entries[0]
    assert history_id == service._history_id(raw)
    assert review.web_search_used is False
    item = service._history_item(history_id, review)
    assert item.model_dump()["web_search_status"] == "unknown"
    assert "未確認" in service._build_ai_review_markdown(history_id, review)
    assert review_module.AI_REVIEW_HISTORY_PATH.read_bytes() == before
