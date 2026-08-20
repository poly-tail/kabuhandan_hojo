from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.schemas.portfolio_ai import (
    LongTermCarryCheck,
    LongTermCarryMonitoringIntervalView,
    PortfolioAiHolding,
    PortfolioAiReviewError,
    PortfolioAiReviewRequest,
    PortfolioAiReviewResponse,
    PortfolioAiReviewSource,
    PortfolioAiStockAnalysis,
    PortfolioAiSummary,
)
from app.services import portfolio_ai_review as portfolio_ai_review_module
from app.services.portfolio_ai_review import portfolio_ai_review_service


TOKYO = ZoneInfo("Asia/Tokyo")


@pytest.fixture(autouse=True)
def isolate_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        portfolio_ai_review_module,
        "AI_REVIEW_HISTORY_PATH",
        tmp_path / "ai_review_history.json",
    )
    monkeypatch.setattr(
        portfolio_ai_review_module,
        "AI_REVIEW_CACHE_PATH",
        tmp_path / "ai_review_cache.json",
    )
    monkeypatch.setenv("APP_USE_MOCK", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _review(
    *,
    generated_at: datetime,
    mode: str = "scanner",
    target: str | None = "holdings",
    holdings_source: str = "database",
    status: str = "success",
    summary: str = "保有銘柄を確認しました。",
    ticker: str = "7203",
    name: str = "トヨタ自動車",
    watchlist_id: int | None = None,
    cache_hit: bool = False,
    raw_model_output: str | None = None,
    sources: list[PortfolioAiReviewSource] | None = None,
) -> PortfolioAiReviewResponse:
    request_payload: dict[str, object] = {
        "user_hypothesis": "一覧へ出してはいけない秘密の仮説",
        "holdings": [{"ticker": ticker, "average_price": 1234.5}],
    }
    if target is not None:
        request_payload["target"] = target
    if watchlist_id is not None:
        request_payload["watchlist_id"] = watchlist_id
    error = None
    if status != "success":
        error = PortfolioAiReviewError(code=status, message="構造化に失敗しました。")  # type: ignore[arg-type]
    return PortfolioAiReviewResponse(
        generated_at=generated_at,
        mode=mode,  # type: ignore[arg-type]
        model="gpt-5.4",
        reasoning_effort="low",
        include_web_search=False,
        web_search_used=False,
        estimated_cost_usd=0.016,
        input_summary={"target": target} if target is not None else {},
        portfolio_summary=PortfolioAiSummary(
            overall_view=summary,
            overall_risk="medium",
            buy_candidates=[ticker],
            theme_exposure=["半導体", "半導体"],
            top_risks=["イベントリスク【E】"],
        ),
        stocks=[
            PortfolioAiStockAnalysis(
                ticker=ticker,
                name=name,
                judgement="watch",
                judgement_label="様子見",
                confidence=0.6,
                short_reason="価格を確認する【U】",
                key_points=["決算日を確認する【V】"],
                sources=sources or [],
            )
        ],
        sources=sources or [],
        raw_model_output=raw_model_output,
        parse_failure_kind="json_syntax" if status == "json_parse_failed" else None,
        status=status,  # type: ignore[arg-type]
        error=error,
        holdings_source=holdings_source,  # type: ignore[arg-type]
        cache_hit=cache_hit,
        holdings_snapshot=[
            PortfolioAiHolding(
                ticker=ticker,
                name=name,
                market="TSE",
                quantity=100,
                average_price=1234.5,
            )
        ],
        request_payload=request_payload,
    )


def _save(review: PortfolioAiReviewResponse) -> None:
    portfolio_ai_review_service.save_ai_review_result(review)


def _holding() -> PortfolioAiHolding:
    return PortfolioAiHolding(
        ticker="7203",
        name="トヨタ自動車",
        market="TSE",
        quantity=100,
        average_price=1234.5,
    )


def test_history_list_is_newest_first_filterable_and_metadata_only(client: TestClient) -> None:
    _save(
        _review(
            generated_at=datetime(2026, 8, 18, 10, 0, tzinfo=TOKYO),
            mode="judge",
            ticker="7011",
            name="三菱重工業",
        )
    )
    _save(
        _review(
            generated_at=datetime(2026, 8, 19, 15, 28, tzinfo=TOKYO),
            mode="scanner",
            target="watchlist",
            holdings_source="watchlist",
            ticker="285A0",
            name="キオクシアホールディングス",
            watchlist_id=7,
            cache_hit=True,
            summary="100株、取得単価1234.5円、一覧へ出してはいけない秘密の仮説",
        )
    )
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    stored = json.loads(history_path.read_text(encoding="utf-8"))
    stored.append({"mode": "scanner"})
    assert portfolio_ai_review_service._write_json(history_path, stored) is True

    response = client.get(
        "/api/ai/stock-review/history",
        params={"mode": "scanner", "target": "watchlist", "status": "success", "limit": 1},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["stored_count"] == 3
    assert payload["invalid_count"] == 1
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["retention_limit"] == 100
    assert payload["mode_counts"] == {
        "scanner": 1,
        "analyst": 0,
        "judge": 1,
        "critical": 0,
        "prompt_only": 0,
    }
    item = payload["items"][0]
    assert len(item["history_id"]) == 64
    assert item["mode_label"] == "軽量スキャン"
    assert item["target_label"] == "ウォッチリスト"
    assert item["watchlist_id"] == 7
    assert item["cache_hit"] is True
    assert item["stock_count"] == 1
    assert item["stocks_preview"] == ["キオクシアホールディングス（285A）"]
    assert item["summary"] == "1銘柄の保存済み結果"
    serialized_item = json.dumps(item, ensure_ascii=False)
    assert "request_payload" not in serialized_item
    assert "raw_model_output" not in serialized_item
    assert "manual_prompt" not in serialized_item
    assert "1234.5" not in serialized_item
    assert "秘密の仮説" not in serialized_item

    repeated = client.get("/api/ai/stock-review/history").json()
    scanner_item = next(entry for entry in repeated["items"] if entry["mode"] == "scanner")
    assert scanner_item["history_id"] == item["history_id"]


def test_history_target_uses_input_then_holdings_source_fallback(client: TestClient) -> None:
    input_fallback = _review(
        generated_at=datetime(2026, 8, 19, 11, 0, tzinfo=TOKYO),
        target=None,
        holdings_source="watchlist",
    )
    input_fallback.input_summary = {"target": "watchlist"}
    _save(input_fallback)
    source_fallback = _review(
        generated_at=datetime(2026, 8, 19, 12, 0, tzinfo=TOKYO),
        target=None,
        holdings_source="database",
        ticker="7974",
        name="任天堂",
    )
    _save(source_fallback)

    watchlist_payload = client.get(
        "/api/ai/stock-review/history", params={"target": "watchlist"}
    ).json()
    holdings_payload = client.get(
        "/api/ai/stock-review/history", params={"target": "holdings"}
    ).json()

    assert watchlist_payload["total"] == 1
    assert holdings_payload["total"] == 1
    assert holdings_payload["items"][0]["stocks_preview"] == ["任天堂（7974）"]


def test_history_list_does_not_use_model_generated_name_without_snapshot(
    client: TestClient,
) -> None:
    review = _review(
        generated_at=datetime(2026, 8, 19, 12, 30, tzinfo=TOKYO),
        summary="一覧へ出してはいけない取得単価 1234.5",
    )
    review.stocks[0].name = "一覧へ出してはいけない秘密の仮説"
    review.holdings_snapshot = []
    _save(review)

    payload = client.get("/api/ai/stock-review/history").json()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["items"][0]["stocks_preview"] == ["7203"]
    assert payload["items"][0]["summary"] == "1銘柄の保存済み結果"
    assert "秘密の仮説" not in serialized
    assert "1234.5" not in serialized


def test_history_detail_strips_request_payload_and_missing_is_no_store(client: TestClient) -> None:
    _save(_review(generated_at=datetime(2026, 8, 19, 13, 0, tzinfo=TOKYO)))
    history_id = client.get("/api/ai/stock-review/history").json()["items"][0]["history_id"]

    response = client.get(f"/api/ai/stock-review/history/{history_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    payload = response.json()
    assert payload["history_id"] == history_id
    assert "request_payload" not in payload["review"]
    assert payload["review"]["stocks"][0]["name"] == "トヨタ自動車"

    missing = client.get("/api/ai/stock-review/history/not-a-valid-id")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-store"
    assert missing.json()["detail"] == "保存済みのAIレビューが見つかりません。"


def test_history_detail_and_export_enrich_old_code_only_references_without_rewriting_file(
    client: TestClient,
) -> None:
    review = _review(
        generated_at=datetime(2026, 8, 19, 14, 0, tzinfo=TOKYO),
        ticker="285A0",
        name="キオクシアホールディングス",
    )
    review.stocks[0].name = "285A0"
    _save(review)
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    stored_before = history_path.read_bytes()
    history_id = client.get("/api/ai/stock-review/history").json()["items"][0]["history_id"]

    detail = client.get(f"/api/ai/stock-review/history/{history_id}").json()["review"]
    markdown = client.get(f"/api/ai/stock-review/history/{history_id}/export.md").text

    assert detail["stocks"][0]["name"] == "キオクシアホールディングス"
    assert detail["portfolio_summary"]["buy_candidates"] == [
        "キオクシアホールディングス（285A）"
    ]
    assert "キオクシアホールディングス（285A）" in markdown
    assert history_path.read_bytes() == stored_before


def test_history_markdown_export_is_semantic_and_escapes_untrusted_content(client: TestClient) -> None:
    sources = [
        PortfolioAiReviewSource(title="公式 [IR]", url="https://example.com/a(b)?q=1"),
        PortfolioAiReviewSource(title="危険<script>", url="javascript:alert(1)"),
    ]
    review = _review(
        generated_at=datetime(2026, 8, 19, 15, 28, tzinfo=TOKYO),
        status="json_parse_failed",
        summary="<script>*強調させない*</script>",
        ticker="285A0",
        name="キオクシアホールディングス",
        raw_model_output='{"raw":"``` <script>raw</script>"}',
        sources=sources,
    )
    stock = review.stocks[0]
    stock.expected_value_view = "期待値は中立"
    stock.position_size_risk = "サイズは小さめ"
    stock.event_risk = "決算イベントに注意"
    stock.gap_risk = "窓開けリスクあり"
    stock.decision_deadline = "次回決算まで"
    stock.what_would_change_my_mind = "業績回復を確認"
    stock.risks = ["半導体循環"]
    stock.risk_flags = ["高ボラ"]
    stock.needs_detail_analysis = True
    stock.needs_analyst_mode = True
    stock.needs_judge_mode = True
    stock.long_term_carry_check = LongTermCarryCheck(
        can_hold_without_daily_monitoring="with_alerts",
        non_monitoring_hold_risk="high",
        business_thesis_strength="normal",
        event_risk_while_unmonitored="high",
        liquidity_risk="low",
        volatility_risk="high",
        position_size_view="小さめにする",
        core_position_suitability="low",
        short_term_position_should_be_removed=True,
        required_alerts=["決算日"],
        must_check_dates_or_events=["次回決算"],
        reduce_before_events=["決算前に縮小"],
        stop_or_reduce_conditions=["見通し悪化"],
        long_term_thesis_break_conditions=["市況回復前提の崩壊"],
        monitoring_interval_view=[
            LongTermCarryMonitoringIntervalView(
                interval="1_week",
                holdability="with_reduction",
                required_conditions=["価格アラート"],
                pre_actions=["一部縮小"],
            )
        ],
        final_long_term_carry_decision="not_suitable_without_daily_monitoring",
        final_note="非監視では慎重",
    )
    _save(review)
    history_id = client.get("/api/ai/stock-review/history").json()["items"][0]["history_id"]

    response = client.get(f"/api/ai/stock-review/history/{history_id}/export.md")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"].startswith("text/markdown; charset=utf-8")
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="ai-review-20260819-152800-scanner-'
    )
    markdown = response.text
    assert "# AIレビュー履歴：軽量スキャン" in markdown
    assert "キオクシアホールディングス（285A）" in markdown
    assert "&lt;script&gt;\\*強調させない\\*&lt;/script&gt;" in markdown
    assert "[公式 \\[IR\\]](https://example.com/a%28b%29?q=1)" in markdown
    assert "危険&lt;script&gt;（HTTP\\(S\\)以外のURLはリンク省略）" in markdown
    assert "javascript:" not in markdown
    assert "````text" in markdown
    assert markdown.splitlines().count("- 半導体") == 1
    assert "#### 期待値" in markdown and "期待値は中立" in markdown
    assert "#### ポジションサイズリスク" in markdown and "サイズは小さめ" in markdown
    assert "#### イベントリスク" in markdown and "決算イベントに注意" in markdown
    assert "#### ギャップリスク" in markdown and "窓開けリスクあり" in markdown
    assert "#### 判断期限" in markdown and "次回決算まで" in markdown
    assert "#### 判断を変える条件" in markdown and "業績回復を確認" in markdown
    assert "#### リスク" in markdown and "半導体循環" in markdown
    assert "#### 警戒フラグ" in markdown and "高ボラ" in markdown
    assert "推奨フォローアップ: 詳細分析 / 個別詳細分析 / 全体売買判断" in markdown
    assert "#### 長期持越しチェック" in markdown
    assert "短期玉の除外: 必要" in markdown
    assert "##### 必要なアラート" in markdown and "決算日" in markdown
    assert "##### 非監視期間別の保有可否" in markdown
    assert "価格アラート" in markdown and "一部縮小" in markdown
    assert "##### 最終補足" in markdown and "非監視では慎重" in markdown
    assert "秘密の仮説" not in markdown
    assert "自動売買や断定的な投資助言ではありません" in markdown


def test_malformed_root_is_counted_and_not_overwritten(client: TestClient) -> None:
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    history_path.write_text("{broken", encoding="utf-8")

    payload = client.get("/api/ai/stock-review/history").json()

    assert payload["items"] == []
    assert payload["stored_count"] == 0
    assert payload["invalid_count"] == 1
    _save(_review(generated_at=datetime(2026, 8, 19, 16, 0, tzinfo=TOKYO)))
    assert history_path.read_text(encoding="utf-8") == "{broken"


def test_non_finite_cost_entry_is_skipped_instead_of_breaking_history_list(
    client: TestClient,
) -> None:
    valid = _review(generated_at=datetime(2026, 8, 19, 16, 30, tzinfo=TOKYO))
    invalid = valid.model_dump(mode="json")
    invalid["estimated_cost_usd"] = float("nan")
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    assert portfolio_ai_review_service._write_json(history_path, [invalid]) is True

    response = client.get("/api/ai/stock-review/history")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["stored_count"] == 1
    assert response.json()["invalid_count"] == 1


@pytest.mark.parametrize(
    "options",
    [
        PortfolioAiReviewRequest(
            mode="prompt_only",
            target="selected",
            save_result=True,
            use_cache=False,
        ),
        PortfolioAiReviewRequest(
            mode="scanner",
            target="selected",
            mock_response=True,
            save_result=True,
            use_cache=False,
        ),
    ],
    ids=["prompt_only", "mock"],
)
def test_non_provider_save_branches_warn_once_when_history_write_fails(
    options: PortfolioAiReviewRequest,
) -> None:
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    history_path.write_text("{broken", encoding="utf-8")

    response = portfolio_ai_review_service.analyze_portfolio_with_openai(
        holdings=[_holding()],
        candidates=[],
        market_snapshots=[],
        options=options,
        holdings_source="request",
    )

    warning = portfolio_ai_review_module.AI_REVIEW_HISTORY_SAVE_WARNING
    assert response.warnings.count(warning) == 1
    assert str(history_path) not in warning
    assert history_path.read_text(encoding="utf-8") == "{broken"


@pytest.mark.parametrize(
    ("raw_output", "expected_status"),
    [
        (
            json.dumps(
                {
                    "generated_at": "2026-08-19T17:00:00+09:00",
                    "mode": "scanner",
                    "portfolio_summary": {},
                    "stocks": [],
                    "sources": [],
                    "warnings": [],
                    "raw_model_output": None,
                },
                ensure_ascii=False,
            ),
            "success",
        ),
        ('{"broken":', "json_parse_failed"),
    ],
    ids=["live_success", "raw_fallback"],
)
def test_provider_save_branches_warn_and_do_not_cache_when_history_write_fails(
    monkeypatch: pytest.MonkeyPatch,
    raw_output: str,
    expected_status: str,
) -> None:
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    history_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(portfolio_ai_review_service, "_can_run_today", lambda _: True)
    monkeypatch.setattr(portfolio_ai_review_service, "_call_openai", lambda **_: raw_output)
    monkeypatch.setattr(portfolio_ai_review_service, "_record_provider_usage", lambda **_: None)
    monkeypatch.setattr(portfolio_ai_review_service, "_increment_daily_usage", lambda: None)

    response = portfolio_ai_review_service.analyze_portfolio_with_openai(
        holdings=[_holding()],
        candidates=[],
        market_snapshots=[],
        options=PortfolioAiReviewRequest(
            mode="scanner",
            target="selected",
            include_web_search=False,
            save_result=True,
            use_cache=False,
        ),
        holdings_source="request",
    )

    warning = portfolio_ai_review_module.AI_REVIEW_HISTORY_SAVE_WARNING
    assert response.status == expected_status
    assert response.warnings.count(warning) == 1
    assert history_path.read_text(encoding="utf-8") == "{broken"
    assert not portfolio_ai_review_module.AI_REVIEW_CACHE_PATH.exists()


def test_save_result_false_does_not_add_history_failure_warning() -> None:
    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    history_path.write_text("{broken", encoding="utf-8")

    response = portfolio_ai_review_service.analyze_portfolio_with_openai(
        holdings=[_holding()],
        candidates=[],
        market_snapshots=[],
        options=PortfolioAiReviewRequest(
            mode="prompt_only",
            target="selected",
            save_result=False,
            use_cache=False,
        ),
        holdings_source="request",
    )

    assert portfolio_ai_review_module.AI_REVIEW_HISTORY_SAVE_WARNING not in response.warnings


def test_history_append_is_thread_safe_and_atomic() -> None:
    base_time = datetime(2026, 8, 19, 9, 0, tzinfo=TOKYO)

    def save_one(index: int) -> None:
        _save(
            _review(
                generated_at=base_time + timedelta(seconds=index),
                ticker=f"T{index:04d}",
                name=f"銘柄{index}",
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_one, range(32)))

    history_path = portfolio_ai_review_module.AI_REVIEW_HISTORY_PATH
    stored = json.loads(history_path.read_text(encoding="utf-8"))
    assert len(stored) == 32
    assert not list(history_path.parent.glob(f".{history_path.name}.*.tmp"))


def test_history_security_labels_only_strip_provider_suffix_for_alpha_codes() -> None:
    assert portfolio_ai_review_service._security_label("キオクシア", "285A0") == "キオクシア（285A）"
    assert portfolio_ai_review_service._security_label("数値コード", "72030") == "数値コード（72030）"
    assert portfolio_ai_review_service._security_label("優先株", "25935") == "優先株（25935）"
