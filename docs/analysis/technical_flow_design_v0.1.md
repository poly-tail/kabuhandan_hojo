# Technical / Flow Analysis 設計メモ v0.1

最終更新: 2026-04-20

## 目的

テクニカル特徴量、需給 snapshot、score breakdown を detail 画面、chart 画面、screening 画面で再利用できる形に揃えるための設計メモです。

## 技術要素

### technical feature

`src/kabuhandan_hojo/features/technical.py` で次の代表値を計算します。

- MA 5 / 25 / 75
- MA slope
- breakout 20 / 60
- ATR / ATR%
- RSI 14
- ROC 20
- MACD line / signal / histogram
- wick ratio
- gap flag / gap size
- volume surge ratio

### flow snapshot

`flow_snapshot` には次の代表値を持たせます。

- `margin_buy_balance`
- `margin_sell_balance`
- `credit_ratio`
- `buy_balance_change_wow`
- `sell_balance_change_wow`
- `buy_balance_to_volume`
- `sell_balance_to_volume`
- `squeeze_potential_subscore`

### scoring

`src/kabuhandan_hojo/scoring/engine.py` では、technical / flow を explainable weighted score に分解して保持します。

例:

```json
{
  "technical_subscores": {
    "trend": 72.0,
    "momentum": 68.0,
    "volatility": 54.0,
    "price_action": 61.0,
    "volume_confirmation": 66.0
  },
  "flow_subscores": {
    "liquidity": 58.0,
    "positioning": 63.0,
    "squeeze_potential": 71.0
  }
}
```

## UI での使い道

- detail 画面:
  - technical summary
  - technical metrics
  - flow summary
  - flow metrics
- chart detail:
  - `price_chart`
  - MA overlay
  - RSI / MACD 補助表示
- screening:
  - matched reasons
  - caution / total score

## 既知の前提

- OHLCV 由来の特徴量は `technical_feature_daily` に寄せる
- 信用需給の raw 値は `flow_snapshot` に寄せる
- 画面表示用の言い換えは `insights` と `dashboard_experience` 側で行う
- live mode では不足データを mock 補完しない
