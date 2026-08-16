from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.db.session import get_db, get_engine, get_session_factory
from app.main import create_app
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from kabuhandan_hojo.connectors.base import DailyBarRecord, DocumentRecord
from kabuhandan_hojo.models import Base as MonitoringBase


@pytest.fixture(autouse=True)
def clear_runtime_state() -> Generator[None, None, None]:
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()
    yield
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()


def _build_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("IR_ALLOWLIST_DOMAINS", "[\"ir.example.jp\"]")

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


def _price_payload(days: int = 240) -> list[dict[str, object]]:
    start_date = date(2025, 8, 1)
    payload: list[dict[str, object]] = []
    for index in range(days):
        trend_boost = Decimal(max(index - (days - 40), 0)) * Decimal("2")
        close_boost = Decimal(max(index - (days - 20), 0)) * Decimal("3")
        open_price = Decimal("1000") + Decimal(index * 10) + trend_boost
        close_price = open_price + Decimal("8") + close_boost
        payload.append(
            {
                "target_date": (start_date + timedelta(days=index)).isoformat(),
                "open": str(open_price),
                "high": str(close_price + Decimal("6")),
                "low": str(open_price - Decimal("12")),
                "close": str(close_price),
                "adjusted_close": str(close_price),
                "volume": 100000 + index * 3000,
                "turnover_value": str(100000000 + index * 1000000),
                "source_name": "manual",
            }
        )
    return payload


def test_phase2_monitoring_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch) as client:
        bootstrap_response = client.post("/sources/bootstrap")
        assert bootstrap_response.status_code == 200
        assert bootstrap_response.json()["processed_count"] == 5

        security_response = client.post(
            "/securities",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
                "industry_17": "Automobiles",
                "industry_33": "Transportation Equipment",
            },
        )
        assert security_response.status_code == 201

        watchlist_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
                "memo": "phase2 monitoring",
            },
        )
        assert watchlist_response.status_code == 201

        prices_response = client.post("/securities/7203/prices", json=_price_payload())
        assert prices_response.status_code == 201
        assert len(prices_response.json()) == 240

        financials_response = client.post(
            "/securities/7203/financials",
            json={
                "target_date": "2026-03-31",
                "revenue_growth_yoy": "20.0",
                "operating_profit_growth_yoy": "15.0",
                "roe": "12.0",
                "equity_ratio": "50.0",
                "source_name": "manual",
            },
        )
        assert financials_response.status_code == 201

        flow_response = client.post(
            "/securities/7203/flow",
            json={
                "target_date": "2026-03-31",
                "average_daily_volume_20": 250000,
                "volume_ratio_20": "1.8",
                "margin_buy_balance": "120000",
                "margin_sell_balance": "90000",
                "buy_balance_change_wow": "3.5",
                "sell_balance_change_wow": "6.0",
                "short_interest_ratio": "0.2",
                "float_turnover_ratio": "1.5",
                "large_holder_activity_score": "20.0",
                "source_name": "manual",
            },
        )
        assert flow_response.status_code == 201

        import_response = client.post(
            "/documents/import",
            json={
                "source_name": "edinet",
                "external_id": "DOC-001",
                "document_type": "timely_disclosure",
                "title": "業績予想の上方修正に関するお知らせ",
                "ticker_code": "7203",
                "published_at": datetime(2026, 4, 1, tzinfo=timezone.utc).isoformat(),
                "storage_uri": "edinet://DOC-001",
                "raw_payload": {"docTypeCode": "120", "important_value": "guidance_raise"},
                "content_text": "通期見通しを上方修正しました。",
            },
        )
        assert import_response.status_code == 201
        assert import_response.json()["event"]["event_type"] == "upward_revision"

        feature_response = client.post("/securities/7203/technical/rebuild")
        assert feature_response.status_code == 200
        feature_payload = feature_response.json()
        assert feature_payload["breakout_20d"] is True
        assert Decimal(feature_payload["rsi_14"]) > Decimal("55")
        assert Decimal(feature_payload["macd_line"]) >= Decimal(feature_payload["macd_signal"])
        assert Decimal(feature_payload["macd_histogram"]) >= Decimal("0")
        assert Decimal(feature_payload["ma_25"]) > Decimal("0")
        assert Decimal(feature_payload["ma_75"]) > Decimal("0")
        assert Decimal(feature_payload["volume_surge_ratio"]) > Decimal("1")

        score_response = client.post("/securities/7203/score/recalculate?target_date=2026-04-01")
        assert score_response.status_code == 200
        score_payload = score_response.json()
        assert Decimal(score_payload["score"]["total_score"]) >= Decimal("65")
        assert score_payload["score"]["score_breakdown"]["technical_subscores"]["trend"] >= 50
        assert score_payload["score"]["score_breakdown"]["flow_subscores"]["liquidity"] >= 50

        detail_response = client.get("/securities/7203")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["security"]["ticker_code"] == "7203"
        assert len(detail_payload["latest_prices"]) == 60
        assert detail_payload["latest_score"]["ticker_code"] == "7203"
        assert detail_payload["technical_context"]["metrics"]
        assert detail_payload["flow_context"]["metrics"]
        assert "moving_average_state" in detail_payload["technical_context"]
        assert "state_summary" in detail_payload["flow_context"]
        assert Decimal(detail_payload["latest_flow"]["credit_ratio"]) > Decimal("1")

        dashboard_response = client.get("/dashboard")
        assert dashboard_response.status_code == 200
        dashboard_payload = dashboard_response.json()
        assert dashboard_payload["high_priority"]
        assert dashboard_payload["recent_events"][0]["ticker_code"] == "7203"

        ui_response = client.get("/ui/dashboard/data?ticker_code=7203")
        assert ui_response.status_code == 200
        ui_payload = ui_response.json()
        assert ui_payload["detail"]["reference_links"]
        assert ui_payload["detail"]["price_chart"]
        assert any(link["url"] == "/securities/7203" for link in ui_payload["detail"]["reference_links"])
        assert any("api.edinet-fsa.go.jp/api/v2/documents/" in link["url"] for link in ui_payload["detail"]["reference_links"])
        assert ui_payload["detail"]["name"] == "トヨタ自動車"
        assert ui_payload["detail"]["materials"][0]["source_links"]
        assert ui_payload["detail"]["technical_source_links"]
        assert ui_payload["detail"]["flow_source_links"]
        assert ui_payload["important_alerts"][0]["source_links"]

        screening_response = client.get("/screening?min_total_score=60")
        assert screening_response.status_code == 200
        screening_payload = screening_response.json()
        assert screening_payload[0]["security"]["ticker_code"] == "7203"
        assert "20d_breakout" in screening_payload[0]["matched_reasons"]
        assert screening_payload[0]["latest_flow"]["credit_ratio"] is not None

        screening_query_response = client.post(
            "/screening/query",
                json={
                    "min_total_score": "60",
                    "limit": 10,
                    "technical": {
                        "min_rsi_14": "55",
                        "macd_histogram_positive": True,
                        "price_above_ma_25": True,
                        "golden_cross_only": False,
                    },
                "flow": {
                    "min_credit_ratio": "1.0",
                    "min_buy_balance_change_wow": "1.0",
                },
            },
        )
        assert screening_query_response.status_code == 200
        screening_query_payload = screening_query_response.json()
        assert screening_query_payload
        assert screening_query_payload[0]["security"]["ticker_code"] == "7203"


def test_phase2_sync_endpoints_use_allowed_connectors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_daily_bars(*args, **kwargs) -> list[DailyBarRecord]:
        return [
            DailyBarRecord(
                ticker_code="7203",
                target_date=date(2026, 4, 1),
                open_price=Decimal("1000"),
                high_price=Decimal("1010"),
                low_price=Decimal("990"),
                close_price=Decimal("1005"),
                adjusted_close=Decimal("1005"),
                volume=150000,
                turnover_value=Decimal("100000000"),
                source_name="jquants",
            )
        ]

    async def fake_fetch_documents(*args, **kwargs) -> list[DocumentRecord]:
        return [
            DocumentRecord(
                source_name="edinet",
                external_id="DOC-777",
                document_type="quarterly_report",
                title="四半期報告書",
                ticker_code="7203",
                published_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                storage_uri=None,
                raw_payload={"docTypeCode": "140"},
                content_text="四半期報告書を提出しました。",
                hash_digest=None,
            )
        ]

    container = get_monitoring_container()
    monkeypatch.setattr(container.jquants_connector, "fetch_daily_bars", fake_fetch_daily_bars)
    monkeypatch.setattr(container.edinet_connector, "fetch_documents", fake_fetch_documents)

    with _build_client(monkeypatch) as client:
        security_response = client.post(
            "/securities",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
            },
        )
        assert security_response.status_code == 201

        prices_sync_response = client.post("/securities/7203/prices/sync?lookback_days=30")
        assert prices_sync_response.status_code == 200
        assert prices_sync_response.json()["processed_count"] == 1

        documents_sync_response = client.post("/documents/sync/edinet?target_date=2026-04-02")
        assert documents_sync_response.status_code == 200
        assert documents_sync_response.json()["processed_count"] == 1
