from __future__ import annotations

from app.prompts.stock_analysis import (
    build_prompt_only_text,
    build_stock_analysis_prompt,
    get_base_policy_prompt,
    get_full_user_stock_analysis_prompt,
    get_mode_profile,
    get_output_schema_for_mode,
    validate_stock_analysis_response,
)
from app.schemas.portfolio_ai import (
    PortfolioAiCandidate,
    PortfolioAiHolding,
    PortfolioAiReviewRequest,
    PortfolioMarketSnapshot,
)


def _holding() -> PortfolioAiHolding:
    return PortfolioAiHolding(
        ticker="7011",
        name="三菱重工業",
        market="TSE",
        quantity=100,
        average_price=2900,
        position_type="core_and_short",
    )


def _candidate() -> PortfolioAiCandidate:
    return PortfolioAiCandidate(
        ticker="6857",
        name="アドバンテスト",
        market="TSE",
        candidate_reason="半導体テーマの主力候補",
        watch_condition="出来高を伴う上抜け、または押し目形成",
    )


def _prompt(mode: str, include_web_search: bool | None = None) -> dict[str, object]:
    request = PortfolioAiReviewRequest(
        mode=mode,  # type: ignore[arg-type]
        target="mock",
        include_web_search=include_web_search,
        user_hypothesis="防衛テーマと決算期待で上値余地があるが、短期過熱も気になる",
        position_intent="short_and_mid",
    )
    return build_stock_analysis_prompt(
        request,
        holdings=[_holding()],
        candidates=[_candidate()],
        market_snapshots=[PortfolioMarketSnapshot(ticker="7011")],
        news_snapshots={},
        technical_snapshots={},
        portfolio_snapshot={},
    )


def test_prompt_only_uses_full_user_prompt() -> None:
    request = PortfolioAiReviewRequest(mode="prompt_only", target="mock")
    manual_prompt = build_prompt_only_text(
        request,
        holdings=[_holding()],
        candidates=[_candidate()],
        market_snapshots=[PortfolioMarketSnapshot(ticker="7011")],
        news_snapshots={},
        technical_snapshots={},
        portfolio_snapshot={},
    )

    assert get_full_user_stock_analysis_prompt().strip() in manual_prompt
    assert "【5.5. 中長期持ち越し・非監視期間リスク】" in manual_prompt
    assert "【14. 辛口チェック】" in manual_prompt
    assert "アプリ側入力データ" in manual_prompt


def test_scanner_prompt_includes_base_policy_and_light_sections() -> None:
    prompt = _prompt("scanner", include_web_search=False)
    text = f"{prompt['system_prompt']}\n{prompt['user_prompt']}"

    assert get_base_policy_prompt().strip() in text
    assert "【0. 入力情報の整理】" in text
    assert "【5.5. 中長期持ち越し・非監視期間リスク 簡易版】" in text
    assert "non_monitoring_hold_risk" in text
    assert "needs_long_term_carry_check" in text
    assert "【9. 総合判断】" in text
    assert "【14. 辛口チェック 短縮版】" in text
    assert "【4. 個別材料・ファンダメンタル】" not in text
    assert "最新Web確認なし" in "\n".join(prompt["warnings"])  # type: ignore[arg-type]


def test_analyst_prompt_includes_detailed_stock_sections() -> None:
    prompt = _prompt("analyst")
    text = f"{prompt['system_prompt']}\n{prompt['user_prompt']}"

    assert get_mode_profile("analyst").default_include_web_search is True
    assert "【4. 個別材料・ファンダメンタル】" in text
    assert "【5.5. 中長期持ち越し・非監視期間リスク】" in text
    assert "long_term_carry_check" in text
    assert "【6. 需給】" in text
    assert "【7. テクニカル】" in text
    assert "検証ラベル" in text
    assert "反証条件" in text


def test_judge_prompt_includes_portfolio_judgement_sections() -> None:
    prompt = _prompt("judge")
    text = f"{prompt['system_prompt']}\n{prompt['user_prompt']}"

    assert "【8. 建玉・ポートフォリオ影響】" in text
    assert "毎日監視できない前提" in text
    assert "毎日見られないなら縮小すべき銘柄" in text or "縮小すべき銘柄" in text
    assert "資金効率" in text
    assert "入れ替え" in text


def test_critical_prompt_includes_full_detail_and_warnings_when_web_off() -> None:
    prompt = _prompt("critical", include_web_search=False)
    text = f"{prompt['system_prompt']}\n{prompt['user_prompt']}"

    assert "【12. シナリオ分析】" in text
    assert "【14. 辛口チェック】" in text
    assert "非監視期間リスクを重く評価" in text
    assert "短期/中期/長期分離" in text
    assert any("critical mode" in warning for warning in prompt["warnings"])  # type: ignore[union-attr]


def test_validation_warning_does_not_raise_for_partial_model_output() -> None:
    warnings = validate_stock_analysis_response({"stocks": [{"ticker": "7011", "name": "三菱重工業"}]}, "analyst")

    assert warnings
    assert any("required field" in warning for warning in warnings)
    assert any("verification_labels" in warning for warning in warnings)
    assert any("long_term_carry_check" in warning for warning in warnings)


def test_output_schema_includes_long_term_carry_check_without_event_conflict() -> None:
    analyst_schema = get_output_schema_for_mode("analyst")
    stock_schema = analyst_schema["properties"]["stocks"]["items"]
    stock_properties = stock_schema["properties"]

    assert "long_term_carry_check" in stock_properties
    assert "long_term_carry_check" in stock_schema["required"]
    assert "event_carry_check" not in stock_properties
    assert "final_long_term_carry_decision" in stock_properties["long_term_carry_check"]["required"]


def test_scanner_schema_uses_simplified_non_monitoring_fields() -> None:
    scanner_schema = get_output_schema_for_mode("scanner")
    stock_schema = scanner_schema["properties"]["stocks"]["items"]

    assert "non_monitoring_hold_risk" in stock_schema["required"]
    assert "needs_long_term_carry_check" in stock_schema["required"]
    assert "long_term_carry_check" not in stock_schema["required"]
