from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.security import SecurityMaster
from app.services.security_profile import security_profile_service
from app.services.watchlist import WatchlistService


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_security_search_matches_lowercase_alphanumeric_ticker_and_keeps_preferred_code() -> None:
    with _session() as session:
        session.add_all(
            [
                SecurityMaster(
                    ticker_code="285A",
                    local_code="285A0",
                    name="キオクシアホールディングス",
                    market="TSE Prime",
                    master_source="jquants",
                    is_active=True,
                ),
                SecurityMaster(
                    ticker_code="25935",
                    local_code="25935",
                    name="伊藤園第1種優先株式",
                    market="TSE Prime",
                    master_source="jquants",
                    is_active=True,
                ),
            ]
        )
        session.commit()

        lowercase_match = WatchlistService().search_candidates(session, "285a")
        preferred_match = WatchlistService().search_candidates(session, "25935")

    assert [item.ticker_code for item in lowercase_match] == ["285A"]
    assert lowercase_match[0].name == "キオクシアホールディングス"
    assert [item.ticker_code for item in preferred_match] == ["25935"]
    assert preferred_match[0].name == "伊藤園第1種優先株式"


def test_security_search_uses_ten_database_profiles_without_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls: list[str] = []
    monkeypatch.setattr(
        security_profile_service,
        "_fetch_from_jquants",
        lambda ticker_code: provider_calls.append(ticker_code),
    )

    with _session() as session:
        session.add_all(
            SecurityMaster(
                ticker_code=f"4{index:03d}",
                local_code=f"4{index:03d}0",
                name=f"検索候補 {index}",
                market="TSE Prime",
                master_source="jquants",
                is_active=True,
            )
            for index in range(10)
        )
        session.commit()

        matches = WatchlistService().search_candidates(session, "検索候補", limit=10)

    assert len(matches) == 10
    assert provider_calls == []


def test_security_search_placeholder_row_does_not_invoke_profile_resolution_or_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_calls: list[str] = []
    provider_calls: list[str] = []
    monkeypatch.setattr(
        security_profile_service,
        "resolve",
        lambda ticker_code, **kwargs: resolver_calls.append(ticker_code),
    )
    monkeypatch.setattr(
        security_profile_service,
        "_fetch_from_jquants",
        lambda ticker_code: provider_calls.append(ticker_code),
    )

    with _session() as session:
        session.add(
            SecurityMaster(
                ticker_code="4999",
                local_code="49990",
                name="4999",
                market=None,
                master_source="legacy",
                is_active=True,
            )
        )
        session.commit()

        matches = WatchlistService().search_candidates(session, "4999")

    assert [item.ticker_code for item in matches] == ["4999"]
    assert matches[0].name == "4999"
    assert resolver_calls == []
    assert provider_calls == []
