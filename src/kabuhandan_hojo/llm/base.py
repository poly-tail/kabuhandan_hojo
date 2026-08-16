"""Document summary abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SummaryGenerator(ABC):
    """Small interface so an external LLM provider can be injected later."""

    @abstractmethod
    def summarize_document(self, title: str, metadata: dict[str, Any], content_text: str | None = None) -> str:
        """Return an explanation-oriented summary."""

