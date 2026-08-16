"""Canonical endpoint for the minimal AI analysis vertical slice."""

from __future__ import annotations

from datetime import timezone
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.ai.errors import OpenAIErrorCode
from app.db.session import get_db
from app.integrations.openai_responses import OpenAIClientError
from app.schemas.ai_analysis import (
    AiAnalysisError,
    AiAnalysisRequest,
    AiAnalysisResponse,
    AiSavedAnalysisResponse,
    AiSecuritySnapshot,
)
from app.services.ai_analysis import AiAnalysisService, SecurityNotFoundError, get_ai_analysis_service
from app.services.ai_analysis_records import (
    AiAnalysisPersistenceError,
    AiAnalysisRecordRepository,
    get_ai_analysis_record_repository,
)


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
    response: Response,
    db: Session | None = Depends(get_db),
    service: AiAnalysisService = Depends(get_ai_analysis_service),
) -> AiAnalysisResponse | JSONResponse:
    """Analyze one registered security through one OpenAI Responses call."""

    response.headers["Cache-Control"] = "no-store"
    request_id = str(uuid4())
    if db is None:
        return _error_response(
            request_id=request_id,
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="銘柄データベースを利用できません。live modeで実行してください。",
        )

    try:
        result = await service.analyze(request_id=request_id, payload=payload, db=db)
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
    except AiAnalysisPersistenceError as exc:
        logger.error(
            "AI analysis persistence failed request_id=%s exception_type=%s",
            request_id,
            exc.exception_type,
        )
        return _error_response(
            request_id=request_id,
            status_code=500,
            code="PERSISTENCE_ERROR",
            message="AI分析の回答を保存できませんでした。",
            openai_response_id=exc.openai_response_id,
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
        saved_at=result.saved_at,
    )


@router.get("/api/ai/analyses/{request_id}", response_model=AiSavedAnalysisResponse)
def get_saved_ai_analysis(
    request_id: UUID,
    response: Response,
    db: Session | None = Depends(get_db),
    repository: AiAnalysisRecordRepository = Depends(get_ai_analysis_record_repository),
) -> AiSavedAnalysisResponse | JSONResponse:
    """Return one saved answer by its unguessable request ID."""

    response.headers["Cache-Control"] = "no-store"
    normalized_request_id = str(request_id)
    if db is None:
        return _error_response(
            request_id=normalized_request_id,
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="銘柄データベースを利用できません。live modeで実行してください。",
        )

    record = repository.get(db=db, request_id=normalized_request_id)
    if record is None:
        return _error_response(
            request_id=normalized_request_id,
            status_code=404,
            code="ANALYSIS_NOT_FOUND",
            message="保存済みのAI分析が見つかりません。",
        )

    return AiSavedAnalysisResponse(
        request_id=record.request_id,
        saved_at=(
            record.created_at
            if record.created_at.tzinfo is not None
            else record.created_at.replace(tzinfo=timezone.utc)
        ),
        security=AiSecuritySnapshot(
            security_code=record.security_code,
            name=record.security_name,
            market=record.security_market,
        ),
        question=record.question,
        answer_text=record.answer_text,
        preset=record.preset,
        model=record.model,
        openai_response_id=record.openai_response_id,
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
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )
