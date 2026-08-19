"""Named watchlist collection service."""

from __future__ import annotations

import unicodedata

from sqlalchemy import case, delete, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.security import SecurityMaster
from app.models.watchlist import Watchlist, WatchlistCollection, WatchlistMembership
from app.schemas.watchlist import (
    SecuritySearchResult,
    WatchlistCollectionCreate,
    WatchlistCollectionRead,
    WatchlistCollectionUpdate,
    WatchlistCreate,
    WatchlistItem,
)
from app.services.security_profile import SecurityProfile, security_profile_service


DEFAULT_WATCHLIST_NAME = "メイン"
DEFAULT_WATCHLIST_SYSTEM_KEY = "default"


class WatchlistCollectionNotFoundError(LookupError):
    """Raised when a requested collection is missing or inactive."""


class WatchlistItemNotFoundError(LookupError):
    """Raised when a requested membership is missing or inactive."""


class DuplicateWatchlistNameError(ValueError):
    """Raised when a normalized collection name is already in use."""


class DefaultWatchlistDeletionError(ValueError):
    """Raised when the built-in default collection is deleted."""


def normalize_watchlist_name(value: str) -> str:
    """Return the cross-database identity key for a collection name."""

    return unicodedata.normalize("NFKC", value).strip().casefold()


class WatchlistService:
    """Manage security-level notes and their named-list memberships."""

    def search_candidates(
        self,
        db: Session,
        query: str,
        limit: int = 10,
        collection_id: int | None = None,
    ) -> list[SecuritySearchResult]:
        normalized = query.strip()
        if not normalized:
            return []

        collection = self._resolve_collection(db, collection_id)
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
        membership_exists = exists(
            select(1)
            .select_from(WatchlistMembership)
            .join(Watchlist, Watchlist.id == WatchlistMembership.watchlist_item_id)
            .where(
                WatchlistMembership.collection_id == collection.id,
                WatchlistMembership.is_active.is_(True),
                Watchlist.is_active.is_(True),
                Watchlist.ticker_code == SecurityMaster.ticker_code,
            )
        )

        statement = (
            select(SecurityMaster, membership_exists.label("in_watchlist"))
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

        return [
            self._to_search_result(
                security=security,
                in_watchlist=bool(in_watchlist),
                profile=None,
            )
            for security, in_watchlist in db.execute(statement).all()
        ]

    def list_collections(self, db: Session) -> list[WatchlistCollectionRead]:
        self._default_collection(db)
        collections = db.scalars(
            select(WatchlistCollection)
            .where(WatchlistCollection.is_active.is_(True))
            .order_by(
                case((WatchlistCollection.system_key == DEFAULT_WATCHLIST_SYSTEM_KEY, 0), else_=1),
                WatchlistCollection.sort_order.asc(),
                WatchlistCollection.created_at.asc(),
            )
        ).all()
        return [self._collection_schema(db, collection) for collection in collections]

    def create_collection(
        self,
        db: Session,
        payload: WatchlistCollectionCreate,
    ) -> WatchlistCollectionRead:
        self._default_collection(db)
        normalized_name = normalize_watchlist_name(payload.name)
        if db.scalar(
            select(WatchlistCollection.id).where(
                WatchlistCollection.normalized_name == normalized_name,
            )
        ) is not None:
            raise DuplicateWatchlistNameError("A watchlist with the same normalized name already exists.")

        collection = WatchlistCollection(
            name=payload.name,
            normalized_name=normalized_name,
            system_key=None,
            sort_order=payload.sort_order,
            is_active=True,
        )
        db.add(collection)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateWatchlistNameError(
                "A watchlist with the same normalized name already exists."
            ) from exc
        db.refresh(collection)
        return self._collection_schema(db, collection)

    def update_collection(
        self,
        db: Session,
        collection_id: int,
        payload: WatchlistCollectionUpdate,
    ) -> WatchlistCollectionRead:
        collection = self._resolve_collection(db, collection_id)
        if payload.name is not None:
            normalized_name = normalize_watchlist_name(payload.name)
            duplicate_id = db.scalar(
                select(WatchlistCollection.id).where(
                    WatchlistCollection.normalized_name == normalized_name,
                    WatchlistCollection.id != collection.id,
                )
            )
            if duplicate_id is not None:
                raise DuplicateWatchlistNameError("A watchlist with the same normalized name already exists.")
            collection.name = payload.name
            collection.normalized_name = normalized_name
        if payload.sort_order is not None:
            collection.sort_order = payload.sort_order
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DuplicateWatchlistNameError(
                "A watchlist with the same normalized name already exists."
            ) from exc
        db.refresh(collection)
        return self._collection_schema(db, collection)

    def delete_collection(self, db: Session, collection_id: int) -> None:
        collection = self._resolve_collection(db, collection_id)
        if collection.system_key == DEFAULT_WATCHLIST_SYSTEM_KEY:
            raise DefaultWatchlistDeletionError("The default watchlist cannot be deleted.")

        item_ids = list(
            db.scalars(
                select(WatchlistMembership.watchlist_item_id).where(
                    WatchlistMembership.collection_id == collection.id,
                )
            ).all()
        )
        db.execute(
            delete(WatchlistMembership).where(WatchlistMembership.collection_id == collection.id)
        )
        db.delete(collection)
        db.flush()
        for item_id in item_ids:
            self._refresh_global_active_state(db, item_id)
        db.commit()

    def list_items(self, db: Session, collection_id: int | None = None) -> list[WatchlistItem]:
        collection = self._resolve_collection(db, collection_id)
        statement = (
            select(Watchlist, WatchlistMembership)
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
            .order_by(
                WatchlistMembership.sort_order.asc(),
                WatchlistMembership.created_at.asc(),
            )
        )
        return [
            self._to_schema(item, collection_id=collection.id, sort_order=membership.sort_order)
            for item, membership in db.execute(statement).all()
        ]

    def create_item(
        self,
        db: Session,
        payload: WatchlistCreate,
        collection_id: int | None = None,
    ) -> WatchlistItem:
        collection = self._resolve_collection(db, collection_id)
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
            db.flush()
        else:
            if "memo" in payload.model_fields_set:
                watchlist.memo = payload.memo
            if "thesis_bull" in payload.model_fields_set:
                watchlist.thesis_bull = payload.thesis_bull
            if "thesis_bear" in payload.model_fields_set:
                watchlist.thesis_bear = payload.thesis_bear
            if collection.system_key == DEFAULT_WATCHLIST_SYSTEM_KEY:
                watchlist.sort_order = payload.sort_order
            watchlist.is_active = True

        membership = db.scalar(
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
            db.add(membership)
        else:
            membership.sort_order = payload.sort_order
            membership.is_active = True

        db.commit()
        db.refresh(watchlist)
        db.refresh(membership)
        db.refresh(security)
        return self._to_schema(
            watchlist,
            collection_id=collection.id,
            sort_order=membership.sort_order,
        )

    def remove_item(self, db: Session, collection_id: int, ticker_code: str) -> None:
        collection = self._resolve_collection(db, collection_id)
        row = db.execute(
            select(WatchlistMembership, Watchlist)
            .join(Watchlist, Watchlist.id == WatchlistMembership.watchlist_item_id)
            .where(
                WatchlistMembership.collection_id == collection.id,
                WatchlistMembership.is_active.is_(True),
                Watchlist.ticker_code == ticker_code,
            )
        ).one_or_none()
        if row is None:
            raise WatchlistItemNotFoundError("The watchlist item was not found.")
        membership, watchlist = row
        membership.is_active = False
        db.flush()
        self._refresh_global_active_state(db, watchlist.id)
        db.commit()

    def _default_collection(self, db: Session) -> WatchlistCollection:
        collection = db.scalar(
            select(WatchlistCollection).where(
                WatchlistCollection.system_key == DEFAULT_WATCHLIST_SYSTEM_KEY,
            )
        )
        if collection is not None:
            if not collection.is_active:
                collection.is_active = True
                db.commit()
                db.refresh(collection)
            return collection

        normalized_name = normalize_watchlist_name(DEFAULT_WATCHLIST_NAME)
        collection = db.scalar(
            select(WatchlistCollection).where(
                WatchlistCollection.normalized_name == normalized_name,
            )
        )
        if collection is None:
            collection = WatchlistCollection(
                name=DEFAULT_WATCHLIST_NAME,
                normalized_name=normalized_name,
                system_key=DEFAULT_WATCHLIST_SYSTEM_KEY,
                sort_order=0,
                is_active=True,
            )
            db.add(collection)
        else:
            collection.system_key = DEFAULT_WATCHLIST_SYSTEM_KEY
            collection.is_active = True
        db.commit()
        db.refresh(collection)
        return collection

    def _resolve_collection(
        self,
        db: Session,
        collection_id: int | None,
    ) -> WatchlistCollection:
        if collection_id is None:
            return self._default_collection(db)
        collection = db.get(WatchlistCollection, collection_id)
        if collection is None or not collection.is_active:
            raise WatchlistCollectionNotFoundError("The watchlist was not found.")
        return collection

    def _collection_schema(
        self,
        db: Session,
        collection: WatchlistCollection,
    ) -> WatchlistCollectionRead:
        item_count = db.scalar(
            select(func.count(WatchlistMembership.id))
            .join(Watchlist, Watchlist.id == WatchlistMembership.watchlist_item_id)
            .where(
                WatchlistMembership.collection_id == collection.id,
                WatchlistMembership.is_active.is_(True),
                Watchlist.is_active.is_(True),
            )
        )
        return WatchlistCollectionRead(
            id=collection.id,
            name=collection.name,
            is_default=collection.system_key == DEFAULT_WATCHLIST_SYSTEM_KEY,
            sort_order=collection.sort_order,
            item_count=int(item_count or 0),
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )

    def _refresh_global_active_state(self, db: Session, watchlist_item_id: int) -> None:
        watchlist = db.get(Watchlist, watchlist_item_id)
        if watchlist is None:
            return
        active_count = db.scalar(
            select(func.count(WatchlistMembership.id))
            .join(
                WatchlistCollection,
                WatchlistCollection.id == WatchlistMembership.collection_id,
            )
            .where(
                WatchlistMembership.watchlist_item_id == watchlist_item_id,
                WatchlistMembership.is_active.is_(True),
                WatchlistCollection.is_active.is_(True),
            )
        )
        watchlist.is_active = bool(active_count)

    def _to_schema(
        self,
        item: Watchlist,
        *,
        collection_id: int,
        sort_order: int,
    ) -> WatchlistItem:
        return WatchlistItem(
            id=item.id,
            collection_id=collection_id,
            ticker_code=item.ticker_code,
            name=item.security.name,
            market=item.security.market,
            memo=item.memo,
            thesis_bull=item.thesis_bull,
            thesis_bear=item.thesis_bear,
            sort_order=sort_order,
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
        if profile is not None and security_profile_service.prefers_profile_name(
            security.name,
            security.ticker_code,
            profile.name,
        ):
            name = profile.name
        if market is None and profile is not None:
            market = profile.market
        return SecuritySearchResult(
            ticker_code=security.ticker_code,
            name=name,
            market=market,
            in_watchlist=in_watchlist,
        )


watchlist_service = WatchlistService()
