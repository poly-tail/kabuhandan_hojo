# implementation backlog v0.1

UI 3 画面と source stack 表示を入れた直後の初期 backlog です。

## 当時の主要論点

1. API / docs の正本化
- `/ui/dashboard/data`
- `/securities/search`
- detail / chart の UI 契約

2. chart detail の強化
- 期間切替
- MA overlay
- RSI / MACD の補助表示

3. portfolio 更新導線の整理
- dead-end button を残すか
- CSV import を用意するか

4. TDnet / EDINET の役割分担
- 一次ソースはどちらを canonical にするか
- UI 参照と自動取得をどう分けるか

## その後の反映

- chart detail 強化は v0.2 時点で実装済み
- dead-end button は撤去済み
- docs/specs と docs/screen_specs は versioned 文書として整理済み
- TDnet / EDINET の役割分担メモは別紙化済み
