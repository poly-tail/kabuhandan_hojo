from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import get_db, get_engine, get_session_factory
from app.main import create_app
from app.models import Base
from app.schemas.portfolio_ai import PortfolioAiHolding, PortfolioAiReviewRequest, PortfolioAiUsage, PortfolioMarketSnapshot
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from app.services.portfolio_ai_review import portfolio_ai_review_service
from kabuhandan_hojo.models import Base as MonitoringBase


@pytest.fixture(autouse=True)
def clear_runtime_state() -> Generator[None, None, None]:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()


def _build_live_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    app = create_app()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    MonitoringBase.metadata.create_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_ai_review_missing_api_key_returns_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with TestClient(create_app()) as client:
        response = client.post(
            "/portfolio/ai-review",
            json={
                "use_mock_holdings": False,
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "analysis_mode": "daily",
                "risk_preference": "balanced",
                "include_web_search": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing_api_key"
    assert payload["error"]["code"] == "missing_api_key"
    assert "OPENAI_API_KEY" in payload["error"]["message"]
    assert payload["stocks"] == []
    assert payload["raw_model_output"] is None


def test_ai_review_mock_response_uses_server_mock_holdings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with TestClient(create_app()) as client:
        response = client.post(
            "/portfolio/ai-review",
            json={
                "use_mock_holdings": True,
                "holdings": [],
                "analysis_mode": "daily",
                "risk_preference": "balanced",
                "include_web_search": False,
                "mock_response": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["mock_response"] is True
    assert payload["web_search_used"] is False
    assert payload["holdings_source"] == "mock"
    assert payload["model"] == "gpt-5.5"
    assert payload["reasoning_effort"] == "high"
    assert len(payload["stocks"]) == 7
    first = payload["stocks"][0]
    assert first["ticker"] == "7011"
    assert first["judgement"]
    assert first["confidence"] >= 0
    assert first["holder_action"]
    assert first["invalidation"]
    assert first["non_monitoring_hold_risk"] in {"low", "medium", "high", "unknown"}
    assert first["needs_long_term_carry_check"] is False
    assert first["long_term_carry_check"]["final_long_term_carry_decision"] == "long_term_hold_ok"
    assert first["long_term_carry_check"]["required_alerts"]
    assert first["long_term_carry_check"]["must_check_dates_or_events"]


def test_stock_review_api_scanner_uses_mode_specific_model_and_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "scanner",
                "target": "mock",
                "include_web_search": False,
                "mock_response": True,
                "save_result": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["mode"] == "scanner"
    assert payload["model"] == "gpt-5.4"
    assert payload["reasoning_effort"] == "low"
    assert payload["estimated_cost_usd"] == 0
    assert payload["stocks"][0]["short_reason"]


def test_mock_target_never_calls_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        raise AssertionError("target=mock must not call OpenAI")

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fail_call_openai)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "scanner",
                "target": "mock",
                "include_web_search": True,
                "mock_response": False,
                "save_result": False,
                "use_cache": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["mock_response"] is True
    assert payload["estimated_cost_usd"] == 0
    assert payload["actual_usage"]["web_search_calls"] == 0
    assert any("OpenAI APIは呼びません" in warning for warning in payload["warnings"])
    assert any(stock["non_monitoring_hold_risk"] == "high" for stock in payload["stocks"])
    assert payload["portfolio_summary"]["non_monitoring_reduce_candidates"]
    assert payload["portfolio_summary"]["core_position_candidates"]
    assert payload["portfolio_summary"]["exit_or_rotate_candidates"]


def test_critical_mock_response_always_includes_long_term_carry_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "critical",
                "target": "selected",
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "include_web_search": False,
                "mock_response": True,
                "save_result": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["mode"] == "critical"
    assert payload["stocks"][0]["long_term_carry_check"]
    assert payload["stocks"][0]["long_term_carry_check"]["monitoring_interval_view"]


def test_stock_review_prompt_only_does_not_require_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "prompt_only",
                "target": "mock",
                "include_web_search": True,
                "save_result": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["mode"] == "prompt_only"
    assert payload["estimated_cost_usd"] == 0
    assert payload["manual_prompt"]
    assert "あなたは、私の株式投資判断を補助する分析担当です。" in payload["manual_prompt"]
    assert "自動投稿" in payload["manual_prompt"]


def test_stock_review_web_search_calls_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ENABLE_WEB_SEARCH", "true")
    monkeypatch.setenv("OPENAI_MAX_WEB_SEARCH_CALLS", "2")
    captured: dict[str, object] = {}

    def fake_call_openai(**kwargs: object) -> tuple[str, PortfolioAiUsage]:
        captured.update(kwargs)
        return (
            """
            {
              "generated_at": "2026-06-15T13:00:00+09:00",
              "mode": "analyst",
              "portfolio_summary": {
                "overall_view": "ok",
                "portfolio_summary": "ok",
                "market_temperature": "neutral",
                "overall_risk": "medium",
                "buy_candidates": [],
                "sell_or_reduce_candidates": [],
                "hold_priority": [],
                "cash_allocation_view": "",
                "concentration_risk": "",
                "theme_exposure": [],
                "action_plan_today": [],
                "invalidation_for_portfolio": "",
                "top_risks": []
              },
              "stocks": [],
              "sources": [],
              "warnings": [],
              "raw_model_output": null
            }
            """,
            PortfolioAiUsage(web_search_calls=2),
        )

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "analyst",
                "target": "selected",
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "include_web_search": True,
                "max_web_search_calls": 9,
                "save_result": False,
                "use_cache": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["include_web_search"] is True
    assert payload["actual_usage"]["web_search_calls"] == 2
    assert captured["max_web_search_calls"] == 2


def test_analyst_defaults_to_web_search_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ENABLE_WEB_SEARCH", "true")
    monkeypatch.setenv("OPENAI_MAX_WEB_SEARCH_CALLS", "5")
    captured: dict[str, object] = {}

    def fake_call_openai(**kwargs: object) -> tuple[str, PortfolioAiUsage]:
        captured.update(kwargs)
        return (
            """
            {
              "generated_at": "2026-06-15T13:00:00+09:00",
              "mode": "analyst",
              "input_summary": {},
              "market_summary": {},
              "portfolio_summary": {},
              "stocks": [],
              "action_plan": [],
              "critical_warnings": [],
              "sources": [],
              "warnings": [],
              "raw_model_output": null
            }
            """,
            PortfolioAiUsage(web_search_calls=5),
        )

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "analyst",
                "target": "selected",
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "save_result": False,
                "use_cache": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["include_web_search"] is True
    assert payload["web_search_policy"] == "required"
    assert captured["include_web_search"] is True


def test_ai_review_request_holdings_override_server_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/portfolio/ai-review",
            json={
                "use_mock_holdings": True,
                "holdings": [
                    {
                        "ticker": "8306",
                        "name": "三菱UFJフィナンシャル・グループ",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 1500,
                    }
                ],
                "mock_response": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["holdings_source"] == "request"
    assert [stock["ticker"] for stock in payload["stocks"]] == ["8306"]


def test_ai_review_uses_live_database_holdings_before_fallback_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_live_client(monkeypatch) as client:
        create_response = client.post(
            "/portfolio",
            json={
                "ticker_code": "7203",
                "quantity": "100",
                "average_cost": "3000",
                "sort_order": 1,
            },
        )
        assert create_response.status_code == 201

        response = client.post(
            "/portfolio/ai-review",
            json={
                "use_mock_holdings": False,
                "holdings": [],
                "mock_response": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["holdings_source"] == "database"
    assert [stock["ticker"] for stock in payload["stocks"]] == ["7203"]


def test_ai_review_parse_failure_returns_raw_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai(**_: object) -> str:
        return "not-json"

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)

    with TestClient(create_app()) as client:
        response = client.post(
            "/portfolio/ai-review",
            json={
                "use_mock_holdings": False,
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "analysis_mode": "daily",
                "risk_preference": "balanced",
                "include_web_search": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "json_parse_failed"
    assert payload["error"]["code"] == "json_parse_failed"
    assert payload["raw_model_output"] == "not-json"
    assert payload["stocks"] == []


def test_ai_review_repairs_long_non_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return ("これはJSONではない分析文です。" * 30, PortfolioAiUsage(input_tokens=10, output_tokens=20))

    def fake_repair(**_: object) -> tuple[str, PortfolioAiUsage]:
        return (
            """
            {
              "generated_at": "2026-06-15T13:00:00+09:00",
              "mode": "judge",
              "input_summary": {},
              "market_summary": {},
              "portfolio_summary": {
                "overall_view": "repair ok",
                "portfolio_summary": "repair ok",
                "market_temperature": "unknown",
                "overall_risk": "medium",
                "buy_candidates": [],
                "sell_or_reduce_candidates": [],
                "hold_priority": [],
                "cash_allocation_view": "",
                "concentration_risk": "",
                "theme_exposure": [],
                "action_plan_today": [],
                "invalidation_for_portfolio": "",
                "top_risks": []
              },
              "stocks": [],
              "action_plan": [],
              "critical_warnings": [],
              "sources": [],
              "warnings": [],
              "raw_model_output": null
            }
            """,
            PortfolioAiUsage(input_tokens=3, output_tokens=4),
        )

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)
    monkeypatch.setattr(portfolio_ai_review_service, "_repair_model_output_json", fake_repair)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "judge",
                "target": "selected",
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "include_web_search": False,
                "save_result": False,
                "use_cache": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["portfolio_summary"]["overall_view"] == "repair ok"
    assert payload["actual_usage"]["input_tokens"] == 13
    assert any("JSON整形リトライ" in warning for warning in payload["warnings"])


def test_ai_review_displays_raw_output_when_repair_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    raw_output = '{"generated_at":"2026-06-15T13:00:00+09:00","mode":"scanner","stocks":['

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return (raw_output, PortfolioAiUsage(input_tokens=10, output_tokens=20))

    def fake_repair(**_: object) -> tuple[str, PortfolioAiUsage]:
        raise ValueError("repair failed")

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)
    monkeypatch.setattr(portfolio_ai_review_service, "_repair_model_output_json", fake_repair)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "scanner",
                "target": "selected",
                "holdings": [
                    {
                        "ticker": "7011",
                        "name": "三菱重工業",
                        "market": "TSE",
                        "quantity": 100,
                        "average_price": 2900,
                    }
                ],
                "include_web_search": True,
                "max_web_search_calls": 2,
                "save_result": False,
                "use_cache": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["raw_model_output"] == raw_output
    assert payload["portfolio_summary"]["market_temperature"] == "raw_output_fallback"
    assert any("生応答" in warning for warning in payload["warnings"])


def test_openai_call_uses_structured_output_when_web_search_is_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(output_text='{"ok": true}')

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    portfolio_ai_review_service._call_openai(
        holdings=[PortfolioAiHolding(ticker="7203", name="トヨタ自動車", market="TSE", quantity=1)],
        market_snapshots=[PortfolioMarketSnapshot(ticker="7203")],
        options=PortfolioAiReviewRequest(include_web_search=True),
        api_key="test-key",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert captured["tools"] == [{"type": "web_search"}]
    assert captured["include"] == ["web_search_call.action.sources"]
    assert captured["reasoning"] == {"effort": "high"}
    assert captured["text"]["format"]["type"] == "json_schema"  # type: ignore[index]


def test_openai_call_uses_structured_output_without_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(output_text='{"ok": true}')

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    portfolio_ai_review_service._call_openai(
        holdings=[PortfolioAiHolding(ticker="7203", name="トヨタ自動車", market="TSE", quantity=1)],
        market_snapshots=[PortfolioMarketSnapshot(ticker="7203")],
        options=PortfolioAiReviewRequest(include_web_search=False),
        api_key="test-key",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "tools" not in captured
    assert captured["reasoning"] == {"effort": "high"}
    assert captured["text"]["format"]["type"] == "json_schema"  # type: ignore[index]


def test_openai_quota_error_message_is_specific() -> None:
    class FakeQuotaError(Exception):
        status_code = 429
        code = "insufficient_quota"

    message = portfolio_ai_review_service._openai_error_message(FakeQuotaError("quota exceeded"))

    assert "利用上限" in message
    assert "請求設定" in message
