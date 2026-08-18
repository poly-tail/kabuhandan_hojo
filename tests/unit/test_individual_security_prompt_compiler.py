from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pytest

import app.prompts.individual_security.compiler as compiler_module
from app.prompts.individual_security import (
    IndividualSecurityPromptCompiler,
    SecurityPromptContext,
)
from app.prompts.individual_security.compiler import PromptConfigurationError


FIXED_NOW = datetime.fromisoformat("2026-08-18T12:34:56+09:00")
FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "ai_analysis"
    / "individual_security_questions_v2026_08_18.json"
)
PROMPT_ASSET_ROOT = (
    Path(__file__).resolve().parents[2] / "app" / "prompts" / "individual_security" / "assets"
)
PROMPT_MANIFEST_PATH = PROMPT_ASSET_ROOT.parent / "manifest.json"


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
    assert "銘柄名（銘柄コード）" in compiled.instructions
    assert "2. 対象銘柄：銘柄名（銘柄コード）" in compiled.instructions
    assert "共通OSに従い、この銘柄を総合分析してください。" in compiled.instructions
    assert "主因、補正項、反証条件、撤退条件、再参入条件を明示してください。" in compiled.instructions
    assert "根拠ラベル表記正規化版" not in compiled.instructions
    assert "このrelease descriptor自体はOpenAI requestへ送信しない" not in compiled.input_text


def test_compiler_includes_security_context_and_user_question() -> None:
    question = "市場要因と個別要因を分けてください。"
    compiled = _compile(question)

    assert '"security_code": "7203"' in compiled.input_text
    assert '"name": "トヨタ自動車"' in compiled.input_text
    assert "銘柄名と銘柄コードを別フィールドとして扱い" in compiled.instructions
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
        '"company_name"',
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

    assert first.trace.prompt_version == "2026.08.18"
    assert first.trace.prompt_profile_id == "individual_security_comprehensive"
    assert first.trace.compiler_version == "individual-security-v2"
    assert first.trace.module_id == "3.1"
    assert first.trace.module_name == "総合的な個別銘柄分析"
    assert (
        first.trace.source_sha256
        == "B1C0AF5B2C33D76E4F836A428380237383FB7EAEA8B6FEAFFD9CC82632416D30"
    )
    assert first.trace.asset_ids == (
        "common_os@2026.08.18",
        "common_input_rules@2026.08.18-mvp1",
        "execution_constraints_no_tools@mvp1",
        "individual_comprehensive@2026.08.18",
    )
    assert len(first.trace.compiled_prompt_sha256) == 64
    assert first.trace.compiled_prompt_sha256 == second.trace.compiled_prompt_sha256
    assert first.trace.compiled_prompt_sha256 != changed.trace.compiled_prompt_sha256


def test_trace_metadata_contains_no_prompt_or_question_text() -> None:
    question = "この秘密ではない質問本文をmetadataへ入れないでください。"
    compiled = _compile(question)
    metadata = compiled.trace.as_openai_metadata()
    serialized = json.dumps(metadata, ensure_ascii=False)

    assert metadata["prompt_version"] == "2026.08.18"
    assert metadata["prompt_module"] == "3.1"
    assert "common_os@2026.08.18" in metadata["prompt_assets"]
    assert question not in serialized
    assert "あなたは、企業の良し悪しを解説するだけのAIではない" not in serialized


def test_compiler_marks_missing_market_data_and_disables_tools() -> None:
    compiled = _compile()

    assert "Web検索、外部ツール、J-Quantsその他の市場データ取得を利用できない" in compiled.instructions
    assert "未提供情報を、知識や典型例から現在の事実として補完せず" in compiled.instructions
    assert '"market_data_as_of": "【U】未提供"' in compiled.input_text
    assert "現在価格・価格取得時刻" in compiled.input_text
    assert "API preset STANDARDとは別軸" in compiled.input_text


def test_compiler_uses_only_formal_verification_brackets() -> None:
    compiled = _compile()
    combined = f"{compiled.instructions}\n{compiled.input_text}"

    assert "\u3016" not in combined
    assert "\u3017" not in combined
    assert "【V】" in combined
    assert "【E】" in combined
    assert "【U】" in combined


def test_compiler_canonicalizes_legacy_brackets_in_all_runtime_text() -> None:
    compiled = _compiler().compile(
        security=SecurityPromptContext(
            security_code="7203\u3016V\u3017",
            name="テスト銘柄\u3016U\u3017",
            market="市場\u3016E\u3017",
            industry_17="業種\u3016V/E/U\u3017",
            industry_33=None,
        ),
        question="質問内の\u3016V\u3017・\u3016E\u3017・\u3016U\u3017を統一してください。",
    )

    assert "\u3016" not in compiled.input_text
    assert "\u3017" not in compiled.input_text
    assert "7203【V】" in compiled.input_text
    assert "テスト銘柄【U】" in compiled.input_text
    assert "市場【E】" in compiled.input_text
    assert "業種【V/E/U】" in compiled.input_text
    assert "質問内の【V】・【E】・【U】" in compiled.input_text


def test_compiler_fails_closed_if_active_static_asset_has_legacy_brackets() -> None:
    compiler = _compiler()
    common_os = compiler._assets["common_os"]
    compiler._assets["common_os"] = replace(
        common_os,
        content=f"{common_os.content}\n\u3016U\u3017 legacy marker",
    )

    with pytest.raises(PromptConfigurationError, match="legacy verification brackets"):
        compiler.compile(
            security=SecurityPromptContext(security_code="7203", name="トヨタ自動車"),
            question="確認してください。",
        )


def test_asset_loader_rejects_legacy_brackets_even_with_matching_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MemoryResource:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read_bytes(self) -> bytes:
            return self._payload

    class MemoryPackageRoot:
        def __init__(self, payloads: dict[str, bytes]) -> None:
            self._payloads = payloads

        def joinpath(self, *parts: str) -> MemoryResource:
            return MemoryResource(self._payloads["/".join(parts)])

    asset_specs = {}
    payloads = {}
    for role in compiler_module.EXPECTED_COMPILE_ORDER:
        content = "\u3016V\u3017 legacy marker" if role == "common_os" else f"safe {role}"
        asset_path = f"{role}.md"
        payload = content.encode("utf-8")
        payloads[asset_path] = payload
        asset_specs[role] = {
            "asset_id": f"{role}@test",
            "path": asset_path,
            "source_section": role,
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
        }

    package_root = MemoryPackageRoot(payloads)
    monkeypatch.setattr(compiler_module.resources, "files", lambda _package: package_root)

    with pytest.raises(PromptConfigurationError, match="legacy verification brackets for common_os"):
        IndividualSecurityPromptCompiler._load_assets({"assets": asset_specs})


def test_v2026_08_17_assets_remain_immutable() -> None:
    expected_hashes = {
        "common_os.md": "EE28BC9B2570FE31ADBBBE4C1D7EEEA9DFF2BD558F16FA9CE9B19044671D4844",
        "common_input_rules.md": "1AF66FE9D3F8A7A66B8BACEFEEF26C0A91E4B791FC8461199F586044E7096EFE",
        "execution_constraints_no_tools.md": "5BE86DFC3DFE350EBAFAE5C4A20742CFDE43D6FC96D1F9DCFB46EAD324F9C843",
        "modules/individual_comprehensive.md": "E83E1C19238C92DD99FD7781A8317AF1ADC6D33743D6C8FCED135E4ABB4E4DB5",
    }

    for relative_path, expected_hash in expected_hashes.items():
        payload = (PROMPT_ASSET_ROOT / "v2026_08_17" / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest().upper() == expected_hash


def test_v2026_08_18_source_descriptor_tracks_base_source_and_is_not_an_asset() -> None:
    manifest = json.loads(PROMPT_MANIFEST_PATH.read_text(encoding="utf-8"))
    source = manifest["source"]
    source_payload = (PROMPT_ASSET_ROOT.parent / source["path"]).read_bytes()

    assert source["title"] == "株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）"
    assert hashlib.sha256(source_payload).hexdigest().upper() == source["sha256"]
    assert manifest["revision"]["base_source"] == {
        "title": "株判断プロジェクト｜定型プロンプト集 v2026.08.17",
        "sha256": "09C7412D2C8FF81BB5F3BDF2EC07C1DC7E251EBA370A0CA994C0D7E2642FFFC1",
    }
    assert source["path"] not in {
        asset["path"] for asset in manifest["assets"].values()
    }


def test_manifest_loader_fails_closed_on_source_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MemoryResource:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read_text(self, *, encoding: str) -> str:
            return self._payload.decode(encoding)

        def read_bytes(self) -> bytes:
            return self._payload

    class MemoryPackageRoot:
        def __init__(self, payloads: dict[str, bytes]) -> None:
            self._payloads = payloads

        def joinpath(self, *parts: str) -> MemoryResource:
            return MemoryResource(self._payloads["/".join(parts)])

    manifest = json.loads(PROMPT_MANIFEST_PATH.read_text(encoding="utf-8"))
    source_path = manifest["source"]["path"]
    source_payload = (PROMPT_ASSET_ROOT.parent / source_path).read_bytes()
    manifest["source"]["sha256"] = "0" * 64
    package_root = MemoryPackageRoot(
        {
            "manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            source_path: source_payload,
        }
    )
    monkeypatch.setattr(compiler_module.resources, "files", lambda _package: package_root)

    with pytest.raises(PromptConfigurationError, match="source hash mismatch"):
        IndividualSecurityPromptCompiler._load_manifest()


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

    assert fixture["prompt_version"] == "2026.08.18"
    assert "根拠ラベル表記" in fixture["human_review_dimensions"]
    serialized_fixture = json.dumps(fixture, ensure_ascii=False)
    assert "\u3016" not in serialized_fixture
    assert "\u3017" not in serialized_fixture
    assert "【V】確認済み" in serialized_fixture
    assert "【E】推定" in serialized_fixture
    assert "【U】未確認" in serialized_fixture
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
