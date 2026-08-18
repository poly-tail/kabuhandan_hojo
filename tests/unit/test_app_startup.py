from fastapi.testclient import TestClient

import app.main as app_main


def test_database_initialization_runs_once_in_lifespan(monkeypatch) -> None:
    calls: list[None] = []

    def fake_init_db() -> None:
        calls.append(None)

    monkeypatch.setattr(app_main, "init_db", fake_init_db)

    app = app_main.create_app()
    assert calls == []

    with TestClient(app):
        assert len(calls) == 1

    assert len(calls) == 1
