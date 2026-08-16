"""Compile the versioned individual-security prompt bundle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from importlib import resources
import json
from pathlib import PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo


TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")
PROMPT_PACKAGE = "app.prompts.individual_security"
EXPECTED_COMPILE_ORDER = (
    "common_os",
    "common_input_rules",
    "execution_constraints",
    "task_module",
)


class PromptConfigurationError(RuntimeError):
    """Raised when a versioned prompt bundle is missing or inconsistent."""


@dataclass(frozen=True, slots=True)
class SecurityPromptContext:
    """Existing security-master facts available to the prompt."""

    security_code: str
    name: str
    market: str | None = None
    industry_17: str | None = None
    industry_33: str | None = None
    listed_date: date | None = None


@dataclass(frozen=True, slots=True)
class PromptTrace:
    """Non-secret identifiers that can be correlated with an OpenAI response ID."""

    prompt_version: str
    prompt_profile_id: str
    compiler_version: str
    module_id: str
    module_name: str
    asset_ids: tuple[str, ...]
    source_sha256: str
    compiled_prompt_sha256: str

    def as_openai_metadata(self) -> dict[str, str]:
        """Return trace-only metadata; never include prompt or question text."""

        return {
            "prompt_version": self.prompt_version,
            "prompt_profile": self.prompt_profile_id,
            "prompt_compiler": self.compiler_version,
            "prompt_module": self.module_id,
            "prompt_assets": ",".join(self.asset_ids),
            "prompt_source_sha256": self.source_sha256,
            "prompt_sha256": self.compiled_prompt_sha256,
        }


@dataclass(frozen=True, slots=True)
class CompiledPrompt:
    """Instructions, runtime input, and safe trace for one OpenAI request."""

    instructions: str
    input_text: str
    trace: PromptTrace


@dataclass(frozen=True, slots=True)
class _PromptAsset:
    role: str
    asset_id: str
    path: str
    source_section: str
    sha256: str
    content: str


class IndividualSecurityPromptCompiler:
    """Load exactly one prompt profile and combine it with runtime input."""

    def __init__(self, *, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(TOKYO_TIMEZONE))
        self._manifest = self._load_manifest()
        self._assets = self._load_assets(self._manifest)

    @property
    def prompt_version(self) -> str:
        return str(self._manifest["prompt_version"])

    @property
    def module_id(self) -> str:
        return str(self._manifest["task_module"]["module_id"])

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(self._assets[role].asset_id for role in EXPECTED_COMPILE_ORDER)

    def compile(self, *, security: SecurityPromptContext, question: str) -> CompiledPrompt:
        """Compile common OS, one task module, security context, and user question."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be blank")

        instruction_parts = [
            (
                f'<prompt_asset role="{asset.role}" id="{asset.asset_id}">'
                f"\n{asset.content}\n</prompt_asset>"
            )
            for asset in (self._assets[role] for role in EXPECTED_COMPILE_ORDER)
        ]
        instructions = "\n\n".join(instruction_parts)
        input_text = self._build_runtime_input(security=security, question=normalized_question)
        compiled_sha256 = hashlib.sha256(
            f"{instructions}\n\n{input_text}".encode("utf-8")
        ).hexdigest().upper()

        task_module = self._manifest["task_module"]
        source = self._manifest["source"]
        trace = PromptTrace(
            prompt_version=self.prompt_version,
            prompt_profile_id=str(self._manifest["prompt_profile_id"]),
            compiler_version=str(self._manifest["compiler_version"]),
            module_id=str(task_module["module_id"]),
            module_name=str(task_module["module_name"]),
            asset_ids=self.asset_ids,
            source_sha256=str(source["sha256"]),
            compiled_prompt_sha256=compiled_sha256,
        )
        return CompiledPrompt(instructions=instructions, input_text=input_text, trace=trace)

    def _build_runtime_input(self, *, security: SecurityPromptContext, question: str) -> str:
        generated_at = self._now_provider()
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=TOKYO_TIMEZONE)
        else:
            generated_at = generated_at.astimezone(TOKYO_TIMEZONE)

        context = {
            "request_generated_at_jst": generated_at.isoformat(timespec="seconds"),
            "market_data_as_of": "【U】未提供",
            "analysis_depth": "【U】未指定（API preset STANDARDとは別軸）",
            "security": {
                "security_code": security.security_code,
                "name": security.name,
                "market": _known_or_unknown(security.market),
                "industry_17": _known_or_unknown(security.industry_17),
                "industry_33": _known_or_unknown(security.industry_33),
                "listed_date": security.listed_date.isoformat() if security.listed_date else "【U】未提供",
            },
            "available_context_scope": "登録済みsecurity_masterの上記項目のみ",
            "unavailable_context": [
                "現在価格・価格取得時刻",
                "ファンダメンタルズ・決算・コンセンサス",
                "チャート・テクニカル・モメンタム",
                "出来高・信用・空売り・その他需給",
                "指数・セクター相対強弱・市場地合い",
                "為替・金利・マクロ環境",
                "直近材料・今後のイベント",
                "保有状況・許容損失・希望時間軸",
            ],
        }
        question_payload = {"question": question}
        return (
            "<security_context>\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
            + "\n</security_context>\n\n"
            + "<user_question>\n"
            + json.dumps(question_payload, ensure_ascii=False, indent=2)
            + "\n</user_question>"
        )

    @staticmethod
    def _load_manifest() -> dict[str, Any]:
        try:
            raw = resources.files(PROMPT_PACKAGE).joinpath("manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(raw)
        except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PromptConfigurationError("individual-security prompt manifest is unreadable") from exc

        if tuple(manifest.get("compile_order") or ()) != EXPECTED_COMPILE_ORDER:
            raise PromptConfigurationError("individual-security prompt compile order is invalid")
        task_module = manifest.get("task_module") or {}
        if task_module.get("module_id") != "3.1" or task_module.get("asset_role") != "task_module":
            raise PromptConfigurationError("individual-security task module must be exactly 3.1")
        source_sha256 = str((manifest.get("source") or {}).get("sha256") or "")
        if len(source_sha256) != 64:
            raise PromptConfigurationError("individual-security source hash is invalid")
        return manifest

    @staticmethod
    def _load_assets(manifest: Mapping[str, Any]) -> dict[str, _PromptAsset]:
        asset_specs = manifest.get("assets") or {}
        package_root = resources.files(PROMPT_PACKAGE)
        loaded: dict[str, _PromptAsset] = {}
        for role in EXPECTED_COMPILE_ORDER:
            spec = asset_specs.get(role) or {}
            relative_path = PurePosixPath(str(spec.get("path") or ""))
            if relative_path.is_absolute() or ".." in relative_path.parts or not relative_path.parts:
                raise PromptConfigurationError(f"invalid prompt asset path for {role}")
            try:
                payload = package_root.joinpath(*relative_path.parts).read_bytes()
            except FileNotFoundError as exc:
                raise PromptConfigurationError(f"prompt asset is missing for {role}") from exc

            actual_sha256 = hashlib.sha256(payload).hexdigest().upper()
            expected_sha256 = str(spec.get("sha256") or "").upper()
            if actual_sha256 != expected_sha256:
                raise PromptConfigurationError(f"prompt asset hash mismatch for {role}")
            try:
                content = payload.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise PromptConfigurationError(f"prompt asset is not UTF-8 for {role}") from exc
            if not content:
                raise PromptConfigurationError(f"prompt asset is empty for {role}")
            loaded[role] = _PromptAsset(
                role=role,
                asset_id=str(spec.get("asset_id") or ""),
                path=relative_path.as_posix(),
                source_section=str(spec.get("source_section") or ""),
                sha256=actual_sha256,
                content=content,
            )
        if any(not asset.asset_id for asset in loaded.values()):
            raise PromptConfigurationError("prompt asset ID is missing")
        return loaded


def _known_or_unknown(value: str | None) -> str:
    normalized = (value or "").strip()
    return normalized or "【U】未提供"
