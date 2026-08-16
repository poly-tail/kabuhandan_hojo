"""Deterministic summary generator used until an external LLM is added."""

from __future__ import annotations

from typing import Any

from kabuhandan_hojo.llm.base import SummaryGenerator


class TemplateSummaryGenerator(SummaryGenerator):
    """Template-based summary generator.

    This keeps Phase 0-2 operational without outsourcing numeric reasoning to an
    LLM. An actual LLM adapter can later implement the same interface.
    """

    def summarize_document(self, title: str, metadata: dict[str, Any], content_text: str | None = None) -> str:
        ticker_code = metadata.get("ticker_code") or metadata.get("secCode") or "不明銘柄"
        important_value = metadata.get("important_value") or metadata.get("docTypeCode") or metadata.get("formCode")
        excerpt = (content_text or "").strip().replace("\n", " ")
        excerpt = excerpt[:120] if excerpt else "本文要約は未抽出です。"
        return f"{ticker_code}: {title}。識別値={important_value}。{excerpt}"

