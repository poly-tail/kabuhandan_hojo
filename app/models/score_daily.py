"""Daily score model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ScoreDaily(TimestampMixin, Base):
    """Daily score breakdown placeholder for later phases."""

    __tablename__ = "score_daily"
    __table_args__ = (UniqueConstraint("ticker_code", "target_date", name="uq_score_daily_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker_code: Mapped[str] = mapped_column(ForeignKey("security_master.ticker_code"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    fundamental_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    technical_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    flow_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    explanation_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(50), default="phase0", nullable=False)

    security: Mapped["SecurityMaster"] = relationship(back_populates="scores")


from app.models.security import SecurityMaster  # noqa: E402

