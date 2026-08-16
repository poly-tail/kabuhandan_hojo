"""Watchlist model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint
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


from app.models.security import SecurityMaster  # noqa: E402
