"""Live target provenance regressions; every provider and write is stubbed."""

from __future__ import annotations

from collections import Counter
from collections.abc import Generator
import json
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Base, SecurityMaster
from app.models.portfolio import PortfolioHolding
from app.schemas.portfolio_ai import (
    PortfolioAiCandidate,
    PortfolioAiHolding,
    PortfolioAiReviewRequest,
    PortfolioAiUsage,
    PortfolioMarketSnapshot,
)
from app.services.portfolio_ai_review import PortfolioAiReviewService
from kabuhandan_hojo.models import Base as MonitoringBase


@pytest.fixture
def review_service(monkeypatch: pytest.MonkeyPatch) -> Generator[Any, None, None]:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-stub-only")
    get_settings.cache_clear()
    service = PortfolioAiReviewService()
    calls: Counter[str] = Counter()
    sent: list[dict[str, Any]] = []

    def call_provider(**kwargs: Any) -> tuple[str, PortfolioAiUsage]:
        calls["provider"] += 1
        sent.append(kwargs["prompt_payload"])
        return json.dumps({
            "generated_at": "2026-09-10T12:00:00+09:00",
            "mode": "scanner",
            "portfolio_summary": {},
            "stocks": [],
            "sources": [],
            "warnings": [],
            "raw_model_output": None,
        }), PortfolioAiUsage(api_calls=1, web_search_calls=0)

    def save_history(*_: Any, **__: Any) -> bool:
        calls["history"] += 1
        return True

    monkeypatch.setattr(service, "_call_openai", call_provider)
    monkeypatch.setattr(service, "_can_run_today", lambda _: True)
    monkeypatch.setattr(
        service, "_increment_daily_usage", lambda: calls.update(["quota"]),
    )
    monkeypatch.setattr(
        service, "_record_provider_usage", lambda **_: calls.update(["usage"]),
    )
    monkeypatch.setattr(service, "save_ai_review_result", save_history)
    monkeypatch.setattr(
        service, "_save_cached_response", lambda *_: calls.update(["cache"]),
    )
    monkeypatch.setattr(
        service, "get_market_snapshot",
        lambda ticker, **_: PortfolioMarketSnapshot(ticker=ticker),
    )
    yield service, calls, sent
    get_settings.cache_clear()


@pytest.fixture
def master_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    MonitoringBase.metadata.create_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            SecurityMaster(
                ticker_code="7011", local_code="70110", name="三菱重工業",
                market="プライム", is_active=True,
            ),
            SecurityMaster(
                ticker_code="285A0", local_code="285A0", name="キオクシアホールディングス",
                market="プライム", is_active=True,
            ),
        ])
        session.commit()
        yield session
    engine.dispose()


def request(**kwargs: Any) -> PortfolioAiReviewRequest:
    return PortfolioAiReviewRequest(
        **{"mode": "scanner", "include_web_search": False,
           "use_cache": False, "save_result": False, **kwargs},
    )


@pytest.mark.parametrize("target", ["holdings", "watchlist", "candidates", "selected"])
def test_empty_live_target_never_substitutes_demo_or_records_usage(
    review_service: Any, target: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls, _ = review_service
    monkeypatch.setattr(service, "get_watchlist", lambda *_, **__: [])
    response = service.review(request(target=target, save_result=True), session=None)
    assert response.status == "no_holdings"
    assert response.holdings_snapshot == []
    assert response.candidates_snapshot == []
    assert response.mock_response is False
    assert response.actual_usage.api_calls == 0
    assert calls == {}
    if target == "candidates":
        assert response.error is not None
        assert "狙い中銘柄が未登録／指定されていません" in response.error.message


def test_live_explicit_candidate_is_sent_without_synthetic_reason(review_service: Any) -> None:
    service, calls, sent = review_service
    candidate = PortfolioAiCandidate(ticker="6857", name="利用者が指定した候補")
    response = service.review(request(target="candidates", candidates=[candidate]), session=None)
    assert response.status == "success"
    assert response.holdings_source == "candidates"
    assert response.candidates_snapshot == [candidate]
    assert sent[0]["candidates"] == [candidate.model_dump(mode="json")]
    assert sent[0]["holdings"] == []
    assert calls == {"provider": 1, "usage": 1, "quota": 1}


def test_selected_unheld_ticker_uses_master_without_demo_position(
    review_service: Any, master_db: Session,
) -> None:
    service, calls, sent = review_service
    response = service.review(request(target="selected", tickers=["7011"]), session=master_db)
    holding = response.holdings_snapshot[0]
    assert holding.name == "三菱重工業"
    assert holding.market == "プライム"
    assert holding.quantity == 0
    assert holding.average_price is None
    assert holding.position_type is None
    assert response.candidates_snapshot == []
    assert sent[0]["holdings"] == [holding.model_dump(mode="json")]
    assert calls["provider"] == 1


@pytest.mark.parametrize("ticker", ["7011", "6857", "999Z"])
def test_selected_without_master_marks_unknown_name_in_provider_input(
    review_service: Any, ticker: str,
) -> None:
    service, calls, sent = review_service
    response = service.review(request(target="selected", tickers=[ticker]), session=None)
    holding = response.holdings_snapshot[0]
    assert holding.name == f"名称未登録（{ticker}）"
    assert holding.quantity == 0
    assert holding.average_price is None
    assert holding.position_type is None
    assert response.candidates_snapshot == []
    assert sent[0]["holdings"][0]["name"] == holding.name
    assert calls["provider"] == 1


@pytest.mark.parametrize("ticker", ["7011", "285A"])
def test_selected_preserves_real_db_position_including_public_code_alias(
    review_service: Any, master_db: Session, ticker: str,
) -> None:
    service, calls, _ = review_service
    canonical = "285A0" if ticker == "285A" else ticker
    master_db.add(PortfolioHolding(ticker_code=canonical, quantity=23, average_cost=1234))
    master_db.commit()
    response = service.review(request(target="selected", tickers=[ticker]), session=master_db)
    assert response.holdings_snapshot[0].ticker == canonical
    assert response.holdings_snapshot[0].quantity == 23
    assert response.holdings_snapshot[0].average_price == 1234
    assert calls["provider"] == 1


def test_explicit_zero_position_overrides_db_and_keeps_no_average_price(
    review_service: Any, master_db: Session,
) -> None:
    service, calls, sent = review_service
    master_db.add(PortfolioHolding(ticker_code="7011", quantity=23, average_cost=1234))
    master_db.commit()
    response = service.review(request(
        target="selected", tickers=["7011"],
        holdings=[PortfolioAiHolding(ticker="7011", name="7011", quantity=0)],
    ), session=master_db)
    assert response.holdings_source == "request"
    assert sent[0]["holdings"][0]["quantity"] == 0
    assert sent[0]["holdings"][0]["average_price"] is None
    assert sent[0]["holdings"][0]["name"] == "三菱重工業"
    assert calls["provider"] == 1


@pytest.mark.parametrize("options", [
    {"target": "mock"},
    {"use_mock_holdings": True},
    {"target": "candidates", "use_mock_holdings": True},
])
def test_explicit_demo_is_provenanced_and_never_calls_provider(
    review_service: Any, options: dict[str, Any],
) -> None:
    service, calls, _ = review_service
    response = service.review(request(**options), session=None)
    assert response.status == "success"
    assert response.holdings_source == "mock"
    assert response.mock_response is True
    assert response.holdings_snapshot or response.candidates_snapshot
    assert calls == {}


def test_app_mock_watchlist_targets_remain_mock_provenanced(
    review_service: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls, _ = review_service
    monkeypatch.setenv("APP_USE_MOCK", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(service, "get_watchlist", lambda *_, **__: [
        PortfolioAiHolding(ticker="7011", name="デモ監視銘柄"),
    ])
    response = service.review(request(target="watchlist"), session=None)
    assert response.holdings_source == "mock"
    assert response.mock_response is True
    assert calls == {}


def test_app_mock_setting_does_not_change_explicit_live_input_to_demo(
    review_service: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls, _ = review_service
    monkeypatch.setenv("APP_USE_MOCK", "true")
    get_settings.cache_clear()
    response = service.review(request(
        holdings=[PortfolioAiHolding(ticker="7011", name="実入力", quantity=9)],
    ), session=None)
    assert response.holdings_source == "request"
    assert response.mock_response is False
    assert response.holdings_snapshot[0].quantity == 9
    assert calls["provider"] == 1


def test_mock_response_uses_requested_live_data_without_replacing_it(review_service: Any) -> None:
    service, calls, _ = review_service
    holding = PortfolioAiHolding(ticker="999Z", name="利用者指定", quantity=4)
    response = service.review(request(holdings=[holding], mock_response=True), session=None)
    assert response.holdings_source == "request"
    assert response.holdings_snapshot == [holding]
    assert response.mock_response is True
    assert calls == {}


def test_unknown_selected_name_is_not_duplicated_in_result_labels(review_service: Any) -> None:
    service, calls, _ = review_service
    response = service.review(request(
        target="selected", tickers=["999Z"], mock_response=True,
    ), session=None)
    assert response.stocks[0].name == "名称未登録"
    for reference in response.portfolio_summary.hold_priority:
        assert reference == "名称未登録（999Z）"
    history_item = service._history_item("a" * 64, response)
    assert history_item.stocks_preview == ["名称未登録（999Z）"]
    assert calls == {}
