import argparse
import asyncio
from datetime import date, datetime, timezone

from kabuhandan_hojo.connectors.base import ConnectorError
from kabuhandan_hojo.services.ingestion import SecurityMasterSyncResult
from scripts import sync_security_master as script


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _result() -> SecurityMasterSyncResult:
    return SecurityMasterSyncResult(
        fetched_count=4443,
        inserted_count=4400,
        updated_count=43,
        reactivated_count=0,
        deactivated_count=0,
        active_total=4443,
        jquants_active_count=4443,
        source="jquants",
        source_scope="tse_listed_issues",
        source_as_of=date(2026, 5, 26),
        sync_id="safe-sync-id",
        synced_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
        complete=True,
        is_current_snapshot=True,
    )


def test_script_dry_run_rolls_back_and_prints_only_safe_statistics(monkeypatch, capsys) -> None:
    session = FakeSession()

    class FakeService:
        def __init__(self, container) -> None:
            pass

        async def sync_security_master_from_jquants(self, db, *, as_of=None, adopt_legacy=False):
            assert db is session
            assert as_of is None
            assert adopt_legacy is False
            return _result()

    monkeypatch.setattr(script, "init_db", lambda: None)
    monkeypatch.setattr(script, "get_monitoring_container", lambda: object())
    monkeypatch.setattr(script, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(script, "IngestionService", FakeService)

    exit_code = asyncio.run(script._run(argparse.Namespace(as_of=None, adopt_legacy=False, dry_run=True)))
    output = capsys.readouterr().out

    assert exit_code == 0
    assert session.rolled_back is True
    assert session.committed is False
    assert '"fetched_count": 4443' in output
    assert '"dry_run": true' in output


def test_script_connector_failure_does_not_echo_provider_detail(monkeypatch, capsys) -> None:
    session = FakeSession()

    class FakeService:
        def __init__(self, container) -> None:
            pass

        async def sync_security_master_from_jquants(self, db, *, as_of=None, adopt_legacy=False):
            raise ConnectorError("provider detail containing secret-token")

    monkeypatch.setattr(script, "init_db", lambda: None)
    monkeypatch.setattr(script, "get_monitoring_container", lambda: object())
    monkeypatch.setattr(script, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(script, "IngestionService", FakeService)

    exit_code = asyncio.run(script._run(argparse.Namespace(as_of=None, adopt_legacy=False, dry_run=False)))
    output = capsys.readouterr().out

    assert exit_code == 1
    assert session.rolled_back is True
    assert "secret-token" not in output
    assert "J-Quants master synchronization failed" in output


def test_script_rejects_legacy_adoption_for_historical_snapshot(capsys) -> None:
    exit_code = asyncio.run(
        script._run(argparse.Namespace(as_of=date(2026, 1, 30), adopt_legacy=True, dry_run=True))
    )

    assert exit_code == 2
    assert "requires a current snapshot" in capsys.readouterr().out
