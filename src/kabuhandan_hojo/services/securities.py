"""Security detail queries."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from kabuhandan_hojo.models.entities import (
    EventFact,
    FinancialSnapshot,
    FlowSnapshot,
    PriceDaily,
    ScoreDaily,
    SecurityMaster,
    TechnicalFeatureDaily,
)


class SecurityService:
    """Query assembled security-level views."""

    def get(self, session: Session, ticker_code: str) -> SecurityMaster | None:
        return session.get(SecurityMaster, ticker_code)

    def latest_score(self, session: Session, ticker_code: str) -> ScoreDaily | None:
        return session.scalar(
            select(ScoreDaily).where(ScoreDaily.ticker_code == ticker_code).order_by(ScoreDaily.target_date.desc()).limit(1)
        )

    def latest_feature(self, session: Session, ticker_code: str) -> TechnicalFeatureDaily | None:
        return session.scalar(
            select(TechnicalFeatureDaily)
            .where(TechnicalFeatureDaily.ticker_code == ticker_code)
            .order_by(TechnicalFeatureDaily.target_date.desc())
            .limit(1)
        )

    def latest_financial(self, session: Session, ticker_code: str) -> FinancialSnapshot | None:
        return session.scalar(
            select(FinancialSnapshot)
            .where(FinancialSnapshot.ticker_code == ticker_code)
            .order_by(FinancialSnapshot.target_date.desc())
            .limit(1)
        )

    def latest_flow(self, session: Session, ticker_code: str) -> FlowSnapshot | None:
        return session.scalar(
            select(FlowSnapshot)
            .where(FlowSnapshot.ticker_code == ticker_code)
            .order_by(FlowSnapshot.target_date.desc())
            .limit(1)
        )

    def recent_events(self, session: Session, ticker_code: str, limit: int = 10) -> list[EventFact]:
        statement = (
            select(EventFact)
            .where(EventFact.ticker_code == ticker_code)
            .order_by(EventFact.event_time.desc())
            .limit(limit)
        )
        return list(session.scalars(statement).all())

    def latest_prices(self, session: Session, ticker_code: str, limit: int = 60) -> list[PriceDaily]:
        statement = (
            select(PriceDaily)
            .where(PriceDaily.ticker_code == ticker_code)
            .order_by(PriceDaily.target_date.desc())
            .limit(limit)
        )
        return list(reversed(session.scalars(statement).all()))
