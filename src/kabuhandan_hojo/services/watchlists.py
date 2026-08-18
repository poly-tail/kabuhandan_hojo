"""Watchlist management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from kabuhandan_hojo.models.entities import EventFact, ScoreDaily, SecurityMaster, Watchlist
from kabuhandan_hojo.schemas.watchlists import WatchlistCreate


class WatchlistService:
    """Manage monitored tickers."""

    def add(self, session: Session, payload: WatchlistCreate) -> Watchlist:
        security = session.get(SecurityMaster, payload.ticker_code)
        if security is None:
            security = SecurityMaster(
                ticker_code=payload.ticker_code,
                local_code=payload.ticker_code,
                name=payload.name or payload.ticker_code,
                market=payload.market,
                industry_17=None,
                industry_33=None,
                master_source="manual",
            )
            session.add(security)

        watchlist = session.scalar(select(Watchlist).where(Watchlist.ticker_code == payload.ticker_code))
        if watchlist is None:
            watchlist = Watchlist(
                ticker_code=payload.ticker_code,
                memo=payload.memo,
                thesis_bull=payload.thesis_bull,
                thesis_bear=payload.thesis_bear,
                sort_order=payload.sort_order,
                is_active=True,
            )
            session.add(watchlist)
        else:
            watchlist.memo = payload.memo
            watchlist.thesis_bull = payload.thesis_bull
            watchlist.thesis_bear = payload.thesis_bear
            watchlist.sort_order = payload.sort_order
            watchlist.is_active = True
        session.flush()
        return watchlist

    def list(self, session: Session) -> list[Watchlist]:
        statement = (
            select(Watchlist)
            .where(Watchlist.is_active.is_(True))
            .order_by(Watchlist.sort_order.asc(), Watchlist.id.asc())
        )
        return list(session.scalars(statement).all())

    def remove(self, session: Session, watchlist_id: int) -> None:
        watchlist = session.get(Watchlist, watchlist_id)
        if watchlist is None:
            raise ValueError("Watchlist item was not found.")
        watchlist.is_active = False
        session.flush()

    def latest_score(self, session: Session, ticker_code: str) -> ScoreDaily | None:
        statement = (
            select(ScoreDaily)
            .where(ScoreDaily.ticker_code == ticker_code)
            .order_by(ScoreDaily.target_date.desc())
            .limit(1)
        )
        return session.scalar(statement)

    def latest_event(self, session: Session, ticker_code: str) -> EventFact | None:
        statement = (
            select(EventFact)
            .where(EventFact.ticker_code == ticker_code)
            .order_by(EventFact.event_time.desc())
            .limit(1)
        )
        return session.scalar(statement)
