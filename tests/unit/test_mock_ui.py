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
        assert ui_payload["watchlist_collections"]
        assert ui_payload["watchlist_collections"][0]["name"] == "メイン"
        assert ui_payload["watchlist_collections"][0]["is_default"] is True
        assert ui_payload["selected_watchlist_id"] == ui_payload["watchlist_collections"][0]["id"]
        assert all(
            item["collection_id"] == ui_payload["selected_watchlist_id"]
            for item in client.get("/watchlist").json()
        )
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
    assert "/securities/search?${searchParams.toString()}" in top_response.text
    assert "security-master-sync-button" in top_response.text
    assert "東証全銘柄を同期" in top_response.text
    assert 'id="security-master-status"' in top_response.text
    assert 'fetchJson("/securities/master/status")' in top_response.text
    assert "情報基準日 ${sourceAsOf}" in top_response.text
    assert "J-Quants ${jquantsCount}件" in top_response.text
    assert "東証全件同期は未確認です。ローカル有効銘柄 ${activeTotal}件。" in top_response.text
    assert "同期状態を取得できませんでした" in top_response.text
    assert "全日本銘柄" not in top_response.text
    assert "market-proxy-sync-button" in top_response.text
    assert 'data-manual-update="watchlist-scores"' in top_response.text
    assert 'data-manual-update="portfolio-prices"' in top_response.text
    assert "保有・ウォッチリストAIレビュー" in top_response.text
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
    assert top_response.text.count("${escapeHtml(publicSecurityCode(stock.ticker))}") == 1
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
    assert "const syncSecurityMaster = async" not in top_response.text
    assert "東証全銘柄を同期しました。検索結果も再取得しました。" not in top_response.text
    assert 'kind === "security-master"' in top_response.text
    assert "J-Quantsから東証全銘柄を同期しています..." in top_response.text
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
    assert "loadDashboard(null)," in html
    assert "loadStockAiUsage()," in html
    assert "loadStockAiHistory()," in html
    assert "loadSecurityMasterStatus()," in html
    assert html.count("await Promise.all([loadStockAiUsage(), loadStockAiHistory()]);") >= 2
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


def test_dashboard_unifies_portfolio_and_named_watchlists_in_one_management_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text
    assert html.count('class="panel management-space-panel"') == 1
    assert 'id="management-space-select"' in html
    assert '.management-space-header > *, #management-space-select {' in html
    assert '#management-space-select {\n        width: 100%;' in html
    assert '.management-space-select-label { width: 100%; min-width: 0; }' in html
    assert 'value="portfolio"' in html
    assert 'value="${escapeAttr(watchlistSpaceKey(item.id))}"' in html
    assert 'id="portfolio-space-header"' in html
    assert 'id="portfolio-space-editor"' in html
    assert 'id="watchlist-space-view" hidden' in html
    assert 'id="active-watchlist-name"' in html
    assert 'id="watchlist-collection-create"' in html
    assert 'id="watchlist-collection-rename"' in html
    assert 'id="watchlist-collection-delete"' in html
    assert 'id="watchlist-collection-form" hidden' in html
    assert 'id="management-space-feedback" aria-live="polite"' in html
    assert 'deleteButton.disabled = Boolean(collection?.is_default);' in html
    assert "既定のウォッチリストは削除できません。" in html

    assert 'postJson("/watchlists", { name })' in html
    assert 'patchJson(`/watchlists/${collection.id}`, { name })' in html
    assert 'deleteJson(`/watchlists/${collection.id}`)' in html
    assert 'postJson(`/watchlists/${collection.id}/items`' in html
    assert 'deleteJson(`/watchlists/${collection.id}/items/${encodeURIComponent(tickerCode)}`)' in html
    assert 'data-add-active-watchlist="${escapeAttr(item.ticker_code)}"' in html
    assert 'data-remove-watchlist="${escapeAttr(item.ticker_code)}"' in html
    assert "if (response.status === 204) return null;" in html

    assert 'activeManagementSpace: INITIAL_WATCHLIST_ID === null ? "portfolio" : `watchlist:${INITIAL_WATCHLIST_ID}`' in html
    assert "watchlistSelections: new Map()" in html
    assert "stockAiRequestId: 0" in html
    assert "selectedWatchlistTickers" not in html
    assert "const activeWatchlistSelection = () => {" in html
    assert "const pruneActiveWatchlistSelection = () => {" in html
    assert 'params.set("watchlist_id", String(watchlistId))' in html
    assert 'searchParams.set("watchlist_id", String(collectionId))' in html
    assert 'watchlist_id: watchlistId' in html
    assert 'const watchlistId = target === "watchlist" ? activeWatchlistId() : null;' in html
    assert "activeWatchlistId() ?? state.data?.selected_watchlist_id" not in html
    assert 'new URLSearchParams(window.location.search).get("watchlist_id")' in html
    assert '`/ui/security/${encodeURIComponent(tickerCode)}${managementSpaceQuery()}`' in html
    assert 'const endpoint = collectionId === null ? "/watchlist" : `/watchlists/${collectionId}/items`;' in html
    assert 'backLink.href = `${TOP_PAGE_URL}${managementSpaceQuery()}`;' in html
    assert 'target === "watchlist"' in html
    assert 'targetInput.value = collectionId === null ? "holdings" : "watchlist";' in html
    assert 'if (INITIAL_WATCHLIST_ID !== null) {' in html
    assert 'if (targetInput) targetInput.value = "watchlist";' in html
    assert "const invalidateStockAiReview = () => {" in html
    assert "state.stockAiRequestId += 1;" in html
    assert "if (requestId !== state.stockAiRequestId) return;" in html
    assert 'if (requestId === state.stockAiRequestId) {\n            setPortfolioAiButtonsDisabled(false);' in html
    assert 'if (PAGE_MODE === "top" && requestedWatchlistId !== activeScopeId) return false;' in html
    assert 'await loadDashboard(state.data?.selected_ticker_code || null, activeWatchlistId())' in html
    assert "const syncWatchlistSelectionToAiTarget = () => {" in html
    assert 'targetInput.value = "selected";' in html
    assert 'targetInput.value = "watchlist";' in html
    assert "共通AIパネルは「選択銘柄」を分析します。" in html
    assert 'aria-label="${escapeAttr(`${item.name}（${publicSecurityCode(item.ticker_code)}）をAI分析対象に選択`)}"' in html
    assert "const stockAiReviewContext = (payload) => {" in html
    assert 'renderAiReviewSummary(data, review.contextLabel || "")' in html
    assert 'title: String(review?.readerTitle || config.title)' in html
    assert 'escapeHtml(item.name)' in html
    assert 'escapeHtml(collection.name)' in html


def test_mock_dashboard_data_scopes_watchlist_items_to_selected_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    created_id: int | None = None
    with TestClient(create_app()) as client:
        try:
            created = client.post("/watchlists", json={"name": "UI切替テスト"})
            assert created.status_code == 201
            created_id = created.json()["id"]

            added = client.post(
                f"/watchlists/{created_id}/items",
                json={"ticker_code": "8035", "name": "東京エレクトロン", "market": "TSE Prime"},
            )
            assert added.status_code == 201

            response = client.get(f"/ui/dashboard/data?watchlist_id={created_id}")
            assert response.status_code == 200
            payload = response.json()
            assert payload["selected_watchlist_id"] == created_id
            assert any(item["id"] == created_id for item in payload["watchlist_collections"])
            assert [item["ticker_code"] for item in payload["watchlist_items"]] == ["8035"]

            search = client.get(f"/securities/search?q=8035&watchlist_id={created_id}")
            assert search.status_code == 200
            assert search.json()[0]["in_watchlist"] is True
        finally:
            if created_id is not None:
                client.delete(f"/watchlists/{created_id}")


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


def test_dashboard_distinguishes_ai_json_syntax_and_schema_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text
    assert 'data?.parse_failure_kind === "schema_validation"' in html
    assert 'data?.parse_failure_kind === "root_shape"' in html
    assert "JSON項目形式エラー" in html
    assert "JSONルート形式エラー" in html
    assert "JSON構文エラー" in html
    assert html.count("aiReviewResultStatusLabel(data)") >= 2


def test_dashboard_formats_structured_ai_reviews_as_safe_semantic_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text

    assert 'id="portfolio-ai-review-results" aria-live="polite" aria-busy="false"' in html
    assert 'id="watchlist-ai-review-results" aria-live="polite" aria-busy="false"' in html
    assert 'setAiResultBusy("portfolio-ai-review-results", review.status === "loading")' in html
    assert 'setAiResultBusy("watchlist-ai-review-results", review.status === "loading")' in html

    assert "const renderAiReviewSummary = (data, contextLabel = \"\") => {" in html
    assert '${renderAiReviewSummary(data, review.contextLabel || "")}' in html
    assert '${renderAiReviewSummary(data, "選択ウォッチリスト")}' in html
    assert html.count("renderAiReviewSummary(data") == 4
    assert 'data.mode ? aiModeLabel(data.mode) : ""' not in html
    assert 'renderAiTextSection("運用スタンス", marketTemperature)' in html
    assert 'escapeHtml(summary.market_temperature || "-")' not in html
    assert "const primarySummary = overallView || portfolioSummary;" in html
    assert 'renderAiTextSection("ポートフォリオ総括", additionalPortfolioSummary)' in html
    assert 'summary.overall_risk || "-"' not in html

    for heading in (
        "主要リスク",
        "今日の優先事項",
        "買い候補",
        "売却・縮小候補",
        "保有優先",
        "テーマ偏り",
        "毎日見られないなら縮小すべき銘柄",
        "コア玉として残せる銘柄",
        "入れ替え候補",
        "具体的な執行案",
        "重要警告",
        "資金配分",
        "集中リスク",
        "全体反証",
        "注意事項",
    ):
        assert f'("{heading}"' in html
    assert "<h4>参照情報</h4>" in html

    assert "const uniqueAiItems = (items = [], excludedItems = []) => {" in html
    assert "const warnings = uniqueAiItems(data.warnings || [], criticalWarnings);" in html
    assert "if (!item || excluded.has(item) || seen.has(item)) return false;" in html

    assert "const renderAiText = (value) => {" in html
    assert "source.matchAll(/(【([VEU])" in html
    assert "html += escapeHtml(source.slice(cursor, match.index));" in html
    assert 'V: { marker: "【V】", meaning: "確認済み" }' in html
    assert 'E: { marker: "【E】", meaning: "推定" }' in html
    assert 'U: { marker: "【U】", meaning: "未確認" }' in html
    assert "const meaningAlreadyFollows = remainder.trimStart().startsWith(label.meaning);" in html
    assert 'const visibleLabel = `${label.marker}${meaningAlreadyFollows ? "" : label.meaning}`;' in html
    assert '${detail ? `<span class="ai-evidence-detail">｜${escapeHtml(detail)}</span>` : ""}' in html
    assert "ai-evidence-v" in html
    assert "ai-evidence-e" in html
    assert "ai-evidence-u" in html

    assert "const renderAiRawFallback = (rawOutput) => {" in html
    assert "OpenAI生応答（解析できなかった内容）" in html
    assert "const displayLimit = 20000;" in html
    assert "const truncated = rawText.length > displayLimit;" in html
    assert '<pre class="ai-raw-content">${escapeHtml(rawText.slice(0, displayLimit))}</pre>' in html
    assert "全文は「Markdown保存」で確認できます。" in html
    assert html.count("const rawOutput = renderAiRawFallback(data.raw_model_output);") == 2

    assert "const safeAiSourceUrl = (value) => {" in html
    assert "if (!/^https?:\\/\\//i.test(candidate)) return null;" in html
    assert '<span class="source-link source-link-plain"' in html
    assert 'rel="noopener noreferrer"' in html
    assert '${renderAiText(stock.judgement_label || aiJudgementLabel(stock.judgement))}' in html
    assert '${renderAiText(stock.judgement)}</span>' in html
    assert "const renderAiStockCard = (stock) => {" in html
    assert html.count("const stockCards = (data.stocks || []).map(renderAiStockCard).join(\"\");") == 2
    assert '<h3 class="ai-card-title">${renderAiText(stock.name)}</h3>' in html
    assert '<h3 class="ai-card-title">${escapeHtml(aiModeLabel(data.mode))}</h3>' in html
    assert 'renderAiListSection("時間軸別判断", timeHorizonViews)' in html
    assert 'renderAiTextSection("不確実性", stock.uncertainty_notes, "warning")' in html
    assert '<div class="subtle">今日見るべきポイント</div>' not in html
    assert "const renderAiSubList = (title, items = []) => {" in html
    assert "const renderAiSubText = (title, value) => {" in html

    assert ".ai-review-grid {" in html
    assert ".ai-review-card {" in html
    assert ".ai-result-section {" in html
    assert "white-space: pre-wrap;" in html
    assert "marked" not in html.lower()
    assert "cdn.jsdelivr.net" not in html


def test_dashboard_opens_current_ai_review_in_safe_blob_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text

    assert html.count('class="action-link ai-review-reader-link"') == 3
    assert 'id="portfolio-ai-review-reader-link"' in html
    assert 'id="watchlist-ai-review-reader-link"' in html
    assert 'id="stock-ai-history-reader-link"' in html
    assert html.count('>回答を別タブ／ウィンドウで大きく表示</a>') == 2
    assert ">別タブ表示・PDF保存（印刷）</a>" in html
    assert html.count('target="_blank"') >= 3
    assert html.count('rel="noopener noreferrer"') >= 3
    assert html.count('referrerpolicy="no-referrer"') == 3
    assert ".ai-review-reader-link[hidden]" in html

    assert "const AI_REVIEW_READER_CONFIG = Object.freeze({" in html
    assert 'resultId: "portfolio-ai-review-results"' in html
    assert 'resultId: "watchlist-ai-review-results"' in html
    assert 'resultId: "stock-ai-history-detail-results"' in html
    assert "const aiReviewReaderObjectUrls = new Map();" in html
    assert "const hasReadableAiReview = (review) => {" in html
    assert 'if (!data || data.mode === "prompt_only") return false;' in html
    assert 'const hasRawOutput = Boolean(String(data.raw_model_output ?? "").trim());' in html
    assert 'return status === "success" || (status === "json_parse_failed" && hasRawOutput);' in html

    assert "document.implementation.createHTMLDocument" in html
    assert 'name: "referrer", content: "no-referrer"' in html
    assert '"http-equiv": "Content-Security-Policy"' in html
    assert "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'" in html
    assert "connect-src 'none'; img-src 'none'; font-src 'none'; frame-src 'none'" in html
    assert "Array.from(sourceElement.children).forEach((child) => {" in html
    assert "const clonedChild = child.cloneNode(true);" in html
    assert 'clonedChild.querySelectorAll("details.ai-raw-output").forEach((details) => {' in html
    assert "details.open = true;" in html
    assert "content.appendChild(clonedChild);" in html
    assert 'new Blob([readerHtml], { type: "text/html;charset=utf-8" })' in html
    assert "URL.createObjectURL" in html
    assert "URL.revokeObjectURL" in html
    assert "width: min(1440px, 100%);" in html
    assert "@media print" in html
    assert "ブラウザの印刷（Ctrl+P）で「PDFに保存」を選んでください。" in html

    reader_helper = html.split("const clearAiReviewReader = (readerKey) => {", 1)[1].split(
        "const text = (id, value) => {", 1
    )[0]
    assert "window.open" not in reader_helper
    assert "document.write" not in reader_helper
    assert "localStorage" not in reader_helper
    assert "sessionStorage" not in reader_helper
    assert "postMessage" not in reader_helper
    assert "fetch(" not in reader_helper
    assert "sourceElement.innerHTML" not in reader_helper

    assert html.count('prepareAiReviewReader("portfolio", review);') == 2
    assert html.count('prepareAiReviewReader("watchlist", review);') == 2
    assert 'const renderError = (error) => {\n        const message = escapeHtml(error.message || String(error));\n        clearAiReviewReader("portfolio");\n        clearAiReviewReader("watchlist");' in html
    assert 'clearAiReviewReader("history");' in html
    assert 'prepareAiReviewReader("portfolio", state.portfolioAiReview);' in html
    assert 'prepareAiReviewReader("watchlist", state.watchlistAiReview);' in html
    assert 'prepareAiReviewReader("history", state.stockAiHistoryDetail);' in html
    assert 'window.addEventListener("pagehide"' in html
    assert 'window.addEventListener("pageshow"' in html


def test_dashboard_lists_saved_ai_reviews_and_exposes_safe_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")

    with TestClient(create_app()) as client:
        response = client.get("/ui/dashboard")

    assert response.status_code == 200
    html = response.text

    assert 'id="stock-ai-history-panel"' in html
    assert 'id="stock-ai-history-mode"' in html
    assert 'id="stock-ai-history-list" aria-live="polite" aria-busy="true"' in html
    assert 'id="stock-ai-history-detail"' in html
    assert 'id="stock-ai-history-detail-results" aria-live="polite" aria-busy="false"' in html
    assert 'id="stock-ai-history-markdown-link" download hidden' in html
    assert "直近100件" in html
    for mode in ("scanner", "analyst", "judge", "critical", "prompt_only"):
        assert f'<option value="{mode}">' in html

    assert "const AI_HISTORY_MODE_ORDER = Object.freeze([" in html
    assert "const safeStockAiHistoryId = (value) => {" in html
    assert "/^[A-Za-z0-9_-]{8,128}$/.test(candidate)" in html
    assert "const renderStockAiHistory = () => {" in html
    assert "const renderStockAiHistoryItem = (item) => {" in html
    assert "const items = Array.isArray(data.items) ? [...data.items] : [];" in html
    assert "return rightTime - leftTime;" not in html
    assert 'data-stock-ai-history-detail="${escapeAttr(historyId)}"' in html
    assert 'data-stock-ai-history-reader="${escapeAttr(historyId)}"' in html
    assert '&& ["success", "json_parse_failed"].includes(status)' in html
    assert "別タブ表示・PDF保存" in html
    assert 'href="/api/ai/stock-review/history/${encodeURIComponent(historyId)}/export.md"' in html
    assert "Markdown保存" in html
    assert "renderAiText(summary)" in html
    assert "escapeHtml(modeLabel)" in html
    assert "escapeHtml(stockPreview)" in html

    assert 'fetchJson("/api/ai/stock-review/history")' in html
    assert "fetchJson(`/api/ai/stock-review/history/${encodeURIComponent(historyId)}`)" in html
    assert "const review = payload?.review;" in html
    assert 'prepareAiReviewReader("history", detail);' in html
    assert "readerLink.click()" not in html
    assert 'readerLink.focus({ preventScroll: true });' in html
    assert "印刷用画面を準備しました" in html
    assert "一覧表示やエクスポートでOpenAI APIは呼びません。" in html
    assert "前回結果（キャッシュ）の再表示は重複保存しません。" in html

    assert 'if (data.mode === "prompt_only") {' in html
    assert 'data.mode === "prompt_only"\n            ? "OpenAI API非呼び出し"' in html
    assert '<pre class="ai-history-prompt">${escapeHtml(data.manual_prompt || "保存されたプロンプトはありません。")}</pre>' in html
    assert "これはOpenAI回答ではなく" in html
    assert "renderAiRawFallback(data.raw_model_output)" in html
    assert ".ai-history-prompt {" in html

    history_helper = html.split("const AI_HISTORY_MODE_ORDER", 1)[1].split(
        "const setPortfolioAiButtonsDisabled", 1
    )[0]
    assert 'method: "POST"' not in history_helper
    assert "localStorage" not in history_helper
    assert "sessionStorage" not in history_helper
    assert "window.open" not in history_helper
    assert "marked" not in history_helper.lower()
