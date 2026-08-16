from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path

import pytest

from app.prompts.individual_security import IndividualSecurityPromptCompiler, SecurityPromptContext


FIXED_NOW = datetime.fromisoformat("2026-08-17T12:34:56+09:00")
FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ai_analysis"
    / "individual_security_questions_v2026_08_16.json"
)


def _compiler() -> IndividualSecurityPromptCompiler:
    return IndividualSecurityPromptCompiler(now_provider=lambda: FIXED_NOW)


def _compile(question: str = "この銘柄を確認してください。"):
    return _compiler().compile(
        security=SecurityPromptContext(
            security_code="7203",
            name="トヨタ自動車",
            market="東証プライム",
            industry_17="自動車・輸送機",
            industry_33="輸送用機器",
            listed_date=date(1949, 5, 16),
        ),
        question=question,
    )


def test_compiler_loads_common_os_and_exact_task_module() -> None:
    compiled = _compile()

    assert "## 1. 最上位原則" in compiled.instructions
    assert "## 5. 株価反応の5層モデル" in compiled.instructions
    assert "根拠不足なら無理に売買結論を出さず、insufficient_data または no_trade" in compiled.instructions
    assert "共通OSに従い、この銘柄を総合分析してください。" in compiled.instructions
    assert "主因、補正項、反証条件、撤退条件、再参入条件を明示してください。" in compiled.instructions


def test_compiler_includes_security_context_and_user_question() -> None:
    question = "市場要因と個別要因を分けてください。"
    compiled = _compile(question)

    assert '"security_code": "7203"' in compiled.input_text
    assert '"name": "トヨタ自動車"' in compiled.input_text
    assert '"market": "東証プライム"' in compiled.input_text
    assert '"industry_33": "輸送用機器"' in compiled.input_text
    assert '"listed_date": "1949-05-16"' in compiled.input_text
    assert question in compiled.input_text
    assert question not in compiled.instructions


@pytest.mark.parametrize(
    "excluded_marker",
    [
        "現在のポジションを起点に判断してください",
        "この銘柄を決算跨ぎする期待値を分析してください",
        "決算内容と株価反応を分離して分析してください",
        "このニュース・IRが投資判断へ与える影響だけを分析してください",
        "この経済指標・政策・政治イベント・金融政策が株式市場へ与える影響",
        "短期～スイングの空売り候補として分析してください",
        "当日トレードとして分析してください",
        "このチャートセットアップが成功しやすい条件",
        "今後数年で数倍化する可能性があるテーマと銘柄を探索してください",
        "この銘柄の値動きの癖を、印象ではなくデータで分類してください",
        "ポートフォリオ全体を最適化してください",
        "このトレードを結果論ではなくプロセスで監査してください",
        "結論に影響する項目だけを3分版で確認してください",
        "回答本文の後に、必ず次のJSONを1つだけ出力してください",
    ],
)
def test_compiler_does_not_include_unselected_modules_or_json_schema(excluded_marker: str) -> None:
    compiled = _compile()

    assert excluded_marker not in compiled.instructions
    assert excluded_marker not in compiled.input_text


def test_compiler_exposes_version_assets_module_and_stable_hash() -> None:
    first = _compile()
    second = _compile()
    changed = _compile("別の質問です。")

    assert first.trace.prompt_version == "2026.08.16"
    assert first.trace.prompt_profile_id == "individual_security_comprehensive"
    assert first.trace.compiler_version == "individual-security-v1"
    assert first.trace.module_id == "3.1"
    assert first.trace.module_name == "総合的な個別銘柄分析"
    assert first.trace.asset_ids == (
        "common_os@2026.08.16",
        "common_input_rules@2026.08.16-mvp1",
        "execution_constraints_no_tools@mvp1",
        "individual_comprehensive@2026.08.16",
    )
    assert len(first.trace.compiled_prompt_sha256) == 64
    assert first.trace.compiled_prompt_sha256 == second.trace.compiled_prompt_sha256
    assert first.trace.compiled_prompt_sha256 != changed.trace.compiled_prompt_sha256


def test_trace_metadata_contains_no_prompt_or_question_text() -> None:
    question = "この秘密ではない質問本文をmetadataへ入れないでください。"
    compiled = _compile(question)
    metadata = compiled.trace.as_openai_metadata()
    serialized = json.dumps(metadata, ensure_ascii=False)

    assert metadata["prompt_version"] == "2026.08.16"
    assert metadata["prompt_module"] == "3.1"
    assert "common_os@2026.08.16" in metadata["prompt_assets"]
    assert question not in serialized
    assert "あなたは、企業の良し悪しを解説するだけのAIではない" not in serialized


def test_compiler_marks_missing_market_data_and_disables_tools() -> None:
    compiled = _compile()

    assert "Web検索、外部ツール、J-Quantsその他の市場データ取得を利用できない" in compiled.instructions
    assert "未提供情報を、知識や典型例から現在の事実として補完せず" in compiled.instructions
    assert '"market_data_as_of": "【U】未提供"' in compiled.input_text
    assert "現在価格・価格取得時刻" in compiled.input_text
    assert "API preset STANDARDとは別軸" in compiled.input_text


def test_compiler_preserves_required_asset_order() -> None:
    compiled = _compile()
    positions = [
        compiled.instructions.index('role="common_os"'),
        compiled.instructions.index('role="common_input_rules"'),
        compiled.instructions.index('role="execution_constraints"'),
        compiled.instructions.index('role="task_module"'),
    ]

    assert positions == sorted(positions)


def test_evaluation_fixture_covers_all_requested_perspectives() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    coverage = {tag for case in cases for tag in case["coverage"]}

    assert fixture["prompt_version"] == "2026.08.16"
    assert 5 <= len(cases) <= 10
    assert len({case["id"] for case in cases}) == len(cases)
    assert {
        "buy_decision",
        "post_earnings",
        "factor_separation",
        "momentum",
        "supply_demand",
        "events",
        "risk",
        "falsification",
        "insufficient_data",
        "no_trade",
    } <= coverage
