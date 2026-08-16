from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.ai.presets import STANDARD_PRESET
from app.ai.runtime import AI_ANALYSIS_MODEL
from app.prompts.individual_security import IndividualSecurityPromptCompiler, SecurityPromptContext
from app.schemas.ai_analysis import AiSecuritySnapshot
from app.services.ai_analysis_records import (
    AiAnalysisPersistenceError,
    AiAnalysisRecordInput,
    AiAnalysisRecordRepository,
)


class CommitFailingSession:
    def __init__(self) -> None:
        self.added = None
        self.rolled_back = False

    def add(self, record) -> None:
        self.added = record

    def commit(self) -> None:
        raise SQLAlchemyError("database detail must stay private")

    def rollback(self) -> None:
        self.rolled_back = True


def test_record_repository_rolls_back_and_sanitizes_commit_failure() -> None:
    compiled = IndividualSecurityPromptCompiler().compile(
        security=SecurityPromptContext(
            security_code="7203",
            name="トヨタ自動車",
            market="東証プライム",
            listed_date=date(1949, 5, 16),
        ),
        question="保存テストです。",
    )
    session = CommitFailingSession()
    record_input = AiAnalysisRecordInput(
        request_id="00000000-0000-4000-8000-000000000001",
        security=AiSecuritySnapshot(
            security_code="7203",
            name="トヨタ自動車",
            market="東証プライム",
        ),
        question="保存テストです。",
        answer_text="回答です。",
        preset=STANDARD_PRESET,
        model=AI_ANALYSIS_MODEL,
        openai_response_id="resp_storage_test",
        prompt_trace=compiled.trace,
    )

    with pytest.raises(AiAnalysisPersistenceError) as caught:
        AiAnalysisRecordRepository().save(db=session, record_input=record_input)  # type: ignore[arg-type]

    assert session.added is not None
    assert session.rolled_back is True
    assert caught.value.exception_type == "SQLAlchemyError"
    assert caught.value.openai_response_id == "resp_storage_test"
    assert "database detail" not in str(caught.value)
