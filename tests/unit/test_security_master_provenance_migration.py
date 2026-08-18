from sqlalchemy import create_engine, inspect, text

from app.db.session import _apply_security_master_provenance_migration


def test_provenance_migration_upgrades_legacy_master_and_is_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE security_master (ticker_code VARCHAR(10) PRIMARY KEY, name VARCHAR(255) NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO security_master (ticker_code, name) VALUES ('7203', 'Toyota')")
        connection.exec_driver_sql(
            """
            CREATE TABLE security_master_sync_run (
                sync_id VARCHAR(36) PRIMARY KEY,
                source VARCHAR(32),
                source_scope VARCHAR(64),
                source_as_of DATE,
                synced_at TIMESTAMP,
                complete BOOLEAN,
                fetched_count INTEGER,
                inserted_count INTEGER,
                updated_count INTEGER,
                reactivated_count INTEGER,
                deactivated_count INTEGER,
                active_total INTEGER,
                jquants_active_count INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO security_master_sync_run (
                sync_id, source, source_scope, synced_at, complete, fetched_count,
                inserted_count, updated_count, reactivated_count, deactivated_count,
                active_total, jquants_active_count
            ) VALUES (
                'legacy-run', 'jquants', 'tse_listed_issues', CURRENT_TIMESTAMP, TRUE,
                4400, 4400, 0, 0, 0, 4400, 4400
            )
            """
        )

    _apply_security_master_provenance_migration(engine)
    _apply_security_master_provenance_migration(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("security_master")}
    assert {"master_source", "source_as_of", "last_seen_sync_id"} <= columns
    run_columns = {
        column["name"] for column in inspect(engine).get_columns("security_master_sync_run")
    }
    assert {"is_current_snapshot", "adopted_legacy_count"} <= run_columns
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT master_source, source_as_of, last_seen_sync_id "
                "FROM security_master WHERE ticker_code = '7203'"
            )
        ).one()
    assert tuple(row) == ("legacy", None, None)
    with engine.connect() as connection:
        run = connection.execute(
            text(
                "SELECT is_current_snapshot, adopted_legacy_count "
                "FROM security_master_sync_run WHERE sync_id = 'legacy-run'"
            )
        ).one()
    assert bool(run.is_current_snapshot) is True
    assert run.adopted_legacy_count == 0
