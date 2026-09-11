"""Pure identity and bounded reuse rules for legacy AI reviews."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

from app.schemas.portfolio_ai import PortfolioMarketSnapshot


CACHE_FORMAT_VERSION = "legacy-review-v2"
MAX_CACHE_TTL_SECONDS = 300
TOKYO = ZoneInfo("Asia/Tokyo")
SERIES_FIELDS = {
    "price": ("price", "change_rate", "volume", "support_levels", "resistance_levels"),
    "technical": ("ma_5", "ma_25", "ma_75", "rsi", "macd", "upper_wick_ratio",
                  "lower_wick_ratio", "body_ratio", "close_position_ratio"),
    "flow": ("credit_ratio",),
    "news": ("recent_news",),
    "events": ("earnings_date",),
}


def canonical_digest(value: Any) -> str:
    """Sort mapping keys only: input arrays retain their semantic order."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_cache_key(request_payload: dict[str, Any]) -> str:
    """Exclude only the builder's top-level processing time, without mutation."""
    return canonical_digest({
        "format_version": CACHE_FORMAT_VERSION,
        "input": {key: value for key, value in request_payload.items()
                  if key != "generated_at"},
    })


def prompt_fingerprint(bundle: dict[str, Any]) -> str:
    """Fingerprint actual instructions/schema; input values have their own identity."""
    return canonical_digest({
        "system_prompt": bundle["system_prompt"],
        "user_instructions": bundle["user_prompt"].split("\n\nInput JSON:\n", 1)[0],
        "output_schema": bundle["output_schema"],
    })


def cache_ineligibility(snapshots: list[PortfolioMarketSnapshot]) -> list[str]:
    """Require provenance for present series, not for absent optional series."""
    reasons = []
    for snapshot in snapshots:
        present = []
        for series, fields in SERIES_FIELDS.items():
            if not any(getattr(snapshot, field) not in (None, [], "") for field in fields):
                continue
            present.append(series)
            metadata = snapshot.source_metadata.get(series, [])
            valid = bool(metadata)
            for record in metadata:
                if not record.source or not record.source.strip() or not record.as_of:
                    valid = False
                    break
                try:
                    if len(record.as_of) == 10:
                        date.fromisoformat(record.as_of)
                    else:
                        datetime.fromisoformat(record.as_of)
                except (TypeError, ValueError):
                    valid = False
                    break
            if series == "news" and len(metadata) != len(snapshot.recent_news):
                valid = False
            if not valid:
                reasons.append(f"{snapshot.ticker}: {series} の由来・基準日時が不足")
        if not present:
            reasons.append(f"{snapshot.ticker}: 市場データが未取得")
    if not snapshots:
        reasons.append("市場データが未取得")
    return reasons


def cache_entry_is_current(entry: Any, *, now: datetime, ttl_seconds: int) -> bool:
    """Server record time is immutable; reject future/naive/bad/old-format entries."""
    if not isinstance(entry, dict) or entry.get("format_version") != CACHE_FORMAT_VERSION:
        return False
    ttl = min(ttl_seconds, MAX_CACHE_TTL_SECONDS)
    if ttl <= 0 or now.tzinfo is None:
        return False
    try:
        recorded = datetime.fromisoformat(entry["recorded_at"])
        if recorded.tzinfo is None:
            return False
        elapsed = (now - recorded).total_seconds()
        return (0 <= elapsed < ttl
                and now.astimezone(TOKYO).date() == recorded.astimezone(TOKYO).date())
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
