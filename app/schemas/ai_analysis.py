"""Schemas for the minimal single-security AI analysis endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.errors import OpenAIErrorCode
from app.ai.presets import AnswerPresetId


AiAnalysisStatus = Literal["success", "error"]
AiAnalysisErrorCode = OpenAIErrorCode | Literal["SECURITY_NOT_FOUND", "DATABASE_UNAVAILABLE"]


class AiAnalysisRequest(BaseModel):
    """Minimal request for asking about one registered security."""

    model_config = ConfigDict(extra="forbid")

    security_code: str = Field(min_length=4, max_length=10)
    question: str = Field(min_length=1, max_length=4_000)
    preset: AnswerPresetId = AnswerPresetId.STANDARD

    @field_validator("security_code", "question")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AiSecuritySnapshot(BaseModel):
    """Security identity captured at request time."""

    model_config = ConfigDict(extra="forbid")

    security_code: str
    name: str
    market: str | None = None


class AiAnalysisError(BaseModel):
    """Safe error details intended for the browser."""

    model_config = ConfigDict(extra="forbid")

    code: AiAnalysisErrorCode
    message: str


class AiAnalysisResponse(BaseModel):
    """Minimal response envelope for success and failure."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: AiAnalysisStatus
    answer_text: str | None = None
    error: AiAnalysisError | None = None
    security: AiSecuritySnapshot | None = None
    openai_response_id: str | None = None
