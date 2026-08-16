"""Weighted scoring engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from kabuhandan_hojo.core.config import Settings
from kabuhandan_hojo.models.entities import EventFact, FinancialSnapshot, FlowSnapshot, TechnicalFeatureDaily


def clamp(value: Decimal, lower: Decimal = Decimal("0"), upper: Decimal = Decimal("100")) -> Decimal:
    return min(max(value, lower), upper)


def _cap_delta(value: Decimal, positive_cap: Decimal, negative_cap: Decimal | None = None) -> Decimal:
    negative_cap = positive_cap if negative_cap is None else negative_cap
    return max(min(value, positive_cap), -negative_cap)


@dataclass(slots=True)
class ScoreWeights:
    event: Decimal
    fundamental: Decimal
    technical: Decimal
    flow: Decimal
    risk: Decimal


@dataclass(slots=True)
class ScoreComputation:
    target_date: date
    event_score: Decimal
    fundamental_score: Decimal
    technical_score: Decimal
    flow_score: Decimal
    risk_penalty: Decimal
    total_score: Decimal
    explanation_summary: str
    calculation_version: str
    score_breakdown: dict[str, Any]
    missing_data_flags: list[str]


class WeightedScoreEngine:
    """Deterministic scoring engine with explainable sub-scores."""

    def __init__(self, weights: ScoreWeights, settings: Settings) -> None:
        self.weights = weights
        self.settings = settings
        self.version = "score-v0.2"

    @classmethod
    def from_settings(cls, settings: Settings) -> "WeightedScoreEngine":
        return cls(
            weights=ScoreWeights(
                event=Decimal(str(settings.scoring_event_weight)),
                fundamental=Decimal(str(settings.scoring_fundamental_weight)),
                technical=Decimal(str(settings.scoring_technical_weight)),
                flow=Decimal(str(settings.scoring_flow_weight)),
                risk=Decimal(str(settings.scoring_risk_weight)),
            ),
            settings=settings,
        )

    def compute(
        self,
        *,
        target_date: date,
        events: list[EventFact],
        financial_snapshot: FinancialSnapshot | None,
        flow_snapshot: FlowSnapshot | None,
        technical_feature: TechnicalFeatureDaily | None,
    ) -> ScoreComputation:
        missing_flags: list[str] = []
        event_score = self._event_score(events, target_date)
        if financial_snapshot is None:
            missing_flags.append("financial_snapshot")
        if flow_snapshot is None:
            missing_flags.append("flow_snapshot")
        if technical_feature is None:
            missing_flags.append("technical_feature")

        fundamental_score = self._fundamental_score(financial_snapshot)
        technical_score, technical_subscores = self._technical_score(technical_feature)
        flow_score, flow_subscores = self._flow_score(flow_snapshot, technical_feature)
        risk_penalty = self._risk_penalty(events, flow_snapshot, technical_feature, missing_flags)

        total_score = (
            self.weights.event * event_score
            + self.weights.fundamental * fundamental_score
            + self.weights.technical * technical_score
            + self.weights.flow * flow_score
            - self.weights.risk * risk_penalty
        )
        total_score = clamp(total_score)
        explanation = self._build_explanation(
            event_score=event_score,
            fundamental_score=fundamental_score,
            technical_score=technical_score,
            flow_score=flow_score,
            risk_penalty=risk_penalty,
            technical_subscores=technical_subscores,
            flow_subscores=flow_subscores,
            missing_flags=missing_flags,
        )
        return ScoreComputation(
            target_date=target_date,
            event_score=event_score,
            fundamental_score=fundamental_score,
            technical_score=technical_score,
            flow_score=flow_score,
            risk_penalty=risk_penalty,
            total_score=total_score,
            explanation_summary=explanation,
            calculation_version=self.version,
            score_breakdown={
                "weights": {
                    "event": float(self.weights.event),
                    "fundamental": float(self.weights.fundamental),
                    "technical": float(self.weights.technical),
                    "flow": float(self.weights.flow),
                    "risk": float(self.weights.risk),
                },
                "technical_subscores": {key: float(value) for key, value in technical_subscores.items()},
                "flow_subscores": {key: float(value) for key, value in flow_subscores.items()},
                "missing_data_flags": missing_flags,
            },
            missing_data_flags=missing_flags,
        )

    def _event_score(self, events: list[EventFact], target_date: date) -> Decimal:
        if not events:
            return Decimal("50")
        cutoff = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc) - timedelta(
            days=self.settings.recent_event_lookback_days
        )
        score = Decimal("50")
        for event in events:
            event_time = self._coerce_utc(event.event_time)
            if event_time < cutoff:
                continue
            multiplier = Decimal("1.0")
            age_days = max((target_date - event_time.date()).days, 0)
            if age_days > 7:
                multiplier = Decimal("0.5")
            elif age_days > 3:
                multiplier = Decimal("0.7")
            score += Decimal(str(event.importance_hint)) * multiplier - Decimal("50") * multiplier
        return clamp(score)

    def _fundamental_score(self, snapshot: FinancialSnapshot | None) -> Decimal:
        if snapshot is None:
            return Decimal("50")
        score = Decimal("50")
        if snapshot.revenue_growth_yoy is not None:
            score += Decimal(str(snapshot.revenue_growth_yoy)) * Decimal("0.4")
        if snapshot.operating_profit_growth_yoy is not None:
            score += Decimal(str(snapshot.operating_profit_growth_yoy)) * Decimal("0.3")
        if snapshot.roe is not None:
            score += Decimal(str(snapshot.roe)) * Decimal("0.6")
        if snapshot.equity_ratio is not None:
            score += Decimal(str(snapshot.equity_ratio)) * Decimal("0.2")
        return clamp(score)

    def _technical_score(self, feature: TechnicalFeatureDaily | None) -> tuple[Decimal, dict[str, Decimal]]:
        if feature is None:
            subscores = {
                "trend": Decimal("50"),
                "momentum": Decimal("50"),
                "volatility": Decimal("50"),
                "price_action": Decimal("50"),
                "volume_confirmation": Decimal("50"),
            }
            return Decimal("50"), subscores

        trend = Decimal("50")
        if feature.sma_25 is not None and feature.sma_75 is not None and feature.sma_25 > feature.sma_75:
            trend += Decimal("12")
        if feature.sma_75 is not None and feature.sma_200 is not None and feature.sma_75 > feature.sma_200:
            trend += Decimal("8")
        if feature.golden_cross_flag:
            trend += Decimal("10")
        if feature.dead_cross_flag:
            trend -= Decimal("10")
        if feature.sma_25_slope_pct is not None:
            trend += _cap_delta(Decimal(str(feature.sma_25_slope_pct)) * Decimal("1.5"), Decimal("10"))
        if feature.sma_75_slope_pct is not None:
            trend += _cap_delta(Decimal(str(feature.sma_75_slope_pct)) * Decimal("1.2"), Decimal("8"))
        if feature.deviation_from_sma_25_pct is not None:
            trend += _cap_delta(Decimal(str(feature.deviation_from_sma_25_pct)) * Decimal("1.0"), Decimal("8"))
        if feature.deviation_from_sma_75_pct is not None:
            trend += _cap_delta(Decimal(str(feature.deviation_from_sma_75_pct)) * Decimal("0.8"), Decimal("6"))
        trend = clamp(trend)

        momentum = Decimal("50")
        if feature.rsi_14 is not None:
            if Decimal("55") <= feature.rsi_14 <= Decimal("75"):
                momentum += Decimal("12")
            elif feature.rsi_14 >= Decimal("80"):
                momentum -= Decimal("10")
            elif feature.rsi_14 <= Decimal("40"):
                momentum -= Decimal("8")
        if feature.roc_20 is not None:
            momentum += _cap_delta(Decimal(str(feature.roc_20)) * Decimal("0.8"), Decimal("10"))
        if feature.macd_histogram is not None:
            momentum += _cap_delta(Decimal(str(feature.macd_histogram)) * Decimal("10"), Decimal("10"))
        if feature.macd_bullish_cross_flag:
            momentum += Decimal("8")
        if feature.macd_bearish_cross_flag:
            momentum -= Decimal("8")
        momentum = clamp(momentum)

        volatility = Decimal("50")
        if feature.atr_pct_14 is not None:
            if Decimal("1.5") <= feature.atr_pct_14 <= Decimal("4.5"):
                volatility += Decimal("8")
            elif feature.atr_pct_14 >= Decimal("8"):
                volatility -= Decimal("12")
        if feature.bollinger_width_20 is not None:
            if Decimal("6") <= feature.bollinger_width_20 <= Decimal("18"):
                volatility += Decimal("6")
            elif feature.bollinger_width_20 > Decimal("25"):
                volatility -= Decimal("6")
        if feature.range_compression_20 is not None and feature.range_compression_20 <= Decimal("0.8"):
            volatility += Decimal("6")
        volatility = clamp(volatility)

        price_action = Decimal("50")
        if (
            feature.lower_wick_ratio is not None
            and feature.lower_wick_ratio >= Decimal("0.35")
            and feature.close_position_ratio is not None
            and feature.close_position_ratio >= Decimal("0.6")
        ):
            if feature.sma_25_slope_pct is not None and feature.sma_25_slope_pct > 0:
                price_action += Decimal("10")
        if (
            feature.upper_wick_ratio is not None
            and feature.upper_wick_ratio >= Decimal("0.35")
            and feature.close_position_ratio is not None
            and feature.close_position_ratio <= Decimal("0.45")
        ):
            if feature.volume_surge_ratio is not None and feature.volume_surge_ratio >= Decimal("1.2"):
                price_action -= Decimal("10")
        if feature.body_ratio is not None and feature.body_ratio >= Decimal("0.55"):
            price_action += Decimal("6")
        if feature.gap_up_flag and feature.close_position_ratio is not None and feature.close_position_ratio >= Decimal("0.6"):
            price_action += Decimal("5")
        if feature.gap_down_flag and feature.close_position_ratio is not None and feature.close_position_ratio <= Decimal("0.4"):
            price_action -= Decimal("5")
        if 2 <= feature.consecutive_up_candles <= 4:
            price_action += Decimal("4")
        if feature.consecutive_up_candles >= 6:
            price_action -= Decimal("4")
        if feature.consecutive_down_candles >= 4:
            price_action -= Decimal("6")
        price_action = clamp(price_action)

        volume_confirmation = Decimal("50")
        if feature.volume_surge_ratio is not None:
            if feature.volume_surge_ratio >= Decimal("1.5"):
                volume_confirmation += Decimal("8")
                if feature.breakout_20d:
                    volume_confirmation += Decimal("4")
            elif feature.volume_surge_ratio >= Decimal("1.2"):
                volume_confirmation += Decimal("4")
            elif feature.breakout_20d:
                volume_confirmation -= Decimal("4")
        if feature.breakout_60d:
            volume_confirmation += Decimal("4")
        if feature.macd_histogram is not None and feature.macd_histogram > 0:
            volume_confirmation += Decimal("4")
        volume_confirmation = clamp(volume_confirmation)

        subscores = {
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility,
            "price_action": price_action,
            "volume_confirmation": volume_confirmation,
        }
        technical_score = clamp(
            (
                trend * Decimal("0.30")
                + momentum * Decimal("0.22")
                + volatility * Decimal("0.14")
                + price_action * Decimal("0.16")
                + volume_confirmation * Decimal("0.18")
            )
        )
        return technical_score, subscores

    def _flow_score(
        self,
        snapshot: FlowSnapshot | None,
        technical_feature: TechnicalFeatureDaily | None,
    ) -> tuple[Decimal, dict[str, Decimal]]:
        if snapshot is None:
            subscores = {
                "liquidity": Decimal("50"),
                "positioning": Decimal("50"),
                "squeeze_potential": Decimal("50"),
            }
            return Decimal("50"), subscores

        liquidity = Decimal("50")
        if snapshot.average_daily_volume_20 is not None:
            if snapshot.average_daily_volume_20 >= self.settings.low_liquidity_daily_volume * 10:
                liquidity += Decimal("12")
            elif snapshot.average_daily_volume_20 < self.settings.low_liquidity_daily_volume:
                liquidity -= Decimal("18")
        if snapshot.volume_ratio_20 is not None:
            liquidity += _cap_delta(Decimal(str(snapshot.volume_ratio_20)) * Decimal("5"), Decimal("10"))
        if snapshot.float_turnover_ratio is not None:
            liquidity += _cap_delta(Decimal(str(snapshot.float_turnover_ratio)) * Decimal("4"), Decimal("8"))
        liquidity = clamp(liquidity)

        positioning = Decimal("50")
        if snapshot.credit_ratio is not None:
            if snapshot.credit_ratio <= Decimal("1.5"):
                positioning += Decimal("8")
            elif snapshot.credit_ratio >= Decimal("5"):
                positioning -= Decimal("12")
        if snapshot.buy_balance_change_wow is not None:
            positioning -= _cap_delta(Decimal(str(snapshot.buy_balance_change_wow)) * Decimal("0.8"), Decimal("12"), Decimal("0"))
        if snapshot.sell_balance_change_wow is not None:
            positioning += _cap_delta(Decimal(str(snapshot.sell_balance_change_wow)) * Decimal("0.6"), Decimal("8"), Decimal("0"))
        if snapshot.buy_balance_to_volume is not None and snapshot.buy_balance_to_volume >= Decimal("3"):
            positioning -= Decimal("10")
        if snapshot.sell_balance_to_volume is not None and snapshot.sell_balance_to_volume >= Decimal("1.5"):
            positioning += Decimal("6")
        if snapshot.large_holder_activity_score is not None:
            positioning += _cap_delta(Decimal(str(snapshot.large_holder_activity_score)) * Decimal("0.4"), Decimal("10"))
        positioning = clamp(positioning)

        squeeze = snapshot.squeeze_potential_subscore if snapshot.squeeze_potential_subscore is not None else Decimal("50")
        if snapshot.squeeze_potential_subscore is None:
            if snapshot.sell_balance_to_volume is not None and snapshot.sell_balance_to_volume >= Decimal("1.5"):
                squeeze += Decimal("12")
            if snapshot.credit_ratio is not None and snapshot.credit_ratio <= Decimal("1.5"):
                squeeze += Decimal("8")
            if technical_feature is not None:
                if technical_feature.deviation_from_sma_25_pct is not None and technical_feature.deviation_from_sma_25_pct > 0:
                    squeeze += Decimal("8")
                if technical_feature.sma_25_slope_pct is not None and technical_feature.sma_25_slope_pct > 0:
                    squeeze += Decimal("6")
                if technical_feature.volume_surge_ratio is not None and technical_feature.volume_surge_ratio >= Decimal("1.2"):
                    squeeze += Decimal("6")
            if snapshot.buy_balance_change_wow is not None and snapshot.buy_balance_change_wow >= Decimal("10"):
                squeeze -= Decimal("8")
        squeeze = clamp(squeeze)

        subscores = {
            "liquidity": liquidity,
            "positioning": positioning,
            "squeeze_potential": squeeze,
        }
        flow_score = clamp(liquidity * Decimal("0.35") + positioning * Decimal("0.35") + squeeze * Decimal("0.30"))
        return flow_score, subscores

    def _risk_penalty(
        self,
        events: list[EventFact],
        flow_snapshot: FlowSnapshot | None,
        technical_feature: TechnicalFeatureDaily | None,
        missing_flags: list[str],
    ) -> Decimal:
        penalty = Decimal("0")
        negative_event_types = {"downward_revision", "dilution_risk"}
        if any(event.event_type in negative_event_types for event in events):
            penalty += Decimal("25")
        if flow_snapshot and flow_snapshot.average_daily_volume_20 is not None:
            if flow_snapshot.average_daily_volume_20 < self.settings.low_liquidity_daily_volume:
                penalty += Decimal("20")
        if flow_snapshot and flow_snapshot.credit_ratio is not None and flow_snapshot.credit_ratio >= Decimal("6"):
            penalty += Decimal("10")
        if flow_snapshot and flow_snapshot.buy_balance_to_volume is not None and flow_snapshot.buy_balance_to_volume >= Decimal("4"):
            penalty += Decimal("8")
        if technical_feature and technical_feature.atr_pct_14 is not None and technical_feature.atr_pct_14 >= Decimal("8"):
            penalty += Decimal("15")
        if (
            technical_feature
            and technical_feature.upper_wick_ratio is not None
            and technical_feature.upper_wick_ratio >= Decimal("0.45")
            and technical_feature.close_position_ratio is not None
            and technical_feature.close_position_ratio <= Decimal("0.35")
        ):
            penalty += Decimal("8")
        penalty += Decimal(str(len(missing_flags) * 5))
        return clamp(penalty)

    def _build_explanation(
        self,
        *,
        event_score: Decimal,
        fundamental_score: Decimal,
        technical_score: Decimal,
        flow_score: Decimal,
        risk_penalty: Decimal,
        technical_subscores: dict[str, Decimal],
        flow_subscores: dict[str, Decimal],
        missing_flags: list[str],
    ) -> str:
        strongest_axis = max(
            [
                ("材料", event_score),
                ("業績", fundamental_score),
                ("テクニカル", technical_score),
                ("需給", flow_score),
            ],
            key=lambda item: item[1],
        )[0]
        strongest_technical = max(technical_subscores.items(), key=lambda item: item[1])[0]
        strongest_flow = max(flow_subscores.items(), key=lambda item: item[1])[0]
        pieces = [
            f"主因は{strongest_axis}です。",
            f"テクニカルは{strongest_technical}寄り、需給は{strongest_flow}寄りの評価です。",
            f"リスク警戒は{risk_penalty:.2f}です。",
        ]
        if missing_flags:
            pieces.append(f"不足データ={', '.join(missing_flags)}")
        return " ".join(pieces)

    def _coerce_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
