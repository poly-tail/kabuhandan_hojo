"""YouTube Data API connector."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from kabuhandan_hojo.connectors.base import ConnectorError, DocumentRecord, MissingCredentialsError


class YouTubeConnector:
    """Fetch video metadata from the official YouTube Data API."""

    def __init__(self, *, base_url: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch_channel_videos(
        self,
        channel_id: str,
        *,
        ticker_code: str | None = None,
        published_after: datetime | None = None,
        max_results: int = 10,
    ) -> list[DocumentRecord]:
        if not self.api_key:
            raise MissingCredentialsError("YOUTUBE_API_KEY is not configured.")

        params = {
            "key": self.api_key,
            "part": "snippet",
            "type": "video",
            "channelId": channel_id,
            "order": "date",
            "maxResults": max_results,
        }
        if published_after is not None:
            if published_after.tzinfo is None:
                published_after = published_after.replace(tzinfo=UTC)
            params["publishedAfter"] = published_after.astimezone(UTC).isoformat().replace("+00:00", "Z")

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/search", params=params)
        if response.status_code >= 400:
            raise ConnectorError(f"YouTube Data API request failed with status {response.status_code}.")

        payload = response.json()
        documents: list[DocumentRecord] = []
        for item in payload.get("items", []):
            video_id = str(((item.get("id") or {}).get("videoId")) or "").strip()
            snippet = item.get("snippet") or {}
            if not video_id:
                continue
            documents.append(
                DocumentRecord(
                    source_name="youtube_data_api",
                    external_id=video_id,
                    document_type="video",
                    title=str(snippet.get("title") or video_id),
                    ticker_code=ticker_code,
                    published_at=self._parse_published_at(snippet.get("publishedAt")),
                    storage_uri=f"https://www.youtube.com/watch?v={video_id}",
                    raw_payload=item,
                    content_text=str(snippet.get("description") or "").strip() or None,
                    hash_digest=None,
                )
            )
        return documents

    def _parse_published_at(self, raw_value: object) -> datetime:
        value = str(raw_value or "").strip()
        if not value:
            return datetime.now(UTC)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
