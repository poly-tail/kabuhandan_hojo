"""Mock monitoring data for dashboard, screening, and UI detail views."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from kabuhandan_hojo.schemas.alerts import AlertRead
from kabuhandan_hojo.schemas.dashboard import DashboardResponse, DashboardRow, ScreeningResult
from kabuhandan_hojo.schemas.events import EventRead
from kabuhandan_hojo.schemas.scores import ScoreRead
from kabuhandan_hojo.schemas.screening import FlowScreeningFilters, ScreeningFilterRequest, TechnicalScreeningFilters
from kabuhandan_hojo.schemas.securities import (
    FinancialSnapshotRead,
    FlowSnapshotRead,
    PriceBarRead,
    SecurityDetailResponse,
    SecurityRead,
    TechnicalFeatureRead,
)
from kabuhandan_hojo.services.insights import build_flow_context, build_technical_context, screening_reasons

DISCLAIMER_TEXT = (
    "このモック表示は日本株の判断補助を想定した暫定データです。"
    "売買を断定するものではなく、材料・地合い・反証条件の確認をしやすくするための検証用です。"
)
TOKYO_TIMEZONE = ZoneInfo("Asia/Tokyo")


def tokyo_today() -> date:
    return datetime.now(TOKYO_TIMEZONE).date()


class MockMonitoringService:
    """Return stable mock payloads for UI and API verification."""

    def get_dashboard(self) -> DashboardResponse:
        target_date = tokyo_today()
        latest_events = {event.ticker_code: event for event in self._recent_events(target_date) if event.ticker_code}
        alerts_by_ticker = self._alerts_by_ticker()
        rows: list[DashboardRow] = []

        for ticker_code in ("7203", "9984", "7974", "6758"):
            rows.append(
                DashboardRow(
                    security=self._security_map()[ticker_code],
                    latest_score=self._score_map(target_date)[ticker_code],
                    alerts=alerts_by_ticker[ticker_code],
                    latest_event=latest_events.get(ticker_code),
                )
            )

        return DashboardResponse(
            target_date=target_date,
            disclaimer=DISCLAIMER_TEXT,
            high_priority=rows,
            recent_events=self._recent_events(target_date),
            alerts=[alert for alerts in alerts_by_ticker.values() for alert in alerts],
        )

    def get_screening(self, min_total_score: Decimal, limit: int) -> list[ScreeningResult]:
        return self.get_screening_query(ScreeningFilterRequest(min_total_score=min_total_score, limit=limit))

    def get_screening_query(self, request: ScreeningFilterRequest) -> list[ScreeningResult]:
        target_date = tokyo_today()
        score_map = self._score_map(target_date)
        feature_map = self._feature_map(target_date)
        flow_map = self._flow_map(target_date)
        results: list[ScreeningResult] = []

        for ticker_code, security in self._security_map().items():
            score = score_map[ticker_code]
            feature = feature_map[ticker_code]
            flow = flow_map[ticker_code]
            if score.total_score < request.min_total_score:
                continue
            if not self._matches_technical_filters(feature, request.technical):
                continue
            if not self._matches_flow_filters(flow, request.flow):
                continue
            results.append(
                ScreeningResult(
                    security=security,
                    latest_score=score,
                    latest_features=feature,
                    latest_flow=flow,
                    matched_reasons=screening_reasons(feature, flow, score),
                )
            )

        results.sort(key=lambda item: item.latest_score.total_score if item.latest_score else Decimal("0"), reverse=True)
        return results[: request.limit]

    def get_security_detail(self, ticker_code: str) -> SecurityDetailResponse | None:
        target_date = tokyo_today()
        security = self._security_map().get(ticker_code)
        if security is None:
            return None

        score = self._score_map(target_date).get(ticker_code)
        feature = self._feature_map(target_date).get(ticker_code)
        flow = self._flow_map(target_date).get(ticker_code)

        return SecurityDetailResponse(
            security=security,
            latest_score=score,
            latest_features=feature,
            technical_context=build_technical_context(feature, score),
            recent_events=[event for event in self._recent_events(target_date) if event.ticker_code == ticker_code],
            latest_financials=self._financial_map(target_date).get(ticker_code),
            latest_flow=flow,
            flow_context=build_flow_context(flow, feature, score),
            latest_prices=self._price_map(target_date).get(ticker_code, []),
            updated_at=datetime.combine(target_date, time(hour=7, minute=0), tzinfo=timezone.utc),
        )

    def has_security(self, ticker_code: str) -> bool:
        return ticker_code in self._security_map()

    def get_alerts_for_ticker(self, ticker_code: str) -> list[AlertRead]:
        return list(self._alerts_by_ticker().get(ticker_code, []))

    def _security_map(self) -> dict[str, SecurityRead]:
        return {
            "7203": SecurityRead(
                ticker_code="7203",
                local_code="7203",
                name="トヨタ自動車",
                market="TSE Prime",
                industry_17="Automobiles",
                industry_33="Transportation Equipment",
                is_active=True,
                listed_date=date(1949, 5, 16),
            ),
            "9984": SecurityRead(
                ticker_code="9984",
                local_code="9984",
                name="ソフトバンクグループ",
                market="TSE Prime",
                industry_17="Information & Communication",
                industry_33="Information & Communication",
                is_active=True,
                listed_date=date(1994, 7, 22),
            ),
            "7974": SecurityRead(
                ticker_code="7974",
                local_code="7974",
                name="任天堂",
                market="TSE Prime",
                industry_17="Other Products",
                industry_33="Other Products",
                is_active=True,
                listed_date=date(1962, 1, 1),
            ),
            "6758": SecurityRead(
                ticker_code="6758",
                local_code="6758",
                name="ソニーグループ",
                market="TSE Prime",
                industry_17="Electrical Appliances",
                industry_33="Electrical Appliances",
                is_active=True,
                listed_date=date(1958, 12, 1),
            ),
            "8035": SecurityRead(
                ticker_code="8035",
                local_code="8035",
                name="東京エレクトロン",
                market="TSE Prime",
                industry_17="Machinery",
                industry_33="Electronics Equipment",
                is_active=True,
                listed_date=date(1963, 11, 11),
            ),
        }

    def _score_map(self, target_date: date) -> dict[str, ScoreRead]:
        return {
            "7203": ScoreRead(
                id=101,
                ticker_code="7203",
                target_date=target_date,
                event_score=Decimal("25.0"),
                fundamental_score=Decimal("20.5"),
                technical_score=Decimal("78.0"),
                flow_score=Decimal("72.0"),
                risk_penalty=Decimal("12.0"),
                total_score=Decimal("81.5"),
                explanation_summary="上方修正後の出来高増加と移動平均線の並びが支えになっています。",
                calculation_version="mock-v3",
                score_breakdown={
                    "technical_subscores": {
                        "trend": 82.0,
                        "momentum": 74.0,
                        "volatility": 58.0,
                        "price_action": 64.0,
                        "volume_confirmation": 80.0,
                    },
                    "flow_subscores": {
                        "liquidity": 74.0,
                        "positioning": 68.0,
                        "squeeze_potential": 62.0,
                    },
                },
                missing_data_flags=[],
            ),
            "9984": ScoreRead(
                id=102,
                ticker_code="9984",
                target_date=target_date,
                event_score=Decimal("22.0"),
                fundamental_score=Decimal("17.0"),
                technical_score=Decimal("71.0"),
                flow_score=Decimal("74.0"),
                risk_penalty=Decimal("14.0"),
                total_score=Decimal("76.0"),
                explanation_summary="還元材料は強い一方で、信用需給と地合い悪化時の振れ幅に注意が必要です。",
                calculation_version="mock-v3",
                score_breakdown={
                    "technical_subscores": {
                        "trend": 74.0,
                        "momentum": 66.0,
                        "volatility": 54.0,
                        "price_action": 55.0,
                        "volume_confirmation": 69.0,
                    },
                    "flow_subscores": {
                        "liquidity": 72.0,
                        "positioning": 58.0,
                        "squeeze_potential": 77.0,
                    },
                },
                missing_data_flags=["youtube_signal_pending"],
            ),
            "7974": ScoreRead(
                id=103,
                ticker_code="7974",
                target_date=target_date,
                event_score=Decimal("21.0"),
                fundamental_score=Decimal("16.0"),
                technical_score=Decimal("67.0"),
                flow_score=Decimal("63.0"),
                risk_penalty=Decimal("12.0"),
                total_score=Decimal("71.7"),
                explanation_summary="次世代機期待は追い風ですが、期待先行になりやすく反証条件の固定が必要です。",
                calculation_version="mock-v3",
                score_breakdown={
                    "technical_subscores": {
                        "trend": 68.0,
                        "momentum": 63.0,
                        "volatility": 57.0,
                        "price_action": 52.0,
                        "volume_confirmation": 61.0,
                    },
                    "flow_subscores": {
                        "liquidity": 60.0,
                        "positioning": 57.0,
                        "squeeze_potential": 59.0,
                    },
                },
                missing_data_flags=[],
            ),
            "6758": ScoreRead(
                id=104,
                ticker_code="6758",
                target_date=target_date,
                event_score=Decimal("18.5"),
                fundamental_score=Decimal("18.0"),
                technical_score=Decimal("64.0"),
                flow_score=Decimal("60.0"),
                risk_penalty=Decimal("14.0"),
                total_score=Decimal("67.8"),
                explanation_summary="還元強化は支えですが、主力事業の進捗確認を継続したい局面です。",
                calculation_version="mock-v3",
                score_breakdown={
                    "technical_subscores": {
                        "trend": 66.0,
                        "momentum": 60.0,
                        "volatility": 56.0,
                        "price_action": 50.0,
                        "volume_confirmation": 58.0,
                    },
                    "flow_subscores": {
                        "liquidity": 58.0,
                        "positioning": 56.0,
                        "squeeze_potential": 55.0,
                    },
                },
                missing_data_flags=[],
            ),
            "8035": ScoreRead(
                id=105,
                ticker_code="8035",
                target_date=target_date,
                event_score=Decimal("16.0"),
                fundamental_score=Decimal("17.5"),
                technical_score=Decimal("69.0"),
                flow_score=Decimal("59.0"),
                risk_penalty=Decimal("16.0"),
                total_score=Decimal("64.2"),
                explanation_summary="セクター追い風はありますが、個別材料の確認がまだ薄い状態です。",
                calculation_version="mock-v3",
                score_breakdown={
                    "technical_subscores": {
                        "trend": 72.0,
                        "momentum": 64.0,
                        "volatility": 52.0,
                        "price_action": 48.0,
                        "volume_confirmation": 67.0,
                    },
                    "flow_subscores": {
                        "liquidity": 55.0,
                        "positioning": 54.0,
                        "squeeze_potential": 58.0,
                    },
                },
                missing_data_flags=["ir_summary_pending"],
            ),
        }

    def _feature_map(self, target_date: date) -> dict[str, TechnicalFeatureRead]:
        return {
            "7203": self._feature(
                target_date=target_date,
                ticker_code="7203",
                sma_5="3812",
                sma_25="3694",
                sma_75="3528",
                sma_200="3320",
                sma_5_slope_pct="2.1",
                sma_25_slope_pct="4.8",
                sma_75_slope_pct="3.0",
                deviation_from_sma_25_pct="3.4",
                deviation_from_sma_75_pct="8.1",
                ma_gap_5_25_pct="3.2",
                ma_gap_25_75_pct="4.7",
                golden_cross_flag=True,
                breakout_20d=True,
                volume_ratio_20="1.9",
                volume_surge_ratio="1.9",
                atr_14="88",
                atr_pct_14="2.2",
                rsi_14="63",
                roc_20="8.4",
                macd_line="32.4",
                macd_signal="27.9",
                macd_histogram="4.5",
                macd_bullish_cross_flag=True,
                bollinger_mid_20="3694",
                bollinger_upper_20="3858",
                bollinger_lower_20="3530",
                bollinger_width_20="8.9",
                upper_wick_ratio="0.18",
                lower_wick_ratio="0.24",
                body_ratio="0.40",
                close_position_ratio="0.76",
                gap_pct="0.8",
                gap_up_flag=True,
                consecutive_up_candles=3,
                range_compression_20="0.72",
            ),
            "9984": self._feature(
                target_date=target_date,
                ticker_code="9984",
                sma_5="9360",
                sma_25="9110",
                sma_75="8870",
                sma_200="8605",
                sma_5_slope_pct="1.4",
                sma_25_slope_pct="3.2",
                sma_75_slope_pct="2.1",
                deviation_from_sma_25_pct="2.9",
                deviation_from_sma_75_pct="5.8",
                ma_gap_5_25_pct="2.7",
                ma_gap_25_75_pct="2.7",
                golden_cross_flag=True,
                breakout_20d=True,
                volume_ratio_20="1.7",
                volume_surge_ratio="1.7",
                atr_14="182",
                atr_pct_14="3.1",
                rsi_14="59",
                roc_20="7.2",
                macd_line="21.2",
                macd_signal="17.8",
                macd_histogram="3.4",
                macd_bullish_cross_flag=True,
                bollinger_mid_20="9110",
                bollinger_upper_20="9498",
                bollinger_lower_20="8722",
                bollinger_width_20="8.5",
                upper_wick_ratio="0.29",
                lower_wick_ratio="0.14",
                body_ratio="0.34",
                close_position_ratio="0.62",
                gap_pct="0.5",
                gap_up_flag=True,
                consecutive_up_candles=2,
                range_compression_20="0.74",
            ),
            "7974": self._feature(
                target_date=target_date,
                ticker_code="7974",
                sma_5="8070",
                sma_25="7892",
                sma_75="7688",
                sma_200="7410",
                sma_5_slope_pct="1.1",
                sma_25_slope_pct="2.8",
                sma_75_slope_pct="1.5",
                deviation_from_sma_25_pct="2.1",
                deviation_from_sma_75_pct="4.8",
                ma_gap_5_25_pct="2.3",
                ma_gap_25_75_pct="2.7",
                breakout_20d=True,
                volume_ratio_20="1.4",
                volume_surge_ratio="1.4",
                atr_14="140",
                atr_pct_14="1.9",
                rsi_14="58",
                roc_20="5.8",
                macd_line="15.8",
                macd_signal="14.6",
                macd_histogram="1.2",
                bollinger_mid_20="7892",
                bollinger_upper_20="8176",
                bollinger_lower_20="7608",
                bollinger_width_20="7.2",
                upper_wick_ratio="0.37",
                lower_wick_ratio="0.16",
                body_ratio="0.28",
                close_position_ratio="0.44",
                gap_pct="0.4",
                consecutive_up_candles=2,
                range_compression_20="0.78",
            ),
            "6758": self._feature(
                target_date=target_date,
                ticker_code="6758",
                sma_5="14310",
                sma_25="13980",
                sma_75="13240",
                sma_200="12820",
                sma_5_slope_pct="1.7",
                sma_25_slope_pct="5.1",
                sma_75_slope_pct="2.8",
                deviation_from_sma_25_pct="2.6",
                deviation_from_sma_75_pct="8.3",
                ma_gap_5_25_pct="2.4",
                ma_gap_25_75_pct="5.6",
                breakout_60d=True,
                volume_ratio_20="1.6",
                volume_surge_ratio="1.6",
                atr_14="245",
                atr_pct_14="1.8",
                rsi_14="60",
                roc_20="6.9",
                macd_line="44.1",
                macd_signal="41.2",
                macd_histogram="2.9",
                bollinger_mid_20="13980",
                bollinger_upper_20="14540",
                bollinger_lower_20="13420",
                bollinger_width_20="8.0",
                upper_wick_ratio="0.22",
                lower_wick_ratio="0.18",
                body_ratio="0.33",
                close_position_ratio="0.63",
                gap_pct="0.3",
                consecutive_up_candles=1,
                range_compression_20="0.69",
            ),
            "8035": self._feature(
                target_date=target_date,
                ticker_code="8035",
                sma_5="38240",
                sma_25="36880",
                sma_75="35120",
                sma_200="33440",
                sma_5_slope_pct="2.9",
                sma_25_slope_pct="6.2",
                sma_75_slope_pct="3.9",
                deviation_from_sma_25_pct="4.1",
                deviation_from_sma_75_pct="9.4",
                ma_gap_5_25_pct="3.7",
                ma_gap_25_75_pct="5.0",
                breakout_20d=True,
                breakout_60d=True,
                volume_ratio_20="2.2",
                volume_surge_ratio="2.2",
                atr_14="940",
                atr_pct_14="2.5",
                rsi_14="67",
                roc_20="10.2",
                macd_line="116.2",
                macd_signal="104.8",
                macd_histogram="11.4",
                macd_bullish_cross_flag=True,
                bollinger_mid_20="36880",
                bollinger_upper_20="39040",
                bollinger_lower_20="34720",
                bollinger_width_20="11.7",
                upper_wick_ratio="0.30",
                lower_wick_ratio="0.12",
                body_ratio="0.41",
                close_position_ratio="0.58",
                gap_pct="1.1",
                gap_up_flag=True,
                consecutive_up_candles=4,
                range_compression_20="0.66",
            ),
        }

    def _feature(self, *, target_date: date, ticker_code: str, **kwargs: object) -> TechnicalFeatureRead:
        numeric_keys = {
            "sma_5",
            "sma_25",
            "sma_75",
            "sma_200",
            "sma_5_slope_pct",
            "sma_25_slope_pct",
            "sma_75_slope_pct",
            "deviation_from_sma_25_pct",
            "deviation_from_sma_75_pct",
            "ma_gap_5_25_pct",
            "ma_gap_25_75_pct",
            "volume_ratio_20",
            "volume_surge_ratio",
            "atr_14",
            "atr_pct_14",
            "rsi_14",
            "roc_20",
            "macd_line",
            "macd_signal",
            "macd_histogram",
            "bollinger_mid_20",
            "bollinger_upper_20",
            "bollinger_lower_20",
            "bollinger_width_20",
            "upper_wick_ratio",
            "lower_wick_ratio",
            "body_ratio",
            "close_position_ratio",
            "gap_pct",
            "range_compression_20",
        }
        payload = {"id": int(ticker_code), "ticker_code": ticker_code, "target_date": target_date}
        for key, value in kwargs.items():
            if key in numeric_keys and value is not None:
                payload[key] = Decimal(str(value))
            else:
                payload[key] = value
        return TechnicalFeatureRead(**payload)

    def _financial_map(self, target_date: date) -> dict[str, FinancialSnapshotRead]:
        return {
            "7203": FinancialSnapshotRead(
                id=301,
                ticker_code="7203",
                target_date=target_date - timedelta(days=20),
                revenue=Decimal("12450000"),
                operating_profit=Decimal("1280000"),
                ordinary_profit=Decimal("1350000"),
                net_income=Decimal("980000"),
                revenue_growth_yoy=Decimal("8.2"),
                operating_profit_growth_yoy=Decimal("16.4"),
                operating_margin=Decimal("10.3"),
                roe=Decimal("11.9"),
                equity_ratio=Decimal("39.8"),
                source_name="mock",
            ),
            "9984": FinancialSnapshotRead(
                id=302,
                ticker_code="9984",
                target_date=target_date - timedelta(days=30),
                revenue=Decimal("1650000"),
                operating_profit=Decimal("325000"),
                ordinary_profit=Decimal("299000"),
                net_income=Decimal("241000"),
                revenue_growth_yoy=Decimal("5.4"),
                operating_profit_growth_yoy=Decimal("12.2"),
                operating_margin=Decimal("19.7"),
                roe=Decimal("10.8"),
                equity_ratio=Decimal("25.1"),
                source_name="mock",
            ),
            "7974": FinancialSnapshotRead(
                id=303,
                ticker_code="7974",
                target_date=target_date - timedelta(days=18),
                revenue=Decimal("403000"),
                operating_profit=Decimal("118000"),
                ordinary_profit=Decimal("125000"),
                net_income=Decimal("93000"),
                revenue_growth_yoy=Decimal("4.1"),
                operating_profit_growth_yoy=Decimal("6.8"),
                operating_margin=Decimal("29.3"),
                roe=Decimal("14.4"),
                equity_ratio=Decimal("72.0"),
                source_name="mock",
            ),
            "6758": FinancialSnapshotRead(
                id=304,
                ticker_code="6758",
                target_date=target_date - timedelta(days=24),
                revenue=Decimal("3350000"),
                operating_profit=Decimal("412000"),
                ordinary_profit=Decimal("438000"),
                net_income=Decimal("312000"),
                revenue_growth_yoy=Decimal("6.2"),
                operating_profit_growth_yoy=Decimal("9.4"),
                operating_margin=Decimal("12.3"),
                roe=Decimal("10.1"),
                equity_ratio=Decimal("31.0"),
                source_name="mock",
            ),
            "8035": FinancialSnapshotRead(
                id=305,
                ticker_code="8035",
                target_date=target_date - timedelta(days=26),
                revenue=Decimal("612000"),
                operating_profit=Decimal("161000"),
                ordinary_profit=Decimal("167000"),
                net_income=Decimal("123000"),
                revenue_growth_yoy=Decimal("14.0"),
                operating_profit_growth_yoy=Decimal("21.8"),
                operating_margin=Decimal("26.3"),
                roe=Decimal("20.4"),
                equity_ratio=Decimal("63.0"),
                source_name="mock",
            ),
        }

    def _flow_map(self, target_date: date) -> dict[str, FlowSnapshotRead]:
        return {
            "7203": self._flow(
                target_date=target_date,
                ticker_code="7203",
                average_daily_volume_20=18_000_000,
                volume_ratio_20="1.9",
                margin_buy_ratio="1.2",
                margin_buy_balance="1480000",
                margin_sell_balance="1120000",
                credit_ratio="1.32",
                buy_balance_change_wow="2.4",
                sell_balance_change_wow="4.1",
                buy_balance_to_volume="0.0822",
                sell_balance_to_volume="0.0622",
                squeeze_potential_subscore="61.0",
                short_interest_ratio="0.1",
                float_turnover_ratio="1.6",
                large_holder_activity_score="19.0",
            ),
            "9984": self._flow(
                target_date=target_date,
                ticker_code="9984",
                average_daily_volume_20=9_200_000,
                volume_ratio_20="1.7",
                margin_buy_ratio="1.4",
                margin_buy_balance="1680000",
                margin_sell_balance="920000",
                credit_ratio="1.83",
                buy_balance_change_wow="6.4",
                sell_balance_change_wow="7.8",
                buy_balance_to_volume="0.1826",
                sell_balance_to_volume="0.1000",
                squeeze_potential_subscore="77.0",
                short_interest_ratio="0.3",
                float_turnover_ratio="1.9",
                large_holder_activity_score="23.0",
            ),
            "7974": self._flow(
                target_date=target_date,
                ticker_code="7974",
                average_daily_volume_20=4_200_000,
                volume_ratio_20="1.4",
                margin_buy_ratio="1.1",
                margin_buy_balance="980000",
                margin_sell_balance="770000",
                credit_ratio="1.27",
                buy_balance_change_wow="5.2",
                sell_balance_change_wow="2.4",
                buy_balance_to_volume="0.2333",
                sell_balance_to_volume="0.1833",
                squeeze_potential_subscore="59.0",
                short_interest_ratio="0.1",
                float_turnover_ratio="1.0",
                large_holder_activity_score="14.0",
            ),
            "6758": self._flow(
                target_date=target_date,
                ticker_code="6758",
                average_daily_volume_20=3_600_000,
                volume_ratio_20="1.6",
                margin_buy_ratio="1.0",
                margin_buy_balance="860000",
                margin_sell_balance="720000",
                credit_ratio="1.19",
                buy_balance_change_wow="2.0",
                sell_balance_change_wow="3.8",
                buy_balance_to_volume="0.2389",
                sell_balance_to_volume="0.2000",
                squeeze_potential_subscore="55.0",
                short_interest_ratio="0.2",
                float_turnover_ratio="0.9",
                large_holder_activity_score="18.0",
            ),
            "8035": self._flow(
                target_date=target_date,
                ticker_code="8035",
                average_daily_volume_20=1_600_000,
                volume_ratio_20="2.2",
                margin_buy_ratio="0.9",
                margin_buy_balance="580000",
                margin_sell_balance="660000",
                credit_ratio="0.88",
                buy_balance_change_wow="1.2",
                sell_balance_change_wow="6.2",
                buy_balance_to_volume="0.3625",
                sell_balance_to_volume="0.4125",
                squeeze_potential_subscore="68.0",
                short_interest_ratio="0.2",
                float_turnover_ratio="1.8",
                large_holder_activity_score="16.0",
            ),
        }

    def _flow(self, *, target_date: date, ticker_code: str, **kwargs: object) -> FlowSnapshotRead:
        numeric_keys = {
            "volume_ratio_20",
            "margin_buy_ratio",
            "margin_buy_balance",
            "margin_sell_balance",
            "credit_ratio",
            "buy_balance_change_wow",
            "sell_balance_change_wow",
            "buy_balance_to_volume",
            "sell_balance_to_volume",
            "squeeze_potential_subscore",
            "short_interest_ratio",
            "float_turnover_ratio",
            "large_holder_activity_score",
        }
        payload = {"id": int(ticker_code), "ticker_code": ticker_code, "target_date": target_date, "source_name": "mock"}
        for key, value in kwargs.items():
            if key in numeric_keys and value is not None:
                payload[key] = Decimal(str(value))
            else:
                payload[key] = value
        return FlowSnapshotRead(**payload)

    def _price_map(self, target_date: date) -> dict[str, list[PriceBarRead]]:
        return {
            "7203": self._price_series("7203", target_date, Decimal("3470"), Decimal("14")),
            "9984": self._price_series("9984", target_date, Decimal("8750"), Decimal("23")),
            "7974": self._price_series("7974", target_date, Decimal("7520"), Decimal("11")),
            "6758": self._price_series("6758", target_date, Decimal("13520"), Decimal("28")),
            "8035": self._price_series("8035", target_date, Decimal("35100"), Decimal("95")),
        }

    def _price_series(
        self,
        ticker_code: str,
        target_date: date,
        base_close: Decimal,
        daily_step: Decimal,
        days: int = 30,
    ) -> list[PriceBarRead]:
        series: list[PriceBarRead] = []
        for offset in range(days):
            day = target_date - timedelta(days=days - offset - 1)
            close_price = base_close + daily_step * Decimal(offset)
            open_price = close_price - Decimal("12")
            high_price = close_price + Decimal("18")
            low_price = close_price - Decimal("20")
            series.append(
                PriceBarRead(
                    id=5000 + offset,
                    ticker_code=ticker_code,
                    target_date=day,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    adjusted_close=close_price,
                    volume=1_200_000 + offset * 15_000,
                    turnover_value=close_price * Decimal(1_200_000 + offset * 15_000),
                    source_name="mock",
                )
            )
        return series

    def _recent_events(self, target_date: date) -> list[EventRead]:
        base = datetime.combine(target_date, time(hour=7, minute=0), tzinfo=timezone.utc)
        return [
            EventRead(
                event_id="mock-evt-001",
                ticker_code="7203",
                event_type="upward_revision",
                event_time=base - timedelta(hours=2),
                source_name="timely_disclosure",
                importance_hint=Decimal("0.93"),
                summary_text="通期見通しの引き上げと主力市場の販売計画の上方修正を発表しました。",
                raw_reference="mock://timely/7203/1",
                metadata_json={"source_class": "allowlisted_ir"},
            ),
            EventRead(
                event_id="mock-evt-002",
                ticker_code="9984",
                event_type="shareholder_return",
                event_time=base - timedelta(hours=4),
                source_name="timely_disclosure",
                importance_hint=Decimal("0.86"),
                summary_text="自己株取得枠の更新と資産売却方針の継続を示しました。",
                raw_reference="mock://timely/9984/1",
                metadata_json={"source_class": "allowlisted_ir"},
            ),
            EventRead(
                event_id="mock-evt-003",
                ticker_code="7974",
                event_type="product_cycle",
                event_time=base - timedelta(hours=7),
                source_name="timely_disclosure",
                importance_hint=Decimal("0.79"),
                summary_text="次世代機関連の準備状況に言及し、ソフトラインアップ拡充を示しました。",
                raw_reference="mock://timely/7974/1",
                metadata_json={"source_class": "allowlisted_ir"},
            ),
            EventRead(
                event_id="mock-evt-004",
                ticker_code="6758",
                event_type="shareholder_return",
                event_time=base - timedelta(hours=10),
                source_name="timely_disclosure",
                importance_hint=Decimal("0.73"),
                summary_text="追加還元方針と事業ポートフォリオ整理の継続を示しました。",
                raw_reference="mock://timely/6758/1",
                metadata_json={"source_class": "allowlisted_ir"},
            ),
            EventRead(
                event_id="mock-evt-005",
                ticker_code="8035",
                event_type="sector_strength",
                event_time=base - timedelta(days=1, hours=3),
                source_name="jquants",
                importance_hint=Decimal("0.68"),
                summary_text="半導体設備セクター全体の強さが続き、候補としての優先度が上がりました。",
                raw_reference="mock://jquants/8035/1",
                metadata_json={"source_class": "jquants"},
            ),
            EventRead(
                event_id="mock-evt-006",
                ticker_code="7203",
                event_type="volume_expansion",
                event_time=base - timedelta(days=1, hours=6),
                source_name="jquants",
                importance_hint=Decimal("0.62"),
                summary_text="20日平均を上回る出来高が入り、価格変化の裏付けが確認されました。",
                raw_reference="mock://jquants/7203/2",
                metadata_json={"source_class": "jquants"},
            ),
            EventRead(
                event_id="mock-evt-007",
                ticker_code="9984",
                event_type="dilution_risk",
                event_time=base - timedelta(days=1, hours=9),
                source_name="analysis",
                importance_hint=Decimal("0.58"),
                summary_text="主要保有資産の値動き次第では評価損益が振れやすく、需給悪化に注意が必要です。",
                raw_reference="mock://analysis/9984/1",
                metadata_json={"source_class": "derived"},
            ),
            EventRead(
                event_id="mock-evt-008",
                ticker_code="7974",
                event_type="volume_expansion",
                event_time=base - timedelta(days=2, hours=1),
                source_name="jquants",
                importance_hint=Decimal("0.44"),
                summary_text="個人投資家主導の売買が増え、期待先行の動きが強まりました。",
                raw_reference="mock://jquants/7974/2",
                metadata_json={"source_class": "jquants"},
            ),
        ]

    def _alerts_by_ticker(self) -> dict[str, list[AlertRead]]:
        return {
            "7203": [
                AlertRead(
                    ticker_code="7203",
                    alert_type="high_priority",
                    severity="high",
                    message="上方修正直後で、個別要因の確認優先度が高い状態です。",
                ),
                AlertRead(
                    ticker_code="7203",
                    alert_type="breakout_volume",
                    severity="medium",
                    message="出来高を伴っており、初動か一過性かを確認したい局面です。",
                ),
            ],
            "9984": [
                AlertRead(
                    ticker_code="9984",
                    alert_type="high_priority",
                    severity="high",
                    message="還元材料は強い一方で、地合い悪化時の振れ幅に注意が必要です。",
                ),
                AlertRead(
                    ticker_code="9984",
                    alert_type="risk_event",
                    severity="high",
                    message="保有資産の値動きによる評価損益の振れを確認してください。",
                ),
            ],
            "7974": [
                AlertRead(
                    ticker_code="7974",
                    alert_type="thesis_check",
                    severity="medium",
                    message="期待先行になりやすく、発売時期や販売計画の反証条件を固定したい状態です。",
                )
            ],
            "6758": [
                AlertRead(
                    ticker_code="6758",
                    alert_type="trend_follow",
                    severity="medium",
                    message="還元強化は支えですが、主力事業の進捗確認を継続してください。",
                )
            ],
            "8035": [
                AlertRead(
                    ticker_code="8035",
                    alert_type="screening_candidate",
                    severity="medium",
                    message="セクター追い風はありますが、個別材料の確認がまだ必要です。",
                )
            ],
        }

    def _matches_technical_filters(
        self,
        feature: TechnicalFeatureRead | None,
        filters: TechnicalScreeningFilters | None,
    ) -> bool:
        if filters is None:
            return True
        if feature is None:
            return False
        if filters.min_rsi_14 is not None and (feature.rsi_14 is None or feature.rsi_14 < filters.min_rsi_14):
            return False
        if filters.max_rsi_14 is not None and (feature.rsi_14 is None or feature.rsi_14 > filters.max_rsi_14):
            return False
        if filters.macd_cross == "bullish" and not feature.macd_bullish_cross_flag:
            return False
        if filters.macd_cross == "bearish" and not feature.macd_bearish_cross_flag:
            return False
        if filters.macd_histogram_positive is True and (feature.macd_histogram is None or feature.macd_histogram <= 0):
            return False
        if filters.macd_histogram_positive is False and (feature.macd_histogram is None or feature.macd_histogram >= 0):
            return False
        if filters.price_above_ma_25 is True and (feature.price_vs_ma_25 is None or feature.price_vs_ma_25 <= 0):
            return False
        if filters.price_above_ma_75 is True and (feature.price_vs_ma_75 is None or feature.price_vs_ma_75 <= 0):
            return False
        if filters.golden_cross_only and not feature.golden_cross_flag:
            return False
        if filters.dead_cross_exclude and feature.dead_cross_flag:
            return False
        if filters.min_volume_surge_ratio is not None and (
            feature.volume_surge_ratio is None or feature.volume_surge_ratio < filters.min_volume_surge_ratio
        ):
            return False
        if filters.min_upper_wick_ratio is not None and (
            feature.upper_wick_ratio is None or feature.upper_wick_ratio < filters.min_upper_wick_ratio
        ):
            return False
        if filters.max_upper_wick_ratio is not None and (
            feature.upper_wick_ratio is None or feature.upper_wick_ratio > filters.max_upper_wick_ratio
        ):
            return False
        if filters.min_lower_wick_ratio is not None and (
            feature.lower_wick_ratio is None or feature.lower_wick_ratio < filters.min_lower_wick_ratio
        ):
            return False
        if filters.gap_up_only and not feature.gap_up_flag:
            return False
        if filters.gap_down_exclude and feature.gap_down_flag:
            return False
        return True

    def _matches_flow_filters(self, flow: FlowSnapshotRead | None, filters: FlowScreeningFilters | None) -> bool:
        if filters is None:
            return True
        if flow is None:
            return False
        if filters.min_credit_ratio is not None and (flow.credit_ratio is None or flow.credit_ratio < filters.min_credit_ratio):
            return False
        if filters.max_credit_ratio is not None and (flow.credit_ratio is None or flow.credit_ratio > filters.max_credit_ratio):
            return False
        if filters.min_buy_balance_change_wow is not None and (
            flow.buy_balance_change_wow is None or flow.buy_balance_change_wow < filters.min_buy_balance_change_wow
        ):
            return False
        if filters.max_buy_balance_change_wow is not None and (
            flow.buy_balance_change_wow is None or flow.buy_balance_change_wow > filters.max_buy_balance_change_wow
        ):
            return False
        if filters.min_sell_balance_change_wow is not None and (
            flow.sell_balance_change_wow is None or flow.sell_balance_change_wow < filters.min_sell_balance_change_wow
        ):
            return False
        if filters.min_buy_balance_to_volume is not None and (
            flow.buy_balance_to_volume is None or flow.buy_balance_to_volume < filters.min_buy_balance_to_volume
        ):
            return False
        if filters.max_buy_balance_to_volume is not None and (
            flow.buy_balance_to_volume is None or flow.buy_balance_to_volume > filters.max_buy_balance_to_volume
        ):
            return False
        if filters.min_sell_balance_to_volume is not None and (
            flow.sell_balance_to_volume is None or flow.sell_balance_to_volume < filters.min_sell_balance_to_volume
        ):
            return False
        if filters.min_squeeze_potential_subscore is not None and (
            flow.squeeze_potential_subscore is None or flow.squeeze_potential_subscore < filters.min_squeeze_potential_subscore
        ):
            return False
        return True


mock_monitoring_service = MockMonitoringService()
