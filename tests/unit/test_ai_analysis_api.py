from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.errors import OpenAIErrorCode
from app.api.routes.ai_analysis import get_ai_analysis_service
from app.core.config import get_settings
from app.db.session import get_db, get_engine, get_session_factory
from app.integrations.openai_responses import OpenAIClientError, OpenAITextResponse
from app.main import create_app
from app.models import Base
from app.models.security import SecurityMaster
from app.services.ai_analysis import AiAnalysisService
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


def _build_client(monkeypatch: pytest.MonkeyPatch, fake_openai: FakeOpenAITextClient) -> TestClient:
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
    app.dependency_overrides[get_ai_analysis_service] = lambda: AiAnalysisService(fake_openai)
    return TestClient(app)


def test_ai_analysis_endpoint_returns_plain_text_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(
            response_id="resp_endpoint_test",
            status="completed",
            output_text="テスト回答です。",
        )
    )

    with _build_client(monkeypatch, fake_openai) as client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "7203",
                "question": "今の注目点は何ですか？",
                "preset": "STANDARD",
            },
        )

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
    assert len(fake_openai.calls) == 1
    assert fake_openai.calls[0]["preset"].preset_id.value == "STANDARD"
    assert '"security_code": "7203"' in fake_openai.calls[0]["input_text"]
    assert "今の注目点は何ですか？" in fake_openai.calls[0]["input_text"]
    assert "## 5. 株価反応の5層モデル" in fake_openai.calls[0]["instructions"]
    assert "共通OSに従い、この銘柄を総合分析してください。" in fake_openai.calls[0]["instructions"]
    assert "現在のポジションを起点に判断してください" not in fake_openai.calls[0]["instructions"]
    assert fake_openai.calls[0]["request_metadata"]["prompt_version"] == "2026.08.16"
    assert fake_openai.calls[0]["request_metadata"]["prompt_module"] == "3.1"
    assert "prompt_version" not in payload
    assert "あなたは、企業の良し悪しを解説するだけのAIではない" not in response.text


def test_ai_analysis_endpoint_returns_typed_openai_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        error=OpenAIClientError(
            OpenAIErrorCode.TIMEOUT,
            "OpenAI APIの応答がタイムアウトしました。",
            exception_type="APITimeoutError",
        )
    )

    with _build_client(monkeypatch, fake_openai) as client:
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
    assert payload["error"] == {
        "code": "TIMEOUT",
        "message": "OpenAI APIの応答がタイムアウトしました。",
    }
    assert "APITimeoutError" not in response.text


def test_ai_analysis_endpoint_rejects_unknown_security(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(response_id="unused", status="completed", output_text="unused")
    )

    with _build_client(monkeypatch, fake_openai) as client:
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


def test_ai_analysis_endpoint_rejects_unsupported_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_openai = FakeOpenAITextClient(
        result=OpenAITextResponse(response_id="unused", status="completed", output_text="unused")
    )

    with _build_client(monkeypatch, fake_openai) as client:
        response = client.post(
            "/api/ai/analyses",
            json={
                "security_code": "7203",
                "question": "確認してください。",
                "preset": "HIGH",
            },
        )

    assert response.status_code == 422
    assert fake_openai.calls == []
