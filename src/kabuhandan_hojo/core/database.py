"""Database bootstrap helpers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from kabuhandan_hojo.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine from application settings."""

    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.database_url,
        echo=settings.sql_echo,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a request-scoped session factory."""

    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

