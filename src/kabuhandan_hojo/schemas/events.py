"""Event and document schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from kabuhandan_hojo.schemas.common import ORMModel


class RawDocumentCreate(BaseModel):
    source_name: str = "edinet"
    external_id: str
    document_type: str
    title: str
    ticker_code: str | None = None
    published_at: datetime
    storage_uri: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    content_text: str | None = None
    hash_digest: str | None = None


class AllowlistedIrDocumentCreate(BaseModel):
    ticker_code: str
    title: str
    url: str
    published_at: datetime
    document_type: str = "ir_update"
    external_id: str | None = None
    event_type_hint: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    content_text: str | None = None


class YouTubeSyncRequest(BaseModel):
    ticker_code: str
    channel_ids: list[str] = Field(min_length=1)
    published_after: datetime | None = None
    max_results: int = Field(default=10, ge=1, le=50)


class RawDocumentRead(ORMModel):
    id: int
    source_name: str
    external_id: str
    document_type: str
    title: str
    ticker_code: str | None = None
    published_at: datetime
    storage_uri: str | None = None
    raw_payload: dict[str, Any]
    content_text: str | None = None
    hash_digest: str | None = None


class EventRead(ORMModel):
    event_id: str
    ticker_code: str | None = None
    event_type: str
    event_time: datetime
    source_name: str
    importance_hint: Decimal
    summary_text: str
    raw_reference: str | None = None
    metadata_json: dict[str, Any]


class DocumentImportResponse(BaseModel):
    raw_document: RawDocumentRead
    event: EventRead
    summary_text: str
