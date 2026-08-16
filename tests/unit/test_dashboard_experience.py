from app.services.dashboard_experience import DashboardExperienceService


def test_reference_source_catalog_urls_and_display_names_cover_manual_reference_stack() -> None:
    service = DashboardExperienceService()

    expected = {
        "tdnet": ("TDnet", "https://www.jpx.co.jp/equities/listing/disclosure/tdnet/index.html"),
        "nikkei": ("日経新聞", "https://www.nikkei.com/"),
        "reuters": ("ロイター", "https://jp.reuters.com/"),
        "bloomberg": ("Bloomberg", "https://www.bloomberg.co.jp/"),
        "kabutan": ("株探", "https://kabutan.jp/"),
        "minkabu": ("みんかぶ", "https://minkabu.jp/"),
        "sbi": ("SBI証券", "https://www.sbisec.co.jp/"),
        "rakuten": ("楽天証券", "https://www.rakuten-sec.co.jp/"),
        "x": ("X", "https://x.com/"),
        "stocktwits": ("StockTwits", "https://stocktwits.com/"),
    }

    for source_name, (display_name, url) in expected.items():
        assert service._source_display_name(source_name) == display_name
        assert service._source_catalog_url(source_name, ticker_code=None) == url
