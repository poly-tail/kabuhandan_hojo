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


def test_dashboard_stock_ai_usage_ui_is_persistent_safe_and_refreshed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text
    assert 'id="stock-ai-usage"' in html
    assert 'id="stock-ai-usage-today"' in html
    assert 'id="stock-ai-usage-month"' in html
    assert 'id="stock-ai-usage-unpriced"' in html
    assert 'id="stock-ai-usage-history-note"' in html
    assert "本日 成功レビュー -- / --回・残り --・OpenAI呼出 --回・概算 $--" in html
    assert "今月 成功レビュー --回・OpenAI呼出 --回・概算 $--" in html
    assert "summary.today?.api_calls" in html
    assert "summary.month?.api_calls" in html
    assert "OpenAI呼出 ${todayApiCalls}回" in html
    assert "OpenAI呼出 ${monthApiCalls}回" in html
    assert "金額未算定のAPI呼び出し" in html
    assert "旧形式のカウンターは新集計へ移行していません。更新前の回数・金額は含まれません。" in html
    assert "1回＝正常完了した一括レビュー1件（銘柄数に関係なし）" in html
    assert "旧stock-review経路だけが対象" in html
    assert "正式な請求額ではありません" in html
    assert "OpenAI PlatformのUsage Dashboardを正本" in html
    assert 'fetchJson("/api/ai/stock-review/usage")' in html
    assert "await Promise.all([loadDashboard(null), loadStockAiUsage()]);" in html
    assert html.count("await loadStockAiUsage();") >= 2
    assert "今回の事前概算" in html
    assert "includeWebSearch ? 0.01 * webCalls : 0" in html
    assert "includeWebSearch ? 0.008 * webCalls : 0" not in html
    assert "data.actual_usage.web_search_calls}回上限" not in html
    assert "data.actual_usage.web_search_calls}回" in html
    assert 'database: "対象: 実DB保有銘柄"' in html
    assert 'escapeHtml(data.holdings_source || "-")' not in html
    assert 'fill("stock-ai-usage-' not in html
    assert 'text("stock-ai-usage-today"' in html
    assert 'text("stock-ai-usage-month"' in html


def test_dashboard_search_can_prepare_a_holding_without_saving_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text
    assert "銘柄名か銘柄コード（数字・英字）で検索" in html
    assert 'placeholder="7203 / 285A / トヨタ / キオクシア"' in html
    assert 'data-prepare-portfolio="${escapeAttr(item.ticker_code)}"' in html
    assert ">保有入力へ</button>" in html
    assert 'data-open-ticker="${escapeAttr(item.ticker_code)}"' in html
    assert ">詳細を見る</button>" in html
    assert "const preparePortfolioHolding = (tickerCode) => {" in html
    assert 'placeholder="7203 / 285A"' in html
    assert "const publicSecurityCode = (value) => {" in html
    assert 'const isJquantsAlphanumericCode = /^[0-9A-Za-z]{4}0$/.test(normalized)' in html
    assert "&& /[A-Za-z]/.test(normalized.slice(0, 4));" in html
    assert "return isJquantsAlphanumericCode ? normalized.slice(0, 4) : normalized;" in html
    assert html.count("escapeHtml(publicSecurityCode(item.ticker_code))") >= 2
    assert "const publicTickerCode = publicSecurityCode(tickerCode);" in html
    assert "tickerInput.value = publicTickerCode;" in html
    assert "`${publicTickerCode} を選択しました。" in html
    assert 'form.scrollIntoView({ behavior: "smooth", block: "center" });' in html
    assert "quantityInput.focus({ preventScroll: true });" in html
    assert "数量を入力して「保有を保存」を押してください。" in html
    assert 'if (!tickerCode || !quantity) {' in html
    assert 'setPortfolioFeedback("銘柄コードと数量は必須です。", "error");' in html

    prepare_handler = html.index('event.target.closest("[data-prepare-portfolio]")')
    detail_handler = html.index('event.target.closest("[data-select-ticker], [data-open-ticker]")')
    assert prepare_handler < detail_handler
