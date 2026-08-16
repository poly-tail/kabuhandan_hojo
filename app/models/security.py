"""Security master model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SecurityMaster(TimestampMixin, Base):
    """Registered Japanese equity master."""

    __tablename__ = "security_master"

    ticker_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    local_code: Mapped[str | None] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_english: Mapped[str | None] = mapped_column(String(255))
    market: Mapped[str | None] = mapped_column(String(50))
    industry_17: Mapped[str | None] = mapped_column(String(100))
    industry_33: Mapped[str | None] = mapped_column(String(100))
    listed_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    watchlist_items: Mapped[list["Watchlist"]] = relationship(back_populates="security")
    prices: Mapped[list["PriceDaily"]] = relationship(back_populates="security")
    scores: Mapped[list["ScoreDaily"]] = relationship(back_populates="security")
    portfolio_holdings: Mapped[list["PortfolioHolding"]] = relationship(back_populates="security")


from app.models.price_daily import PriceDaily  # noqa: E402
from app.models.portfolio import PortfolioHolding  # noqa: E402
from app.models.score_daily import ScoreDaily  # noqa: E402
from app.models.watchlist import Watchlist  # noqa: E402
