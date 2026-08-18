"""SQLAlchemy model registry."""

from kabuhandan_hojo.models.base import Base
from kabuhandan_hojo.models.entities import (
    AlertRule,
    EventFact,
    FinancialSnapshot,
    FlowSnapshot,
    PriceDaily,
    RawDocument,
    ScoreDaily,
    SecurityMaster,
    SecurityMasterSyncRun,
    SourceRegistry,
    TechnicalFeatureDaily,
    ThesisNote,
    VideoItem,
    Watchlist,
)

__all__ = [
    "AlertRule",
    "Base",
    "EventFact",
    "FinancialSnapshot",
    "FlowSnapshot",
    "PriceDaily",
    "RawDocument",
    "ScoreDaily",
    "SecurityMaster",
    "SecurityMasterSyncRun",
    "SourceRegistry",
    "TechnicalFeatureDaily",
    "ThesisNote",
    "VideoItem",
    "Watchlist",
]
