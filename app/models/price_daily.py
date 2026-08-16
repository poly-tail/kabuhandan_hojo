"""Daily OHLCV model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PriceDaily(TimestampMixin, Base):
    """Daily price snapshot for a security."""

    __tablename__ = "price_daily"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_price_daily_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Decimal] = mapped_column("open", Numeric(18, 4), nullable=False)
    high_price: Mapped[Decimal] = mapped_column("high", Numeric(18, 4), nullable=False)
    low_price: Mapped[Decimal] = mapped_column("low", Numeric(18, 4), nullable=False)
    close_price: Mapped[Decimal] = mapped_column("close", Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    source_name: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)

    security: Mapped["SecurityMaster"] = relationship(back_populates="prices")


from app.models.security import SecurityMaster  # noqa: E402

