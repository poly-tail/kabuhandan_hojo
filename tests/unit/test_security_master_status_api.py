from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.api.routes.monitoring as monitoring_routes
from app.core.config import get_settings
from app.db.session import get_db, get_engine, get_session_factory
from app.main import create_app
from app.services.monitoring_runtime import get_monitoring_container, get_monitoring_settings
from kabuhandan_hojo.connectors.base import MissingCredentialsError


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


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@dataclass
class FakeStatus:
    active_total: int = 4_430
    jquants_active_count: int = 4_430
    source: str = "jquants"
    source_scope: str = "tse_listed_issues"
    source_as_of: date | None = date(2026, 8, 18)
    sync_id: str | None = "sync-test"
    synced_at: datetime | None = datetime(2026, 8, 18, 9, 30, tzinfo=timezone.utc)
    complete: bool = True


@dataclass
class FakeSyncResult(FakeStatus):
    fetched_count: int = 4_430
    inserted_count: int = 100
    updated_count: int = 4_330
    reactivated_count: int = 10
    deactivated_count: int = 2

    @property
    def upserted_count(self) -> int:
        return self.inserted_count + self.updated_count


class FakeIngestionService:
    def __init__(self, *, status_snapshot: FakeStatus | None = None, sync_result: FakeSyncResult | None = None) -> None:
        self.status_snapshot = status_snapshot or FakeStatus()
        self.sync_result = sync_result or FakeSyncResult()
        self.sync_calls = 0
        self.requested_as_of: date | None = None

    def get_security_master_status(self, session: DummySession) -> FakeStatus:
        return self.status_snapshot

    async def sync_security_master_from_jquants(
        self,
        session: DummySession,
        *,
        as_of: date | None = None,
    ) -> FakeSyncResult:
        self.sync_calls += 1
        self.requested_as_of = as_of
        return self.sync_result


def _build_client(monkeypatch: pytest.MonkeyPatch, service: object, session: DummySession) -> TestClient:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(monitoring_routes, "_build_ingestion_service", lambda: service)
    app = create_app()

    def override_get_db() -> Generator[DummySession, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_security_master_status_reports_scope_count_and_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession()
    service = FakeIngestionService()

    with _build_client(monkeypatch, service, session) as client:
        response = client.get("/securities/master/status")

    assert response.status_code == 200
    assert response.json() == {
        "source": "jquants",
        "source_scope": "tse_listed_issues",
        "source_as_of": "2026-08-18",
        "sync_id": "sync-test",
        "synced_at": "2026-08-18T09:30:00Z",
        "complete": True,
        "active_total": 4430,
        "jquants_active_count": 4430,
    }


def test_security_master_status_reports_fresh_install_as_incomplete_without_claiming_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = DummySession()
    service = FakeIngestionService(
        status_snapshot=FakeStatus(
            active_total=36,
            jquants_active_count=0,
            source_as_of=None,
            sync_id=None,
            synced_at=None,
            complete=False,
        )
    )

    with _build_client(monkeypatch, service, session) as client:
        response = client.get("/securities/master/status")

    assert response.status_code == 200
    assert response.json() == {
        "source": "jquants",
        "source_scope": "tse_listed_issues",
        "source_as_of": None,
        "sync_id": None,
        "synced_at": None,
        "complete": False,
        "active_total": 36,
        "jquants_active_count": 0,
    }


def test_security_master_sync_reports_fetch_and_persistence_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession()
    service = FakeIngestionService()

    with _build_client(monkeypatch, service, session) as client:
        response = client.post("/securities/master/sync?require_jquants=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["complete"] is True
    assert payload["source"] == "jquants"
    assert payload["source_scope"] == "tse_listed_issues"
    assert payload["source_as_of"] == "2026-08-18"
    assert payload["fetched_count"] == 4430
    assert payload["upserted_count"] == 4430
    assert payload["inserted_count"] == 100
    assert payload["updated_count"] == 4330
    assert payload["reactivated_count"] == 10
    assert payload["deactivated_count"] == 2
    assert payload["active_total"] == 4430
    assert payload["jquants_active_count"] == 4430
    assert service.sync_calls == 1
    assert session.commits == 1
    assert session.rollbacks == 0


def test_required_security_master_sync_keeps_missing_key_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession()

    class MissingKeyService(FakeIngestionService):
        async def sync_security_master_from_jquants(self, session, *, as_of=None):
            raise MissingCredentialsError("J-Quants API key is not configured.")

    with _build_client(monkeypatch, MissingKeyService(), session) as client:
        response = client.post("/securities/master/sync?require_jquants=true")

    assert response.status_code == 400
    assert "JQUANTS_API_KEY" in response.json()["detail"]
    assert session.commits == 0
    assert session.rollbacks == 1


def test_optional_security_master_sync_reports_bundled_seed_as_incomplete_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = DummySession()

    class MissingKeyService(FakeIngestionService):
        async def sync_security_master_from_jquants(self, session, *, as_of=None):
            raise MissingCredentialsError("J-Quants API key is not configured.")

    monkeypatch.setattr(monitoring_routes.local_security_master_catalog, "load", lambda: [object()] * 36)
    monkeypatch.setattr(
        monitoring_routes.local_security_master_catalog,
        "sync_to_db",
        lambda _session: 5,
    )

    with _build_client(monkeypatch, MissingKeyService(), session) as client:
        response = client.post("/securities/master/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local_seed"
    assert payload["source_scope"] == "bundled_search_seed_only"
    assert payload["complete"] is False
    assert payload["fetched_count"] == 36
    assert payload["inserted_count"] == 5
    assert payload["updated_count"] == 0
    assert payload["upserted_count"] == 5
    assert payload["processed_count"] == 5
    assert "api_key" not in payload
    assert session.commits == 1
    assert session.rollbacks == 0


def test_required_security_master_sync_rejects_incomplete_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession()
    result = FakeSyncResult(fetched_count=0, complete=False, active_total=0, jquants_active_count=0)
    service = FakeIngestionService(sync_result=result)

    with _build_client(monkeypatch, service, session) as client:
        response = client.post("/securities/master/sync?require_jquants=true")

    assert response.status_code == 400
    assert "complete, non-empty snapshot" in response.json()["detail"]
    assert service.sync_calls == 1
    assert session.commits == 0
    assert session.rollbacks == 1


def test_historical_security_master_sync_accepts_incomplete_result_without_current_deactivation_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = DummySession()
    target_date = date(2026, 8, 15)
    result = FakeSyncResult(
        source_as_of=target_date,
        fetched_count=900,
        inserted_count=25,
        updated_count=875,
        complete=False,
        deactivated_count=0,
    )
    service = FakeIngestionService(sync_result=result)

    with _build_client(monkeypatch, service, session) as client:
        response = client.post(
            "/securities/master/sync",
            params={"require_jquants": "true", "target_date": target_date.isoformat()},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["complete"] is False
    assert payload["source_as_of"] == target_date.isoformat()
    assert payload["deactivated_count"] == 0
    assert "historical (2026-08-15)" in payload["detail"]
    assert service.requested_as_of == target_date
    assert session.commits == 1
    assert session.rollbacks == 0


def test_required_historical_security_master_sync_still_rejects_zero_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = DummySession()
    target_date = date(2026, 8, 15)
    service = FakeIngestionService(
        sync_result=FakeSyncResult(
            source_as_of=target_date,
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            complete=False,
            active_total=0,
            jquants_active_count=0,
        )
    )

    with _build_client(monkeypatch, service, session) as client:
        response = client.post(
            "/securities/master/sync",
            params={"require_jquants": "true", "target_date": target_date.isoformat()},
        )

    assert response.status_code == 400
    assert service.requested_as_of == target_date
    assert session.commits == 0
    assert session.rollbacks == 1
