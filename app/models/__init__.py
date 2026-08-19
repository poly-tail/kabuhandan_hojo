"""SQLAlchemy model registry."""

from app.models.base import Base
from app.models.ai_analysis_record import AiAnalysisRecord
from app.models.portfolio import PortfolioHolding
from app.models.price_daily import PriceDaily
from app.models.score_daily import ScoreDaily
from app.models.security import SecurityMaster
from app.models.watchlist import Watchlist, WatchlistCollection, WatchlistMembership

__all__ = [
    "Base",
    "AiAnalysisRecord",
    "PortfolioHolding",
    "PriceDaily",
    "ScoreDaily",
    "SecurityMaster",
    "Watchlist",
    "WatchlistCollection",
    "WatchlistMembership",
]
