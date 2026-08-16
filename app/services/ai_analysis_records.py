"""Local persistence for successful canonical AI analysis responses."""

from __future__ import annotations

from dataclasses import dataclass
import json

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.presets import AnswerPreset
from app.models.ai_analysis_record import AiAnalysisRecord
from app.models.base import utc_now
from app.prompts.individual_security import PromptTrace
from app.schemas.ai_analysis import AiSecuritySnapshot


class AiAnalysisPersistenceError(RuntimeError):
    """Sanitized error raised when a completed answer cannot be saved."""

    def __init__(self, *, exception_type: str, openai_response_id: str) -> None:
        super().__init__("AI分析の回答を保存できませんでした。")
        self.exception_type = exception_type
        self.openai_response_id = openai_response_id


@dataclass(frozen=True, slots=True)
class AiAnalysisRecordInput:
    """Values required to persist one verified successful response."""

    request_id: str
    security: AiSecuritySnapshot
    question: str
    answer_text: str
    preset: AnswerPreset
    model: str
    openai_response_id: str
    prompt_trace: PromptTrace


class AiAnalysisRecordRepository:
    """Store and retrieve immutable local AI response records."""

    def save(self, *, db: Session, record_input: AiAnalysisRecordInput) -> AiAnalysisRecord:
        created_at = utc_now()
        trace = record_input.prompt_trace
        record = AiAnalysisRecord(
            request_id=record_input.request_id,
            security_code=record_input.security.security_code,
            security_name=record_input.security.name,
            security_market=record_input.security.market,
            question=record_input.question,
            answer_text=record_input.answer_text,
            preset=record_input.preset.preset_id.value,
            model=record_input.model,
            reasoning_effort=record_input.preset.reasoning_effort,
            reasoning_mode=record_input.preset.reasoning_mode,
            text_verbosity=record_input.preset.text_verbosity,
            openai_response_id=record_input.openai_response_id,
            prompt_version=trace.prompt_version,
            prompt_profile_id=trace.prompt_profile_id,
            compiler_version=trace.compiler_version,
            prompt_module_id=trace.module_id,
            prompt_module_name=trace.module_name,
            prompt_asset_ids=json.dumps(trace.asset_ids, ensure_ascii=False, separators=(",", ":")),
            prompt_source_sha256=trace.source_sha256,
            compiled_prompt_sha256=trace.compiled_prompt_sha256,
            created_at=created_at,
        )
        try:
            db.add(record)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise AiAnalysisPersistenceError(
                exception_type=exc.__class__.__name__,
                openai_response_id=record_input.openai_response_id,
            ) from exc
        return record

    @staticmethod
    def get(*, db: Session, request_id: str) -> AiAnalysisRecord | None:
        return db.get(AiAnalysisRecord, request_id)


def get_ai_analysis_record_repository() -> AiAnalysisRecordRepository:
    """Return the production local response repository."""

    return AiAnalysisRecordRepository()
