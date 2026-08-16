"""Interpretation helpers for technical and flow data."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from kabuhandan_hojo.schemas.scores import ScoreRead
from kabuhandan_hojo.schemas.securities import (
    FlowContextRead,
    FlowSnapshotRead,
    InterpretedMetricRead,
    TechnicalContextRead,
    TechnicalFeatureRead,
)


def _to_decimal(value: Any, default: Decimal = Decimal("50")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _format_decimal(value: Decimal | None, *, suffix: str = "", places: int = 2) -> str:
    if value is None:
        return "--"
    return f"{value:.{places}f}{suffix}"


def _get_subscore(score: ScoreRead | None, group: str, key: str) -> Decimal:
    if score is None:
        return Decimal("50")
    group_payload = score.score_breakdown.get(group, {})
    if not isinstance(group_payload, dict):
        return Decimal("50")
    return _to_decimal(group_payload.get(key))


def build_technical_context(feature: TechnicalFeatureRead | None, score: ScoreRead | None) -> TechnicalContextRead | None:
    if feature is None:
        return None

    trend_subscore = _get_subscore(score, "technical_subscores", "trend")
    momentum_subscore = _get_subscore(score, "technical_subscores", "momentum")
    volatility_subscore = _get_subscore(score, "technical_subscores", "volatility")
    price_action_subscore = _get_subscore(score, "technical_subscores", "price_action")
    volume_confirmation_subscore = _get_subscore(score, "technical_subscores", "volume_confirmation")

    interpretations: list[str] = []
    if feature.ma_25 and feature.ma_75 and feature.ma_25 > feature.ma_75:
        interpretations.append("移動平均線の並びは短中期で上向きです。")
    else:
        interpretations.append("移動平均線の並びはまだ強弱が割れています。")

    if feature.macd_histogram is not None and feature.macd_histogram > 0:
        interpretations.append("MACD ヒストグラムはプラスで、モメンタムは改善寄りです。")
    elif feature.macd_histogram is not None:
        interpretations.append("MACD ヒストグラムはマイナスで、勢いは鈍っています。")

    if feature.rsi_14 is not None:
        if feature.rsi_14 >= Decimal("75"):
            interpretations.append("RSI はやや過熱圏で、伸びた後の失速に注意です。")
        elif feature.rsi_14 >= Decimal("55"):
            interpretations.append("RSI は中立より強く、上昇モメンタムは維持されています。")
        else:
            interpretations.append("RSI は強気一辺倒ではなく、方向感の確認が必要です。")

    if feature.upper_wick_ratio is not None and feature.upper_wick_ratio >= Decimal("0.35"):
        interpretations.append("上髭が長く、引け位置や出来高を合わせて売り圧力を確認したい形です。")
    if feature.lower_wick_ratio is not None and feature.lower_wick_ratio >= Decimal("0.35"):
        interpretations.append("下髭が長く、押し目での買い戻しが入った可能性があります。")

    metrics = [
        InterpretedMetricRead(
            key="ma_25",
            label="25日線乖離",
            value=_format_decimal(feature.price_vs_ma_25, suffix="%"),
            interpretation="25日線より上なら短中期の地合いは追い風寄りです。"
            if feature.price_vs_ma_25 is not None and feature.price_vs_ma_25 > 0
            else "25日線を下回る場合は押し戻されやすさを確認します。",
        ),
        InterpretedMetricRead(
            key="ma_75",
            label="75日線乖離",
            value=_format_decimal(feature.price_vs_ma_75, suffix="%"),
            interpretation="75日線より上なら中期トレンドは崩れていない見方がしやすいです。"
            if feature.price_vs_ma_75 is not None and feature.price_vs_ma_75 > 0
            else "75日線を下回る場合は中期トレンドの弱化を疑います。",
        ),
        InterpretedMetricRead(
            key="rsi_14",
            label="RSI",
            value=_format_decimal(feature.rsi_14),
            interpretation="55〜75 は上昇継続を見やすい帯、75超は過熱注意です。",
        ),
        InterpretedMetricRead(
            key="macd_histogram",
            label="MACDヒストグラム",
            value=_format_decimal(feature.macd_histogram),
            interpretation="プラス圏は勢い改善、マイナス圏は鈍化を示します。",
        ),
        InterpretedMetricRead(
            key="volume_surge_ratio",
            label="出来高急増率",
            value=_format_decimal(feature.volume_surge_ratio),
            interpretation="1.5倍以上なら価格変化の裏付けとして見やすくなります。",
        ),
        InterpretedMetricRead(
            key="upper_wick_ratio",
            label="上髭率",
            value=_format_decimal(feature.upper_wick_ratio),
            interpretation="単独ではなく、引け位置と出来高と組み合わせて評価します。",
        ),
    ]

    return TechnicalContextRead(
        trend_subscore=trend_subscore,
        momentum_subscore=momentum_subscore,
        volatility_subscore=volatility_subscore,
        price_action_subscore=price_action_subscore,
        volume_confirmation_subscore=volume_confirmation_subscore,
        moving_average_state=_moving_average_state(feature),
        momentum_state=_momentum_state(feature),
        volatility_state=_volatility_state(feature),
        price_action_state=_price_action_state(feature),
        volume_confirmation_state=_volume_confirmation_state(feature),
        interpretations=interpretations,
        metrics=metrics,
    )


def build_flow_context(
    flow: FlowSnapshotRead | None,
    feature: TechnicalFeatureRead | None,
    score: ScoreRead | None,
) -> FlowContextRead | None:
    if flow is None:
        return None

    liquidity_subscore = _get_subscore(score, "flow_subscores", "liquidity")
    positioning_subscore = _get_subscore(score, "flow_subscores", "positioning")
    squeeze_subscore = _get_subscore(score, "flow_subscores", "squeeze_potential")

    interpretations: list[str] = []
    if flow.credit_ratio is not None:
        if flow.credit_ratio >= Decimal("5"):
            interpretations.append("信用倍率は高く、買い残の積み上がりが重しになる可能性があります。")
        elif flow.credit_ratio <= Decimal("1.5"):
            interpretations.append("信用倍率は高すぎず、需給の偏りはまだ限定的です。")

    if flow.sell_balance_to_volume is not None and flow.sell_balance_to_volume >= Decimal("1.5"):
        interpretations.append("売り残の厚みがあり、上昇時は踏み上げ余地を意識できます。")
    if flow.buy_balance_change_wow is not None and flow.buy_balance_change_wow >= Decimal("10"):
        interpretations.append("買い残の増加が速く、値動きが止まると需給悪化に転びやすいです。")
    if feature is not None and feature.price_vs_ma_25 is not None and feature.price_vs_ma_25 <= 0:
        interpretations.append("価格が25日線を下回ると、信用需給の重さが出やすくなります。")

    metrics = [
        InterpretedMetricRead(
            key="credit_ratio",
            label="信用倍率",
            value=_format_decimal(flow.credit_ratio),
            interpretation="単独判断ではなく、価格トレンドと残高増減率を合わせて見ます。",
        ),
        InterpretedMetricRead(
            key="buy_balance_change_wow",
            label="買残 前週比",
            value=_format_decimal(flow.buy_balance_change_wow, suffix="%"),
            interpretation="急増しすぎると押し目での投げが出やすくなります。",
        ),
        InterpretedMetricRead(
            key="sell_balance_change_wow",
            label="売残 前週比",
            value=_format_decimal(flow.sell_balance_change_wow, suffix="%"),
            interpretation="売残増は逆日歩ではなく、踏み上げ余地とセットで確認します。",
        ),
        InterpretedMetricRead(
            key="buy_balance_to_volume",
            label="買残 / 20日出来高",
            value=_format_decimal(flow.buy_balance_to_volume),
            interpretation="大きいほど需給の重さを警戒します。",
        ),
        InterpretedMetricRead(
            key="sell_balance_to_volume",
            label="売残 / 20日出来高",
            value=_format_decimal(flow.sell_balance_to_volume),
            interpretation="大きいほど上昇時の買い戻し余地を意識します。",
        ),
        InterpretedMetricRead(
            key="squeeze_potential_subscore",
            label="踏み上げ余地",
            value=_format_decimal(flow.squeeze_potential_subscore),
            interpretation="売り残と価格トレンド、出来高を合わせた補助評価です。",
        ),
    ]

    return FlowContextRead(
        liquidity_subscore=liquidity_subscore,
        positioning_subscore=positioning_subscore,
        squeeze_potential_subscore=squeeze_subscore,
        state_summary=_flow_state_summary(flow),
        interpretations=interpretations,
        metrics=metrics,
    )


def screening_reasons(
    feature: TechnicalFeatureRead | None,
    flow: FlowSnapshotRead | None,
    score: ScoreRead | None,
) -> list[str]:
    reasons: list[str] = []
    if score is not None and score.total_score >= Decimal("65"):
        reasons.append(f"total_score={score.total_score:.2f}")
    if feature is not None:
        if feature.breakout_20d:
            reasons.append("20d_breakout")
        if feature.breakout_60d:
            reasons.append("60d_breakout")
        if feature.golden_cross_flag:
            reasons.append("golden_cross")
        if feature.macd_bullish_cross_flag:
            reasons.append("macd_bullish_cross")
        if feature.rsi_14 is not None and Decimal("55") <= feature.rsi_14 <= Decimal("75"):
            reasons.append("rsi_55_75")
        if feature.volume_surge_ratio is not None and feature.volume_surge_ratio >= Decimal("1.5"):
            reasons.append("volume_surge>=1.5")
    if flow is not None:
        if flow.credit_ratio is not None and flow.credit_ratio <= Decimal("1.5"):
            reasons.append("credit_ratio<=1.5")
        if flow.squeeze_potential_subscore is not None and flow.squeeze_potential_subscore >= Decimal("65"):
            reasons.append("squeeze_potential>=65")
    return reasons


def _moving_average_state(feature: TechnicalFeatureRead) -> str:
    if feature.ma_25 and feature.ma_75 and feature.ma_25 > feature.ma_75:
        if feature.ma_75 and feature.ma_200 and feature.ma_75 > feature.ma_200:
            return "短中長期の移動平均線は上向きに並んでいます。"
        return "25日線が75日線を上回り、短中期は強めです。"
    return "移動平均線の並びはまだ整っていません。"


def _momentum_state(feature: TechnicalFeatureRead) -> str:
    if feature.macd_histogram is not None and feature.macd_histogram > 0:
        return "モメンタムは改善寄りです。"
    if feature.rsi_14 is not None and feature.rsi_14 < Decimal("45"):
        return "モメンタムはまだ弱めです。"
    return "モメンタムは中立圏です。"


def _volatility_state(feature: TechnicalFeatureRead) -> str:
    if feature.atr_pct_14 is not None and feature.atr_pct_14 >= Decimal("6"):
        return "値幅は大きく、ボラティリティには注意が必要です。"
    if feature.bollinger_width_20 is not None and feature.bollinger_width_20 <= Decimal("8"):
        return "値幅は比較的落ち着いています。"
    return "ボラティリティは中立です。"


def _price_action_state(feature: TechnicalFeatureRead) -> str:
    if feature.upper_wick_ratio is not None and feature.upper_wick_ratio >= Decimal("0.35"):
        return "上髭が長く、戻り売り圧力の確認が必要です。"
    if feature.lower_wick_ratio is not None and feature.lower_wick_ratio >= Decimal("0.35"):
        return "下髭が長く、押し目での買い支えが入っています。"
    return "ローソク足の形状は中立です。"


def _volume_confirmation_state(feature: TechnicalFeatureRead) -> str:
    if feature.volume_surge_ratio is not None and feature.volume_surge_ratio >= Decimal("1.5"):
        return "出来高が伴っており、価格変化の裏付けがあります。"
    return "出来高の裏付けはまだ強くありません。"


def _flow_state_summary(flow: FlowSnapshotRead) -> str:
    if flow.credit_ratio is not None and flow.credit_ratio >= Decimal("5"):
        return "信用買いの偏りが重しになりやすい状態です。"
    if flow.squeeze_potential_subscore is not None and flow.squeeze_potential_subscore >= Decimal("65"):
        return "需給改善や踏み上げ余地を見やすい状態です。"
    return "信用需給は中立圏です。"
