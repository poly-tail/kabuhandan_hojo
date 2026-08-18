"""Watchlist service."""

from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.security import SecurityMaster
from app.models.watchlist import Watchlist
from app.schemas.watchlist import SecuritySearchResult, WatchlistCreate, WatchlistItem
from app.services.security_profile import SecurityProfile, security_profile_service


class WatchlistService:
    """Handle minimal Phase 0 watchlist operations."""

    def search_candidates(self, db: Session, query: str, limit: int = 10) -> list[SecuritySearchResult]:
        normalized = query.strip()
        if not normalized:
            return []

        lowered = normalized.lower()
        ticker_lower = func.lower(SecurityMaster.ticker_code)
        local_code_lower = func.lower(func.coalesce(SecurityMaster.local_code, ""))
        ticker_exact = ticker_lower == lowered
        local_code_exact = local_code_lower == lowered
        ticker_prefix = ticker_lower.like(f"{lowered}%")
        local_code_prefix = local_code_lower.like(f"{lowered}%")
        name_contains = func.lower(SecurityMaster.name).like(f"%{lowered}%")
        name_english_contains = func.lower(func.coalesce(SecurityMaster.name_english, "")).like(f"%{lowered}%")
        market_contains = func.lower(func.coalesce(SecurityMaster.market, "")).like(f"%{lowered}%")

        statement = (
            select(SecurityMaster, Watchlist.id)
            .outerjoin(
                Watchlist,
                (Watchlist.ticker_code == SecurityMaster.ticker_code) & (Watchlist.is_active.is_(True)),
            )
            .where(
                SecurityMaster.is_active.is_(True),
                or_(ticker_prefix, local_code_prefix, name_contains, name_english_contains, market_contains),
            )
            .order_by(
                case(
                    (ticker_exact, 0),
                    (local_code_exact, 1),
                    (ticker_prefix, 2),
                    (local_code_prefix, 3),
                    (name_contains, 4),
                    (name_english_contains, 5),
                    else_=6,
                ),
                SecurityMaster.ticker_code.asc(),
            )
            .limit(limit)
        )

        matches = [
            self._to_search_result(
                security=security,
                in_watchlist=watchlist_id is not None,
                profile=None,
            )
            for security, watchlist_id in db.execute(statement).all()
        ]
        return matches

    def list_items(self, db: Session) -> list[WatchlistItem]:
        statement = (
            select(Watchlist)
            .options(selectinload(Watchlist.security))
            .where(Watchlist.is_active.is_(True))
            .order_by(Watchlist.sort_order.asc(), Watchlist.created_at.asc())
        )
        items = db.scalars(statement).all()
        return [self._to_schema(item) for item in items]

    def create_item(self, db: Session, payload: WatchlistCreate) -> WatchlistItem:
        profile = security_profile_service.resolve(payload.ticker_code, session=db)
        resolved_name = payload.name or (profile.name if profile is not None else payload.ticker_code)
        resolved_market = payload.market if payload.market is not None else (profile.market if profile is not None else None)

        security = db.get(SecurityMaster, payload.ticker_code)
        if security is None:
            security = SecurityMaster(
                ticker_code=payload.ticker_code,
                local_code=profile.local_code if profile is not None else payload.ticker_code,
                name=resolved_name,
                name_english=getattr(profile, "name_english", None) if profile is not None else None,
                market=resolved_market,
                industry_17=profile.industry_17 if profile is not None else None,
                industry_33=profile.industry_33 if profile is not None else None,
                listed_date=profile.listed_date if profile is not None else None,
                source_as_of=profile.source_as_of if profile is not None else None,
                master_source="manual",
            )
            db.add(security)
        else:
            if payload.name:
                security.name = payload.name
            elif profile is not None and security_profile_service.prefers_profile_name(
                security.name,
                payload.ticker_code,
                profile.name,
            ):
                security.name = profile.name
            if security.local_code is None and profile is not None:
                security.local_code = profile.local_code
            if security.name_english is None and getattr(profile, "name_english", None) is not None:
                security.name_english = getattr(profile, "name_english")
            if payload.market:
                security.market = payload.market
            elif security.market is None and profile is not None:
                security.market = profile.market
            if security.industry_17 is None and profile is not None:
                security.industry_17 = profile.industry_17
            if security.industry_33 is None and profile is not None:
                security.industry_33 = profile.industry_33
            if security.listed_date is None and profile is not None:
                security.listed_date = profile.listed_date

        watchlist = db.scalar(select(Watchlist).where(Watchlist.ticker_code == payload.ticker_code))
        if watchlist is None:
            watchlist = Watchlist(
                ticker_code=payload.ticker_code,
                memo=payload.memo,
                thesis_bull=payload.thesis_bull,
                thesis_bear=payload.thesis_bear,
                sort_order=payload.sort_order,
                is_active=True,
            )
            db.add(watchlist)
        else:
            watchlist.memo = payload.memo
            watchlist.thesis_bull = payload.thesis_bull
            watchlist.thesis_bear = payload.thesis_bear
            watchlist.sort_order = payload.sort_order
            watchlist.is_active = True

        db.commit()
        db.refresh(watchlist)
        db.refresh(security)
        return self._to_schema(watchlist)

    def _to_schema(self, item: Watchlist) -> WatchlistItem:
        return WatchlistItem(
            id=item.id,
            ticker_code=item.ticker_code,
            name=item.security.name,
            market=item.security.market,
            memo=item.memo,
            thesis_bull=item.thesis_bull,
            thesis_bear=item.thesis_bear,
            sort_order=item.sort_order,
            is_active=item.is_active,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _to_search_result(
        self,
        *,
        security: SecurityMaster,
        in_watchlist: bool,
        profile: SecurityProfile | None,
    ) -> SecuritySearchResult:
        name = security.name
        market = security.market
        if profile is not None and security_profile_service.prefers_profile_name(security.name, security.ticker_code, profile.name):
            name = profile.name
        if market is None and profile is not None:
            market = profile.market
        return SecuritySearchResult(
            ticker_code=security.ticker_code,
            name=name,
            market=market,
            in_watchlist=in_watchlist,
        )
