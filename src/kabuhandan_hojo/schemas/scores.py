"""Score schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from kabuhandan_hojo.schemas.alerts import AlertRead
from kabuhandan_hojo.schemas.common import ORMModel


class ScoreRead(ORMModel):
    id: int
    ticker_code: str
    target_date: date
    event_score: Decimal
    fundamental_score: Decimal
    technical_score: Decimal
    flow_score: Decimal
    risk_penalty: Decimal
    total_score: Decimal
    explanation_summary: str
    calculation_version: str
    score_breakdown: dict[str, Any]
    missing_data_flags: list[str]


class ScoreRecalculateResponse(BaseModel):
    score: ScoreRead
    generated_alerts: list["AlertRead"]
