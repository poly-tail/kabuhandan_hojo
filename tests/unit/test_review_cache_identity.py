"""Cache regressions use server clocks, local records and a provider stub only."""

from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Base, SecurityMaster
from app.models.portfolio import PortfolioHolding
from app.prompts.stock_analysis import build_stock_analysis_prompt
from app.schemas.portfolio_ai import PortfolioAiReviewRequest, PortfolioAiUsage
from app.services import ai_usage
from app.services import portfolio_ai_review as review_module
from app.services.portfolio_ai_review import PortfolioAiReviewService
from kabuhandan_hojo.models import Base as MonitoringBase
from kabuhandan_hojo.models.entities import (
    EventFact, FlowSnapshot, PriceDaily, TechnicalFeatureDaily,
)


TOKYO = ZoneInfo("Asia/Tokyo")


@pytest.fixture
def cache_case(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "stub-only")
    monkeypatch.setenv("OPENAI_REVIEW_CACHE_TTL_SECONDS", "300")
    get_settings.cache_clear()
    monkeypatch.setattr(review_module, "AI_REVIEW_CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(review_module, "AI_REVIEW_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(ai_usage, "AI_REVIEW_USAGE_V2_PATH", tmp_path / "usage.json")
    service = PortfolioAiReviewService()
    clock = [datetime(2026, 9, 11, 10, 0, tzinfo=TOKYO)]
    monkeypatch.setattr(service, "_tokyo_now", lambda: clock[0])
    calls = []

    def provider(**kwargs):
        calls.append(kwargs)
        return json.dumps({
            "generated_at": "2000-01-01T00:00:00+09:00",
            "mode": kwargs["options"].mode,
            "portfolio_summary": {}, "stocks": [], "sources": [],
            "warnings": [], "raw_model_output": None,
        }), PortfolioAiUsage(input_tokens=100, output_tokens=20, api_calls=1,
                             web_search_calls=0)

    monkeypatch.setattr(service, "_call_openai", provider)
    engine = create_engine("sqlite://")
    MonitoringBase.metadata.create_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SecurityMaster(ticker_code="7011", name="三菱重工業", is_active=True))
        session.add(PortfolioHolding(ticker_code="7011", quantity=20, average_cost=2500))
        session.add(PriceDaily(
            ticker_code="7011", target_date=date(2026, 9, 10),
            open_price=2900, high_price=3100, low_price=2800,
            close_price=3000, volume=10000, source_name="J-Quants",
        ))
        session.commit()
        request = PortfolioAiReviewRequest(mode="scanner", include_web_search=False)
        yield service, session, request, clock, calls, tmp_path
    engine.dispose()
    get_settings.cache_clear()


def test_only_generated_time_changes_identity_is_stable():
    service = PortfolioAiReviewService()
    request = PortfolioAiReviewRequest(mode="scanner", include_web_search=False)
    first = build_stock_analysis_prompt(request, [], [], [], {}, {}, {})["prompt_payload"]
    second = deepcopy(first)
    second["generated_at"] = "2099-01-01T00:00:00+09:00"
    before = deepcopy(first)
    assert service._cache_key(first) == service._cache_key(second)
    assert first == before


def test_review_twice_uses_real_dated_input_without_new_provider_or_usage(cache_case):
    service, session, request, clock, calls, directory = cache_case
    first = service.review(request, session=session)
    assert first.status == "success"
    usage_before = (directory / "usage.json").read_bytes()
    history_before = (directory / "history.json").read_bytes()
    cache_before = (directory / "cache.json").read_bytes()
    clock[0] += timedelta(seconds=12)
    second = service.review(request, session=session)
    assert second.cache_hit is True
    assert len(calls) == 1
    assert second.generated_at == first.generated_at
    assert second.generated_at.year == 2026  # Server owns generation time.
    assert second.actual_usage == first.actual_usage
    assert (directory / "usage.json").read_bytes() == usage_before
    assert (directory / "history.json").read_bytes() == history_before
    assert (directory / "cache.json").read_bytes() == cache_before
    assert second.market_snapshot[0].source_metadata["price"][0].as_of == "2026-09-10"
    assert "source_metadata" in calls[0]["user_prompt"]


@pytest.mark.parametrize("elapsed,hit", [(299.999, True), (300, False), (301, False), (-1, False)])
def test_ttl_boundary(cache_case, elapsed, hit):
    service, session, request, clock, calls, _ = cache_case
    service.review(request, session=session)
    clock[0] += timedelta(seconds=elapsed)
    second = service.review(request, session=session)
    assert second.cache_hit is hit
    assert len(calls) == (1 if hit else 2)


def test_jst_day_boundary_is_miss(cache_case):
    service, session, request, clock, calls, _ = cache_case
    clock[0] = datetime(2026, 9, 11, 23, 59, 59, tzinfo=TOKYO)
    service.review(request, session=session)
    clock[0] += timedelta(seconds=2)
    assert service.review(request, session=session).cache_hit is False
    assert len(calls) == 2


@pytest.mark.parametrize("ttl,elapsed,hit", [(0, 0, False), (2, 1, True), (2, 2, False)])
def test_config_can_shorten_or_disable_cache(cache_case, monkeypatch, ttl, elapsed, hit):
    service, session, request, clock, calls, _ = cache_case
    monkeypatch.setenv("OPENAI_REVIEW_CACHE_TTL_SECONDS", str(ttl))
    get_settings.cache_clear()
    service.review(request, session=session)
    clock[0] += timedelta(seconds=elapsed)
    assert service.review(request, session=session).cache_hit is hit
    assert len(calls) == (1 if hit else 2)


@pytest.mark.parametrize("field,value", [
    ("mode", "analyst"), ("risk_preference", "aggressive"),
    ("reasoning_effort", "high"), ("user_hypothesis", "成長を確認"),
    ("position_intent", "長期保有"), ("include_web_search", True),
    ("max_web_search_calls", 0), ("watchlist_id", 7),
    ("target", "selected"),
])
def test_semantic_request_changes_miss(cache_case, field, value):
    service, session, request, _, calls, _ = cache_case
    service.review(request, session=session)
    assert service.review(request, session=session).cache_hit is True
    changed = request.model_copy(update={field: value})
    if field == "target":
        changed.tickers = ["7011"]
    assert service.review(changed, session=session).cache_hit is False
    assert len(calls) == 2


@pytest.mark.parametrize("attribute,value", [
    ("quantity", 30), ("average_cost", 2600),
])
def test_holding_changes_miss(cache_case, attribute, value):
    service, session, request, _, calls, _ = cache_case
    service.review(request, session=session)
    assert service.review(request, session=session).cache_hit is True
    setattr(session.scalar(select(PortfolioHolding)), attribute, value)
    session.commit()
    assert service.review(request, session=session).cache_hit is False
    assert len(calls) == 2


@pytest.mark.parametrize("attribute,value", [
    ("close_price", 3050), ("target_date", date(2026, 9, 11)),
    ("updated_at", datetime(2026, 9, 11, 1, 0)), ("source_name", "manual"),
])
def test_market_value_date_version_and_provenance_changes_miss(cache_case, attribute, value):
    service, session, request, _, calls, _ = cache_case
    service.review(request, session=session)
    assert service.review(request, session=session).cache_hit is True
    setattr(session.scalar(select(PriceDaily)), attribute, value)
    session.commit()
    assert service.review(request, session=session).cache_hit is False
    assert len(calls) == 2


def test_prompt_content_and_model_changes_miss(cache_case, monkeypatch):
    service, session, request, _, calls, _ = cache_case
    service.review(request, session=session)
    original = review_module.build_stock_analysis_prompt

    def revised(*args, **kwargs):
        bundle = original(*args, **kwargs)
        bundle["system_prompt"] += "\n追加の分析指示"
        return bundle

    monkeypatch.setattr(review_module, "build_stock_analysis_prompt", revised)
    assert service.review(request, session=session).cache_hit is False
    monkeypatch.setenv("OPENAI_MODEL_SCANNER", "different-stub-model")
    get_settings.cache_clear()
    assert service.review(request, session=session).cache_hit is False
    assert len(calls) == 3


def test_present_series_without_date_is_ineligible_but_absent_series_is_not(cache_case, monkeypatch):
    service, session, request, _, calls, directory = cache_case
    snapshot = service.get_market_snapshot("7011", session=session)
    snapshot.rsi = 55  # Present technical input has no matching source/date.
    monkeypatch.setattr(service, "get_market_snapshot", lambda *a, **kw: snapshot)
    first = service.review(request, session=session)
    assert any("technical" in warning and "キャッシュ" in warning for warning in first.warnings)
    assert service.review(request, session=session).cache_hit is False
    assert len(calls) == 2
    assert not (directory / "cache.json").exists()


def test_existing_technical_flow_and_news_dates_are_connected(cache_case):
    service, session, request, _, calls, _ = cache_case
    session.add(TechnicalFeatureDaily(ticker_code="7011", target_date=date(2026, 9, 9), sma_5=2800))
    session.add(FlowSnapshot(ticker_code="7011", target_date=date(2026, 9, 4), credit_ratio=2,
                             source_name="J-Quants"))
    session.add(EventFact(event_id="stub-event", ticker_code="7011", event_type="IR",
                          event_time=datetime(2026, 9, 8, 3, 0), source_name="allowlisted-IR",
                          summary_text="一時DBのテスト資料"))
    session.commit()
    first = service.review(request, session=session)
    metadata = first.market_snapshot[0].source_metadata
    assert metadata["technical"][0].as_of == "2026-09-09"
    assert metadata["flow"][0].as_of == "2026-09-04"
    assert metadata["news"][0].as_of.startswith("2026-09-08")
    assert service.review(request, session=session).cache_hit is True
    assert len(calls) == 1


def test_opt_out_regenerates_and_operational_settings_do_not_change_identity(cache_case):
    service, session, request, _, calls, _ = cache_case
    service.review(request, session=session)
    assert service.review(request.model_copy(update={"save_result": False}), session=session).cache_hit
    assert not service.review(request.model_copy(update={"use_cache": False}), session=session).cache_hit
    assert len(calls) == 2


@pytest.mark.parametrize("damage", ["old", "broken", "naive", "invalid", "future", "wrong_version", "wrong_input"])
def test_old_corrupt_and_bad_timestamps_are_safe_misses(cache_case, damage):
    service, session, request, clock, calls, directory = cache_case
    first = service.review(request, session=session)
    path = directory / "cache.json"
    contents = json.loads(path.read_text(encoding="utf-8"))
    key = next(iter(contents))
    if damage == "old":
        contents[key] = first.model_dump(mode="json")
    elif damage == "broken":
        contents[key] = []
    elif damage == "wrong_version":
        contents[key]["format_version"] = "old"
    elif damage == "wrong_input":
        contents[key]["response"]["request_payload"]["risk_preference"] = "aggressive"
    else:
        contents[key]["recorded_at"] = {
            "naive": "2026-09-11T10:00:00", "invalid": "not-a-date",
            "future": (clock[0] + timedelta(seconds=10)).isoformat(),
        }[damage]
    path.write_text(json.dumps(contents), encoding="utf-8")
    assert service.review(request, session=session).cache_hit is False
    assert len(calls) == 2


def test_history_failure_retains_answer_and_never_saves_cache(cache_case, monkeypatch):
    service, session, request, _, calls, directory = cache_case
    monkeypatch.setattr(service, "save_ai_review_result", lambda response: False)
    response = service.review(request, session=session)
    assert response.status == "success"
    assert review_module.AI_REVIEW_HISTORY_SAVE_WARNING in response.warnings
    assert not (directory / "cache.json").exists()
    assert len(calls) == 1


def test_raw_failure_is_never_cached(cache_case, monkeypatch):
    service, session, request, _, _, directory = cache_case
    monkeypatch.setattr(service, "_call_openai", lambda **kw: ("plain raw response " * 30, PortfolioAiUsage(api_calls=1)))
    monkeypatch.setattr(service, "_repair_model_output_json", lambda **kw: ("invalid", PortfolioAiUsage(api_calls=1)))
    response = service.review(request, session=session)
    assert response.status == "json_parse_failed"
    assert not (directory / "cache.json").exists()


def test_cache_key_preserves_order_and_all_semantic_payload_fields():
    service = PortfolioAiReviewService()
    payload = {"generated_at": "volatile", "holdings": [{"ticker": "7011"}, {"ticker": "7203"}],
               "candidates": [{"ticker": "6857", "candidate_reason": "入力理由"}],
               "prompt_fingerprint": "first", "output_schema": {"type": "object"}}
    key = service._cache_key(payload)
    for field, value in [
        ("holdings", list(reversed(payload["holdings"]))),
        ("candidates", [{"ticker": "6857", "candidate_reason": "変更理由"}]),
        ("prompt_fingerprint", "second"), ("output_schema", {"type": "array"}),
    ]:
        assert service._cache_key({**payload, field: value}) != key


@pytest.mark.parametrize("metadata", [
    {}, {"price": [{"source": "J-Quants", "as_of": None}]},
    {"price": [{"source": None, "as_of": "2026-09-10"}]},
    {"price": [{"source": "J-Quants", "as_of": "invalid"}]},
])
def test_incomplete_input_metadata_explains_automatic_miss(cache_case, monkeypatch, metadata):
    service, session, request, _, calls, directory = cache_case
    snapshot = service.get_market_snapshot("7011", session=session)
    snapshot = snapshot.model_validate({**snapshot.model_dump(), "source_metadata": metadata})
    monkeypatch.setattr(service, "get_market_snapshot", lambda *a, **kw: snapshot)
    first = service.review(request, session=session)
    assert any("price" in item and "キャッシュ" in item for item in first.warnings)
    assert not service.review(request, session=session).cache_hit
    assert len(calls) == 2
    assert not (directory / "cache.json").exists()


def test_markdown_distinguishes_generation_and_data_dates(cache_case):
    service, session, request, _, _, _ = cache_case
    response = service.review(request, session=session)
    markdown = service._build_ai_review_markdown("a" * 64, response)
    assert r"回答生成日時: 2026\-09\-11" in markdown
    assert r"価格: 2026\-09\-10（J\-Quants）" in markdown
    assert "ニュース: 未入力・未取得" in markdown
