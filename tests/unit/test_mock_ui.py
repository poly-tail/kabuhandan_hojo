from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings


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


def test_mock_dashboard_screening_and_ui_data_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://invalid:invalid@127.0.0.1:1/invalid")

    with TestClient(create_app()) as client:
        dashboard_response = client.get("/dashboard")
        assert dashboard_response.status_code == 200
        dashboard = dashboard_response.json()
        assert dashboard["high_priority"]
        assert dashboard["high_priority"][0]["security"]["ticker_code"] == "7203"
        assert dashboard["disclaimer"]

        screening_response = client.get("/screening?min_total_score=65")
        assert screening_response.status_code == 200
        screening = screening_response.json()
        assert screening
        assert Decimal(screening[0]["latest_score"]["total_score"]) >= Decimal("65")

        ui_response = client.get("/ui/dashboard/data?ticker_code=7203")
        assert ui_response.status_code == 200
        ui_payload = ui_response.json()
        assert ui_payload["market_overview"]["label"]
        assert ui_payload["priority_items"]
        assert ui_payload["screening_items"]
        assert ui_payload["selected_ticker_code"] == "7203"
        assert ui_payload["detail"]["ticker_code"] == "7203"
        assert ui_payload["detail"]["reference_links"]
        assert ui_payload["detail"]["price_chart"]
        assert ui_payload["detail"]["technical_metrics"]
        assert ui_payload["detail"]["flow_metrics"]
        assert ui_payload["detail"]["hypothesis"]["primary"]
        assert ui_payload["detail"]["materials"][0]["source_links"]
        assert ui_payload["detail"]["technical_source_links"]
        assert ui_payload["important_alerts"][0]["source_links"]
        assert any(link["url"] == "/securities/7203" for link in ui_payload["detail"]["reference_links"])
        assert any(
            link["url"] == "https://finance.yahoo.co.jp/quote/7203.T"
            for link in ui_payload["detail"]["reference_links"]
        )
        assert any("global.toyota/jp/ir/" in link["url"] for link in ui_payload["detail"]["reference_links"])
        assert not any("jquants" in link["url"] for link in ui_payload["detail"]["reference_links"])
        assert any(link["url"].startswith("https://") for link in ui_payload["detail"]["materials"][0]["source_links"])
        assert any(link["url"].startswith("https://") for link in ui_payload["important_alerts"][0]["source_links"])
        assert any(link["url"].startswith("https://") for link in ui_payload["detail"]["flow_source_links"])


def test_dashboard_ui_shells_are_served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        top_response = client.get("/ui/dashboard")
        detail_response = client.get("/ui/security/7203")
        chart_response = client.get("/ui/security/7203/chart")
        review_response = client.get("/ui/review")

    assert top_response.status_code == 200
    assert detail_response.status_code == 200
    assert chart_response.status_code == 200
    assert review_response.status_code == 200

    assert "page-top" in top_response.text
    assert "/ui/dashboard/data" in top_response.text
    assert "/ui/security/" in top_response.text
    assert "/dashboard" in top_response.text
    assert "/securities/search?q=" in top_response.text
    assert "security-master-sync-button" in top_response.text
    assert "market-proxy-sync-button" in top_response.text
    assert 'data-manual-update="watchlist-scores"' in top_response.text
    assert 'data-manual-update="portfolio-prices"' in top_response.text
    assert "今日の保有銘柄レビュー" in top_response.text
    assert "軽量スキャン" in top_response.text
    assert "個別詳細分析" in top_response.text
    assert "全体売買判断" in top_response.text
    assert "重要局面分析" in top_response.text
    assert "ChatGPT投入用プロンプトを生成" in top_response.text
    assert "プロンプトをコピー" in top_response.text
    assert "watchlist-ai-review-results" in top_response.text
    assert 'data-watchlist-ai-select="' in top_response.text
    assert "Web検索ON" in top_response.text
    assert "APIなしのサンプル表示（課金なし）" in top_response.text
    assert "reasoning ${data.reasoning_effort}" in top_response.text
    assert "/api/ai/stock-review" in top_response.text
    assert "portfolio-ai-review-results" in top_response.text
    assert "中長期持ち越し・非監視期間リスク" in top_response.text
    assert "非監視リスク高" in top_response.text
    assert "毎日見られないなら非推奨" in top_response.text
    assert "サイズ縮小なら持ち越し可" in top_response.text
    assert "アラート必須で持ち越し可" in top_response.text
    assert "必要なアラート" in top_response.text
    assert "必ず確認すべき日付・イベント" in top_response.text
    assert "最終中長期持ち越し判断" in top_response.text
    assert "APIキー未設定" in top_response.text
    assert 'data-manual-update="edinet"' in top_response.text
    assert 'data-manual-update="tdnet-all"' in top_response.text
    assert 'data-manual-feedback="materials-refresh-feedback"' in top_response.text
    assert 'data-manual-feedback="screening-refresh-feedback"' in top_response.text
    assert "const formatManualError = (error) => {" in top_response.text
    assert "JQUANTS_API_KEY" in top_response.text
    assert "/securities/master/sync?require_jquants=true" in top_response.text
    assert "zeroIsError: true" in top_response.text
    assert "Manual Refresh" not in top_response.text
    assert "/screening?min_total_score=60" in top_response.text
    assert "Asia/Tokyo" in top_response.text
    assert "JST" in top_response.text
    assert "portfolio-note" in top_response.text
    assert "watchlist-score-candidates" in top_response.text
    assert "モック補完" not in top_response.text
    assert "保有銘柄更新" not in top_response.text

    assert "page-detail" in detail_response.text
    assert "/securities/${escapeAttr(detail.ticker_code)}" in detail_response.text
    assert 'data-manual-update="selected-factor"' in detail_response.text
    assert 'data-manual-update="selected-flow"' in detail_response.text
    assert 'data-manual-update="selected-technical"' in detail_response.text
    assert 'data-manual-update="selected-youtube"' in detail_response.text
    assert 'data-manual-feedback="detail-materials-refresh-feedback"' in detail_response.text
    assert "この銘柄を一括更新" not in detail_response.text
    assert "\u4e3b\u8981\u53c2\u7167\u5148" in detail_response.text
    assert "モック補完" not in detail_response.text
    assert "直近チャートプレビュー" in detail_response.text
    assert 'window.open(detailPageUrl(tickerCode), "_blank", "noopener")' in top_response.text
    assert "window.location.assign(detailPageUrl(tickerCode))" not in top_response.text
    assert "const notifyNewTabBlocked = () => {" in top_response.text
    assert "page-chart" in chart_response.text
    assert "/ui/security/${encodeURIComponent(tickerCode)}/chart" in chart_response.text
    assert 'href="${detailPageUrl(detail.ticker_code)}" target="_blank" rel="noopener noreferrer"' in chart_response.text
    assert "const renderChartPage = (detail) => {" in chart_response.text
    assert "const renderChartRangeControls = (currentRangeKey) => {" in chart_response.text
    assert 'data-chart-range="${option.key}"' in chart_response.text
    assert "MA 25" in chart_response.text
    assert "RSI 14" in chart_response.text
    assert "MACD" in chart_response.text
    assert "const renderSearchCandidates = (screeningItems, watchlistItems) => {" in top_response.text
    assert "毎日の review queue" in review_response.text
    assert "/ui/dashboard/data" in review_response.text
