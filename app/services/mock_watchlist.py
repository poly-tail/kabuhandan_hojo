"""In-memory watchlist service for mock mode."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.schemas.watchlist import SecuritySearchResult, WatchlistCreate, WatchlistItem
from app.services.security_profile import security_profile_service

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

    def list_items(self) -> list[WatchlistItem]:
        """Return a copy of the current mock watchlist."""

        with self._lock:
            ordered = sorted(self._items, key=lambda item: (item.sort_order, item.id))
            return [item.model_copy(deep=True) for item in ordered]

    def get_item(self, ticker_code: str) -> WatchlistItem | None:
        """Return a single mock watchlist item by ticker."""

        with self._lock:
            for item in self._items:
                if item.ticker_code == ticker_code and item.is_active:
                    return item.model_copy(deep=True)
        return None

    def search_candidates(self, query: str, limit: int = 10) -> list[SecuritySearchResult]:
        normalized = query.strip()
        if not normalized:
            return []

        lowered = normalized.lower()
        with self._lock:
            watchlist_tickers = {item.ticker_code for item in self._items if item.is_active}
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

    def create_item(self, payload: WatchlistCreate) -> WatchlistItem:
        """Create or update a mock watchlist item."""

        with self._lock:
            now = datetime.now(timezone.utc)
            profile = security_profile_service.resolve(payload.ticker_code)
            for index, item in enumerate(self._items):
                if item.ticker_code != payload.ticker_code:
                    continue

                updated = item.model_copy(
                    update={
                        "name": payload.name or (profile.name if profile is not None else item.name),
                        "market": payload.market if payload.market is not None else (profile.market if profile is not None else item.market),
                        "memo": payload.memo,
                        "thesis_bull": payload.thesis_bull,
                        "thesis_bear": payload.thesis_bear,
                        "sort_order": payload.sort_order,
                        "is_active": True,
                        "updated_at": now,
                    }
                )
                self._items[index] = updated
                return updated.model_copy(deep=True)

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
            self._next_id += 1
            return created.model_copy(deep=True)


mock_watchlist_service = MockWatchlistService()
