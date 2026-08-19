from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as app_main
import app.api.routes.watchlist as watchlist_routes
from app.core.config import get_settings
from app.db.session import (
    _apply_watchlist_collections_migration,
    get_db,
    get_engine,
    get_session_factory,
)
from app.models import Base
from app.models.security import SecurityMaster
from app.models.watchlist import Watchlist, WatchlistCollection, WatchlistMembership
from app.schemas.watchlist import WatchlistCollectionCreate, WatchlistCreate
from app.services.watchlist import WatchlistService
from kabuhandan_hojo.models import Base as MonitoringBase
from app.services.mock_watchlist import MockWatchlistService


@pytest.fixture(autouse=True)
def clear_settings() -> Generator[None, None, None]:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture
def live_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("APP_USE_MOCK", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(app_main, "init_db", lambda: None)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MonitoringBase.metadata.create_all(engine)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    application = app_main.create_app()
    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as client:
        yield client


def test_named_watchlist_api_preserves_legacy_default_and_scopes_memberships(
    live_client: TestClient,
) -> None:
    legacy_create = live_client.post(
        "/watchlist",
        json={
            "ticker_code": "7203",
            "name": "Toyota",
            "memo": "shared memo",
            "thesis_bull": "shared bull",
            "sort_order": 7,
        },
    )
    assert legacy_create.status_code == 201
    default_item = legacy_create.json()
    default_id = default_item["collection_id"]

    create_collection = live_client.post(
        "/watchlists",
        json={"name": "半導体", "sort_order": 20},
    )
    assert create_collection.status_code == 201
    named_id = create_collection.json()["id"]

    named_add = live_client.post(
        f"/watchlists/{named_id}/items",
        json={"ticker_code": "7203", "sort_order": 3},
    )
    assert named_add.status_code == 201
    assert named_add.json()["memo"] == "shared memo"
    assert named_add.json()["thesis_bull"] == "shared bull"
    assert named_add.json()["sort_order"] == 3

    collections = live_client.get("/watchlists").json()
    assert collections[0]["id"] == default_id
    assert collections[0]["is_default"] is True
    assert {item["name"]: item["item_count"] for item in collections} == {
        "メイン": 1,
        "半導体": 1,
    }

    remove_named = live_client.delete(f"/watchlists/{named_id}/items/7203")
    assert remove_named.status_code == 204
    assert live_client.get(f"/watchlists/{named_id}/items").json() == []
    assert [item["ticker_code"] for item in live_client.get("/watchlist").json()] == ["7203"]


def test_collection_names_are_nfkc_trim_casefold_unique_and_default_is_not_deletable(
    live_client: TestClient,
) -> None:
    created = live_client.post("/watchlists", json={"name": "  ＴＥＣＨ  "})
    assert created.status_code == 201
    collection_id = created.json()["id"]
    assert created.json()["name"] == "TECH"

    duplicate = live_client.post("/watchlists", json={"name": "tech"})
    assert duplicate.status_code == 409

    nfkc_expansion = live_client.post("/watchlists", json={"name": "㍿" * 21})
    assert nfkc_expansion.status_code == 422

    renamed = live_client.patch(
        f"/watchlists/{collection_id}",
        json={"name": "成長株"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "成長株"

    default_id = live_client.get("/watchlists").json()[0]["id"]
    assert live_client.delete(f"/watchlists/{default_id}").status_code == 409
    assert live_client.get("/watchlists/999999/items").status_code == 404

    assert live_client.delete(f"/watchlists/{collection_id}").status_code == 204
    assert live_client.get(f"/watchlists/{collection_id}/items").status_code == 404


def test_search_membership_is_scoped_without_duplicate_security_rows(
    live_client: TestClient,
) -> None:
    first = live_client.post("/watchlists", json={"name": "一軍"}).json()
    second = live_client.post("/watchlists", json={"name": "二軍"}).json()
    for collection in (first, second):
        response = live_client.post(
            f"/watchlists/{collection['id']}/items",
            json={"ticker_code": "7203", "name": "Toyota"},
        )
        assert response.status_code == 201

    first_search = live_client.get(
        "/securities/search",
        params={"q": "Toyota", "watchlist_id": first["id"]},
    )
    assert first_search.status_code == 200
    assert [item["ticker_code"] for item in first_search.json()] == ["7203"]
    assert first_search.json()[0]["in_watchlist"] is True

    default_search = live_client.get("/securities/search", params={"q": "Toyota"})
    assert default_search.status_code == 200
    assert [item["ticker_code"] for item in default_search.json()] == ["7203"]
    assert default_search.json()[0]["in_watchlist"] is False


def test_initial_migration_backfills_once_and_does_not_leak_named_only_items_to_default() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SecurityMaster(ticker_code="7203", name="Toyota", is_active=True))
        session.add(
            Watchlist(
                ticker_code="7203",
                memo="legacy",
                sort_order=9,
                is_active=True,
            )
        )
        session.commit()

    _apply_watchlist_collections_migration(engine)
    _apply_watchlist_collections_migration(engine)

    with Session(engine) as session:
        default = session.scalar(
            select(WatchlistCollection).where(WatchlistCollection.system_key == "default")
        )
        assert default is not None
        assert session.scalar(
            select(func.count(WatchlistMembership.id)).where(
                WatchlistMembership.collection_id == default.id
            )
        ) == 1

        service = WatchlistService()
        named = service.create_collection(session, WatchlistCollectionCreate(name="追加候補"))
        service.create_item(
            session,
            WatchlistCreate(ticker_code="6758", name="Sony"),
            collection_id=named.id,
        )

    _apply_watchlist_collections_migration(engine)

    with Session(engine) as session:
        default = session.scalar(
            select(WatchlistCollection).where(WatchlistCollection.system_key == "default")
        )
        default_tickers = list(
            session.scalars(
                select(Watchlist.ticker_code)
                .join(
                    WatchlistMembership,
                    WatchlistMembership.watchlist_item_id == Watchlist.id,
                )
                .where(WatchlistMembership.collection_id == default.id)
            ).all()
        )
        assert default_tickers == ["7203"]


def test_named_watchlist_ai_review_uses_only_selected_collection_and_empty_stays_empty(
    live_client: TestClient,
) -> None:
    selected = live_client.post("/watchlists", json={"name": "AI対象"}).json()
    empty = live_client.post("/watchlists", json={"name": "空リスト"}).json()
    added = live_client.post(
        f"/watchlists/{selected['id']}/items",
        json={"ticker_code": "8035", "name": "Tokyo Electron"},
    )
    assert added.status_code == 201

    reviewed = live_client.post(
        "/api/ai/stock-review",
        json={
            "mode": "scanner",
            "target": "watchlist",
            "watchlist_id": selected["id"],
            "mock_response": True,
            "include_web_search": False,
            "save_result": False,
            "use_cache": False,
        },
    )
    assert reviewed.status_code == 200
    payload = reviewed.json()
    assert payload["status"] == "success"
    assert payload["holdings_source"] == "watchlist"
    assert [item["ticker"] for item in payload["holdings_snapshot"]] == ["8035"]
    assert payload["request_payload"]["watchlist_id"] == selected["id"]

    empty_review = live_client.post(
        "/api/ai/stock-review",
        json={
            "mode": "scanner",
            "target": "watchlist",
            "watchlist_id": empty["id"],
            "mock_response": True,
            "include_web_search": False,
            "save_result": False,
            "use_cache": False,
        },
    )
    assert empty_review.status_code == 200
    empty_payload = empty_review.json()
    assert empty_payload["status"] == "no_holdings"
    assert empty_payload["holdings_source"] == "watchlist"
    assert empty_payload["holdings_snapshot"] == []


def test_mock_mode_supports_named_watchlist_crud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_USE_MOCK", "true")
    monkeypatch.setattr(app_main, "init_db", lambda: None)
    monkeypatch.setattr(watchlist_routes, "mock_service", MockWatchlistService())
    get_settings.cache_clear()

    with TestClient(app_main.create_app()) as client:
        created = client.post("/watchlists", json={"name": "Mock追加"})
        assert created.status_code == 201
        collection_id = created.json()["id"]

        added = client.post(
            f"/watchlists/{collection_id}/items",
            json={"ticker_code": "7203"},
        )
        assert added.status_code == 201
        assert added.json()["collection_id"] == collection_id
        assert [
            item["ticker_code"]
            for item in client.get(f"/watchlists/{collection_id}/items").json()
        ] == ["7203"]

        assert client.delete(f"/watchlists/{collection_id}/items/7203").status_code == 204
        assert client.delete(f"/watchlists/{collection_id}").status_code == 204
