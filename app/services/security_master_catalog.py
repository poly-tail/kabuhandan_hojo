"""Local Japanese security master catalog."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.security import SecurityMaster


DEFAULT_SECURITY_MASTER_CSV = Path(__file__).resolve().parents[2] / "data" / "security_master_jp.csv"


@dataclass(slots=True)
class LocalSecurityMasterRecord:
    ticker_code: str
    local_code: str | None
    name: str
    name_english: str | None
    market: str | None
    industry_17: str | None
    industry_33: str | None
    listed_date: date | None
    is_active: bool


class LocalSecurityMasterCatalog:
    """Load a checked-in Japanese security master into security_master."""

    def __init__(self, csv_path: Path = DEFAULT_SECURITY_MASTER_CSV) -> None:
        self.csv_path = csv_path

    def load(self) -> list[LocalSecurityMasterRecord]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            return [record for row in reader if (record := self._coerce_row(row)) is not None]

    def sync_to_db(self, db: Session, *, commit: bool = False) -> int:
        processed_count = 0
        for record in self.load():
            self._upsert(db, record)
            processed_count += 1
        if commit:
            db.commit()
        else:
            db.flush()
        return processed_count

    def _upsert(self, db: Session, record: LocalSecurityMasterRecord) -> SecurityMaster:
        security = db.get(SecurityMaster, record.ticker_code)
        if security is None:
            security = SecurityMaster(
                ticker_code=record.ticker_code,
                local_code=record.local_code or record.ticker_code,
                name=record.name,
                name_english=record.name_english,
                market=record.market,
                industry_17=record.industry_17,
                industry_33=record.industry_33,
                listed_date=record.listed_date,
                is_active=record.is_active,
            )
            db.add(security)
            return security

        security.local_code = record.local_code or security.local_code or record.ticker_code
        security.name = record.name or security.name
        security.name_english = record.name_english or security.name_english
        security.market = record.market or security.market
        security.industry_17 = record.industry_17 or security.industry_17
        security.industry_33 = record.industry_33 or security.industry_33
        security.listed_date = record.listed_date or security.listed_date
        security.is_active = record.is_active
        return security

    def _coerce_row(self, row: dict[str, str]) -> LocalSecurityMasterRecord | None:
        ticker_code = (row.get("ticker_code") or row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        if not ticker_code or not name:
            return None
        return LocalSecurityMasterRecord(
            ticker_code=ticker_code,
            local_code=self._clean(row.get("local_code")) or ticker_code,
            name=name,
            name_english=self._clean(row.get("name_english")),
            market=self._clean(row.get("market")),
            industry_17=self._clean(row.get("industry_17")),
            industry_33=self._clean(row.get("industry_33")),
            listed_date=self._parse_date(row.get("listed_date")),
            is_active=self._parse_bool(row.get("is_active")),
        )

    @staticmethod
    def _clean(value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        cleaned = (value or "").strip()
        if not cleaned:
            return None
        return date.fromisoformat(cleaned[:10])

    @staticmethod
    def _parse_bool(value: str | None) -> bool:
        cleaned = (value or "true").strip().lower()
        return cleaned not in {"0", "false", "no", "inactive"}


local_security_master_catalog = LocalSecurityMasterCatalog()
