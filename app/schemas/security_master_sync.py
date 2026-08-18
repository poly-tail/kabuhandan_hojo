"""API contracts for the local TSE security-master snapshot."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class SecurityMasterStatusResponse(BaseModel):
    """Describe the latest complete J-Quants TSE-master synchronization."""

    source: str = "jquants"
    source_scope: str = "tse_listed_issues"
    source_as_of: date | None = None
    sync_id: str | None = None
    synced_at: datetime | None = None
    complete: bool = False
    active_total: int = Field(default=0, ge=0)
    jquants_active_count: int = Field(default=0, ge=0)


class SecurityMasterSyncResponse(SecurityMasterStatusResponse):
    """Report both provider-fetch and local-persistence outcomes for one sync."""

    job_name: str = "sync_security_master"
    processed_count: int = Field(ge=0)
    fetched_count: int = Field(ge=0)
    upserted_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    reactivated_count: int = Field(ge=0)
    deactivated_count: int = Field(ge=0)
    detail: str
    executed_at: datetime
