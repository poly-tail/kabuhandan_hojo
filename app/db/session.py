"""SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from pathlib import Path
import unicodedata

from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.base import Base


def _prepare_sqlite_path(database_url: str) -> None:
    url: URL = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return
    database = url.database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


def _apply_sqlite_compat_migrations(engine) -> None:
    """Patch legacy SQLite tables forward when create_all cannot alter them."""

    if engine.dialect.name != "sqlite":
        return

    compatibility_columns: dict[str, list[tuple[str, str]]] = {
        "security_master": [
            ("local_code", "ALTER TABLE security_master ADD COLUMN local_code VARCHAR(10)"),
            ("name_english", "ALTER TABLE security_master ADD COLUMN name_english VARCHAR(255)"),
            ("industry_17", "ALTER TABLE security_master ADD COLUMN industry_17 VARCHAR(100)"),
            ("industry_33", "ALTER TABLE security_master ADD COLUMN industry_33 VARCHAR(100)"),
        ],
        "watchlist": [
            ("thesis_bull", "ALTER TABLE watchlist ADD COLUMN thesis_bull TEXT"),
            ("thesis_bear", "ALTER TABLE watchlist ADD COLUMN thesis_bear TEXT"),
            ("sort_order", "ALTER TABLE watchlist ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 100"),
            ("last_reviewed_at", "ALTER TABLE watchlist ADD COLUMN last_reviewed_at DATETIME"),
        ],
        "flow_snapshot": [
            ("margin_buy_balance", "ALTER TABLE flow_snapshot ADD COLUMN margin_buy_balance NUMERIC(18, 2)"),
            ("margin_sell_balance", "ALTER TABLE flow_snapshot ADD COLUMN margin_sell_balance NUMERIC(18, 2)"),
            ("credit_ratio", "ALTER TABLE flow_snapshot ADD COLUMN credit_ratio NUMERIC(8, 4)"),
            ("buy_balance_change_wow", "ALTER TABLE flow_snapshot ADD COLUMN buy_balance_change_wow NUMERIC(8, 4)"),
            ("sell_balance_change_wow", "ALTER TABLE flow_snapshot ADD COLUMN sell_balance_change_wow NUMERIC(8, 4)"),
            ("buy_balance_to_volume", "ALTER TABLE flow_snapshot ADD COLUMN buy_balance_to_volume NUMERIC(12, 4)"),
            ("sell_balance_to_volume", "ALTER TABLE flow_snapshot ADD COLUMN sell_balance_to_volume NUMERIC(12, 4)"),
            (
                "squeeze_potential_subscore",
                "ALTER TABLE flow_snapshot ADD COLUMN squeeze_potential_subscore NUMERIC(8, 4)",
            ),
        ],
        "technical_feature_daily": [
            ("sma_200", "ALTER TABLE technical_feature_daily ADD COLUMN sma_200 NUMERIC(18, 4)"),
            ("sma_75_slope_pct", "ALTER TABLE technical_feature_daily ADD COLUMN sma_75_slope_pct NUMERIC(8, 4)"),
            (
                "deviation_from_sma_75_pct",
                "ALTER TABLE technical_feature_daily ADD COLUMN deviation_from_sma_75_pct NUMERIC(8, 4)",
            ),
            ("ma_gap_5_25_pct", "ALTER TABLE technical_feature_daily ADD COLUMN ma_gap_5_25_pct NUMERIC(8, 4)"),
            ("ma_gap_25_75_pct", "ALTER TABLE technical_feature_daily ADD COLUMN ma_gap_25_75_pct NUMERIC(8, 4)"),
            ("golden_cross_flag", "ALTER TABLE technical_feature_daily ADD COLUMN golden_cross_flag BOOLEAN DEFAULT 0"),
            ("dead_cross_flag", "ALTER TABLE technical_feature_daily ADD COLUMN dead_cross_flag BOOLEAN DEFAULT 0"),
            ("volume_surge_ratio", "ALTER TABLE technical_feature_daily ADD COLUMN volume_surge_ratio NUMERIC(8, 4)"),
            ("macd_line", "ALTER TABLE technical_feature_daily ADD COLUMN macd_line NUMERIC(10, 4)"),
            ("macd_signal", "ALTER TABLE technical_feature_daily ADD COLUMN macd_signal NUMERIC(10, 4)"),
            ("macd_histogram", "ALTER TABLE technical_feature_daily ADD COLUMN macd_histogram NUMERIC(10, 4)"),
            (
                "macd_bullish_cross_flag",
                "ALTER TABLE technical_feature_daily ADD COLUMN macd_bullish_cross_flag BOOLEAN DEFAULT 0",
            ),
            (
                "macd_bearish_cross_flag",
                "ALTER TABLE technical_feature_daily ADD COLUMN macd_bearish_cross_flag BOOLEAN DEFAULT 0",
            ),
            ("bollinger_mid_20", "ALTER TABLE technical_feature_daily ADD COLUMN bollinger_mid_20 NUMERIC(18, 4)"),
            (
                "bollinger_upper_20",
                "ALTER TABLE technical_feature_daily ADD COLUMN bollinger_upper_20 NUMERIC(18, 4)",
            ),
            (
                "bollinger_lower_20",
                "ALTER TABLE technical_feature_daily ADD COLUMN bollinger_lower_20 NUMERIC(18, 4)",
            ),
            (
                "bollinger_width_20",
                "ALTER TABLE technical_feature_daily ADD COLUMN bollinger_width_20 NUMERIC(8, 4)",
            ),
            (
                "upper_wick_ratio",
                "ALTER TABLE technical_feature_daily ADD COLUMN upper_wick_ratio NUMERIC(8, 4)",
            ),
            (
                "lower_wick_ratio",
                "ALTER TABLE technical_feature_daily ADD COLUMN lower_wick_ratio NUMERIC(8, 4)",
            ),
            ("body_ratio", "ALTER TABLE technical_feature_daily ADD COLUMN body_ratio NUMERIC(8, 4)"),
            (
                "close_position_ratio",
                "ALTER TABLE technical_feature_daily ADD COLUMN close_position_ratio NUMERIC(8, 4)",
            ),
            ("gap_up_flag", "ALTER TABLE technical_feature_daily ADD COLUMN gap_up_flag BOOLEAN DEFAULT 0"),
            ("gap_down_flag", "ALTER TABLE technical_feature_daily ADD COLUMN gap_down_flag BOOLEAN DEFAULT 0"),
            (
                "consecutive_up_candles",
                "ALTER TABLE technical_feature_daily ADD COLUMN consecutive_up_candles INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "consecutive_down_candles",
                "ALTER TABLE technical_feature_daily ADD COLUMN consecutive_down_candles INTEGER NOT NULL DEFAULT 0",
            ),
        ],
    }

    db_inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, column_specs in compatibility_columns.items():
            if not db_inspector.has_table(table_name):
                continue

            existing_columns = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, ddl in column_specs:
                if column_name in existing_columns:
                    continue
                connection.exec_driver_sql(ddl)
                existing_columns.add(column_name)


def _apply_security_master_provenance_migration(engine) -> None:
    """Add master-sync provenance columns to existing SQLite/PostgreSQL tables."""

    db_inspector = inspect(engine)
    if not db_inspector.has_table("security_master"):
        return
    existing_columns = {column["name"] for column in db_inspector.get_columns("security_master")}
    column_specs = (
        (
            "master_source",
            "ALTER TABLE security_master ADD COLUMN master_source VARCHAR(32) NOT NULL DEFAULT 'legacy'",
        ),
        ("source_as_of", "ALTER TABLE security_master ADD COLUMN source_as_of DATE"),
        ("last_seen_sync_id", "ALTER TABLE security_master ADD COLUMN last_seen_sync_id VARCHAR(36)"),
    )
    with engine.begin() as connection:
        for column_name, ddl in column_specs:
            if column_name in existing_columns:
                continue
            connection.exec_driver_sql(ddl)
            existing_columns.add(column_name)

    db_inspector = inspect(engine)
    if not db_inspector.has_table("security_master_sync_run"):
        return
    existing_run_columns = {
        column["name"] for column in db_inspector.get_columns("security_master_sync_run")
    }
    run_column_specs = (
        ("source", "ALTER TABLE security_master_sync_run ADD COLUMN source VARCHAR(32)"),
        ("source_scope", "ALTER TABLE security_master_sync_run ADD COLUMN source_scope VARCHAR(64)"),
        ("source_as_of", "ALTER TABLE security_master_sync_run ADD COLUMN source_as_of DATE"),
        ("synced_at", "ALTER TABLE security_master_sync_run ADD COLUMN synced_at TIMESTAMP"),
        (
            "complete",
            "ALTER TABLE security_master_sync_run ADD COLUMN complete BOOLEAN NOT NULL DEFAULT FALSE",
        ),
        (
            "is_current_snapshot",
            "ALTER TABLE security_master_sync_run ADD COLUMN is_current_snapshot BOOLEAN NOT NULL DEFAULT TRUE",
        ),
        (
            "fetched_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN fetched_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "inserted_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN inserted_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "updated_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN updated_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "reactivated_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN reactivated_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "deactivated_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN deactivated_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "active_total",
            "ALTER TABLE security_master_sync_run ADD COLUMN active_total INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "jquants_active_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN jquants_active_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "adopted_legacy_count",
            "ALTER TABLE security_master_sync_run ADD COLUMN adopted_legacy_count INTEGER NOT NULL DEFAULT 0",
        ),
    )
    with engine.begin() as connection:
        for column_name, ddl in run_column_specs:
            if column_name in existing_run_columns:
                continue
            connection.exec_driver_sql(ddl)
            existing_run_columns.add(column_name)


def _apply_watchlist_collections_migration(engine) -> None:
    """Create the default collection and backfill legacy watchlist rows once."""

    db_inspector = inspect(engine)
    required_tables = {"watchlist", "watchlist_collection", "watchlist_membership"}
    if not required_tables <= set(db_inspector.get_table_names()):
        return

    from app.models.watchlist import WatchlistCollection, WatchlistMembership

    default_name = "メイン"
    normalized_name = unicodedata.normalize("NFKC", default_name).strip().casefold()
    reflected_metadata = MetaData()
    legacy_table = Table("watchlist", reflected_metadata, autoload_with=engine)

    with Session(engine) as session:
        default_collection = session.scalar(
            select(WatchlistCollection).where(WatchlistCollection.system_key == "default")
        )
        if default_collection is not None:
            if not default_collection.is_active:
                default_collection.is_active = True
            session.commit()
            return

        if default_collection is None:
            default_collection = session.scalar(
                select(WatchlistCollection).where(
                    WatchlistCollection.normalized_name == normalized_name
                )
            )
        if default_collection is None:
            default_collection = WatchlistCollection(
                name=default_name,
                normalized_name=normalized_name,
                system_key="default",
                sort_order=0,
                is_active=True,
            )
            session.add(default_collection)
        else:
            default_collection.system_key = "default"
            default_collection.is_active = True
        session.flush()

        selected_columns = [legacy_table.c.id, legacy_table.c.ticker_code]
        if "sort_order" in legacy_table.c:
            selected_columns.append(legacy_table.c.sort_order)
        if "is_active" in legacy_table.c:
            selected_columns.append(legacy_table.c.is_active)
        if "updated_at" in legacy_table.c:
            selected_columns.append(legacy_table.c.updated_at)

        # Old databases may predate the intended ticker uniqueness. Choose the
        # newest active row deterministically, while leaving every legacy row
        # untouched for manual reconciliation.
        preferred_by_ticker: dict[str, object] = {}
        for row in session.execute(select(*selected_columns)).mappings():
            ticker_code = str(row["ticker_code"])
            score = (
                bool(row.get("is_active", True)),
                str(row.get("updated_at") or ""),
                int(row["id"]),
            )
            existing = preferred_by_ticker.get(ticker_code)
            if existing is None:
                preferred_by_ticker[ticker_code] = (score, row)
                continue
            existing_score, _ = existing
            if score > existing_score:
                preferred_by_ticker[ticker_code] = (score, row)

        existing_item_ids = set(
            session.scalars(
                select(WatchlistMembership.watchlist_item_id).where(
                    WatchlistMembership.collection_id == default_collection.id
                )
            ).all()
        )
        for _, row in preferred_by_ticker.values():
            item_id = int(row["id"])
            if item_id in existing_item_ids:
                continue
            legacy_sort_order = row.get("sort_order", 100)
            session.add(
                WatchlistMembership(
                    collection_id=default_collection.id,
                    watchlist_item_id=item_id,
                    sort_order=int(legacy_sort_order if legacy_sort_order is not None else 100),
                    is_active=bool(row.get("is_active", True)),
                )
            )
        session.commit()


@lru_cache(maxsize=1)
def get_engine():
    """Return the lazily initialized SQLAlchemy engine."""

    settings = get_settings()
    _prepare_sqlite_path(settings.database_url)
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@lru_cache(maxsize=1)
def get_session_factory():
    """Return the lazily initialized SQLAlchemy session factory."""

    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    """Create tables for Phase 0."""

    if get_settings().app_use_mock:
        return
    engine = get_engine()

    # The extended monitoring models live under src/ and are a superset of the
    # Phase 0 schema. Create them first so later routes can rely on the richer
    # tables while the Phase 0 ORM remains backward-compatible.
    from kabuhandan_hojo.models import Base as MonitoringBase

    MonitoringBase.metadata.create_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _apply_security_master_provenance_migration(engine)
    _apply_sqlite_compat_migrations(engine)
    _apply_watchlist_collections_migration(engine)
    _sync_local_security_master(engine)


def _sync_local_security_master(engine) -> None:
    """Keep the checked-in Japanese security master available for search."""

    from app.services.security_master_catalog import local_security_master_catalog

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)
    with session_factory() as session:
        local_security_master_catalog.sync_to_db(session, commit=True)


def get_db() -> Generator[Session | None, None, None]:
    """Yield a request-scoped database session when live mode is enabled."""

    if get_settings().app_use_mock:
        yield None
        return

    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
