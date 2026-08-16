"""Event normalization for EDINET and other document sources."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from kabuhandan_hojo.connectors.base import DocumentRecord


@dataclass(slots=True)
class NormalizedEvent:
    event_id: str
    ticker_code: str | None
    event_type: str
    importance_hint: Decimal
    summary_text: str
    raw_reference: str | None
    metadata_json: dict[str, Any]


class EdinetEventNormalizer:
    """Convert raw document records into application events."""

    TITLE_RULES: list[tuple[str, str, Decimal]] = [
        ("上方修正", "upward_revision", Decimal("90")),
        ("下方修正", "downward_revision", Decimal("10")),
        ("自己株式取得", "shareholder_return", Decimal("85")),
        ("大株主", "large_shareholding", Decimal("75")),
        ("四半期", "quarterly_report", Decimal("60")),
        ("有価証券報告書", "annual_report", Decimal("65")),
        ("臨時報告書", "extraordinary_report", Decimal("55")),
        ("希薄化", "dilution_risk", Decimal("15")),
        ("決算説明会", "quarterly_report", Decimal("60")),
        ("新製品", "product_cycle", Decimal("70")),
        ("share buyback", "shareholder_return", Decimal("85")),
        ("buyback", "shareholder_return", Decimal("85")),
        ("upward revision", "upward_revision", Decimal("90")),
        ("guidance raise", "upward_revision", Decimal("90")),
        ("guidance cut", "downward_revision", Decimal("10")),
        ("new product", "product_cycle", Decimal("70")),
        ("product launch", "product_cycle", Decimal("70")),
    ]

    EVENT_HINT_SCORES: dict[str, Decimal] = {
        "upward_revision": Decimal("90"),
        "downward_revision": Decimal("10"),
        "shareholder_return": Decimal("85"),
        "large_shareholding": Decimal("75"),
        "quarterly_report": Decimal("60"),
        "annual_report": Decimal("65"),
        "extraordinary_report": Decimal("55"),
        "dilution_risk": Decimal("15"),
        "product_cycle": Decimal("70"),
        "document_update": Decimal("50"),
    }

    def normalize(self, document: DocumentRecord) -> NormalizedEvent:
        event_type = "document_update"
        importance = Decimal("50")

        hint = str(document.raw_payload.get("event_type_hint") or "").strip().lower()
        if hint:
            event_type = hint
            importance = self.EVENT_HINT_SCORES.get(hint, Decimal("50"))
        else:
            title = document.title
            lowered_title = title.lower()
            for keyword, mapped_type, mapped_score in self.TITLE_RULES:
                if keyword in title or keyword in lowered_title:
                    event_type = mapped_type
                    importance = mapped_score
                    break

        event_id = f"{document.source_name}:{document.external_id}:{event_type}"
        ticker_code = self._normalize_ticker_code(document.ticker_code)
        summary_text = f"{document.title} ({event_type})"
        metadata_json = {
            "document_type": document.document_type,
            "ticker_code": ticker_code,
            "source_name": document.source_name,
            "published_at": document.published_at.isoformat(),
        }
        return NormalizedEvent(
            event_id=event_id,
            ticker_code=ticker_code,
            event_type=event_type,
            importance_hint=importance,
            summary_text=summary_text,
            raw_reference=document.storage_uri or document.external_id,
            metadata_json=metadata_json,
        )

    @staticmethod
    def _normalize_ticker_code(ticker_code: str | None) -> str | None:
        if not ticker_code:
            return None
        normalized = ticker_code.strip()
        return normalized[:4] if normalized.isdigit() and len(normalized) >= 4 else normalized
