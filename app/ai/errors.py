"""Shared error codes for the minimal OpenAI vertical slice."""

from __future__ import annotations

from enum import StrEnum


class OpenAIErrorCode(StrEnum):
    """Stable OpenAI failure categories exposed by the API."""

    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INVALID_API_PARAMETERS = "INVALID_API_PARAMETERS"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    UNKNOWN_OPENAI_ERROR = "UNKNOWN_OPENAI_ERROR"

