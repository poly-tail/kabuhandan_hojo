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
    assert 'id="analysis-persistence-warning"' in response.text
    assert 'id="analysis-saved-status"' in response.text
    assert 'id="open-saved-analysis"' in response.text
    assert 'target="_blank"' in response.text
    assert 'rel="noopener noreferrer"' in response.text
    assert "openSavedAnalysisLink.removeAttribute(\"href\")" in response.text
    assert "/ui/analysis/results/${encodeURIComponent(requestId)}" in response.text
    assert 'payload.persistence_status === "saved" && requestId' in response.text
    assert 'persistenceWarningElement.hidden = false' in response.text
    assert "回答は生成されましたが、ローカルDBへ保存できませんでした。大画面での再表示は利用できません。" in response.text
    assert 'savedStatusElement.hidden = false' in response.text
    assert "white-space: pre-wrap" in response.text
    assert "/securities/search?q=" in response.text
    assert 'fetch("/api/ai/analyses"' in response.text
    assert 'preset: "STANDARD"' in response.text
    assert "answerElement.textContent = answerText" in response.text
    assert "queryInput.disabled = isSubmitting" in response.text
    assert "questionInput.disabled = isSubmitting" in response.text
    assert "searchButton.disabled = isSubmitting || isSearching" in response.text
    assert 'button.disabled = isSubmitting' in response.text
    assert "if (isSubmitting || isSearching)" in response.text
    assert "innerHTML" not in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_saved_analysis_reader_shell_is_large_plain_text_and_no_store(monkeypatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    get_settings.cache_clear()
    request_id = "00000000-0000-4000-8000-000000000123"

    try:
        with TestClient(create_app()) as client:
            response = client.get(f"/ui/analysis/results/{request_id}")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert 'id="saved-analysis-status"' in response.text
    assert 'id="saved-analysis-error"' in response.text
    assert 'id="saved-analysis-content"' in response.text
    assert 'id="saved-question"' in response.text
    assert 'id="saved-answer"' in response.text
    assert "width: min(1380px, 100%)" in response.text
    assert "white-space: pre-wrap" in response.text
    assert f'const requestId = "{request_id}"' in response.text
    assert "/api/ai/analyses/${encodeURIComponent(requestId)}" in response.text
    assert 'cache: "no-store"' in response.text
    assert "questionElement.textContent = questionText" in response.text
    assert "answerElement.textContent = answerText" in response.text
    assert "innerHTML" not in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
