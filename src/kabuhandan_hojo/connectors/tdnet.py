"""TDnet API connector."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from kabuhandan_hojo.connectors.base import DocumentConnector, DocumentRecord, MissingCredentialsError

logger = logging.getLogger(__name__)


class TdnetConnector(DocumentConnector):
    """Minimal TDnet API client wrapper.

    This uses the official paid TDnet API service described by JPX/JPXI.
    Only the index API is required for event ingestion because title, code,
    disclosure time, and disclosure number are enough to create normalized
    event records.
    """

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch_documents(
        self,
        target_date: date,
        ticker_code: str | None = None,
    ) -> list[DocumentRecord]:
        self._require_api_key()
        payload: dict[str, Any] = {
            "accessKey": self.api_key,
            "dateFrom": target_date.isoformat(),
            "dateTo": target_date.isoformat(),
        }
        if ticker_code:
            payload["code"] = self._tdnet_code(ticker_code)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/tdlist",
                json=payload,
                headers={
                    "x-api-key": self.api_key or "",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        records = self._extract_documents(data, target_date=target_date)
        logger.info("Fetched %s TDnet documents for %s", len(records), target_date)
        return records

    def _extract_documents(self, payload: dict[str, Any], *, target_date: date) -> list[DocumentRecord]:
        items = payload.get("informationList") or payload.get("results") or payload.get("data") or []
        if isinstance(items, dict):
            items = [items]

        records: list[DocumentRecord] = []
        for item in items:
            disclosure_number = str(item.get("disclosureNumber") or "").strip()
            if not disclosure_number:
                continue
            raw_code = str(item.get("code") or item.get("stockCode") or "").strip()
            ticker_code = self._normalize_ticker_code(raw_code)
            title = str(item.get("title") or "TDnet disclosure")
            disclosed_date = str(item.get("disclosedDate") or target_date.isoformat())
            disclosed_time = str(item.get("disclosedTime") or "00:00:00")
            published_at = self._parse_published_at(disclosed_date, disclosed_time)
            disclosure_items = item.get("disclosureItems")
            document_type = (
                ",".join(str(value) for value in disclosure_items)
                if isinstance(disclosure_items, list) and disclosure_items
                else "tdnet_document"
            )
            modified_history = str(item.get("modifiedHistory") or "0")
            records.append(
                DocumentRecord(
                    source_name="tdnet_api",
                    external_id=f"{disclosure_number}:{modified_history}",
                    document_type=document_type,
                    title=title,
                    ticker_code=ticker_code,
                    published_at=published_at,
                    storage_uri=f"tdnet://{disclosure_number}",
                    raw_payload=item,
                    content_text=None,
                    hash_digest=None,
                )
            )
        return records

    def _parse_published_at(self, disclosed_date: str, disclosed_time: str) -> datetime:
        iso_text = f"{disclosed_date}T{disclosed_time}+09:00"
        try:
            return datetime.fromisoformat(iso_text).astimezone(timezone.utc)
        except ValueError:
            return datetime.fromisoformat(f"{disclosed_date}T00:00:00+09:00").astimezone(timezone.utc)

    def _normalize_ticker_code(self, raw_code: str | None) -> str | None:
        if not raw_code:
            return None
        normalized = raw_code.strip()
        if normalized.isdigit() and len(normalized) >= 4:
            return normalized[:4]
        return normalized or None

    def _tdnet_code(self, ticker_code: str) -> str:
        normalized = ticker_code.strip()
        if normalized.isdigit() and len(normalized) == 4:
            return f"{normalized}0"
        return normalized

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise MissingCredentialsError("TDnet API key is not configured.")
