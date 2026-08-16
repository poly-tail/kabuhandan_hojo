"""Alert schemas."""

from __future__ import annotations

from pydantic import BaseModel


class AlertRead(BaseModel):
    ticker_code: str
    alert_type: str
    severity: str
    message: str

