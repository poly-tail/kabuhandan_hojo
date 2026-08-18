"""Security profile resolution from known catalogs and official APIs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from kabuhandan_hojo.connectors.jquants import normalize_jquants_master_code

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SecurityProfile:
    ticker_code: str
    name: str
    name_english: str | None = None
    market: str | None = None
    industry_17: str | None = None
    industry_33: str | None = None
    listed_date: date | None = None
    source_as_of: date | None = None
    local_code: str | None = None
    ir_url: str | None = None
    source: str = "internal"
    aliases: tuple[str, ...] = ()


class SecurityProfileService:
    """Resolve company metadata for a ticker code."""

    _known_profiles: dict[str, SecurityProfile] = {
        "7203": SecurityProfile(
            ticker_code="7203",
            local_code="7203",
            name="トヨタ自動車",
            market="TSE Prime",
            industry_17="Automobiles",
            industry_33="Transportation Equipment",
            listed_date=date(1949, 5, 16),
            ir_url="https://global.toyota/jp/ir/",
            source="seed",
            aliases=("Toyota Motor Corporation", "Toyota"),
            name_english="Toyota Motor Corporation",
        ),
        "9984": SecurityProfile(
            ticker_code="9984",
            local_code="9984",
            name="ソフトバンクグループ",
            market="TSE Prime",
            industry_17="Information & Communication",
            industry_33="Information & Communication",
            listed_date=date(1994, 7, 22),
            ir_url="https://group.softbank/ir/",
            source="seed",
            aliases=("SoftBank Group Corp.", "SoftBank Group"),
            name_english="SoftBank Group Corp.",
        ),
        "7974": SecurityProfile(
            ticker_code="7974",
            local_code="7974",
            name="任天堂",
            market="TSE Prime",
            industry_17="Other Products",
            industry_33="Other Products",
            listed_date=date(1962, 1, 1),
            ir_url="https://www.nintendo.co.jp/ir/index.html",
            source="seed",
            aliases=("Nintendo Co., Ltd.", "Nintendo"),
            name_english="Nintendo Co., Ltd.",
        ),
        "6758": SecurityProfile(
            ticker_code="6758",
            local_code="6758",
            name="ソニーグループ",
            market="TSE Prime",
            industry_17="Electrical Appliances",
            industry_33="Electrical Appliances",
            listed_date=date(1958, 12, 1),
            ir_url="https://www.sony.com/ja/SonyInfo/IR/",
            source="seed",
            aliases=("Sony Group Corporation", "Sony Group"),
            name_english="Sony Group Corporation",
        ),
        "8035": SecurityProfile(
            ticker_code="8035",
            local_code="8035",
            name="東京エレクトロン",
            market="TSE Prime",
            industry_17="Machinery",
            industry_33="Electronics Equipment",
            listed_date=date(1963, 11, 11),
            ir_url="https://www.tel.co.jp/ir/",
            source="seed",
            aliases=("Tokyo Electron Limited", "Tokyo Electron"),
            name_english="Tokyo Electron Limited",
        ),
        "8306": SecurityProfile(
            ticker_code="8306",
            local_code="8306",
            name="三菱UFJフィナンシャル・グループ",
            market="TSE Prime",
            industry_17="Banks",
            industry_33="Banks",
            ir_url="https://www.mufg.jp/ir/index.html",
            source="seed",
            aliases=("Mitsubishi UFJ Financial Group, Inc.", "MUFG"),
            name_english="Mitsubishi UFJ Financial Group, Inc.",
        ),
    }

    def resolve(self, ticker_code: str, *, session: Session | None = None) -> SecurityProfile | None:
        normalized = ticker_code.strip()
        if not normalized:
            return None

        db_profile = self._from_session(session, normalized) if session is not None else None
        known_profile = self._known_profiles.get(normalized)
        if db_profile is not None:
            if known_profile is not None:
                return self._merge_profiles(db_profile, known_profile)
            return db_profile
        if known_profile is not None:
            return known_profile
        return self._fetch_from_jquants(normalized)

    def search_known_profiles(self, query: str, *, limit: int = 10) -> list[SecurityProfile]:
        normalized = query.strip()
        if not normalized:
            return []

        lowered = normalized.lower()
        matches = [
            profile
            for profile in self._known_profiles.values()
            if profile.ticker_code.startswith(normalized)
            or lowered in profile.name.lower()
            or lowered in (profile.market or "").lower()
            or any(lowered in alias.lower() for alias in profile.aliases)
        ]
        matches.sort(
            key=lambda profile: (
                0 if profile.ticker_code == normalized else 1,
                0 if profile.ticker_code.startswith(normalized) else 1,
                0 if lowered == profile.name.lower() else 1,
                profile.ticker_code,
            )
        )
        return matches[:limit]

    def list_known_profiles(self) -> list[SecurityProfile]:
        return list(self._known_profiles.values())

    def _from_session(self, session: Session, ticker_code: str) -> SecurityProfile | None:
        from app.models.security import SecurityMaster as AppSecurityMaster

        security = session.get(AppSecurityMaster, ticker_code)
        if security is None:
            return None
        if self._is_placeholder_name(security.name, ticker_code) and not security.market:
            return None
        return SecurityProfile(
            ticker_code=ticker_code,
            local_code=security.local_code or ticker_code,
            name=security.name,
            name_english=security.name_english,
            market=security.market,
            industry_17=security.industry_17,
            industry_33=security.industry_33,
            listed_date=security.listed_date,
            source_as_of=security.source_as_of,
            source="db",
        )

    def _fetch_from_jquants(self, ticker_code: str) -> SecurityProfile | None:
        settings = get_settings()
        if not settings.database_url and not settings.app_name:
            return None

        monitoring_settings = None
        try:
            from kabuhandan_hojo.core.config import get_settings as get_monitoring_settings

            monitoring_settings = get_monitoring_settings()
        except Exception:
            monitoring_settings = None

        api_key = getattr(monitoring_settings, "jquants_api_key", None)
        base_url = getattr(monitoring_settings, "jquants_base_url", "https://api.jquants.com")
        if not api_key:
            return None

        candidate_paths = (
            "/v2/equities/master",
            "/v1/listed/info",
            "/v1/listed/info/",
            "/v1/listed/issues",
        )
        params_candidates = ({"code": ticker_code},)

        for path in candidate_paths:
            for params in params_candidates:
                try:
                    response = httpx.get(
                        f"{base_url.rstrip('/')}{path}",
                        params=params,
                        headers={"x-api-key": api_key},
                        timeout=10.0,
                    )
                except Exception as exc:
                    logger.debug("J-Quants listed info lookup failed for %s: %s", ticker_code, exc)
                    return None

                if response.status_code in {401, 403, 404}:
                    continue
                try:
                    response.raise_for_status()
                except Exception:
                    continue
                profile = self._parse_jquants_payload(ticker_code, response.json())
                if profile is not None:
                    return profile
        return None

    def _parse_jquants_payload(self, ticker_code: str, payload: dict[str, Any]) -> SecurityProfile | None:
        items = (
            payload.get("info")
            or payload.get("listed_info")
            or payload.get("listed_infos")
            or payload.get("issues")
            or payload.get("data")
            or []
        )
        if isinstance(items, dict):
            items = [items]
        for item in items:
            raw_code = str(
                item.get("Code")
                or item.get("code")
                or item.get("LocalCode")
                or item.get("local_code")
                or ""
            ).strip().upper()
            code = normalize_jquants_master_code(raw_code)
            normalized_ticker = ticker_code.strip().upper()
            alpha_public_alias = (
                len(normalized_ticker) == 4
                and raw_code == f"{normalized_ticker}0"
                and not raw_code.isdigit()
            )
            if code != normalized_ticker and not alpha_public_alias:
                continue
            name = (
                item.get("CompanyName")
                or item.get("CoName")
                or item.get("Name")
                or item.get("CompanyNameEnglish")
                or item.get("CoNameEn")
                or item.get("name")
            )
            if not name:
                continue
            market = (
                item.get("MarketCodeName")
                or item.get("MarketSegmentName")
                or item.get("MarketName")
                or item.get("MktNm")
                or item.get("market")
            )
            listed_date = self._parse_date(
                item.get("ListingDate") or item.get("ListedDate") or item.get("listed_date")
            )
            source_as_of = self._parse_date(item.get("Date") or item.get("date"))
            return SecurityProfile(
                ticker_code=normalized_ticker,
                local_code=raw_code or normalized_ticker,
                name=str(name),
                name_english=(
                    str(item.get("CompanyNameEnglish"))
                    if item.get("CompanyNameEnglish") is not None
                    else (
                        str(item.get("CoNameEn"))
                        if item.get("CoNameEn") is not None
                        else (
                            str(item.get("company_name_english"))
                            if item.get("company_name_english") is not None
                            else None
                        )
                    )
                ),
                market=str(market) if market is not None else None,
                industry_17=item.get("Sector17CodeName") or item.get("S17Nm") or item.get("sector_17"),
                industry_33=item.get("Sector33CodeName") or item.get("S33Nm") or item.get("sector_33"),
                listed_date=listed_date,
                source_as_of=source_as_of,
                source="jquants",
            )
        return None

    def prefers_profile_name(self, current_name: str | None, ticker_code: str, preferred_name: str | None) -> bool:
        if not preferred_name:
            return False
        if self._is_placeholder_name(current_name, ticker_code):
            return True
        if current_name is None:
            return True
        current = current_name.strip()
        preferred = preferred_name.strip()
        if not current or current == preferred:
            return False
        if self._contains_japanese(preferred) and not self._contains_japanese(current):
            return True
        return False

    def _is_placeholder_name(self, value: str | None, ticker_code: str) -> bool:
        if value is None:
            return True
        normalized = value.strip()
        return not normalized or normalized == ticker_code

    def _merge_profiles(self, base: SecurityProfile, preferred: SecurityProfile) -> SecurityProfile:
        return SecurityProfile(
            ticker_code=base.ticker_code,
            name=preferred.name if self.prefers_profile_name(base.name, base.ticker_code, preferred.name) else base.name,
            market=base.market or preferred.market,
            industry_17=base.industry_17 or preferred.industry_17,
            industry_33=base.industry_33 or preferred.industry_33,
            listed_date=base.listed_date or preferred.listed_date,
            source_as_of=base.source_as_of or preferred.source_as_of,
            local_code=base.local_code or preferred.local_code,
            name_english=base.name_english or preferred.name_english,
            ir_url=base.ir_url or preferred.ir_url,
            source=preferred.source if preferred.source != "internal" else base.source,
            aliases=tuple(dict.fromkeys((*base.aliases, *preferred.aliases))),
        )

    @staticmethod
    def _parse_date(value: object | None) -> date | None:
        text = str(value or "").strip()
        if not text:
            return None
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _contains_japanese(self, value: str) -> bool:
        return bool(re.search(r"[ぁ-んァ-ヶ一-龯々ー]", value))


security_profile_service = SecurityProfileService()
