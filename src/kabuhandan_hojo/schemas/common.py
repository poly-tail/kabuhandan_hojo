"""Common API schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base model with ORM support."""

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    environment: str


class DisclaimerResponse(BaseModel):
    product_name: str
    disclaimer: str
    usage_principles: list[str]


class JobRunResponse(BaseModel):
    job_name: str
    processed_count: int
    detail: str
    executed_at: datetime


class DateRangeQuery(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

