import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.security_master_catalog import LocalSecurityMasterCatalog
from kabuhandan_hojo.connectors.base import ConnectorError, ListedIssueRecord
from kabuhandan_hojo.models import Base as MonitoringBase
from kabuhandan_hojo.models.entities import SecurityMaster, SecurityMasterSyncRun, Watchlist
from kabuhandan_hojo.services.ingestion import DEFAULT_MIN_COMPLETE_MASTER_RECORDS, IngestionService


class FakeJQuantsConnector:
    def __init__(self, records: list[ListedIssueRecord]) -> None:
        self.records = records
        self.calls = 0

    async def fetch_listed_issues(self, as_of: date | None = None) -> list[ListedIssueRecord]:
        self.calls += 1
        return list(self.records)


def _issue(code: str, *, source_as_of: date, name: str | None = None) -> ListedIssueRecord:
    return ListedIssueRecord(
        ticker_code=code,
        local_code=f"{code}0" if code.isdigit() and len(code) == 4 else code,
        name=name or f"Issue {code}",
        name_english=None,
        market="Prime",
        industry_17=None,
        industry_33=None,
        listed_date=None,
        source_as_of=source_as_of,
    )


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MonitoringBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory() as session:
        yield session


def _service(records: list[ListedIssueRecord], *, minimum: int = 2) -> tuple[IngestionService, FakeJQuantsConnector]:
    connector = FakeJQuantsConnector(records)
    container = SimpleNamespace(jquants_connector=connector)
    return IngestionService(container, minimum_complete_master_records=minimum), connector


def test_current_full_snapshot_upserts_reactivates_and_deactivates_only_explicit_jquants(db_session) -> None:
    snapshot_date = date(2026, 5, 26)
    db_session.add_all(
        [
            SecurityMaster(ticker_code="7203", local_code="72030", name="Old", is_active=False, master_source="jquants"),
            SecurityMaster(ticker_code="9999", local_code="99990", name="Gone", is_active=True, master_source="jquants"),
            SecurityMaster(ticker_code="1111", local_code="11110", name="Legacy", is_active=True, master_source="legacy"),
            SecurityMaster(ticker_code="2222", local_code="22220", name="Seed", is_active=True, master_source="local_seed"),
        ]
    )
    db_session.flush()
    service, connector = _service([_issue("7203", source_as_of=snapshot_date), _issue("285A0", source_as_of=snapshot_date)])

    result = asyncio.run(service.sync_security_master_from_jquants(db_session))

    assert connector.calls == 1
    assert result.complete is True
    assert result.is_current_snapshot is True
    assert result.fetched_count == 2
    assert result.inserted_count == 1
    assert result.updated_count == 1
    assert result.reactivated_count == 1
    assert result.deactivated_count == 1
    assert result.active_total == 4
    assert result.jquants_active_count == 2
    assert result.source_as_of == snapshot_date
    assert db_session.get(SecurityMaster, "9999").is_active is False
    assert db_session.get(SecurityMaster, "1111").is_active is True
    assert db_session.get(SecurityMaster, "2222").master_source == "local_seed"

    status = service.get_security_master_status(db_session)
    assert status.complete is True
    assert status.sync_id == result.sync_id
    assert status.source_as_of == snapshot_date


def test_incomplete_current_snapshot_raises_before_database_mutation(db_session) -> None:
    original = SecurityMaster(
        ticker_code="7203",
        local_code="72030",
        name="Original",
        is_active=True,
        master_source="jquants",
    )
    db_session.add(original)
    db_session.flush()
    service, connector = _service([_issue("7203", source_as_of=date(2026, 5, 26), name="Changed")])

    with pytest.raises(ConnectorError, match="incomplete"):
        asyncio.run(service.sync_security_master_from_jquants(db_session))

    assert connector.calls == 1
    assert original.name == "Original"
    assert db_session.scalar(select(func.count()).select_from(SecurityMasterSyncRun)) == 0


def test_production_master_completeness_floor_is_full_market_sized() -> None:
    assert DEFAULT_MIN_COMPLETE_MASTER_RECORDS == 4_000


def test_current_snapshot_rejects_coherent_large_shrink_before_database_mutation(db_session) -> None:
    snapshot_date = date(2026, 5, 26)
    existing = [
        SecurityMaster(
            ticker_code=str(1000 + index),
            local_code=f"{1000 + index}0",
            name=f"Original {index}",
            is_active=True,
            master_source="jquants",
        )
        for index in range(20)
    ]
    db_session.add_all(existing)
    db_session.flush()
    service, connector = _service(
        [_issue(str(1000 + index), source_as_of=snapshot_date, name=f"Changed {index}") for index in range(18)]
    )

    with pytest.raises(ConnectorError, match="shrank beyond the safe threshold"):
        asyncio.run(service.sync_security_master_from_jquants(db_session))

    assert connector.calls == 1
    assert existing[0].name == "Original 0"
    assert all(security.is_active for security in existing)
    assert db_session.scalar(select(func.count()).select_from(SecurityMasterSyncRun)) == 0


def test_current_snapshot_requires_explicit_dominant_legacy_reconciliation_before_mutation(db_session) -> None:
    bad_snapshot_date = date(2026, 1, 30)
    existing = [
        SecurityMaster(
            ticker_code="7203",
            local_code="72030",
            name="Original Toyota",
            listed_date=bad_snapshot_date,
            is_active=True,
            master_source="legacy",
        ),
        SecurityMaster(
            ticker_code="8306",
            local_code="83060",
            name="Original MUFG",
            listed_date=bad_snapshot_date,
            is_active=True,
            master_source="legacy",
        ),
    ]
    db_session.add_all(existing)
    db_session.flush()
    service, connector = _service(
        [
            _issue("7203", source_as_of=date(2026, 5, 26), name="Changed Toyota"),
            _issue("8306", source_as_of=date(2026, 5, 26), name="Changed MUFG"),
        ]
    )

    with pytest.raises(ConnectorError, match="--adopt-legacy"):
        asyncio.run(service.sync_security_master_from_jquants(db_session))

    assert connector.calls == 1
    assert existing[0].name == "Original Toyota"
    assert existing[0].master_source == "legacy"
    assert db_session.scalar(select(func.count()).select_from(SecurityMasterSyncRun)) == 0


def test_repeating_same_current_snapshot_is_idempotent(db_session) -> None:
    snapshot_date = date(2026, 5, 26)
    records = [_issue("7203", source_as_of=snapshot_date), _issue("8306", source_as_of=snapshot_date)]
    service, connector = _service(records)

    first = asyncio.run(service.sync_security_master_from_jquants(db_session))
    second = asyncio.run(service.sync_security_master_from_jquants(db_session))

    assert connector.calls == 2
    assert first.inserted_count == 2
    assert second.inserted_count == 0
    assert second.updated_count == 2
    assert second.reactivated_count == 0
    assert second.deactivated_count == 0
    assert second.active_total == 2
    assert db_session.scalar(select(func.count()).select_from(SecurityMaster)) == 2


def test_current_snapshot_repairs_legacy_ordinary_preferred_code_collision(db_session) -> None:
    snapshot_date = date(2026, 5, 26)
    db_session.add(
        SecurityMaster(
            ticker_code="2593",
            local_code="25935",
            name="伊藤園（優先株式）",
            is_active=True,
            master_source="legacy",
        )
    )
    db_session.commit()
    service, _ = _service(
        [
            _issue("2593", source_as_of=snapshot_date, name="伊藤園"),
            _issue("25935", source_as_of=snapshot_date, name="伊藤園第1種優先株式"),
        ]
    )

    result = asyncio.run(service.sync_security_master_from_jquants(db_session))

    ordinary = db_session.get(SecurityMaster, "2593")
    preferred = db_session.get(SecurityMaster, "25935")
    assert result.complete is True
    assert result.updated_count == 1
    assert result.inserted_count == 1
    assert ordinary is not None
    assert ordinary.local_code == "25930"
    assert ordinary.name == "伊藤園"
    assert ordinary.is_active is True
    assert ordinary.master_source == "jquants"
    assert preferred is not None
    assert preferred.local_code == "25935"
    assert preferred.name == "伊藤園第1種優先株式"
    assert preferred.is_active is True
    assert preferred.master_source == "jquants"


def test_current_snapshot_rejects_referenced_code_collision_before_mutation(db_session) -> None:
    snapshot_date = date(2026, 5, 26)
    existing = SecurityMaster(
        ticker_code="2593",
        local_code="25935",
        name="Legacy preferred identity",
        is_active=True,
        # A prior partial sync may already have relabelled this row.  The guard
        # must depend on the identity transition, not this provenance value.
        master_source="jquants",
    )
    db_session.add(existing)
    db_session.flush()
    db_session.add(Watchlist(ticker_code="2593", memo="must remain attached"))
    # Commit before schema inspection. The in-memory SQLite fixture uses one
    # StaticPool connection, so Inspector's temporary connection must not roll
    # back the setup transaction it is about to inspect.
    db_session.commit()
    service, connector = _service(
        [
            _issue("2593", source_as_of=snapshot_date, name="Ordinary"),
            _issue("25935", source_as_of=snapshot_date, name="Preferred"),
        ]
    )

    with pytest.raises(ConnectorError, match="dependent records"):
        asyncio.run(service.sync_security_master_from_jquants(db_session))

    assert connector.calls == 1
    assert existing.local_code == "25935"
    assert existing.name == "Legacy preferred identity"
    assert db_session.get(SecurityMaster, "25935") is None
    assert db_session.scalar(select(func.count()).select_from(SecurityMasterSyncRun)) == 0


def test_historical_snapshot_is_complete_without_deactivating_current_rows_or_replacing_status(db_session) -> None:
    current_date = date(2026, 5, 26)
    current_service, _ = _service(
        [_issue("7203", source_as_of=current_date), _issue("8306", source_as_of=current_date)]
    )
    current_result = asyncio.run(current_service.sync_security_master_from_jquants(db_session))

    historical_date = date(2026, 1, 30)
    historical_service, _ = _service(
        [_issue("7203", source_as_of=historical_date), _issue("9999", source_as_of=historical_date)]
    )
    historical_result = asyncio.run(
        historical_service.sync_security_master_from_jquants(db_session, as_of=historical_date)
    )

    assert historical_result.complete is True
    assert historical_result.is_current_snapshot is False
    assert historical_result.deactivated_count == 0
    assert db_session.get(SecurityMaster, "8306").is_active is True
    assert db_session.get(SecurityMaster, "9999").is_active is False
    status = historical_service.get_security_master_status(db_session)
    assert status.sync_id == current_result.sync_id
    assert status.source_as_of == current_date


def test_explicit_legacy_adoption_repairs_only_dominant_legacy_snapshot_date(db_session) -> None:
    bad_snapshot_date = date(2026, 1, 30)
    db_session.add_all(
        [
            SecurityMaster(ticker_code="7203", name="Legacy match", listed_date=bad_snapshot_date, master_source="legacy"),
            SecurityMaster(ticker_code="9999", name="Legacy gone", listed_date=bad_snapshot_date, master_source="legacy"),
            SecurityMaster(ticker_code="4444", name="Genuine legacy", listed_date=date(2001, 1, 1), master_source="legacy"),
            SecurityMaster(ticker_code="1111", name="Manual", listed_date=bad_snapshot_date, master_source="manual"),
        ]
    )
    db_session.flush()
    source_date = date(2026, 5, 26)
    service, _ = _service([_issue("7203", source_as_of=source_date), _issue("8306", source_as_of=source_date)])

    result = asyncio.run(service.sync_security_master_from_jquants(db_session, adopt_legacy=True))

    assert result.adopted_legacy_count == 1
    assert db_session.get(SecurityMaster, "7203").listed_date is None
    assert db_session.get(SecurityMaster, "9999").listed_date is None
    assert db_session.get(SecurityMaster, "9999").is_active is False
    assert db_session.get(SecurityMaster, "4444").master_source == "legacy"
    assert db_session.get(SecurityMaster, "4444").is_active is True
    assert db_session.get(SecurityMaster, "4444").listed_date == date(2001, 1, 1)
    assert db_session.get(SecurityMaster, "1111").listed_date == bad_snapshot_date
    assert db_session.get(SecurityMaster, "1111").master_source == "manual"


def test_local_seed_is_insert_only_and_never_overwrites_jquants(db_session) -> None:
    catalog = LocalSecurityMasterCatalog()
    seed_records = catalog.load()
    assert seed_records
    protected = seed_records[0]
    db_session.add(
        SecurityMaster(
            ticker_code=protected.ticker_code,
            local_code=protected.local_code,
            name="Authoritative provider value",
            is_active=False,
            master_source="jquants",
        )
    )
    db_session.flush()

    inserted = catalog.sync_to_db(db_session)

    assert inserted == len(seed_records) - 1
    assert db_session.get(SecurityMaster, protected.ticker_code).name == "Authoritative provider value"
    assert db_session.get(SecurityMaster, protected.ticker_code).is_active is False
    inserted_seed = next(record for record in seed_records if record.ticker_code != protected.ticker_code)
    assert db_session.get(SecurityMaster, inserted_seed.ticker_code).master_source == "local_seed"
