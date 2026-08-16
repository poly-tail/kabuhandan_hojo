from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_minimal_analysis_ui_shell_is_served(monkeypatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    get_settings.cache_clear()

    try:
        with TestClient(create_app()) as client:
            response = client.get("/ui/analysis")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert 'id="security-query"' in response.text
    assert 'id="security-search-results"' in response.text
    assert 'id="selected-security"' in response.text
    assert 'id="question"' in response.text
    assert 'id="submit-analysis"' in response.text
    assert 'id="analysis-status"' in response.text
    assert 'id="analysis-error"' in response.text
    assert 'id="answer-text"' in response.text
    assert "white-space: pre-wrap" in response.text
    assert "/securities/search?q=" in response.text
    assert 'fetch("/api/ai/analyses"' in response.text
    assert 'preset: "STANDARD"' in response.text
    assert "answerElement.textContent = answerText" in response.text
    assert "innerHTML" not in response.text
    assert "OPENAI_API_KEY" not in response.text

