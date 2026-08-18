import asyncio
from datetime import date
from decimal import Decimal

import httpx
import pytest

from kabuhandan_hojo.connectors.base import ConnectorError
from kabuhandan_hojo.connectors.jquants import JQuantsConnector, normalize_jquants_master_code


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        status_code: int = 200,
        payload: dict,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
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
    assert records[0].source_as_of == date(2026, 4, 23)
    assert records[0].listed_date is None


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


def test_master_code_normalization_preserves_distinct_five_character_issues() -> None:
    assert normalize_jquants_master_code("25930") == "2593"
    assert normalize_jquants_master_code("25935") == "25935"
    assert normalize_jquants_master_code("285A0") == "285A0"


def test_fetch_listed_issues_keeps_ordinary_and_preferred_issues_distinct(monkeypatch) -> None:
    pairs = (("25930", "25935"), ("50760", "50765"), ("75500", "75505"))
    payload = {
        "data": [
            {
                "Date": "2026-05-26",
                "Code": raw_code,
                "CoName": f"Issue {raw_code}",
            }
            for pair in pairs
            for raw_code in pair
        ]
    }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params=None, headers=None) -> _FakeResponse:
            return _FakeResponse(url=url, payload=payload)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    records = asyncio.run(connector.fetch_listed_issues())

    assert [(record.ticker_code, record.local_code) for record in records] == [
        ("2593", "25930"),
        ("25935", "25935"),
        ("5076", "50760"),
        ("50765", "50765"),
        ("7550", "75500"),
        ("75505", "75505"),
    ]


def test_extract_listed_issue_keeps_source_date_separate_from_listing_date() -> None:
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    records = connector._extract_listed_issues(
        {
            "data": [
                {
                    "Date": "2026-05-26",
                    "ListingDate": "2025-12-17",
                    "Code": "285A0",
                    "CoName": "Test Alpha",
                }
            ]
        }
    )

    assert len(records) == 1
    assert records[0].ticker_code == "285A0"
    assert records[0].local_code == "285A0"
    assert records[0].source_as_of == date(2026, 5, 26)
    assert records[0].listed_date == date(2025, 12, 17)


def test_fetch_listed_issues_rejects_repeated_pagination_key(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params=None, headers=None) -> _FakeResponse:
            return _FakeResponse(
                url=url,
                payload={
                    "data": [{"Date": "2026-05-26", "Code": "72030", "CoName": "Toyota"}],
                    "pagination_key": "same-key",
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    with pytest.raises(ConnectorError, match="repeated pagination key"):
        asyncio.run(connector.fetch_listed_issues())


def test_fetch_listed_issues_retries_429_with_retry_after_and_backoff(monkeypatch) -> None:
    calls = 0
    delays: list[float] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params=None, headers=None) -> _FakeResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                return _FakeResponse(url=url, status_code=429, payload={}, headers={"Retry-After": "0"})
            if calls == 2:
                return _FakeResponse(url=url, status_code=429, payload={})
            return _FakeResponse(
                url=url,
                payload={"data": [{"Date": "2026-05-26", "Code": "72030", "CoName": "Toyota"}]},
            )

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    records = asyncio.run(connector.fetch_listed_issues())

    assert len(records) == 1
    assert calls == 3
    assert delays == [0.0, 2.0]


@pytest.mark.parametrize(
    ("transport_error", "expected_message"),
    [
        (httpx.ReadTimeout("private timeout detail"), "timed out"),
        (httpx.ConnectError("private network detail"), "network request failed"),
    ],
)
def test_fetch_listed_issues_wraps_transport_errors_without_leaking_detail(
    monkeypatch,
    transport_error: httpx.RequestError,
    expected_message: str,
) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params=None, headers=None) -> _FakeResponse:
            raise transport_error

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    with pytest.raises(ConnectorError, match=expected_message) as exc_info:
        asyncio.run(connector.fetch_listed_issues())

    assert "private" not in str(exc_info.value)
    assert "test-key" not in str(exc_info.value)


def test_fetch_listed_issues_rejects_invalid_json(monkeypatch) -> None:
    class InvalidJsonResponse(_FakeResponse):
        def json(self) -> dict:
            raise ValueError("private response body")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params=None, headers=None) -> _FakeResponse:
            return InvalidJsonResponse(url=url, payload={})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    with pytest.raises(ConnectorError, match="invalid JSON") as exc_info:
        asyncio.run(connector.fetch_listed_issues())

    assert "private response body" not in str(exc_info.value)


def test_fetch_listed_issues_http_error_excludes_provider_body(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, *, params=None, headers=None) -> _FakeResponse:
            return _FakeResponse(
                url=url,
                status_code=403,
                payload={"message": "private provider response body"},
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    connector = JQuantsConnector(base_url="https://api.jquants.com", api_key="test-key")

    with pytest.raises(ConnectorError, match="status 403") as exc_info:
        asyncio.run(connector.fetch_listed_issues())

    assert "private provider response body" not in str(exc_info.value)
    assert "test-key" not in str(exc_info.value)
