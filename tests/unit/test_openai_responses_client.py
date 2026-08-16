from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)

from app.ai.errors import OpenAIErrorCode
from app.ai.presets import STANDARD_PRESET
from app.ai.runtime import AI_ANALYSIS_MODEL, AI_ANALYSIS_TIMEOUT_SECONDS
from app.integrations.openai_responses import OpenAIClientError, OpenAIResponsesClient


class FakeResponsesApi:
    def __init__(self, *, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _run(client: OpenAIResponsesClient):
    return asyncio.run(
        client.create_text(
            instructions="テスト用instructionsです。",
            input_text="短い疎通確認です。",
            preset=STANDARD_PRESET,
            request_metadata={"prompt_version": "test-v1"},
        )
    )


def _status_error(error_type, status_code: int, *, body=None):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    return error_type("test error", response=response, body=body)


def test_openai_client_returns_completed_non_empty_output_text() -> None:
    responses = FakeResponsesApi(
        response=SimpleNamespace(id="resp_test", status="completed", output_text="  疎通成功  ")
    )
    client = OpenAIResponsesClient(api_key="test-key", responses_api=responses)

    result = _run(client)

    assert result.response_id == "resp_test"
    assert result.status == "completed"
    assert result.output_text == "疎通成功"
    assert responses.calls == [
        {
            "model": AI_ANALYSIS_MODEL,
            "instructions": "テスト用instructionsです。",
            "input": "短い疎通確認です。",
            "reasoning": {"effort": "medium"},
            "text": {"verbosity": "medium"},
            "timeout": AI_ANALYSIS_TIMEOUT_SECONDS,
            "metadata": {"prompt_version": "test-v1"},
        }
    ]


def test_openai_client_rejects_empty_output_text() -> None:
    responses = FakeResponsesApi(response=SimpleNamespace(id="resp_empty", status="completed", output_text="  "))
    client = OpenAIResponsesClient(api_key="test-key", responses_api=responses)

    with pytest.raises(OpenAIClientError) as caught:
        _run(client)

    assert caught.value.code is OpenAIErrorCode.EMPTY_RESPONSE
    assert caught.value.response_id == "resp_empty"


def test_openai_client_rejects_non_completed_status() -> None:
    responses = FakeResponsesApi(response=SimpleNamespace(id="resp_incomplete", status="incomplete", output_text="途中"))
    client = OpenAIResponsesClient(api_key="test-key", responses_api=responses)

    with pytest.raises(OpenAIClientError) as caught:
        _run(client)

    assert caught.value.code is OpenAIErrorCode.UNKNOWN_OPENAI_ERROR
    assert caught.value.response_status == "incomplete"


def test_openai_client_classifies_timeout() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    responses = FakeResponsesApi(error=APITimeoutError(request=request))
    client = OpenAIResponsesClient(api_key="test-key", responses_api=responses)

    with pytest.raises(OpenAIClientError) as caught:
        _run(client)

    assert caught.value.code is OpenAIErrorCode.TIMEOUT
    assert caught.value.exception_type == "APITimeoutError"


@pytest.mark.parametrize(
    ("sdk_error", "expected_code"),
    [
        (_status_error(AuthenticationError, 401), OpenAIErrorCode.AUTHENTICATION_ERROR),
        (_status_error(NotFoundError, 404), OpenAIErrorCode.MODEL_UNAVAILABLE),
        (_status_error(BadRequestError, 400), OpenAIErrorCode.INVALID_API_PARAMETERS),
        (_status_error(RateLimitError, 429), OpenAIErrorCode.RATE_LIMITED),
        (
            APIConnectionError(
                request=httpx.Request("POST", "https://api.openai.com/v1/responses")
            ),
            OpenAIErrorCode.NETWORK_ERROR,
        ),
    ],
)
def test_openai_client_classifies_sdk_errors(sdk_error: Exception, expected_code: OpenAIErrorCode) -> None:
    responses = FakeResponsesApi(error=sdk_error)
    client = OpenAIResponsesClient(api_key="test-key", responses_api=responses)

    with pytest.raises(OpenAIClientError) as caught:
        _run(client)

    assert caught.value.code is expected_code
    assert "test-key" not in str(caught.value)


def test_openai_client_rejects_missing_api_key_without_calling_sdk() -> None:
    responses = FakeResponsesApi(response=SimpleNamespace(id="unused", status="completed", output_text="unused"))
    client = OpenAIResponsesClient(api_key=None, responses_api=responses)

    with pytest.raises(OpenAIClientError) as caught:
        _run(client)

    assert caught.value.code is OpenAIErrorCode.AUTHENTICATION_ERROR
    assert responses.calls == []
