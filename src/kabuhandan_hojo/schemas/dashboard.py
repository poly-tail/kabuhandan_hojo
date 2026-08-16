"""Dashboard and alert schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from kabuhandan_hojo.schemas.alerts import AlertRead
from kabuhandan_hojo.schemas.events import EventRead
from kabuhandan_hojo.schemas.scores import ScoreRead
from kabuhandan_hojo.schemas.securities import SecurityRead


class DashboardRow(BaseModel):
    security: SecurityRead
    latest_score: ScoreRead | None = None
    alerts: list[AlertRead]
    latest_event: EventRead | None = None


class DashboardResponse(BaseModel):
    target_date: date
    disclaimer: str
    high_priority: list[DashboardRow]
    recent_events: list[EventRead]
    alerts: list[AlertRead]


class ScreeningResult(BaseModel):
    security: SecurityRead
    latest_score: ScoreRead | None = None
    latest_features: "TechnicalFeatureRead | None" = None
    latest_flow: "FlowSnapshotRead | None" = None
    matched_reasons: list[str]


from kabuhandan_hojo.schemas.securities import FlowSnapshotRead, TechnicalFeatureRead  # noqa: E402

ScreeningResult.model_rebuild()
