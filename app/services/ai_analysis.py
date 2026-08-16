"""Application service for the minimal single-security AI analysis flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.presets import AnswerPreset, get_answer_preset
from app.ai.runtime import AI_ANALYSIS_MODEL
from app.core.config import get_settings
from app.integrations.openai_responses import OpenAIResponsesClient, OpenAITextResponse
from app.models.security import SecurityMaster
from app.prompts.individual_security import (
    IndividualSecurityPromptCompiler,
    PromptTrace,
    SecurityPromptContext,
)
from app.schemas.ai_analysis import AiAnalysisRequest, AiSecuritySnapshot
from app.services.ai_analysis_records import AiAnalysisRecordInput, AiAnalysisRecordRepository


class OpenAITextClient(Protocol):
    async def create_text(
        self,
        *,
        instructions: str,
        input_text: str,
        preset: AnswerPreset,
        request_metadata: dict[str, str] | None = None,
    ) -> OpenAITextResponse: ...


class SecurityNotFoundError(LookupError):
    """Raised when the requested registered security does not exist."""


@dataclass(frozen=True, slots=True)
class AiAnalysisServiceResult:
    """Successful result returned to the API route."""

    answer_text: str
    openai_response_id: str
    security: AiSecuritySnapshot
    prompt_trace: PromptTrace
    saved_at: datetime


class AiAnalysisService:
    """Resolve one security and perform exactly one OpenAI request."""

    def __init__(
        self,
        openai_client: OpenAITextClient,
        *,
        prompt_compiler: IndividualSecurityPromptCompiler | None = None,
        record_repository: AiAnalysisRecordRepository | None = None,
    ) -> None:
        self._openai_client = openai_client
        self._prompt_compiler = prompt_compiler or IndividualSecurityPromptCompiler()
        self._record_repository = record_repository or AiAnalysisRecordRepository()

    async def analyze(
        self,
        *,
        request_id: str,
        payload: AiAnalysisRequest,
        db: Session,
    ) -> AiAnalysisServiceResult:
        security = db.get(SecurityMaster, payload.security_code)
        if security is None or not security.is_active:
            raise SecurityNotFoundError(payload.security_code)

        snapshot = AiSecuritySnapshot(
            security_code=security.ticker_code,
            name=security.name,
            market=security.market,
        )
        compiled_prompt = self._prompt_compiler.compile(
            security=SecurityPromptContext(
                security_code=security.ticker_code,
                name=security.name,
                market=security.market,
                industry_17=security.industry_17,
                industry_33=security.industry_33,
                listed_date=security.listed_date,
            ),
            question=payload.question,
        )
        preset = get_answer_preset(payload.preset)
        response = await self._openai_client.create_text(
            instructions=compiled_prompt.instructions,
            input_text=compiled_prompt.input_text,
            preset=preset,
            request_metadata=compiled_prompt.trace.as_openai_metadata(),
        )
        record = self._record_repository.save(
            db=db,
            record_input=AiAnalysisRecordInput(
                request_id=request_id,
                security=snapshot,
                question=payload.question,
                answer_text=response.output_text,
                preset=preset,
                model=AI_ANALYSIS_MODEL,
                openai_response_id=response.response_id,
                prompt_trace=compiled_prompt.trace,
            ),
        )
        return AiAnalysisServiceResult(
            answer_text=response.output_text,
            openai_response_id=response.response_id,
            security=snapshot,
            prompt_trace=compiled_prompt.trace,
            saved_at=record.created_at,
        )


def get_ai_analysis_service() -> AiAnalysisService:
    """Build the production service without mock, cache, or fallback."""

    settings = get_settings()
    return AiAnalysisService(OpenAIResponsesClient(api_key=settings.openai_api_key))
