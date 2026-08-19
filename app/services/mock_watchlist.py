"""In-memory watchlist service for mock mode."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.schemas.watchlist import (
    SecuritySearchResult,
    WatchlistCollectionCreate,
    WatchlistCollectionRead,
    WatchlistCollectionUpdate,
    WatchlistCreate,
    WatchlistItem,
)
from app.services.security_profile import security_profile_service
from app.services.watchlist import (
    DefaultWatchlistDeletionError,
    DuplicateWatchlistNameError,
    WatchlistCollectionNotFoundError,
    WatchlistItemNotFoundError,
    normalize_watchlist_name,
)

_SEED_TIMESTAMP = datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)


class MockWatchlistService:
    """Store sample watchlist data in memory for mock mode."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._catalog = [
            {"ticker_code": "7203", "name": "トヨタ自動車", "market": "TSE Prime"},
            {"ticker_code": "6758", "name": "ソニーグループ", "market": "TSE Prime"},
            {"ticker_code": "8035", "name": "東京エレクトロン", "market": "TSE Prime"},
            {"ticker_code": "9984", "name": "ソフトバンクグループ", "market": "TSE Prime"},
        ]
        self._items = [
            WatchlistItem(
                id=1,
                ticker_code="7203",
                name="トヨタ自動車",
                market="TSE Prime",
                memo="業績とハイブリッド需要の継続を確認したい",
                thesis_bull="販売台数の回復と利益率改善が継続するなら仮説維持。",
                thesis_bear="上方修正が止まり、決算の上振れ余地が細るなら見直す。",
                sort_order=10,
                is_active=True,
                created_at=_SEED_TIMESTAMP,
                updated_at=_SEED_TIMESTAMP,
            ),
            WatchlistItem(
                id=2,
                ticker_code="9984",
                name="ソフトバンクグループ",
                market="TSE Prime",
                memo="還元姿勢と資産価値の再評価を監視",
                thesis_bull="NAVディスカウント縮小と自己株買い継続が見えるなら仮説維持。",
                thesis_bear="主要投資先の悪化で還元余力が弱まるなら撤退条件。",
                sort_order=20,
                is_active=True,
                created_at=_SEED_TIMESTAMP,
                updated_at=_SEED_TIMESTAMP,
            ),
            WatchlistItem(
                id=3,
                ticker_code="7974",
                name="任天堂",
                market="TSE Prime",
                memo="次世代機とソフト販売の勢いを確認",
                thesis_bull="新ハード期待とソフト販売の積み上がりが続くなら維持。",
                thesis_bear="新ハード時期の後ずれで材料が空白化するなら見直す。",
                sort_order=30,
                is_active=True,
                created_at=_SEED_TIMESTAMP,
                updated_at=_SEED_TIMESTAMP,
            ),
            WatchlistItem(
                id=4,
                ticker_code="6758",
                name="ソニーグループ",
                market="TSE Prime",
                memo="音楽・ゲーム・イメージセンサーのバランスを確認",
                thesis_bull="主力セグメントの利益が分散しながら伸びるなら維持。",
                thesis_bear="主力セグメントの失速で成長説明が崩れるなら見直す。",
                sort_order=40,
                is_active=True,
                created_at=_SEED_TIMESTAMP,
                updated_at=_SEED_TIMESTAMP,
            ),
        ]
        self._next_id = len(self._items) + 1
        self._collections = {
            1: WatchlistCollectionRead(
                id=1,
                name="メイン",
                is_default=True,
                sort_order=0,
                item_count=len(self._items),
                created_at=_SEED_TIMESTAMP,
                updated_at=_SEED_TIMESTAMP,
            )
        }
        self._memberships: dict[int, dict[str, dict[str, int | bool]]] = {
            1: {
                item.ticker_code: {"sort_order": item.sort_order, "is_active": item.is_active}
                for item in self._items
            }
        }
        self._next_collection_id = 2

    def list_collections(self) -> list[WatchlistCollectionRead]:
        with self._lock:
            collections = sorted(
                self._collections.values(),
                key=lambda item: (0 if item.is_default else 1, item.sort_order, item.id),
            )
            return [self._collection_copy_locked(item) for item in collections]

    def create_collection(self, payload: WatchlistCollectionCreate) -> WatchlistCollectionRead:
        with self._lock:
            normalized_name = normalize_watchlist_name(payload.name)
            if any(
                normalize_watchlist_name(item.name) == normalized_name
                for item in self._collections.values()
            ):
                raise DuplicateWatchlistNameError(
                    "A watchlist with the same normalized name already exists."
                )
            now = datetime.now(timezone.utc)
            collection = WatchlistCollectionRead(
                id=self._next_collection_id,
                name=payload.name,
                is_default=False,
                sort_order=payload.sort_order,
                item_count=0,
                created_at=now,
                updated_at=now,
            )
            self._collections[collection.id] = collection
            self._memberships[collection.id] = {}
            self._next_collection_id += 1
            return collection.model_copy(deep=True)

    def update_collection(
        self,
        collection_id: int,
        payload: WatchlistCollectionUpdate,
    ) -> WatchlistCollectionRead:
        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            if payload.name is not None:
                normalized_name = normalize_watchlist_name(payload.name)
                if any(
                    item.id != collection_id
                    and normalize_watchlist_name(item.name) == normalized_name
                    for item in self._collections.values()
                ):
                    raise DuplicateWatchlistNameError(
                        "A watchlist with the same normalized name already exists."
                    )
            updated = collection.model_copy(
                update={
                    "name": payload.name if payload.name is not None else collection.name,
                    "sort_order": (
                        payload.sort_order if payload.sort_order is not None else collection.sort_order
                    ),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._collections[collection_id] = updated
            return self._collection_copy_locked(updated)

    def delete_collection(self, collection_id: int) -> None:
        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            if collection.is_default:
                raise DefaultWatchlistDeletionError("The default watchlist cannot be deleted.")
            self._collections.pop(collection_id)
            self._memberships.pop(collection_id, None)
            self._refresh_all_item_states_locked()

    def list_items(self, collection_id: int | None = None) -> list[WatchlistItem]:
        """Return active items from one named mock collection."""

        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            membership_map = self._memberships[collection.id]
            items = [
                item
                for item in self._items
                if item.is_active
                and bool(membership_map.get(item.ticker_code, {}).get("is_active", False))
            ]
            ordered = sorted(
                items,
                key=lambda item: (
                    int(membership_map[item.ticker_code]["sort_order"]),
                    item.id,
                ),
            )
            return [
                item.model_copy(
                    update={
                        "collection_id": collection.id,
                        "sort_order": int(membership_map[item.ticker_code]["sort_order"]),
                    },
                    deep=True,
                )
                for item in ordered
            ]

    def get_item(
        self,
        ticker_code: str,
        collection_id: int | None = None,
    ) -> WatchlistItem | None:
        """Return a single active mock membership by ticker."""

        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            membership = self._memberships[collection.id].get(ticker_code)
            if not membership or not membership["is_active"]:
                return None
            for item in self._items:
                if item.ticker_code == ticker_code and item.is_active:
                    return item.model_copy(
                        update={
                            "collection_id": collection.id,
                            "sort_order": int(membership["sort_order"]),
                        },
                        deep=True,
                    )
        return None

    def search_candidates(
        self,
        query: str,
        limit: int = 10,
        collection_id: int | None = None,
    ) -> list[SecuritySearchResult]:
        normalized = query.strip()
        if not normalized:
            return []

        lowered = normalized.lower()
        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            membership_map = self._memberships[collection.id]
            watchlist_tickers = {
                ticker_code
                for ticker_code, membership in membership_map.items()
                if membership["is_active"]
            }
            catalog = {entry["ticker_code"]: entry for entry in self._catalog}
            for item in self._items:
                catalog[item.ticker_code] = {
                    "ticker_code": item.ticker_code,
                    "name": item.name,
                    "market": item.market,
                }

            matches: list[SecuritySearchResult] = []
            for entry in catalog.values():
                profile = security_profile_service.resolve(entry["ticker_code"])
                aliases = profile.aliases if profile is not None else ()
                if not (
                    entry["ticker_code"].startswith(normalized)
                    or lowered in entry["name"].lower()
                    or lowered in (entry["market"] or "").lower()
                    or any(lowered in alias.lower() for alias in aliases)
                ):
                    continue
                matches.append(
                    SecuritySearchResult(
                        ticker_code=entry["ticker_code"],
                        name=profile.name if profile is not None else entry["name"],
                        market=entry["market"] or (profile.market if profile is not None else None),
                        in_watchlist=entry["ticker_code"] in watchlist_tickers,
                    )
                )

            matches.sort(
                key=lambda item: (
                    0 if item.ticker_code == normalized else 1,
                    0 if item.ticker_code.startswith(normalized) else 1,
                    item.ticker_code,
                )
            )
            if matches:
                return matches[:limit]

            if normalized.isdigit() and 4 <= len(normalized) <= 10:
                profile = security_profile_service.resolve(normalized)
                return [
                    SecuritySearchResult(
                        ticker_code=normalized,
                        name=profile.name if profile is not None else normalized,
                        market=profile.market if profile is not None else None,
                        in_watchlist=normalized in watchlist_tickers,
                    )
                ]

            return []

    def create_item(
        self,
        payload: WatchlistCreate,
        collection_id: int | None = None,
    ) -> WatchlistItem:
        """Create or update a mock watchlist item."""

        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            now = datetime.now(timezone.utc)
            profile = security_profile_service.resolve(payload.ticker_code)
            for index, item in enumerate(self._items):
                if item.ticker_code != payload.ticker_code:
                    continue

                updated = item.model_copy(
                    update={
                        "name": payload.name or (profile.name if profile is not None else item.name),
                        "market": payload.market if payload.market is not None else (profile.market if profile is not None else item.market),
                        "memo": payload.memo if "memo" in payload.model_fields_set else item.memo,
                        "thesis_bull": (
                            payload.thesis_bull
                            if "thesis_bull" in payload.model_fields_set
                            else item.thesis_bull
                        ),
                        "thesis_bear": (
                            payload.thesis_bear
                            if "thesis_bear" in payload.model_fields_set
                            else item.thesis_bear
                        ),
                        "sort_order": payload.sort_order if collection.is_default else item.sort_order,
                        "is_active": True,
                        "updated_at": now,
                    }
                )
                self._items[index] = updated
                self._memberships[collection.id][payload.ticker_code] = {
                    "sort_order": payload.sort_order,
                    "is_active": True,
                }
                self._touch_collection_locked(collection.id, now)
                return updated.model_copy(
                    update={
                        "collection_id": collection.id,
                        "sort_order": payload.sort_order,
                    },
                    deep=True,
                )

            created = WatchlistItem(
                id=self._next_id,
                ticker_code=payload.ticker_code,
                name=payload.name or (profile.name if profile is not None else payload.ticker_code),
                market=payload.market if payload.market is not None else (profile.market if profile is not None else None),
                memo=payload.memo,
                thesis_bull=payload.thesis_bull,
                thesis_bear=payload.thesis_bear,
                sort_order=payload.sort_order,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            self._items.append(created)
            self._memberships[collection.id][payload.ticker_code] = {
                "sort_order": payload.sort_order,
                "is_active": True,
            }
            self._next_id += 1
            self._touch_collection_locked(collection.id, now)
            return created.model_copy(
                update={"collection_id": collection.id},
                deep=True,
            )

    def remove_item(self, collection_id: int, ticker_code: str) -> None:
        with self._lock:
            collection = self._resolve_collection_locked(collection_id)
            membership = self._memberships[collection.id].get(ticker_code)
            if membership is None or not membership["is_active"]:
                raise WatchlistItemNotFoundError("The watchlist item was not found.")
            membership["is_active"] = False
            now = datetime.now(timezone.utc)
            self._touch_collection_locked(collection.id, now)
            self._refresh_all_item_states_locked()

    def _resolve_collection_locked(
        self,
        collection_id: int | None,
    ) -> WatchlistCollectionRead:
        resolved_id = 1 if collection_id is None else collection_id
        collection = self._collections.get(resolved_id)
        if collection is None:
            raise WatchlistCollectionNotFoundError("The watchlist was not found.")
        return collection

    def _collection_copy_locked(
        self,
        collection: WatchlistCollectionRead,
    ) -> WatchlistCollectionRead:
        membership_map = self._memberships.get(collection.id, {})
        active_tickers = {item.ticker_code for item in self._items if item.is_active}
        item_count = sum(
            1
            for ticker_code, membership in membership_map.items()
            if membership["is_active"] and ticker_code in active_tickers
        )
        return collection.model_copy(update={"item_count": item_count}, deep=True)

    def _touch_collection_locked(self, collection_id: int, now: datetime) -> None:
        collection = self._collections[collection_id]
        self._collections[collection_id] = collection.model_copy(update={"updated_at": now})

    def _refresh_all_item_states_locked(self) -> None:
        active_tickers = {
            ticker_code
            for membership_map in self._memberships.values()
            for ticker_code, membership in membership_map.items()
            if membership["is_active"]
        }
        self._items = [
            item.model_copy(update={"is_active": item.ticker_code in active_tickers})
            for item in self._items
        ]


mock_watchlist_service = MockWatchlistService()
