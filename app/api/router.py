"""Top-level API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.ai_analysis import router as ai_analysis_router
from app.api.routes.analysis_ui import router as analysis_ui_router
from app.api.routes.health import router as health_router
from app.api.routes.monitoring import router as monitoring_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.ui import router as ui_router
from app.api.routes.watchlist import router as watchlist_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ai_analysis_router)
api_router.include_router(analysis_ui_router)
api_router.include_router(watchlist_router)
api_router.include_router(portfolio_router)
api_router.include_router(monitoring_router)
api_router.include_router(ui_router)
