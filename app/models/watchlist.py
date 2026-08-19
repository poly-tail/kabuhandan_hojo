"""Watchlist model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Watchlist(TimestampMixin, Base):
    """User-managed watchlist entries."""

    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("ticker_code", name="uq_watchlist_ticker_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    memo: Mapped[str | None] = mapped_column(Text)
    thesis_bull: Mapped[str | None] = mapped_column(Text)
    thesis_bear: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    security: Mapped["SecurityMaster"] = relationship(back_populates="watchlist_items")
    memberships: Mapped[list["WatchlistMembership"]] = relationship(back_populates="watchlist_item")


class WatchlistCollection(TimestampMixin, Base):
    """A named collection of monitored securities."""

    __tablename__ = "watchlist_collection"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_watchlist_collection_normalized_name"),
        UniqueConstraint("system_key", name="uq_watchlist_collection_system_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(256), nullable=False)
    system_key: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list["WatchlistMembership"]] = relationship(back_populates="collection")


class WatchlistMembership(TimestampMixin, Base):
    """Membership of a security-level watchlist item in one collection."""

    __tablename__ = "watchlist_membership"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "watchlist_item_id",
            name="uq_watchlist_membership_collection_item",
        ),
        Index(
            "ix_watchlist_membership_item_active",
            "watchlist_item_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("watchlist_collection.id"),
        nullable=False,
    )
    watchlist_item_id: Mapped[int] = mapped_column(ForeignKey("watchlist.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    collection: Mapped["WatchlistCollection"] = relationship(back_populates="memberships")
    watchlist_item: Mapped["Watchlist"] = relationship(back_populates="memberships")


from app.models.security import SecurityMaster  # noqa: E402
