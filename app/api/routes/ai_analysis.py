"""Canonical endpoint for the minimal AI analysis vertical slice."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.ai.errors import OpenAIErrorCode
from app.db.session import get_db
from app.integrations.openai_responses import OpenAIClientError
from app.schemas.ai_analysis import AiAnalysisError, AiAnalysisRequest, AiAnalysisResponse
from app.services.ai_analysis import AiAnalysisService, SecurityNotFoundError, get_ai_analysis_service


logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai-analysis"])


OPENAI_ERROR_HTTP_STATUS: dict[OpenAIErrorCode, int] = {
    OpenAIErrorCode.AUTHENTICATION_ERROR: 503,
    OpenAIErrorCode.MODEL_UNAVAILABLE: 502,
    OpenAIErrorCode.INVALID_API_PARAMETERS: 502,
    OpenAIErrorCode.RATE_LIMITED: 429,
    OpenAIErrorCode.TIMEOUT: 504,
    OpenAIErrorCode.NETWORK_ERROR: 502,
    OpenAIErrorCode.EMPTY_RESPONSE: 502,
    OpenAIErrorCode.UNKNOWN_OPENAI_ERROR: 502,
}


@router.post("/api/ai/analyses", response_model=AiAnalysisResponse)
async def create_ai_analysis(
    payload: AiAnalysisRequest,
    db: Session | None = Depends(get_db),
    service: AiAnalysisService = Depends(get_ai_analysis_service),
) -> AiAnalysisResponse | JSONResponse:
    """Analyze one registered security through one OpenAI Responses call."""

    request_id = str(uuid4())
    if db is None:
        return _error_response(
            request_id=request_id,
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="銘柄データベースを利用できません。live modeで実行してください。",
        )

    try:
        result = await service.analyze(payload=payload, db=db)
    except SecurityNotFoundError:
        return _error_response(
            request_id=request_id,
            status_code=404,
            code="SECURITY_NOT_FOUND",
            message="指定された銘柄が登録されていません。",
        )
    except OpenAIClientError as exc:
        logger.warning(
            "AI analysis failed request_id=%s code=%s exception_type=%s upstream_status=%s openai_request_id=%s",
            request_id,
            exc.code.value,
            exc.exception_type,
            exc.status_code,
            exc.request_id,
        )
        return _error_response(
            request_id=request_id,
            status_code=OPENAI_ERROR_HTTP_STATUS[exc.code],
            code=exc.code,
            message=exc.user_message,
            openai_response_id=exc.response_id,
        )

    logger.info(
        "AI analysis completed request_id=%s openai_response_id=%s prompt_version=%s "
        "prompt_module=%s prompt_assets=%s prompt_sha256=%s",
        request_id,
        result.openai_response_id,
        result.prompt_trace.prompt_version,
        result.prompt_trace.module_id,
        ",".join(result.prompt_trace.asset_ids),
        result.prompt_trace.compiled_prompt_sha256,
    )

    return AiAnalysisResponse(
        request_id=request_id,
        status="success",
        answer_text=result.answer_text,
        error=None,
        security=result.security,
        openai_response_id=result.openai_response_id,
    )


def _error_response(
    *,
    request_id: str,
    status_code: int,
    code,
    message: str,
    openai_response_id: str | None = None,
) -> JSONResponse:
    response = AiAnalysisResponse(
        request_id=request_id,
        status="error",
        answer_text=None,
        error=AiAnalysisError(code=code, message=message),
        openai_response_id=openai_response_id,
    )
    return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))
