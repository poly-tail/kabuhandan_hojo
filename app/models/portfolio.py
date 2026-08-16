"""Portfolio holding model."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PortfolioHolding(TimestampMixin, Base):
    """Manually maintained holdings for the portfolio panel."""

    __tablename__ = "portfolio_holding"
    __table_args__ = (UniqueConstraint("ticker_code", name="uq_portfolio_holding_ticker_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    note: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    security: Mapped["SecurityMaster"] = relationship(back_populates="portfolio_holdings")


from app.models.security import SecurityMaster  # noqa: E402
