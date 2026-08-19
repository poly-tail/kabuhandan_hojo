"""Watchlist collection management for monitoring services."""

from __future__ import annotations

import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from kabuhandan_hojo.models.entities import (
    EventFact,
    ScoreDaily,
    SecurityMaster,
    Watchlist,
    WatchlistCollection,
    WatchlistMembership,
)
from kabuhandan_hojo.schemas.watchlists import WatchlistCreate


class WatchlistService:
    """Manage monitored tickers, defaulting to the legacy-compatible list."""

    def add(
        self,
        session: Session,
        payload: WatchlistCreate,
        collection_id: int | None = None,
    ) -> Watchlist:
        collection = self._resolve_collection(session, collection_id)
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
            session.flush()
        else:
            if "memo" in payload.model_fields_set:
                watchlist.memo = payload.memo
            if "thesis_bull" in payload.model_fields_set:
                watchlist.thesis_bull = payload.thesis_bull
            if "thesis_bear" in payload.model_fields_set:
                watchlist.thesis_bear = payload.thesis_bear
            if collection.system_key == "default":
                watchlist.sort_order = payload.sort_order
            watchlist.is_active = True

        membership = session.scalar(
            select(WatchlistMembership).where(
                WatchlistMembership.collection_id == collection.id,
                WatchlistMembership.watchlist_item_id == watchlist.id,
            )
        )
        if membership is None:
            membership = WatchlistMembership(
                collection_id=collection.id,
                watchlist_item_id=watchlist.id,
                sort_order=payload.sort_order,
                is_active=True,
            )
            session.add(membership)
        else:
            membership.sort_order = payload.sort_order
            membership.is_active = True
        session.flush()
        return watchlist

    def list(
        self,
        session: Session,
        collection_id: int | None = None,
    ) -> list[Watchlist]:
        collection = self._resolve_collection(session, collection_id)
        statement = (
            select(Watchlist)
            .join(
                WatchlistMembership,
                WatchlistMembership.watchlist_item_id == Watchlist.id,
            )
            .options(selectinload(Watchlist.security))
            .where(
                WatchlistMembership.collection_id == collection.id,
                WatchlistMembership.is_active.is_(True),
                Watchlist.is_active.is_(True),
            )
            .order_by(WatchlistMembership.sort_order.asc(), Watchlist.id.asc())
        )
        return list(session.scalars(statement).all())

    def remove(self, session: Session, watchlist_id: int) -> None:
        collection = self._resolve_collection(session, None)
        membership = session.scalar(
            select(WatchlistMembership).where(
                WatchlistMembership.collection_id == collection.id,
                WatchlistMembership.watchlist_item_id == watchlist_id,
                WatchlistMembership.is_active.is_(True),
            )
        )
        if membership is None:
            raise ValueError("Watchlist item was not found.")
        membership.is_active = False
        session.flush()
        active_count = session.scalar(
            select(func.count(WatchlistMembership.id)).where(
                WatchlistMembership.watchlist_item_id == watchlist_id,
                WatchlistMembership.is_active.is_(True),
            )
        )
        watchlist = session.get(Watchlist, watchlist_id)
        if watchlist is not None:
            watchlist.is_active = bool(active_count)
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

    def _resolve_collection(
        self,
        session: Session,
        collection_id: int | None,
    ) -> WatchlistCollection:
        if collection_id is None:
            collection = session.scalar(
                select(WatchlistCollection).where(WatchlistCollection.system_key == "default")
            )
            if collection is None:
                name = "メイン"
                collection = WatchlistCollection(
                    name=name,
                    normalized_name=unicodedata.normalize("NFKC", name).strip().casefold(),
                    system_key="default",
                    sort_order=0,
                    is_active=True,
                )
                session.add(collection)
                session.flush()
            return collection
        collection = session.get(WatchlistCollection, collection_id)
        if collection is None or not collection.is_active:
            raise ValueError("Watchlist was not found.")
        return collection
