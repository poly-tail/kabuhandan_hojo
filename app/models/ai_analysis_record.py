"""Persisted successful responses from the canonical AI analysis flow."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now


class AiAnalysisRecord(Base):
    """Immutable local audit record for one successful OpenAI response."""

    __tablename__ = "ai_analysis_record"
    __table_args__ = (
        Index("ix_ai_analysis_record_security_created_at", "security_code", "created_at"),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    security_code: Mapped[str] = mapped_column(String(10), nullable=False)
    security_name: Mapped[str] = mapped_column(String(255), nullable=False)
    security_market: Mapped[str | None] = mapped_column(String(50))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    preset: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(16), nullable=False)
    reasoning_mode: Mapped[str | None] = mapped_column(String(16))
    text_verbosity: Mapped[str] = mapped_column(String(16), nullable=False)
    openai_response_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Prompt provenance only. Full instructions and runtime input are never stored here.
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    compiler_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_module_id: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_module_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_asset_ids: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
