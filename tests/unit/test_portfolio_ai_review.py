from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import REPO_ROOT, get_settings
from app.db.session import get_db, get_engine, get_session_factory
from app.main import create_app
from app.models import Base, SecurityMaster
from app.schemas.portfolio_ai import (
    PortfolioAiHolding,
    PortfolioAiReviewRequest,
    PortfolioAiUsage,
    PortfolioMarketSnapshot,
)
from app.services import ai_usage as ai_usage_module
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from app.services import portfolio_ai_review as portfolio_ai_review_module
from app.services.portfolio_ai_review import AiReviewOutputError, portfolio_ai_review_service
from kabuhandan_hojo.models import Base as MonitoringBase


@pytest.fixture(autouse=True)
def clear_runtime_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None, None, None]:
    monkeypatch.setattr(ai_usage_module, "AI_REVIEW_USAGE_V2_PATH", tmp_path / "ai_review_usage_v2.json")
    monkeypatch.setattr(portfolio_ai_review_module, "AI_REVIEW_HISTORY_PATH", tmp_path / "ai_review_history.json")
    monkeypatch.setattr(portfolio_ai_review_module, "AI_REVIEW_CACHE_PATH", tmp_path / "ai_review_cache.json")
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


def _minimal_success_output(mode: str = "scanner") -> str:
    return (
        "{"
        '"generated_at":"2026-08-17T12:00:00+09:00",'
        f'"mode":"{mode}",'
        '"portfolio_summary":{},"stocks":[],"sources":[],"warnings":[],"raw_model_output":null'
        "}"
    )


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
    assert all(
        "（" in reference and "）" in reference
        for field in (
            "non_monitoring_reduce_candidates",
            "core_position_candidates",
            "exit_or_rotate_candidates",
        )
        for reference in payload["portfolio_summary"][field]
    )
    assert "三菱重工業（7011）" in payload["portfolio_summary"]["core_position_candidates"]


def test_selected_ticker_identity_is_hydrated_from_security_master(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MonitoringBase.metadata.create_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        session.add(
            SecurityMaster(
                ticker_code="6501",
                local_code="65010",
                name="日立製作所",
                market="プライム",
                is_active=True,
            )
        )
        session.add(
            SecurityMaster(
                ticker_code="285A",
                local_code="285A0",
                name="キオクシアホールディングス",
                market="プライム",
                is_active=True,
            )
        )
        session.add(
            SecurityMaster(
                ticker_code="7203",
                local_code="72030",
                name="トヨタ自動車",
                market="プライム",
                is_active=True,
            )
        )
        session.commit()

        response = portfolio_ai_review_service.review(
            PortfolioAiReviewRequest(
                mode="scanner",
                target="selected",
                tickers=["6501", "285A", "285A0"],
                mock_response=True,
                include_web_search=False,
                save_result=False,
                use_cache=False,
            ),
            session=session,
        )
        explicit_response = portfolio_ai_review_service.review(
            PortfolioAiReviewRequest(
                mode="scanner",
                target="selected",
                holdings=[
                    PortfolioAiHolding(
                        ticker="6501",
                        name="6501",
                        market="TSE",
                        quantity=0,
                    ),
                    PortfolioAiHolding(
                        ticker="285A0",
                        name="285A0",
                        market="TSE",
                        quantity=0,
                    ),
                    PortfolioAiHolding(
                        ticker="72030",
                        name="72030",
                        market="TSE",
                        quantity=0,
                    ),
                ],
                mock_response=True,
                include_web_search=False,
                save_result=False,
                use_cache=False,
            ),
            session=session,
        )

    assert response.status == "success"
    assert len(response.holdings_snapshot) == 2
    assert response.holdings_snapshot[0].ticker == "6501"
    assert response.holdings_snapshot[0].name == "日立製作所"
    assert response.stocks[0].name == "日立製作所"
    assert response.holdings_snapshot[1].ticker == "285A"
    assert response.holdings_snapshot[1].name == "キオクシアホールディングス"
    assert explicit_response.holdings_snapshot[0].name == "日立製作所"
    assert explicit_response.stocks[0].name == "日立製作所"
    assert explicit_response.holdings_snapshot[1].ticker == "285A"
    assert explicit_response.holdings_snapshot[1].name == "キオクシアホールディングス"
    assert explicit_response.stocks[1].name == "キオクシアホールディングス"
    assert explicit_response.holdings_snapshot[2].ticker == "7203"
    assert explicit_response.holdings_snapshot[2].name == "トヨタ自動車"


def test_response_security_references_use_trusted_names_and_public_codes() -> None:
    raw_output = json.dumps(
        {
            "generated_at": "2026-08-19T12:00:00+09:00",
            "mode": "scanner",
            "input_summary": {},
            "market_summary": {},
            "portfolio_summary": {
                "non_monitoring_reduce_candidates": ["285A0", "誤った名称（7011）", "9999"],
                "core_position_candidates": ["キオクシアホールディングス"],
                "exit_or_rotate_candidates": [],
            },
            "stocks": [
                {
                    "ticker": "285A0",
                    "name": "285A0",
                    "judgement": "watch",
                    "judgement_label": "様子見",
                    "confidence": 0.5,
                    "non_monitoring_hold_risk": "high",
                    "needs_long_term_carry_check": True,
                    "short_reason": "確認待ち",
                    "key_risks": [],
                    "invalidation": "",
                    "needs_analyst_mode": False,
                    "needs_judge_mode": False,
                    "verification_labels": [],
                    "watch_points": [],
                    "risk_flags": [],
                    "needs_detail_analysis": False,
                    "key_points": [],
                    "technical_view": "",
                    "market_context_view": "",
                    "holder_action": "",
                    "stop_or_reduce_condition": "",
                    "execution_plan": [],
                    "critical_check": [],
                    "sources": [],
                }
            ],
            "action_plan": [],
            "critical_warnings": [],
            "sources": [],
            "warnings": [],
            "raw_model_output": None,
        },
        ensure_ascii=False,
    )
    response = portfolio_ai_review_service.parse_ai_review_result(
        raw_output,
        options=PortfolioAiReviewRequest(mode="scanner", target="holdings"),
    )
    response.stocks.append(
        response.stocks[0].model_copy(
            update={"ticker": "9999", "name": "モデルが作った未確認名称"}
        )
    )

    enriched = portfolio_ai_review_service._enrich_response_security_references(
        response,
        holdings=[
            PortfolioAiHolding(
                ticker="285A0",
                name="キオクシアホールディングス",
                market="プライム",
                quantity=100,
            ),
            PortfolioAiHolding(
                ticker="7011",
                name="三菱重工業",
                market="プライム",
                quantity=100,
            ),
            PortfolioAiHolding(
                ticker="9999",
                name="9999",
                market="TSE",
                quantity=0,
            ),
        ],
        candidates=[],
    )

    assert enriched.stocks[0].ticker == "285A0"
    assert enriched.stocks[0].name == "キオクシアホールディングス"
    assert enriched.stocks[1].ticker == "9999"
    assert enriched.stocks[1].name == "名称未登録"
    assert enriched.portfolio_summary.non_monitoring_reduce_candidates == [
        "キオクシアホールディングス（285A）",
        "三菱重工業（7011）",
        "名称未登録（9999）",
    ]
    assert enriched.portfolio_summary.core_position_candidates == [
        "キオクシアホールディングス（285A）"
    ]
    assert portfolio_ai_review_service._public_security_code("72030") == "72030"


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
        usage_response = client.get("/api/ai/stock-review/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "json_parse_failed"
    assert payload["error"]["code"] == "json_parse_failed"
    assert payload["parse_failure_kind"] == "json_syntax"
    assert payload["raw_model_output"] == "not-json"
    assert payload["stocks"] == []
    usage_payload = usage_response.json()
    assert usage_payload["today"]["review_runs"] == 0
    assert usage_payload["today"]["api_calls"] == 1
    assert usage_payload["today"]["unpriced_api_calls"] == 1


def test_scanner_accepts_legacy_concentration_comment_without_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    raw_output = json.dumps(
        {
            "generated_at": "2026-08-19T12:24:34+09:00",
            "mode": "scanner",
            "portfolio_summary": {
                "concentration_comment": "集中リスクを確認する",
            },
            "stocks": [
                {
                    "ticker": "285A0",
                    "name": "キオクシアホールディングス",
                    "judgement": "毎日見られないなら縮小候補",
                    "judgement_label": "非監視なら縮小候補",
                }
            ],
            "sources": [],
            "warnings": [],
            "raw_model_output": None,
        },
        ensure_ascii=False,
    )

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return raw_output, PortfolioAiUsage(input_tokens=10, output_tokens=20)

    def fail_if_repair_is_called(**_: object) -> tuple[str, PortfolioAiUsage]:
        raise AssertionError("compatible JSON must not trigger another OpenAI call")

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)
    monkeypatch.setattr(portfolio_ai_review_service, "_repair_model_output_json", fail_if_repair_is_called)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/ai/stock-review",
            json={
                "mode": "scanner",
                "target": "selected",
                "holdings": [
                    {
                        "ticker": "285A0",
                        "name": "キオクシアホールディングス",
                        "market": "TSE",
                        "quantity": 100,
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
    assert payload["portfolio_summary"]["concentration_risk"] == "集中リスクを確認する"
    assert payload["stocks"][0]["judgement"] == "reduce_risk"
    assert payload["raw_model_output"] is None
    assert payload["actual_usage"]["api_calls"] == 1


def test_valid_json_schema_failure_is_not_reported_as_json_syntax_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    raw_output = json.dumps(
        {
            "generated_at": "2026-08-19T12:24:34+09:00",
            "mode": "scanner",
            "portfolio_summary": {
                "unsupported_summary_field": "x" * 220,
            },
            "stocks": [],
            "sources": [],
            "warnings": [],
            "raw_model_output": None,
        },
        ensure_ascii=False,
    )

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return raw_output, PortfolioAiUsage(input_tokens=10, output_tokens=20)

    repair_calls = 0

    def fake_repair(**_: object) -> tuple[str, PortfolioAiUsage]:
        nonlocal repair_calls
        repair_calls += 1
        raise ValueError("sensitive repair detail")

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
                        "ticker": "7203",
                        "name": "トヨタ自動車",
                        "market": "TSE",
                        "quantity": 100,
                    }
                ],
                "include_web_search": False,
                "save_result": True,
                "use_cache": True,
            },
        )
        usage_response = client.get("/api/ai/stock-review/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "json_parse_failed"
    assert payload["error"]["code"] == "json_parse_failed"
    assert payload["parse_failure_kind"] == "schema_validation"
    assert "有効なJSON" in payload["portfolio_summary"]["overall_view"]
    assert "JSON構文を解析できません" not in payload["portfolio_summary"]["overall_view"]
    assert repair_calls == 1
    assert usage_response.json()["today"]["review_runs"] == 0
    cache_path = portfolio_ai_review_module.AI_REVIEW_CACHE_PATH
    assert cache_path == tmp_path / "ai_review_cache.json"
    assert not cache_path.exists()
    portfolio_ai_review_service._write_json(cache_path, {"legacy-fallback": payload})
    assert portfolio_ai_review_service._load_cached_response("legacy-fallback") is None
    log_text = caplog.text
    assert "error_type=ValueError" in log_text
    assert "x" * 220 not in log_text
    assert "sensitive repair detail" not in log_text


def test_scanner_accepts_legacy_summary_view_alias() -> None:
    raw_output = json.dumps(
        {
            "generated_at": "2026-08-18T22:48:00+09:00",
            "mode": "scanner",
            "portfolio_summary": {"summary_view": "全体所見"},
            "stocks": [],
            "sources": [],
            "warnings": [],
            "raw_model_output": None,
        },
        ensure_ascii=False,
    )

    parsed = portfolio_ai_review_service.parse_ai_review_result(raw_output)

    assert parsed.portfolio_summary.overall_view == "全体所見"


@pytest.mark.parametrize(
    ("raw_output", "failure_kind"),
    [
        ("[]", "root_shape"),
        (
            '[{"generated_at":"2026-08-19T12:24:34+09:00","mode":"scanner",'
            '"portfolio_summary":{},"stocks":[],"sources":[],"warnings":[],'
            '"raw_model_output":null}]',
            "root_shape",
        ),
        ("{}", "schema_validation"),
        (
            '{"generated_at":"2026-08-19T12:24:34+09:00","mode":"scanner",'
            '"portfolio_summary":{},"stocks":"not-a-list","sources":[],"warnings":[],'
            '"raw_model_output":null}',
            "schema_validation",
        ),
        (
            '{"generated_at":"2026-08-19T12:24:34+09:00","mode":"scanner",'
            '"portfolio_summary":{},"stocks":["not-an-object"],"sources":[],"warnings":[],'
            '"raw_model_output":null}',
            "schema_validation",
        ),
        (
            '{"generated_at":"2026-08-19T12:24:34+09:00","mode":"scanner",'
            '"portfolio_summary":{},"stocks":[{"ticker":"7203","name":"トヨタ",'
            '"judgement":123}],"sources":[],"warnings":[],"raw_model_output":null}',
            "schema_validation",
        ),
        (
            '{"generated_at":"2026-08-19T12:24:34+09:00","mode":"scanner",'
            '"portfolio_summary":{"summary_view":["not-a-string"]},"stocks":[],'
            '"sources":[],"warnings":[],"raw_model_output":null}',
            "schema_validation",
        ),
        (
            '{"generated_at":"2026-08-19T12:24:34+09:00","mode":"scanner",'
            '"portfolio_summary":{},"stocks":[],"sources":[],"warnings":[],'
            '"raw_model_output":null,"status":"json_parse_failed"}',
            "schema_validation",
        ),
    ],
)
def test_parse_rejects_invalid_root_and_required_shapes(raw_output: str, failure_kind: str) -> None:
    with pytest.raises(AiReviewOutputError) as exc_info:
        portfolio_ai_review_service.parse_ai_review_result(raw_output)

    assert exc_info.value.failure_kind == failure_kind


def test_ai_review_repairs_long_non_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return (
            "これはJSONではない分析文です。" * 30,
            PortfolioAiUsage(input_tokens=10, cached_input_tokens=0, output_tokens=20),
        )

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
            PortfolioAiUsage(input_tokens=3, cached_input_tokens=0, output_tokens=4),
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
        usage_response = client.get("/api/ai/stock-review/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["portfolio_summary"]["overall_view"] == "repair ok"
    assert payload["actual_usage"]["input_tokens"] == 13
    assert payload["actual_usage"]["api_calls"] == 2
    assert any("JSON整形リトライ" in warning for warning in payload["warnings"])
    usage_payload = usage_response.json()
    assert usage_payload["today"]["review_runs"] == 1
    assert usage_payload["today"]["api_calls"] == 2
    assert usage_payload["today"]["input_tokens"] == 13
    assert usage_payload["today"]["output_tokens"] == 24


def test_ai_review_displays_raw_output_when_repair_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    raw_output = (
        '{"generated_at":"2026-06-15T13:00:00+09:00","mode":"scanner","stocks":['
        + "x" * 250
    )
    repair_calls = 0

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return (raw_output, PortfolioAiUsage(input_tokens=10, output_tokens=20))

    def fake_repair(**_: object) -> tuple[str, PortfolioAiUsage]:
        nonlocal repair_calls
        repair_calls += 1
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
        usage_response = client.get("/api/ai/stock-review/usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "json_parse_failed"
    assert payload["error"]["code"] == "json_parse_failed"
    assert payload["parse_failure_kind"] == "json_syntax"
    assert payload["raw_model_output"] == raw_output
    assert payload["portfolio_summary"]["market_temperature"] == "raw_output_fallback"
    assert any("生応答" in warning for warning in payload["warnings"])
    assert repair_calls == 1
    assert usage_response.json()["today"]["review_runs"] == 0


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


def test_five_stock_scan_counts_as_one_review_and_usage_endpoint_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_DAILY_REQUEST_LIMIT", "300")
    production_v1_path = REPO_ROOT / "data" / "ai_review_usage.json"
    production_v2_path = REPO_ROOT / "data" / "ai_review_usage_v2.json"
    production_v1_before = production_v1_path.read_bytes() if production_v1_path.exists() else None
    production_v2_before = production_v2_path.read_bytes() if production_v2_path.exists() else None

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        return (
            _minimal_success_output("scanner"),
            PortfolioAiUsage(
                input_tokens=1_000,
                cached_input_tokens=100,
                output_tokens=200,
                reasoning_tokens=50,
            ),
        )

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)
    holdings = [
        {
            "ticker": f"{7000 + index}",
            "name": f"銘柄{index}",
            "market": "TSE",
            "quantity": 1,
            "average_price": 1000,
        }
        for index in range(1, 6)
    ]

    with TestClient(create_app()) as client:
        request_payload = {
            "mode": "scanner",
            "target": "selected",
            "holdings": holdings,
            "include_web_search": False,
            "save_result": False,
            "use_cache": False,
        }
        response = client.post("/api/ai/stock-review", json=request_payload)
        second_response = client.post("/api/ai/stock-review", json=request_payload)
        usage_response = client.get("/api/ai/stock-review/usage")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "success"
    assert usage_response.status_code == 200
    assert usage_response.headers["cache-control"] == "no-store"
    usage_payload = usage_response.json()
    assert usage_payload["scope"] == "legacy_stock_review"
    assert usage_payload["daily_limit"] == 300
    assert usage_payload["remaining_today"] == 298
    assert usage_payload["today"]["review_runs"] == 2
    assert usage_payload["today"]["api_calls"] == 2
    assert usage_payload["today"]["input_tokens"] == 2_000
    assert usage_payload["today"]["cached_input_tokens"] == 200
    assert usage_payload["today"]["estimated_cost_usd"] > 0
    production_v1_after = production_v1_path.read_bytes() if production_v1_path.exists() else None
    production_v2_after = production_v2_path.read_bytes() if production_v2_path.exists() else None
    assert production_v1_after == production_v1_before
    assert production_v2_after == production_v2_before


def test_daily_quota_allows_the_300th_review_and_rejects_the_next_before_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_DAILY_REQUEST_LIMIT", "300")
    ledger = ai_usage_module.get_legacy_ai_usage_ledger()
    for _ in range(299):
        ledger.record_review_success()

    openai_calls = 0

    def fake_call_openai(**_: object) -> tuple[str, PortfolioAiUsage]:
        nonlocal openai_calls
        openai_calls += 1
        return (
            _minimal_success_output("scanner"),
            PortfolioAiUsage(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=20,
            ),
        )

    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", fake_call_openai)
    request_payload = {
        "mode": "scanner",
        "target": "selected",
        "holdings": [
            {
                "ticker": "7203",
                "name": "トヨタ自動車",
                "market": "TSE",
                "quantity": 1,
                "average_price": 1000,
            }
        ],
        "include_web_search": False,
        "save_result": False,
        "use_cache": False,
    }

    with TestClient(create_app()) as client:
        allowed_response = client.post("/api/ai/stock-review", json=request_payload)
        rejected_response = client.post("/api/ai/stock-review", json=request_payload)
        usage_response = client.get("/api/ai/stock-review/usage")

    assert allowed_response.status_code == 200
    assert allowed_response.json()["status"] == "success"
    assert rejected_response.status_code == 200
    assert rejected_response.json()["status"] == "daily_limit_exceeded"
    assert openai_calls == 1
    usage_payload = usage_response.json()
    assert usage_payload["today"]["review_runs"] == 300
    assert usage_payload["today"]["api_calls"] == 1
    assert usage_payload["remaining_today"] == 0


def test_extract_usage_counts_actual_web_search_items_instead_of_configured_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponses:
        def create(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                output_text=_minimal_success_output("analyst"),
                output=[
                    SimpleNamespace(type="web_search_call"),
                    SimpleNamespace(type="message"),
                ],
                usage=SimpleNamespace(
                    input_tokens=120,
                    input_tokens_details=SimpleNamespace(cached_tokens=20),
                    output_tokens=30,
                    output_tokens_details=SimpleNamespace(reasoning_tokens=10),
                ),
            )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    _, usage = portfolio_ai_review_service._call_openai(
        holdings=[PortfolioAiHolding(ticker="7203", name="トヨタ自動車", market="TSE", quantity=1)],
        market_snapshots=[PortfolioMarketSnapshot(ticker="7203")],
        options=PortfolioAiReviewRequest(mode="analyst", include_web_search=True, max_web_search_calls=5),
        api_key="test-key",
        model="gpt-5.4",
        reasoning_effort="medium",
    )

    assert usage.api_calls == 1
    assert usage.input_tokens == 120
    assert usage.cached_input_tokens == 20
    assert usage.output_tokens == 30
    assert usage.reasoning_tokens == 10
    assert usage.web_search_calls == 1
