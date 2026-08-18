from datetime import date
from types import SimpleNamespace

from app.models.security import SecurityMaster
from app.services.security_profile import SecurityProfileService


def test_jquants_profile_keeps_provider_code_and_separates_snapshot_date() -> None:
    profile = SecurityProfileService()._parse_jquants_payload(
        "285A",
        {
            "data": [
                {
                    "Code": "285A0",
                    "CoName": "キオクシアホールディングス",
                    "Date": "2026-05-26",
                    "ListingDate": "2024-12-18",
                    "S17Nm": "電機・精密",
                    "S33Nm": "電気機器",
                }
            ]
        },
    )

    assert profile is not None
    assert profile.ticker_code == "285A"
    assert profile.local_code == "285A0"
    assert profile.source_as_of == date(2026, 5, 26)
    assert profile.listed_date == date(2024, 12, 18)
    assert profile.industry_17 == "電機・精密"
    assert profile.industry_33 == "電気機器"


def test_jquants_profile_does_not_collapse_nonzero_numeric_suffix() -> None:
    service = SecurityProfileService()
    payload = {"data": [{"Code": "25935", "CoName": "Preferred", "Date": "2026-05-26"}]}

    assert service._parse_jquants_payload("2593", payload) is None
    profile = service._parse_jquants_payload("25935", payload)
    assert profile is not None
    assert profile.ticker_code == "25935"
    assert profile.local_code == "25935"


def test_database_profile_preserves_provider_code_industries_and_source_date() -> None:
    security = SecurityMaster(
        ticker_code="285A0",
        local_code="285A0",
        name="キオクシアホールディングス",
        market="Prime",
        industry_17="電機・精密",
        industry_33="電気機器",
        source_as_of=date(2026, 5, 26),
    )
    fake_session = SimpleNamespace(get=lambda model, key: security if key == "285A0" else None)

    profile = SecurityProfileService()._from_session(fake_session, "285A0")

    assert profile is not None
    assert profile.local_code == "285A0"
    assert profile.industry_17 == "電機・精密"
    assert profile.industry_33 == "電気機器"
    assert profile.source_as_of == date(2026, 5, 26)
