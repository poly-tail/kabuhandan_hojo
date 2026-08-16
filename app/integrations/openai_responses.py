"""Minimal OpenAI Responses API client for plain-text answers."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Protocol

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from app.ai.errors import OpenAIErrorCode
from app.ai.presets import AnswerPreset
from app.ai.runtime import AI_ANALYSIS_MODEL, AI_ANALYSIS_TIMEOUT_SECONDS


class ResponsesApi(Protocol):
    """Subset of the SDK Responses resource used by this adapter."""

    async def create(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class OpenAITextResponse:
    """Verified plain-text response returned by OpenAI."""

    response_id: str
    status: str
    output_text: str


class OpenAIClientError(RuntimeError):
    """Sanitized OpenAI error with safe diagnostics separated from UI text."""

    def __init__(
        self,
        code: OpenAIErrorCode,
        user_message: str,
        *,
        exception_type: str | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
        response_id: str | None = None,
        response_status: str | None = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.exception_type = exception_type
        self.status_code = status_code
        self.request_id = request_id
        self.response_id = response_id
        self.response_status = response_status


class OpenAIResponsesClient:
    """Call one model once and return a verified non-empty text answer."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = AI_ANALYSIS_MODEL,
        timeout_seconds: float = AI_ANALYSIS_TIMEOUT_SECONDS,
        responses_api: ResponsesApi | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._responses_api = responses_api

    @property
    def model(self) -> str:
        return self._model

    async def create_text(
        self,
        *,
        instructions: str,
        input_text: str,
        preset: AnswerPreset,
        request_metadata: Mapping[str, str] | None = None,
    ) -> OpenAITextResponse:
        """Run a synchronous Responses generation and validate its plain text."""

        if not self._api_key:
            raise OpenAIClientError(
                OpenAIErrorCode.AUTHENTICATION_ERROR,
                "OpenAI APIキーが設定されていません。",
            )

        try:
            if self._responses_api is not None:
                response = await self._create_response(
                    self._responses_api,
                    instructions=instructions,
                    input_text=input_text,
                    preset=preset,
                    request_metadata=request_metadata,
                )
            else:
                async with AsyncOpenAI(
                    api_key=self._api_key,
                    timeout=self._timeout_seconds,
                    max_retries=0,
                ) as sdk_client:
                    response = await self._create_response(
                        sdk_client.responses,
                        instructions=instructions,
                        input_text=input_text,
                        preset=preset,
                        request_metadata=request_metadata,
                    )
        except APITimeoutError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.TIMEOUT,
                "OpenAI APIの応答がタイムアウトしました。",
                exc,
            ) from exc
        except AuthenticationError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.AUTHENTICATION_ERROR,
                "OpenAI APIの認証に失敗しました。",
                exc,
            ) from exc
        except (NotFoundError, PermissionDeniedError) as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.MODEL_UNAVAILABLE,
                "指定されたOpenAIモデルを利用できません。",
                exc,
            ) from exc
        except (BadRequestError, UnprocessableEntityError) as exc:
            code = getattr(exc, "code", None)
            error_code = OpenAIErrorCode.MODEL_UNAVAILABLE if code == "model_not_found" else OpenAIErrorCode.INVALID_API_PARAMETERS
            user_message = (
                "指定されたOpenAIモデルを利用できません。"
                if error_code is OpenAIErrorCode.MODEL_UNAVAILABLE
                else "OpenAI APIへ送信したパラメータが不正です。"
            )
            raise self._error_from_exception(error_code, user_message, exc) from exc
        except RateLimitError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.RATE_LIMITED,
                "OpenAI APIの利用上限またはレート制限に達しました。",
                exc,
            ) from exc
        except APIConnectionError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.NETWORK_ERROR,
                "OpenAI APIへ接続できませんでした。",
                exc,
            ) from exc
        except APIStatusError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.UNKNOWN_OPENAI_ERROR,
                "OpenAI APIで予期しないエラーが発生しました。",
                exc,
            ) from exc
        except OpenAIError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.UNKNOWN_OPENAI_ERROR,
                "OpenAI APIで予期しないエラーが発生しました。",
                exc,
            ) from exc
        except OSError as exc:
            raise self._error_from_exception(
                OpenAIErrorCode.NETWORK_ERROR,
                "OpenAI APIへ接続できませんでした。",
                exc,
            ) from exc

        response_id = str(getattr(response, "id", "") or "")
        response_status = str(getattr(response, "status", "") or "")
        if not response_id or response_status != "completed":
            raise OpenAIClientError(
                OpenAIErrorCode.UNKNOWN_OPENAI_ERROR,
                "OpenAI APIの応答が正常に完了しませんでした。",
                response_id=response_id or None,
                response_status=response_status or None,
            )

        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            raise OpenAIClientError(
                OpenAIErrorCode.EMPTY_RESPONSE,
                "OpenAI APIから空の回答が返されました。",
                response_id=response_id,
                response_status=response_status,
            )

        return OpenAITextResponse(
            response_id=response_id,
            status=response_status,
            output_text=output_text,
        )

    async def _create_response(
        self,
        responses_api: ResponsesApi,
        *,
        instructions: str,
        input_text: str,
        preset: AnswerPreset,
        request_metadata: Mapping[str, str] | None,
    ) -> Any:
        reasoning: dict[str, str] = {"effort": preset.reasoning_effort}
        if preset.reasoning_mode is not None:
            reasoning["mode"] = preset.reasoning_mode
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": instructions,
            "input": input_text,
            "reasoning": reasoning,
            "text": {"verbosity": preset.text_verbosity},
            "timeout": self._timeout_seconds,
        }
        if request_metadata:
            request["metadata"] = dict(request_metadata)
        return await responses_api.create(
            **request,
        )

    @staticmethod
    def _error_from_exception(
        code: OpenAIErrorCode,
        user_message: str,
        exc: Exception,
    ) -> OpenAIClientError:
        return OpenAIClientError(
            code,
            user_message,
            exception_type=exc.__class__.__name__,
            status_code=getattr(exc, "status_code", None),
            request_id=getattr(exc, "request_id", None),
        )
