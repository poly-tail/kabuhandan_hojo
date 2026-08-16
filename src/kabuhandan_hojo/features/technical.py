"""Technical feature calculations from OHLCV time series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import sqrt
from statistics import mean

from kabuhandan_hojo.connectors.base import DailyBarRecord

_EPSILON = 1e-9
_GAP_THRESHOLD_PCT = 0.5


@dataclass(slots=True)
class TechnicalFeatureSnapshot:
    ticker_code: str
    target_date: date
    sma_5: Decimal | None
    sma_25: Decimal | None
    sma_75: Decimal | None
    sma_200: Decimal | None
    sma_5_slope_pct: Decimal | None
    sma_25_slope_pct: Decimal | None
    sma_75_slope_pct: Decimal | None
    deviation_from_sma_25_pct: Decimal | None
    deviation_from_sma_75_pct: Decimal | None
    ma_gap_5_25_pct: Decimal | None
    ma_gap_25_75_pct: Decimal | None
    golden_cross_flag: bool
    dead_cross_flag: bool
    breakout_20d: bool
    breakout_60d: bool
    volume_ratio_20: Decimal | None
    volume_surge_ratio: Decimal | None
    atr_14: Decimal | None
    atr_pct_14: Decimal | None
    rsi_14: Decimal | None
    roc_20: Decimal | None
    macd_line: Decimal | None
    macd_signal: Decimal | None
    macd_histogram: Decimal | None
    macd_bullish_cross_flag: bool
    macd_bearish_cross_flag: bool
    bollinger_mid_20: Decimal | None
    bollinger_upper_20: Decimal | None
    bollinger_lower_20: Decimal | None
    bollinger_width_20: Decimal | None
    upper_wick_ratio: Decimal | None
    lower_wick_ratio: Decimal | None
    body_ratio: Decimal | None
    close_position_ratio: Decimal | None
    gap_pct: Decimal | None
    gap_up_flag: bool
    gap_down_flag: bool
    consecutive_up_candles: int
    consecutive_down_candles: int
    range_compression_20: Decimal | None


class TechnicalFeatureCalculator:
    """Compute technical indicators using only numeric time series."""

    def calculate_latest(self, ticker_code: str, bars: list[DailyBarRecord]) -> TechnicalFeatureSnapshot:
        if len(bars) < 20:
            raise ValueError("At least 20 bars are required to calculate technical features.")

        ordered = sorted(bars, key=lambda bar: bar.target_date)
        closes = [float(bar.adjusted_close or bar.close_price) for bar in ordered]
        raw_closes = [float(bar.close_price) for bar in ordered]
        highs = [float(bar.high_price) for bar in ordered]
        lows = [float(bar.low_price) for bar in ordered]
        opens = [float(bar.open_price) for bar in ordered]
        volumes = [float(bar.volume) for bar in ordered]
        target_date = ordered[-1].target_date
        current_close = closes[-1]

        sma_5_series = self._sma_series(closes, 5)
        sma_25_series = self._sma_series(closes, 25)
        sma_75_series = self._sma_series(closes, 75)
        sma_200_series = self._sma_series(closes, 200)
        macd_line_series, macd_signal_series, macd_histogram_series = self._macd_series(closes)
        bollinger_mid, bollinger_upper, bollinger_lower, bollinger_width = self._bollinger(closes, 20, 2.0)
        upper_wick_ratio, lower_wick_ratio, body_ratio, close_position_ratio = self._candle_shape(
            open_price=opens[-1],
            high_price=highs[-1],
            low_price=lows[-1],
            close_price=raw_closes[-1],
        )
        gap_pct = self._pct_change(raw_closes[-2], opens[-1]) if len(raw_closes) >= 2 else None
        volume_ratio_20 = self._ratio(volumes[-1], mean(volumes[-20:]))

        return TechnicalFeatureSnapshot(
            ticker_code=ticker_code,
            target_date=target_date,
            sma_5=self._decimal(sma_5_series[-1]),
            sma_25=self._decimal(sma_25_series[-1]),
            sma_75=self._decimal(sma_75_series[-1]),
            sma_200=self._decimal(sma_200_series[-1]),
            sma_5_slope_pct=self._slope_pct(sma_5_series, lookback=5),
            sma_25_slope_pct=self._slope_pct(sma_25_series, lookback=5),
            sma_75_slope_pct=self._slope_pct(sma_75_series, lookback=5),
            deviation_from_sma_25_pct=self._pct_change(sma_25_series[-1], current_close),
            deviation_from_sma_75_pct=self._pct_change(sma_75_series[-1], current_close),
            ma_gap_5_25_pct=self._pct_change(sma_25_series[-1], sma_5_series[-1]),
            ma_gap_25_75_pct=self._pct_change(sma_75_series[-1], sma_25_series[-1]),
            golden_cross_flag=self._crossed_above(sma_25_series, sma_75_series),
            dead_cross_flag=self._crossed_below(sma_25_series, sma_75_series),
            breakout_20d=self._breakout(current_close, highs, window=20),
            breakout_60d=self._breakout(current_close, highs, window=60),
            volume_ratio_20=volume_ratio_20,
            volume_surge_ratio=volume_ratio_20,
            atr_14=self._decimal(self._atr(ordered, 14)),
            atr_pct_14=self._atr_pct(self._atr(ordered, 14), current_close),
            rsi_14=self._decimal(self._rsi(closes, 14)),
            roc_20=self._pct_change(closes[-21], current_close) if len(closes) >= 21 else None,
            macd_line=self._decimal(macd_line_series[-1]),
            macd_signal=self._decimal(macd_signal_series[-1]),
            macd_histogram=self._decimal(macd_histogram_series[-1]),
            macd_bullish_cross_flag=self._crossed_above(macd_line_series, macd_signal_series),
            macd_bearish_cross_flag=self._crossed_below(macd_line_series, macd_signal_series),
            bollinger_mid_20=self._decimal(bollinger_mid),
            bollinger_upper_20=self._decimal(bollinger_upper),
            bollinger_lower_20=self._decimal(bollinger_lower),
            bollinger_width_20=self._decimal(bollinger_width),
            upper_wick_ratio=self._decimal(upper_wick_ratio),
            lower_wick_ratio=self._decimal(lower_wick_ratio),
            body_ratio=self._decimal(body_ratio),
            close_position_ratio=self._decimal(close_position_ratio),
            gap_pct=gap_pct,
            gap_up_flag=bool(gap_pct is not None and gap_pct >= Decimal(str(_GAP_THRESHOLD_PCT))),
            gap_down_flag=bool(gap_pct is not None and gap_pct <= Decimal(str(-_GAP_THRESHOLD_PCT))),
            consecutive_up_candles=self._count_consecutive_candles(opens, raw_closes, bullish=True),
            consecutive_down_candles=self._count_consecutive_candles(opens, raw_closes, bullish=False),
            range_compression_20=self._range_compression(highs, lows),
        )

    def _sma_series(self, values: list[float], window: int) -> list[float | None]:
        series: list[float | None] = []
        for index in range(len(values)):
            if index + 1 < window:
                series.append(None)
                continue
            series.append(mean(values[index - window + 1 : index + 1]))
        return series

    def _ema_series(self, values: list[float], window: int) -> list[float | None]:
        if len(values) < window:
            return [None] * len(values)
        multiplier = 2 / (window + 1)
        series: list[float | None] = [None] * (window - 1)
        ema_value = mean(values[:window])
        series.append(ema_value)
        for value in values[window:]:
            ema_value = ((value - ema_value) * multiplier) + ema_value
            series.append(ema_value)
        return series

    def _macd_series(self, closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
        ema_12 = self._ema_series(closes, 12)
        ema_26 = self._ema_series(closes, 26)
        macd_line: list[float | None] = []
        for fast, slow in zip(ema_12, ema_26):
            if fast is None or slow is None:
                macd_line.append(None)
            else:
                macd_line.append(fast - slow)

        macd_defined = [value for value in macd_line if value is not None]
        signal_defined = self._ema_series(macd_defined, 9) if macd_defined else []
        signal: list[float | None] = []
        cursor = 0
        for value in macd_line:
            if value is None:
                signal.append(None)
                continue
            signal.append(signal_defined[cursor] if cursor < len(signal_defined) else None)
            cursor += 1

        histogram: list[float | None] = []
        for line_value, signal_value in zip(macd_line, signal):
            if line_value is None or signal_value is None:
                histogram.append(None)
            else:
                histogram.append(line_value - signal_value)
        return macd_line, signal, histogram

    def _bollinger(self, closes: list[float], window: int, deviations: float) -> tuple[float | None, float | None, float | None, float | None]:
        if len(closes) < window:
            return None, None, None, None
        recent = closes[-window:]
        mid = mean(recent)
        variance = sum((value - mid) ** 2 for value in recent) / window
        std_dev = sqrt(variance)
        upper = mid + deviations * std_dev
        lower = mid - deviations * std_dev
        width = ((upper - lower) / mid) * 100 if mid else None
        return mid, upper, lower, width

    def _atr(self, bars: list[DailyBarRecord], window: int) -> float | None:
        if len(bars) < window + 1:
            return None
        ranges: list[float] = []
        for index in range(1, len(bars)):
            current = bars[index]
            previous = bars[index - 1]
            true_range = max(
                float(current.high_price) - float(current.low_price),
                abs(float(current.high_price) - float(previous.close_price)),
                abs(float(current.low_price) - float(previous.close_price)),
            )
            ranges.append(true_range)
        return mean(ranges[-window:])

    def _atr_pct(self, atr_value: float | None, current_close: float) -> Decimal | None:
        if atr_value is None or current_close <= 0:
            return None
        return self._decimal((atr_value / current_close) * 100)

    def _rsi(self, closes: list[float], window: int) -> float | None:
        if len(closes) < window + 1:
            return None
        gains: list[float] = []
        losses: list[float] = []
        for previous, current in zip(closes[:-1], closes[1:]):
            change = current - previous
            gains.append(max(change, 0.0))
            losses.append(abs(min(change, 0.0)))
        average_gain = mean(gains[-window:])
        average_loss = mean(losses[-window:])
        if average_loss == 0:
            return 100.0
        relative_strength = average_gain / average_loss
        return 100 - (100 / (1 + relative_strength))

    def _breakout(self, current_close: float, highs: list[float], window: int) -> bool:
        if len(highs) <= window:
            return False
        return current_close >= max(highs[-window - 1 : -1])

    def _candle_shape(
        self,
        *,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        total_range = max(high_price - low_price, _EPSILON)
        upper_wick = max(high_price - max(open_price, close_price), 0.0)
        lower_wick = max(min(open_price, close_price) - low_price, 0.0)
        body = abs(close_price - open_price)
        close_position = (close_price - low_price) / total_range
        return upper_wick / total_range, lower_wick / total_range, body / total_range, close_position

    def _count_consecutive_candles(self, opens: list[float], closes: list[float], *, bullish: bool) -> int:
        count = 0
        for open_price, close_price in zip(reversed(opens), reversed(closes)):
            if bullish and close_price > open_price:
                count += 1
                continue
            if not bullish and close_price < open_price:
                count += 1
                continue
            break
        return count

    def _range_compression(self, highs: list[float], lows: list[float]) -> Decimal | None:
        if len(highs) < 20:
            return None
        recent_ranges = [high - low for high, low in zip(highs[-5:], lows[-5:])]
        base_ranges = [high - low for high, low in zip(highs[-20:], lows[-20:])]
        base_average = mean(base_ranges)
        if base_average == 0:
            return None
        return self._decimal(mean(recent_ranges) / base_average)

    def _ratio(self, numerator: float | None, denominator: float | None) -> Decimal | None:
        if numerator is None or denominator in (None, 0):
            return None
        return self._decimal(numerator / denominator)

    def _pct_change(self, base: float | None, current: float | None) -> Decimal | None:
        if base in (None, 0) or current is None:
            return None
        return self._decimal(((current - base) / base) * 100)

    def _slope_pct(self, series: list[float | None], lookback: int) -> Decimal | None:
        if not series:
            return None
        current = series[-1]
        previous_index = len(series) - lookback - 1
        if previous_index < 0:
            return None
        previous = series[previous_index]
        return self._pct_change(previous, current)

    def _crossed_above(self, lhs: list[float | None], rhs: list[float | None]) -> bool:
        if len(lhs) < 2 or len(rhs) < 2:
            return False
        current_left, previous_left = lhs[-1], lhs[-2]
        current_right, previous_right = rhs[-1], rhs[-2]
        if None in {current_left, previous_left, current_right, previous_right}:
            return False
        return bool(current_left > current_right and previous_left <= previous_right)

    def _crossed_below(self, lhs: list[float | None], rhs: list[float | None]) -> bool:
        if len(lhs) < 2 or len(rhs) < 2:
            return False
        current_left, previous_left = lhs[-1], lhs[-2]
        current_right, previous_right = rhs[-1], rhs[-2]
        if None in {current_left, previous_left, current_right, previous_right}:
            return False
        return bool(current_left < current_right and previous_left >= previous_right)

    def _decimal(self, value: float | None) -> Decimal | None:
        if value is None:
            return None
        return Decimal(f"{value:.4f}")
