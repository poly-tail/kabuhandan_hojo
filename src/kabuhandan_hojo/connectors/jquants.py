"""J-Quants connector."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from kabuhandan_hojo.connectors.base import (
    ConnectorError,
    DailyBarRecord,
    ListedIssueRecord,
    MarginSnapshotRecord,
    MarketDataConnector,
    MissingCredentialsError,
)

logger = logging.getLogger(__name__)


def normalize_jquants_master_code(value: str) -> str:
    """Map an ordinary-share provider code to the existing public identifier.

    J-Quants uses five characters for issue identifiers.  A numeric trailing
    zero denotes the ordinary share represented by the familiar four-digit
    code, while a non-zero suffix can distinguish another listed issue (for
    example, a preferred share) and must therefore be retained.  Existing
    alphanumeric identifiers remain raw for backward compatibility.
    """

    normalized = value.strip().upper()
    if normalized.isdigit() and len(normalized) == 5 and normalized.endswith("0"):
        return normalized[:4]
    return normalized


class JQuantsConnector(MarketDataConnector):
    """Minimal J-Quants client wrapper.

    The concrete endpoints can evolve by subscription plan. The connector is
    isolated so path or field updates do not affect scoring or API layers.
    """

    MAX_LISTED_MASTER_PAGES = 1_000
    MAX_RATE_LIMIT_RETRIES = 2
    DEFAULT_RATE_LIMIT_DELAY_SECONDS = 1.0
    MAX_RATE_LIMIT_DELAY_SECONDS = 10.0

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def fetch_daily_bars(
        self,
        ticker_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyBarRecord]:
        self._require_api_key()
        url = f"{self.base_url}/v2/equities/bars/daily"
        async with httpx.AsyncClient(timeout=30.0) as client:
            for requested_code in self._candidate_codes(ticker_code):
                params: dict[str, Any] = {"code": requested_code}
                if start_date:
                    params["from"] = start_date.isoformat()
                if end_date:
                    params["to"] = end_date.isoformat()

                response = await client.get(url, params=params, headers={"x-api-key": self.api_key or ""})
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {400, 404}:
                        continue
                    raise self._connector_error_from_response(exc.response) from exc

                payload = response.json()
                records = self._extract_items(payload, requested_ticker_code=ticker_code)
                if records:
                    logger.info(
                        "Fetched %s daily bars for %s using J-Quants code %s",
                        len(records),
                        ticker_code,
                        requested_code,
                    )
                    return records

        logger.info("Fetched 0 daily bars for %s", ticker_code)
        return []

    async def fetch_listed_issues(self, as_of: date | None = None) -> list[ListedIssueRecord]:
        self._require_api_key()
        candidate_paths = (
            "/v2/equities/master",
            "/v1/listed/info",
            "/v1/listed/issues",
        )
        headers = {"x-api-key": self.api_key or ""}
        base_params: dict[str, Any] = {}
        if as_of is not None:
            base_params["date"] = as_of.isoformat()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for path in candidate_paths:
                issues: list[ListedIssueRecord] = []
                pagination_key: str | None = None
                seen_pagination_keys: set[str] = set()
                page_count = 0
                while True:
                    page_count += 1
                    if page_count > self.MAX_LISTED_MASTER_PAGES:
                        raise ConnectorError("J-Quants listed master pagination exceeded the safe page limit.")
                    params = dict(base_params)
                    if pagination_key:
                        params["pagination_key"] = pagination_key

                    response = await self._get_with_rate_limit_retry(
                        client,
                        f"{self.base_url}{path}",
                        params=params,
                        headers=headers,
                    )
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code in {400, 404} and not issues:
                            issues = []
                            break
                        raise self._connector_error_from_response(exc.response) from exc

                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise ConnectorError("J-Quants listed master returned invalid JSON.") from exc
                    if not isinstance(payload, dict):
                        raise ConnectorError("J-Quants listed master returned an invalid JSON object.")
                    issues.extend(self._extract_listed_issues(payload))
                    pagination_key = self._next_pagination_key(payload)
                    if not pagination_key:
                        break
                    if pagination_key in seen_pagination_keys:
                        raise ConnectorError("J-Quants listed master returned a repeated pagination key.")
                    seen_pagination_keys.add(pagination_key)

                if issues:
                    deduped_by_ticker: dict[str, ListedIssueRecord] = {}
                    for issue in issues:
                        existing = deduped_by_ticker.get(issue.ticker_code)
                        if existing is not None and existing.local_code != issue.local_code:
                            raise ConnectorError(
                                "J-Quants listed master contains conflicting provider codes "
                                f"for normalized identifier {issue.ticker_code}."
                            )
                        deduped_by_ticker[issue.ticker_code] = issue
                    deduped = list(deduped_by_ticker.values())
                    deduped.sort(key=lambda issue: issue.ticker_code)
                    logger.info("Fetched %s listed issues using J-Quants path %s", len(deduped), path)
                    return deduped

        logger.info("Fetched 0 listed issues from J-Quants")
        return []

    async def fetch_margin_snapshot(
        self,
        ticker_code: str,
        as_of: date | None = None,
    ) -> MarginSnapshotRecord | None:
        self._require_api_key()
        candidate_paths = (
            "/v2/markets/daily_margin_interest",
            "/v2/markets/weekly_margin_interest",
            "/v2/markets/margin_interest",
            "/v1/markets/daily_margin_interest",
            "/v1/markets/weekly_margin_interest",
            "/v1/markets/margin_interest",
        )
        normalized_code = self._normalize_local_code(ticker_code)
        headers = {"x-api-key": self.api_key or ""}
        async with httpx.AsyncClient(timeout=30.0) as client:
            for path in candidate_paths:
                for params in self._margin_params_candidates(normalized_code, as_of=as_of):
                    response = await client.get(f"{self.base_url}{path}", params=params, headers=headers)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code in {400, 404}:
                            continue
                        raise self._connector_error_from_response(exc.response) from exc
                    record = self._extract_margin_snapshot(response.json(), ticker_code=normalized_code, as_of=as_of)
                    if record is not None:
                        logger.info("Fetched margin snapshot for %s using J-Quants path %s", normalized_code, path)
                        return record
        logger.info("Fetched 0 margin snapshots for %s", normalized_code)
        return None

    def _extract_items(
        self,
        payload: dict[str, Any],
        *,
        requested_ticker_code: str | None = None,
    ) -> list[DailyBarRecord]:
        items = (
            payload.get("daily_quotes")
            or payload.get("daily_bars")
            or payload.get("prices")
            or payload.get("data")
            or []
        )
        results: list[DailyBarRecord] = []
        for item in items:
            results.append(
                DailyBarRecord(
                    ticker_code=(
                        requested_ticker_code
                        or str(item.get("LocalCode") or item.get("Code") or item.get("code"))
                    ),
                    target_date=date.fromisoformat(str(item.get("Date") or item.get("date"))[:10]),
                    open_price=Decimal(str(self._first_present(item, "Open", "O", "open"))),
                    high_price=Decimal(str(self._first_present(item, "High", "H", "high"))),
                    low_price=Decimal(str(self._first_present(item, "Low", "L", "low"))),
                    close_price=Decimal(str(self._first_present(item, "Close", "C", "close"))),
                    adjusted_close=(
                        Decimal(str(adjusted_close))
                        if (adjusted_close := self._first_present(item, "AdjustedClose", "AdjC", "adjusted_close")) is not None
                        else None
                    ),
                    volume=int(self._first_present(item, "Volume", "Vo", "volume") or 0),
                    turnover_value=(
                        Decimal(str(turnover_value))
                        if (turnover_value := self._first_present(item, "TurnoverValue", "Va", "turnover_value")) is not None
                        else None
                    ),
                    source_name="jquants",
                )
            )
        return results

    def _extract_listed_issues(self, payload: dict[str, Any]) -> list[ListedIssueRecord]:
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

        results: list[ListedIssueRecord] = []
        for item in items:
            raw_code = str(
                item.get("LocalCode")
                or item.get("Code")
                or item.get("code")
                or item.get("local_code")
                or ""
            ).strip()
            ticker_code = self._normalize_local_code(raw_code)
            name = (
                item.get("CompanyName")
                or item.get("CoName")
                or item.get("Name")
                or item.get("company_name")
                or item.get("name")
            )
            if not ticker_code or not name:
                continue

            source_as_of = self._parse_date(item.get("Date") or item.get("date"))
            listed_date = self._parse_date(
                item.get("ListingDate") or item.get("ListedDate") or item.get("listed_date")
            )

            results.append(
                ListedIssueRecord(
                    ticker_code=ticker_code,
                    local_code=raw_code or ticker_code,
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
                    market=(
                        item.get("MarketCodeName")
                        or item.get("MarketSegmentName")
                        or item.get("MarketName")
                        or item.get("MktNm")
                        or item.get("market")
                    ),
                    industry_17=item.get("Sector17CodeName") or item.get("S17Nm") or item.get("sector_17"),
                    industry_33=item.get("Sector33CodeName") or item.get("S33Nm") or item.get("sector_33"),
                    listed_date=listed_date,
                    source_as_of=source_as_of,
                    is_active=True,
                )
            )
        return results

    def _candidate_codes(self, ticker_code: str) -> list[str]:
        normalized = ticker_code.strip()
        if not normalized:
            return [ticker_code]

        candidates: list[str] = [normalized]
        if normalized.isdigit():
            if len(normalized) == 4:
                candidates.append(f"{normalized}0")
            elif len(normalized) == 5 and normalized.endswith("0"):
                candidates.append(normalized[:4])
        return list(dict.fromkeys(candidates))

    def _normalize_local_code(self, value: str) -> str:
        return normalize_jquants_master_code(value)

    async def _get_with_rate_limit_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        """GET one master page with a bounded Retry-After-aware 429 retry."""

        for attempt in range(self.MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = await client.get(url, params=params, headers=headers)
            except httpx.TimeoutException as exc:
                raise ConnectorError("J-Quants listed master request timed out.") from exc
            except httpx.RequestError as exc:
                raise ConnectorError("J-Quants listed master network request failed.") from exc
            if response.status_code != 429 or attempt >= self.MAX_RATE_LIMIT_RETRIES:
                return response
            retry_after = getattr(response, "headers", {}).get("Retry-After")
            try:
                delay = (
                    float(retry_after)
                    if retry_after is not None
                    else self.DEFAULT_RATE_LIMIT_DELAY_SECONDS * (2**attempt)
                )
            except (TypeError, ValueError):
                delay = self.DEFAULT_RATE_LIMIT_DELAY_SECONDS * (2**attempt)
            delay = max(0.0, min(delay, self.MAX_RATE_LIMIT_DELAY_SECONDS))
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    def _next_pagination_key(self, payload: dict[str, Any]) -> str | None:
        pagination = payload.get("pagination")
        if isinstance(pagination, dict):
            for key in ("key", "pagination_key", "next_key", "cursor", "next_cursor"):
                value = pagination.get(key)
                if value:
                    return str(value)
        for key in ("pagination_key", "next_page_token", "next_token", "cursor", "paginationToken"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    def _margin_params_candidates(self, ticker_code: str, *, as_of: date | None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        date_value = as_of.strftime("%Y-%m-%d") if as_of is not None else None
        compact_date_value = as_of.strftime("%Y%m%d") if as_of is not None else None
        for base in (
            {"code": ticker_code},
            {"LocalCode": ticker_code},
            {"stock_code": ticker_code},
        ):
            candidates.append(dict(base))
            if date_value is not None:
                for params in (
                    {"date": date_value},
                    {"date": compact_date_value},
                    {"from": date_value, "to": date_value},
                    {"from": compact_date_value, "to": compact_date_value},
                ):
                    merged = dict(base)
                    merged.update(params)
                    candidates.append(merged)
        return candidates

    def _extract_margin_snapshot(
        self,
        payload: dict[str, Any],
        *,
        ticker_code: str,
        as_of: date | None,
    ) -> MarginSnapshotRecord | None:
        items = (
            payload.get("margin_interest")
            or payload.get("weekly_margin_interest")
            or payload.get("daily_margin_interest")
            or payload.get("margin_trading_outstandings")
            or payload.get("data")
            or []
        )
        if isinstance(items, dict):
            items = [items]

        candidates: list[MarginSnapshotRecord] = []
        for item in items:
            raw_code = str(
                item.get("Code")
                or item.get("LocalCode")
                or item.get("code")
                or item.get("local_code")
                or item.get("stock_code")
                or ""
            ).strip()
            if self._normalize_local_code(raw_code) != ticker_code:
                continue

            raw_date = (
                item.get("Date")
                or item.get("TargetDate")
                or item.get("PublishedDate")
                or item.get("date")
            )
            if not raw_date:
                continue
            target_date = self._parse_date(raw_date)
            if target_date is None:
                continue
            if as_of is not None and target_date > as_of:
                continue

            buy_balance = self._decimal_from_aliases(
                item,
                "MarginBuyBalance",
                "BuyBalance",
                "LongBalance",
                "margin_buy_balance",
                "marginTradePurchaseBalance",
            )
            sell_balance = self._decimal_from_aliases(
                item,
                "MarginSellBalance",
                "SellBalance",
                "ShortBalance",
                "margin_sell_balance",
                "marginTradeSalesBalance",
            )
            if buy_balance is None and sell_balance is None:
                continue

            source_name = str(item.get("SourceName") or item.get("source_name") or "jquants")
            candidates.append(
                MarginSnapshotRecord(
                    ticker_code=ticker_code,
                    target_date=target_date,
                    margin_buy_balance=buy_balance,
                    margin_sell_balance=sell_balance,
                    source_name=source_name,
                )
            )

        if not candidates:
            return None
        candidates.sort(key=lambda record: record.target_date, reverse=True)
        return candidates[0]

    def _parse_date(self, value: object) -> date | None:
        text = str(value).strip()
        if not text:
            return None
        if len(text) == 8 and text.isdigit():
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _decimal_from_aliases(self, payload: dict[str, Any], *aliases: str) -> Decimal | None:
        for alias in aliases:
            value = payload.get(alias)
            if value is None:
                continue
            return Decimal(str(value))
        return None

    def _first_present(self, payload: dict[str, Any], *aliases: str) -> Any:
        for alias in aliases:
            value = payload.get(alias)
            if value is not None:
                return value
        return None

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise MissingCredentialsError("J-Quants API key is not configured.")

    def _connector_error_from_response(self, response: httpx.Response) -> ConnectorError:
        # Provider response bodies can contain operational or account-specific
        # details.  Keep the exception safe for logs and API error surfaces.
        return ConnectorError(f"J-Quants API request failed with status {response.status_code}.")
