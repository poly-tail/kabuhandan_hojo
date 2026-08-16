import asyncio
from datetime import date
from decimal import Decimal

import httpx
import pytest

from kabuhandan_hojo.connectors.base import ConnectorError
from kabuhandan_hojo.connectors.jquants import JQuantsConnector


class _FakeResponse:
    def __init__(self, *, url: str, status_code: int = 200, payload: dict) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", url)
        self.response = httpx.Response(status_code, request=self.request)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=self.response,
            )


def test_fetch_daily_bars_retries_with_five_digit_code(monkeypatch) -> None:
    calls: list[str] = []
    payloads = {
        "1306": {"daily_quotes": []},
        "13060": {
            "daily_quotes": [
                {
                    "Code": "13060",
                    "Date": "2026-04-01",
                    "Open": "2500",
                    "High": "2520",
                    "Low": "2495",
                    "Close": "2510",
                    "AdjustedClose": "2510",
                    "Volume": 100000,
                    "TurnoverValue": "100000000",
                }
            ]
        },
    }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> _FakeResponse:
            assert params is not None
            requested_code = str(params["code"])
            calls.append(requested_code)
            return _FakeResponse(url=url, payload=payloads[requested_code])

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")
    records = asyncio.run(
        connector.fetch_daily_bars(
            "1306",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 2),
        )
    )

    assert calls == ["1306", "13060"]
    assert len(records) == 1
    assert records[0].ticker_code == "1306"
    assert records[0].target_date == date(2026, 4, 1)
    assert records[0].close_price == Decimal("2510")


def test_fetch_listed_issues_uses_v2_equities_master_with_pagination(monkeypatch) -> None:
    calls: list[dict | None] = []
    payloads = [
        {
            "data": [
                {
                    "Date": "2026-04-23",
                    "Code": "72030",
                    "CoName": "トヨタ自動車",
                    "CoNameEn": "Toyota Motor Corporation",
                    "S17Nm": "自動車・輸送機",
                    "S33Nm": "輸送用機器",
                    "MktNm": "プライム",
                }
            ],
            "pagination_key": "next-page",
        },
        {
            "data": [
                {
                    "Date": "2026-04-23",
                    "Code": "83060",
                    "CoName": "三菱ＵＦＪフィナンシャル・グループ",
                    "CoNameEn": "Mitsubishi UFJ Financial Group, Inc.",
                    "S17Nm": "銀行",
                    "S33Nm": "銀行業",
                    "MktNm": "プライム",
                }
            ]
        },
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> _FakeResponse:
            assert url == "https://api.jquants.com/v2/equities/master"
            assert headers == {"x-api-key": "test-key"}
            calls.append(params)
            return _FakeResponse(url=url, payload=payloads[len(calls) - 1])

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")
    records = asyncio.run(connector.fetch_listed_issues())

    assert calls == [{}, {"pagination_key": "next-page"}]
    assert [record.ticker_code for record in records] == ["7203", "8306"]
    assert records[0].local_code == "72030"
    assert records[0].name == "トヨタ自動車"
    assert records[0].market == "プライム"
    assert records[0].industry_33 == "輸送用機器"


def test_fetch_daily_bars_converts_rate_limit_to_connector_error(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params: dict | None = None, headers: dict | None = None) -> _FakeResponse:
            return _FakeResponse(url=url, status_code=429, payload={"message": "rate limit exceeded"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    with pytest.raises(ConnectorError, match="429"):
        asyncio.run(
            connector.fetch_daily_bars(
                "1306",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 4, 2),
            )
        )
