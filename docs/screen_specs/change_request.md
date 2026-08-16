# Screen Change Request

画面仕様を更新するときのメモです。

## 変更要求の整理観点

1. どの画面に影響するか
- analysis
- top
- detail
- chart

2. API 契約の変更が必要か
- `/ui/dashboard/data`
- `/securities/search`
- `/api/ai/analyses`
- search / watchlist / monitoring API

3. live mode と mock mode で挙動差があるか

4. source policy に抵触しないか

5. どちらのAI経路に影響するか
- 個別銘柄AI分析 (`/api/ai/analyses`)
- legacy Portfolio AI分析 (`/api/ai/stock-review`)

6. prompt version / module、Web、Structured Outputs、mock、fallback の境界が変わるか

## 更新時に一緒に見る文書

- `docs/specs/current.md`
- `docs/screen_specs/current.md`
- `docs/spec_change_history.md`
- `docs/context.md`
- `docs/changelog.md`
