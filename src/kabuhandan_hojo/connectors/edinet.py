"""EDINET connector."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from kabuhandan_hojo.connectors.base import DocumentConnector, DocumentRecord, MissingCredentialsError

logger = logging.getLogger(__name__)


class EdinetConnector(DocumentConnector):
    """Minimal EDINET API client wrapper."""

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch_documents(self, target_date: date) -> list[DocumentRecord]:
        self._require_api_key()
        params = {"date": target_date.isoformat(), "type": 2}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/documents.json",
                params=params,
                headers={"x-api-key": self.api_key or ""},
            )
            response.raise_for_status()
            payload = response.json()

        items = payload.get("results") or []
        records: list[DocumentRecord] = []
        for item in items:
            records.append(
                DocumentRecord(
                    source_name="edinet",
                    external_id=str(item.get("docID") or item.get("doc_id")),
                    document_type=str(item.get("docDescription") or item.get("docTypeCode") or "edinet_document"),
                    title=str(item.get("docDescription") or item.get("filerName") or "EDINET document"),
                    ticker_code=str(item.get("secCode")) if item.get("secCode") else None,
                    published_at=datetime.fromisoformat(
                        str(item.get("submitDateTime") or f"{target_date.isoformat()}T00:00:00+00:00")
                    ).astimezone(timezone.utc),
                    storage_uri=None,
                    raw_payload=item,
                    content_text=None,
                    hash_digest=None,
                )
            )
        logger.info("Fetched %s EDINET documents for %s", len(records), target_date)
        return records

    async def fetch_document_body(self, doc_id: str, response_type: int = 5) -> bytes:
        self._require_api_key()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self.base_url}/documents/{doc_id}",
                params={"type": response_type},
                headers={"x-api-key": self.api_key or ""},
            )
            response.raise_for_status()
            return response.content

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise MissingCredentialsError("EDINET API key is not configured.")

