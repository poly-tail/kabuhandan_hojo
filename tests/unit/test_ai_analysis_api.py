from __future__ import annotations

from collections.abc import Generator
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.errors import OpenAIErrorCode
from app.ai.runtime import AI_ANALYSIS_MODEL
from app.api.routes.ai_analysis import get_ai_analysis_service
from app.core.config import get_settings
from app.db.session import get_db, get_engine, get_session_factory
from app.integrations.openai_responses import OpenAIClientError, OpenAITextResponse
from app.main import create_app
from app.models import AiAnalysisRecord, Base
from app.models.security import SecurityMaster
from app.services.ai_analysis import AiAnalysisService, PERSISTENCE_FAILURE_WARNING
from app.services.ai_analysis_records import AiAnalysisPersistenceError, AiAnalysisRecordRepository
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from kabuhandan_hojo.models import Base as MonitoringBase


class FakeOpenAITextClient:
    def __init__(self, *, result: OpenAITextResponse | None = None, error: OpenAIClientError | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    async def create_text(self, **kwargs) -> OpenAITextResponse:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


@pytest.fixture(autouse=True)
def clear_runtime_state() -> Generator[None, None, None]:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    get_monitoring_settings.cache_clear()
    get_monitoring_container.cache_clear()


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_openai: FakeOpenAITextClient,
    *,
    record_repository: AiAnalysisRecordRepository | None = None,
) -> tuple[TestClient, sessionmaker]:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    app = create_app()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    MonitoringBase.metadata.create_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as db:
        db.add(
            SecurityMaster(
                ticker_code="7203",
                local_code="7203",
                name="トヨタ自動車",
                market="東証プライム",
                is_active=True,
            )
        )
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_ai_analysis_service] = lambda: AiAnalysisService(
        fake_openai,
        record_repository=record_repository,
    )
    return TestClient(app), testing_session_local


def test_ai_analysis_endpoint_returns_plain_text_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(
            response_id="resp_endpoint_test",
            status="completed",
            output_text="テスト回答です。",
        )
    )

    client, session_factory = _build_client(monkeypatch, fake_openai)
    with client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "7203",
                "question": "今の注目点は何ですか？",
                "preset": "STANDARD",
            },
        )
        saved_response = client.get(f"/api/ai/analyses/{response.json()['request_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["answer_text"] == "テスト回答です。"
    assert payload["error"] is None
    assert payload["openai_response_id"] == "resp_endpoint_test"
    assert payload["security"] == {
        "security_code": "7203",
        "name": "トヨタ自動車",
        "market": "東証プライム",
    }
    assert payload["request_id"]
    assert payload["persistence_status"] == "saved"
    assert payload["saved_at"]
    assert payload["persistence_warning"] is None
    assert response.headers["cache-control"] == "no-store"
    assert len(fake_openai.calls) == 1
    assert fake_openai.calls[0]["preset"].preset_id.value == "STANDARD"
    assert '"security_code": "7203"' in fake_openai.calls[0]["input_text"]
    assert "今の注目点は何ですか？" in fake_openai.calls[0]["input_text"]
    assert "## 5. 株価反応の5層モデル" in fake_openai.calls[0]["instructions"]
    assert "共通OSに従い、この銘柄を総合分析してください。" in fake_openai.calls[0]["instructions"]
    assert "現在のポジションを起点に判断してください" not in fake_openai.calls[0]["instructions"]
    assert fake_openai.calls[0]["request_metadata"]["prompt_version"] == "2026.08.18"
    assert fake_openai.calls[0]["request_metadata"]["prompt_module"] == "3.1"
    assert "prompt_version" not in payload
    assert "あなたは、企業の良し悪しを解説するだけのAIではない" not in response.text

    assert saved_response.status_code == 200
    assert saved_response.headers["cache-control"] == "no-store"
    assert saved_response.json() == {
        "request_id": payload["request_id"],
        "status": "success",
        "saved_at": payload["saved_at"],
        "security": payload["security"],
        "question": "今の注目点は何ですか？",
        "answer_text": "テスト回答です。",
        "preset": "STANDARD",
        "model": AI_ANALYSIS_MODEL,
        "openai_response_id": "resp_endpoint_test",
    }
    with session_factory() as db:
        record = db.get(AiAnalysisRecord, payload["request_id"])
        assert record is not None
        assert record.prompt_version == "2026.08.18"
        assert record.prompt_module_id == "3.1"
        assert json.loads(record.prompt_asset_ids) == [
            "common_os@2026.08.18",
            "common_input_rules@2026.08.18-mvp1",
            "execution_constraints_no_tools@mvp1",
            "individual_comprehensive@2026.08.18",
        ]
        assert record.reasoning_effort == "medium"
        assert record.reasoning_mode is None
        assert record.text_verbosity == "medium"
        assert not hasattr(record, "api_key")
        assert not hasattr(record, "instructions")


def test_ai_analysis_endpoint_returns_typed_openai_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        error=OpenAIClientError(
            OpenAIErrorCode.TIMEOUT,
            "OpenAI APIの応答がタイムアウトしました。",
            exception_type="APITimeoutError",
        )
    )

    client, session_factory = _build_client(monkeypatch, fake_openai)
    with client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "7203",
                "question": "今の注目点は何ですか？",
                "preset": "STANDARD",
            },
        )

    assert response.status_code == 504
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["answer_text"] is None
    assert payload["persistence_status"] is None
    assert payload["saved_at"] is None
    assert payload["persistence_warning"] is None
    assert payload["error"] == {
        "code": "TIMEOUT",
        "message": "OpenAI APIの応答がタイムアウトしました。",
    }
    assert "APITimeoutError" not in response.text
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AiAnalysisRecord)) == 0


def test_ai_analysis_endpoint_rejects_unknown_security(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(response_id="unused", status="completed", output_text="unused")
    )

    client, session_factory = _build_client(monkeypatch, fake_openai)
    with client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "9999",
                "question": "確認してください。",
                "preset": "STANDARD",
            },
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SECURITY_NOT_FOUND"
    assert fake_openai.calls == []
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AiAnalysisRecord)) == 0


def test_ai_analysis_endpoint_rejects_unsupported_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(response_id="unused", status="completed", output_text="unused")
    )

    client, _ = _build_client(monkeypatch, fake_openai)
    with client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "7203",
                "question": "確認してください。",
                "preset": "HIGH",
            },
        )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert fake_openai.calls == []


class FailingRecordRepository(AiAnalysisRecordRepository):
    def save(self, *, db: Session, record_input):
        try:
            raise SQLAlchemyError("PRIVATE_DATABASE_DETAIL_MARKER")
        except SQLAlchemyError as exc:
            raise AiAnalysisPersistenceError(
                exception_type="OperationalError",
                openai_response_id=record_input.openai_response_id,
            ) from exc


def test_ai_analysis_endpoint_returns_answer_when_successful_answer_cannot_be_saved(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    question = "保存エラー時も返す質問マーカーです。"
    answer_text = "保存されない回答マーカーです。"
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(
            response_id="resp_unsaved",
            status="completed",
            output_text=answer_text,
        )
    )
    client, session_factory = _build_client(
        monkeypatch,
        fake_openai,
        record_repository=FailingRecordRepository(),
    )

    caplog.set_level("INFO")
    with client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "7203",
                "question": question,
                "preset": "STANDARD",
            },
        )
        missing = client.get(f"/api/ai/analyses/{response.json()['request_id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["answer_text"] == answer_text
    assert payload["error"] is None
    assert payload["openai_response_id"] == "resp_unsaved"
    assert payload["persistence_status"] == "failed"
    assert payload["saved_at"] is None
    assert payload["persistence_warning"] == PERSISTENCE_FAILURE_WARNING
    assert len(fake_openai.calls) == 1
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert "OperationalError" not in response.text
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AiAnalysisRecord)) == 0

    app_log = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name in {"app.services.ai_analysis", "app.api.routes.ai_analysis"}
    )
    assert "AI analysis persistence failed" in app_log
    assert "OperationalError" in app_log
    assert "PRIVATE_DATABASE_DETAIL_MARKER" not in app_log
    assert question not in app_log
    assert answer_text not in app_log
    assert "あなたは、企業の良し悪しを解説するだけのAIではない" not in app_log


def test_saved_analysis_endpoint_rejects_unknown_or_invalid_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(response_id="unused", status="completed", output_text="unused")
    )
    client, _ = _build_client(monkeypatch, fake_openai)

    with client:
        missing = client.get("/api/ai/analyses/00000000-0000-4000-8000-000000000000")
        invalid = client.get("/api/ai/analyses/not-a-uuid")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert missing.headers["cache-control"] == "no-store"
    assert invalid.status_code == 422
    assert invalid.headers["cache-control"] == "no-store"
    assert fake_openai.calls == []
