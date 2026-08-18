from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_db, get_engine, get_session_factory, init_db
from app.main import create_app
from app.models import Base
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from app.services.security_master_catalog import local_security_master_catalog
from kabuhandan_hojo.connectors.base import DailyBarRecord, DocumentRecord, ListedIssueRecord, MarginSnapshotRecord
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


def _build_live_client(*, seed_catalog: bool = False) -> TestClient:
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
    if seed_catalog:
        with testing_session_local() as seed_session:
            local_security_master_catalog.sync_to_db(seed_session, commit=True)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"


def test_watchlist_create_and_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client() as client:
        create_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
                "memo": "phase0 test",
            },
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["ticker_code"] == "7203"
        assert created["name"] == "Toyota Motor Corporation"

        list_response = client.get("/watchlist")
        assert list_response.status_code == 200
        items = list_response.json()
        assert len(items) == 1
        assert items[0]["ticker_code"] == "7203"


def test_watchlist_create_with_code_only_keeps_missing_live_data_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client() as client:
        create_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "7203",
            },
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["ticker_code"] == "7203"
        assert created["name"] == "トヨタ自動車"

        ui_response = client.get("/ui/dashboard/data?ticker_code=7203")
        assert ui_response.status_code == 200
        payload = ui_response.json()
        assert payload["detail"]["reference_links"]
        assert payload["detail"]["price_chart"] == []
        assert any(link["url"] == "/securities/7203" for link in payload["detail"]["reference_links"])
        assert any("global.toyota/jp/ir/" in link["url"] for link in payload["detail"]["reference_links"])
        assert payload["detail"]["name"] == "トヨタ自動車"
        assert payload["detail"]["technical_summary"] == "テクニカル情報は未取得です。"
        assert payload["detail"]["technical_metrics"] == []
        assert payload["detail"]["technical_interpretations"] == []
        assert payload["detail"]["technical_source_links"]
        assert payload["detail"]["flow_summary"] == "信用需給データは未取得です。"
        assert payload["detail"]["flow_metrics"] == []
        assert any(link["url"].startswith("https://") for link in payload["detail"]["flow_source_links"])
        assert payload["market_overview"]["label"] == "\u672a\u53d6\u5f97"
        assert payload["market_overview"]["breadth"] == "\u672a\u53d6\u5f97"
        assert "uses_fallback" not in payload["detail"]
        assert all("uses_fallback" not in item for item in payload["priority_items"])
        assert all("uses_fallback" not in item for item in payload["watchlist_items"])


def test_ui_detail_auto_syncs_prices_from_jquants_when_live_prices_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JQUANTS_API_KEY", "test-key")
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()
    called_tickers: list[str] = []

    async def fake_fetch_daily_bars(*args, **kwargs) -> list[DailyBarRecord]:
        ticker_code = kwargs["ticker_code"]
        called_tickers.append(ticker_code)
        base_price = {
            "7203": Decimal("2000"),
        }.get(ticker_code, Decimal("1500"))
        step = {
            "7203": Decimal("5"),
        }.get(ticker_code, Decimal("3"))
        base_date = date(2026, 4, 1)
        bars: list[DailyBarRecord] = []
        for index in range(35):
            close_price = base_price + (step * Decimal(index))
            bars.append(
                DailyBarRecord(
                    ticker_code=ticker_code,
                    target_date=base_date + timedelta(days=index),
                    open_price=close_price - Decimal("8"),
                    high_price=close_price + Decimal("12"),
                    low_price=close_price - Decimal("15"),
                    close_price=close_price,
                    adjusted_close=close_price,
                    volume=100_000 + (index * 1_000),
                    turnover_value=Decimal("100000000"),
                    source_name="jquants",
                )
            )
        return bars

    container = get_monitoring_container()
    monkeypatch.setattr(container.jquants_connector, "fetch_daily_bars", fake_fetch_daily_bars)

    with _build_live_client() as client:
        create_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "7203",
            },
        )
        assert create_response.status_code == 201

        ui_response = client.get("/ui/dashboard/data?ticker_code=7203")
        assert ui_response.status_code == 200
        payload = ui_response.json()
        assert payload["detail"]["price_chart"]
        assert payload["detail"]["technical_summary"] != "テクニカル情報は未取得です。"
        assert payload["detail"]["technical_metrics"]
        assert payload["detail"]["technical_interpretations"]
        assert payload["detail"]["price_chart"][0]["source_name"] == "jquants"
        assert payload["market_overview"]["breadth"] == "\u672a\u53d6\u5f97"
        assert "市場価格更新ボタン" in payload["market_overview"]["comment"]
        assert payload["detail"]["factor_split"]["market"] <= 50
        assert "uses_fallback" not in payload["detail"]
        assert called_tickers == ["7203"]


def test_price_sync_endpoint_uses_jquants_daily_bars_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JQUANTS_API_KEY", "test-key")
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()

    async def fake_fetch_daily_bars(*args, **kwargs) -> list[DailyBarRecord]:
        ticker_code = kwargs["ticker_code"]
        return [
            DailyBarRecord(
                ticker_code=ticker_code,
                target_date=date(2026, 4, 1),
                open_price=Decimal("2500"),
                high_price=Decimal("2520"),
                low_price=Decimal("2490"),
                close_price=Decimal("2510"),
                adjusted_close=Decimal("2510"),
                volume=100_000,
                turnover_value=Decimal("100000000"),
                source_name="jquants",
            )
        ]

    container = get_monitoring_container()
    monkeypatch.setattr(container.jquants_connector, "fetch_daily_bars", fake_fetch_daily_bars)

    with _build_live_client() as client:
        response = client.post("/securities/1306/prices/sync?lookback_days=60")

    assert response.status_code == 200
    payload = response.json()
    assert payload["processed_count"] == 1
    assert payload["job_name"] == "sync_prices_from_jquants"


def test_security_search_supports_watchlist_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client() as client:
        create_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
            },
        )
        assert create_response.status_code == 201

        search_response = client.get("/securities/search?q=Toy")
        assert search_response.status_code == 200
        matches = search_response.json()
        assert matches
        assert matches[0]["ticker_code"] == "7203"
        assert matches[0]["in_watchlist"] is True

        security_response = client.post(
            "/securities",
            json={
                "ticker_code": "8306",
                "name": "三菱UFJフィナンシャル・グループ",
                "market": "TSE Prime",
                "industry_17": "Banks",
                "industry_33": "Banks",
            },
        )
        assert security_response.status_code == 201

        manual_response = client.get("/securities/search?q=三菱UFJ")
        assert manual_response.status_code == 200
        manual_matches = manual_response.json()
        assert manual_matches == [
            {
                "ticker_code": "8306",
                "name": "三菱UFJフィナンシャル・グループ",
                "market": "TSE Prime",
                "in_watchlist": False,
            }
        ]


def test_security_master_sync_populates_db_search_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    async def fake_fetch_listed_issues(*, as_of=None) -> list[ListedIssueRecord]:
        source_date = date(2026, 5, 26)
        records = [
            ListedIssueRecord(
                ticker_code="7203",
                local_code="72030",
                name="トヨタ自動車",
                name_english="Toyota Motor Corporation",
                market="TSE Prime",
                industry_17="Automobiles",
                industry_33="Transportation Equipment",
                listed_date=date(1949, 5, 16),
                source_as_of=source_date,
            )
        ]
        records.extend(
            ListedIssueRecord(
                ticker_code=str(code),
                local_code=f"{code}0",
                name=f"Test {code}",
                name_english=None,
                market="TSE Prime",
                industry_17=None,
                industry_33=None,
                listed_date=None,
                source_as_of=source_date,
            )
            for code in range(1000, 4999)
        )
        return records

    container = get_monitoring_container()
    monkeypatch.setattr(container.jquants_connector, "fetch_listed_issues", fake_fetch_listed_issues)

    with _build_live_client() as client:
        sync_response = client.post("/securities/master/sync")
        assert sync_response.status_code == 200
        assert sync_response.json()["processed_count"] >= 1

        response = client.get("/securities/search", params={"q": "トヨ"})

    assert response.status_code == 200
    matches = response.json()
    assert matches
    assert matches[0]["ticker_code"] == "7203"
    assert matches[0]["in_watchlist"] is False


def test_security_master_sync_can_require_jquants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JQUANTS_API_KEY", "")

    with _build_live_client() as client:
        sync_response = client.post("/securities/master/sync?require_jquants=true")

    assert sync_response.status_code == 400
    assert "JQUANTS_API_KEY" in sync_response.json()["detail"]


def test_security_search_uses_local_japanese_catalog_for_known_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client(seed_catalog=True) as client:
        response = client.get("/securities/search", params={"q": "3563"})

    assert response.status_code == 200
    matches = response.json()
    assert matches == [
        {
            "ticker_code": "3563",
            "name": "ＦＯＯＤ　＆　ＬＩＦＥ　ＣＯＭＰＡＮＩＥＳ",
            "market": "TSE Prime",
            "in_watchlist": False,
        }
    ]


def test_ui_detail_does_not_fallback_to_another_watchlist_ticker_for_unknown_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client() as client:
        create_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "7203",
            },
        )
        assert create_response.status_code == 201

        ui_response = client.get("/ui/dashboard/data?ticker_code=3563")

    assert ui_response.status_code == 200
    payload = ui_response.json()
    assert payload["selected_ticker_code"] == "3563"
    assert payload["detail"] is None


def test_portfolio_crud_and_dashboard_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    with _build_live_client() as client:
        create_response = client.post(
            "/portfolio",
            json={
                "ticker_code": "7203",
                "quantity": "100",
                "average_cost": "3200",
                "note": "manual portfolio",
                "sort_order": 1,
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["ticker_code"] == "7203"
        assert created["quantity"] == "100.0000"

        list_response = client.get("/portfolio")
        assert list_response.status_code == 200
        items = list_response.json()
        assert len(items) == 1
        assert items[0]["note"] == "manual portfolio"

        ui_response = client.get("/ui/dashboard/data")
        assert ui_response.status_code == 200
        payload = ui_response.json()
        assert payload["portfolio_items"]
        assert payload["portfolio_items"][0]["ticker_code"] == "7203"

        delete_response = client.delete("/portfolio/7203")
        assert delete_response.status_code == 204
        assert client.get("/portfolio").json() == []


def test_portfolio_public_alphanumeric_code_reuses_existing_jquants_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    kioxia_name = "\u30ad\u30aa\u30af\u30b7\u30a2\u30db\u30fc\u30eb\u30c7\u30a3\u30f3\u30b0\u30b9"

    with _build_live_client() as client:
        master_response = client.post(
            "/securities",
            json={
                "ticker_code": "285A0",
                "name": kioxia_name,
                "market": "TSE Prime",
            },
        )
        assert master_response.status_code == 201

        alias_response = client.post(
            "/portfolio",
            json={
                "ticker_code": " 285a ",
                "quantity": "100",
                "average_cost": "2500",
            },
        )
        assert alias_response.status_code == 201
        alias_holding = alias_response.json()
        assert alias_holding["ticker_code"] == "285A0"
        assert alias_holding["name"] == kioxia_name

        search_response = client.get("/securities/search", params={"q": kioxia_name})
        assert search_response.status_code == 200
        search_matches = search_response.json()
        assert len(search_matches) == 1
        assert search_matches[0]["ticker_code"] == "285A0"
        assert search_matches[0]["name"] == kioxia_name

        direct_response = client.post(
            "/portfolio",
            json={
                "ticker_code": search_matches[0]["ticker_code"],
                "quantity": "120",
                "average_cost": "2450",
            },
        )
        assert direct_response.status_code == 201
        direct_holding = direct_response.json()
        assert direct_holding["id"] == alias_holding["id"]
        assert direct_holding["ticker_code"] == "285A0"

        holdings = client.get("/portfolio").json()
        assert len(holdings) == 1
        assert holdings[0]["ticker_code"] == "285A0"
        assert holdings[0]["quantity"] == "120.0000"
        assert client.get("/securities/285A").status_code == 404


def test_portfolio_csv_public_alphanumeric_code_reuses_existing_jquants_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    kioxia_name = "\u30ad\u30aa\u30af\u30b7\u30a2\u30db\u30fc\u30eb\u30c7\u30a3\u30f3\u30b0\u30b9"

    with _build_live_client() as client:
        master_response = client.post(
            "/securities",
            json={
                "ticker_code": "285A0",
                "name": kioxia_name,
                "market": "TSE Prime",
            },
        )
        assert master_response.status_code == 201

        import_response = client.post(
            "/portfolio/import/csv",
            json={
                "csv_text": (
                    "ticker_code,quantity,average_cost,note,sort_order\n"
                    "285a,25,2600,memory,1\n"
                ),
                "replace_existing": False,
            },
        )
        assert import_response.status_code == 200
        assert import_response.json()["imported_count"] == 1

        holdings = client.get("/portfolio").json()
        assert len(holdings) == 1
        assert holdings[0]["ticker_code"] == "285A0"
        assert holdings[0]["name"] == kioxia_name
        assert client.get("/securities/285A").status_code == 404


def test_portfolio_csv_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    csv_text = "ticker_code,quantity,average_cost,note,sort_order\n7203,100,3200,core,1\n7974,50,7800,growth,2\n"

    with _build_live_client() as client:
        response = client.post(
            "/portfolio/import/csv",
            json={"csv_text": csv_text, "replace_existing": False},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["imported_count"] == 2
        assert payload["archived_count"] == 0

        items = client.get("/portfolio").json()
        assert [item["ticker_code"] for item in items] == ["7203", "7974"]


def test_flow_sync_endpoint_uses_jquants_margin_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JQUANTS_API_KEY", "test-key")
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()

    async def fake_fetch_margin_snapshot(*args, **kwargs) -> MarginSnapshotRecord | None:
        return MarginSnapshotRecord(
            ticker_code="7203",
            target_date=date(2026, 4, 1),
            margin_buy_balance=Decimal("120000"),
            margin_sell_balance=Decimal("80000"),
            source_name="jquants",
        )

    container = get_monitoring_container()
    monkeypatch.setattr(container.jquants_connector, "fetch_margin_snapshot", fake_fetch_margin_snapshot)

    with _build_live_client() as client:
        security_response = client.post(
            "/securities",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
            },
        )
        assert security_response.status_code == 201

        sync_response = client.post("/securities/7203/flow/sync?target_date=2026-04-01")
        assert sync_response.status_code == 200
        assert sync_response.json()["processed_count"] == 1

        detail_response = client.get("/securities/7203")
        assert detail_response.status_code == 200
        latest_flow = detail_response.json()["latest_flow"]
        assert latest_flow["margin_buy_balance"] == "120000.00"
        assert latest_flow["margin_sell_balance"] == "80000.00"
        assert latest_flow["source_name"] == "jquants"


def test_tdnet_sync_endpoint_imports_recent_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")

    async def fake_fetch_documents(target_date: date, ticker_code: str | None = None) -> list[DocumentRecord]:
        assert target_date == date(2026, 4, 1)
        assert ticker_code == "7203"
        return [
            DocumentRecord(
                source_name="tdnet_api",
                external_id="12345678901234:0",
                document_type="tdnet_document",
                title="自己株式取得に係る事項の決定に関するお知らせ",
                ticker_code="7203",
                published_at=datetime(2026, 4, 1, 6, 0, tzinfo=timezone.utc),
                storage_uri="tdnet://12345678901234",
                raw_payload={"code": "72030"},
                content_text=None,
                hash_digest=None,
            )
        ]

    container = get_monitoring_container()
    monkeypatch.setattr(container.tdnet_connector, "fetch_documents", fake_fetch_documents)

    with _build_live_client() as client:
        sync_response = client.post("/documents/sync/tdnet?target_date=2026-04-01&ticker_code=7203")
        assert sync_response.status_code == 200
        assert sync_response.json()["processed_count"] == 1

        detail_response = client.get("/securities/7203")
        assert detail_response.status_code == 200
        recent_events = detail_response.json()["recent_events"]
        assert recent_events
        assert recent_events[0]["source_name"] == "tdnet_api"


def test_youtube_sync_endpoint_and_ui_auto_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_MONITORED_CHANNELS", '{"7203":["UC_TOYOTA_IR"]}')
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()

    async def fake_fetch_channel_videos(
        channel_id: str,
        *,
        ticker_code: str | None = None,
        published_after: datetime | None = None,
        max_results: int = 10,
    ) -> list[DocumentRecord]:
        assert channel_id == "UC_TOYOTA_IR"
        assert ticker_code == "7203"
        assert max_results >= 1
        assert published_after is not None
        return [
            DocumentRecord(
                source_name="youtube_data_api",
                external_id="yt-001",
                document_type="video",
                title="新製品発表会 2026",
                ticker_code="7203",
                published_at=datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
                storage_uri="https://www.youtube.com/watch?v=yt-001",
                raw_payload={"channelId": channel_id},
                content_text="新製品サイクルの説明",
                hash_digest=None,
            )
        ]

    container = get_monitoring_container()
    monkeypatch.setattr(container.youtube_connector, "fetch_channel_videos", fake_fetch_channel_videos)

    with _build_live_client() as client:
        security_response = client.post(
            "/securities",
            json={
                "ticker_code": "7203",
                "name": "Toyota Motor Corporation",
                "market": "TSE Prime",
            },
        )
        assert security_response.status_code == 201

        watchlist_response = client.post("/watchlist", json={"ticker_code": "7203"})
        assert watchlist_response.status_code == 201

        sync_response = client.post(
            "/documents/sync/youtube",
            json={
                "ticker_code": "7203",
                "channel_ids": ["UC_TOYOTA_IR"],
                "published_after": "2026-03-01T00:00:00Z",
                "max_results": 5,
            },
        )
        assert sync_response.status_code == 200
        assert sync_response.json()["processed_count"] == 1

        detail_response = client.get("/securities/7203")
        assert detail_response.status_code == 200
        recent_events = detail_response.json()["recent_events"]
        assert recent_events
        assert recent_events[0]["source_name"] == "youtube_data_api"
        assert recent_events[0]["event_type"] == "product_cycle"

        monitored_response = client.post("/documents/sync/youtube/monitored?ticker_code=7203")
        assert monitored_response.status_code == 200
        assert monitored_response.json()["processed_count"] == 1

        ui_response = client.get("/ui/dashboard/data?ticker_code=7203")
        assert ui_response.status_code == 200
        reference_links = ui_response.json()["detail"]["reference_links"]
        assert any(link["url"] == "/securities/7203" for link in reference_links)
        assert any("youtube.com/watch?v=yt-001" in link["url"] for link in reference_links)


def test_allowlisted_ir_import_endpoint_validates_domain_and_creates_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("IR_ALLOWLIST_DOMAINS", '["global.toyota"]')
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()

    with _build_live_client() as client:
        ok_response = client.post(
            "/documents/import/ir",
            json={
                "ticker_code": "7203",
                "title": "自己株式取得の方針について",
                "url": "https://global.toyota/jp/ir/library/shareholder-return.html",
                "published_at": "2026-04-01T09:00:00Z",
                "event_type_hint": "shareholder_return",
                "content_text": "株主還元方針を更新しました。",
            },
        )
        assert ok_response.status_code == 201
        payload = ok_response.json()
        assert payload["raw_document"]["source_name"] == "ir_allowlist"
        assert payload["event"]["event_type"] == "shareholder_return"
        assert payload["event"]["raw_reference"] == "https://global.toyota/jp/ir/library/shareholder-return.html"

        bad_response = client.post(
            "/documents/import/ir",
            json={
                "ticker_code": "7203",
                "title": "invalid",
                "url": "https://example.com/not-allowed",
                "published_at": "2026-04-01T09:00:00Z",
            },
        )
        assert bad_response.status_code == 400
        assert "IR URL domain" in bad_response.json()["detail"]


def test_mock_health_and_watchlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://invalid:invalid@127.0.0.1:1/invalid")

    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200
        health = health_response.json()
        assert health["database"] == "mock"

        list_response = client.get("/watchlist")
        assert list_response.status_code == 200
        items = list_response.json()
        assert len(items) >= 2
        assert items[0]["ticker_code"] == "7203"

        create_response = client.post(
            "/watchlist",
            json={
                "ticker_code": "9984",
                "name": "SoftBank Group Corp.",
                "market": "TSE Prime",
                "memo": "mock item",
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["ticker_code"] == "9984"

        search_response = client.get("/securities/search?q=SoftBank")
        assert search_response.status_code == 200
        search_matches = search_response.json()
        assert search_matches[0]["ticker_code"] == "9984"
        assert search_matches[0]["in_watchlist"] is True

        updated_list_response = client.get("/watchlist")
        updated_items = updated_list_response.json()
        assert any(item["ticker_code"] == "9984" for item in updated_items)


def test_init_db_upgrades_legacy_sqlite_schema(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE security_master (
            ticker_code VARCHAR(10) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            market VARCHAR(50),
            listed_date DATE,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker_code VARCHAR(10) NOT NULL,
            memo TEXT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE flow_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker_code VARCHAR(10) NOT NULL,
            target_date DATE NOT NULL,
            average_daily_volume_20 INTEGER,
            volume_ratio_20 NUMERIC(8, 4),
            margin_buy_ratio NUMERIC(8, 4),
            short_interest_ratio NUMERIC(8, 4),
            float_turnover_ratio NUMERIC(8, 4),
            large_holder_activity_score NUMERIC(8, 4),
            source_name VARCHAR(50) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE technical_feature_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker_code VARCHAR(10) NOT NULL,
            target_date DATE NOT NULL,
            sma_5 NUMERIC(18, 4),
            sma_25 NUMERIC(18, 4),
            sma_75 NUMERIC(18, 4),
            sma_5_slope_pct NUMERIC(8, 4),
            sma_25_slope_pct NUMERIC(8, 4),
            deviation_from_sma_25_pct NUMERIC(8, 4),
            breakout_20d BOOLEAN NOT NULL DEFAULT 0,
            breakout_60d BOOLEAN NOT NULL DEFAULT 0,
            volume_ratio_20 NUMERIC(8, 4),
            atr_14 NUMERIC(18, 4),
            atr_pct_14 NUMERIC(8, 4),
            rsi_14 NUMERIC(8, 4),
            roc_20 NUMERIC(8, 4),
            gap_pct NUMERIC(8, 4),
            range_compression_20 NUMERIC(8, 4),
            source_name VARCHAR(50) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    init_db()

    verify_conn = sqlite3.connect(database_path)
    verify_cursor = verify_conn.cursor()
    verify_cursor.execute("PRAGMA table_info(security_master)")
    security_columns = {row[1] for row in verify_cursor.fetchall()}
    verify_cursor.execute("PRAGMA table_info(watchlist)")
    watchlist_columns = {row[1] for row in verify_cursor.fetchall()}
    verify_cursor.execute("PRAGMA table_info(flow_snapshot)")
    flow_columns = {row[1] for row in verify_cursor.fetchall()}
    verify_cursor.execute("PRAGMA table_info(technical_feature_daily)")
    technical_columns = {row[1] for row in verify_cursor.fetchall()}
    verify_conn.close()

    assert {"local_code", "industry_17", "industry_33"} <= security_columns
    assert {"thesis_bull", "thesis_bear", "sort_order", "last_reviewed_at"} <= watchlist_columns
    assert {
        "margin_buy_balance",
        "margin_sell_balance",
        "credit_ratio",
        "buy_balance_change_wow",
        "sell_balance_change_wow",
        "buy_balance_to_volume",
        "sell_balance_to_volume",
        "squeeze_potential_subscore",
    } <= flow_columns
    assert {
        "sma_200",
        "sma_75_slope_pct",
        "deviation_from_sma_75_pct",
        "ma_gap_5_25_pct",
        "ma_gap_25_75_pct",
        "golden_cross_flag",
        "dead_cross_flag",
        "volume_surge_ratio",
        "macd_line",
        "macd_signal",
        "macd_histogram",
        "bollinger_mid_20",
        "bollinger_upper_20",
        "bollinger_lower_20",
        "bollinger_width_20",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "body_ratio",
        "close_position_ratio",
        "gap_up_flag",
        "gap_down_flag",
        "consecutive_up_candles",
        "consecutive_down_candles",
    } <= technical_columns


def test_init_db_seeds_local_security_master_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    database_path = tmp_path / "seeded.db"

    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    init_db()

    verify_conn = sqlite3.connect(database_path)
    verify_cursor = verify_conn.cursor()
    verify_cursor.execute("SELECT COUNT(*) FROM security_master")
    count = verify_cursor.fetchone()[0]
    verify_conn.close()

    assert count >= 1
