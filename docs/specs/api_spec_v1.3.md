# kabuhandan_hojo API Spec v1.3

## 1. scope

この版は、lightweight UI とその view model、および live mode の市場地合い表示ルールを含む現行 API 契約を対象にします。

## 2. endpoints

| method | path | purpose | response |
|---|---|---|---|
| `GET` | `/health` | アプリ状態確認 | `HealthResponse` |
| `GET` | `/watchlist` | watchlist 一覧 | `list[WatchlistItem]` |
| `POST` | `/watchlist` | watchlist 追加 / 再有効化 | `WatchlistItem` |
| `GET` | `/securities/search` | 銘柄検索 | `list[SecuritySearchResult]` |
| `POST` | `/sources/bootstrap` | source registry 初期化 | `JobRunResponse` |
| `POST` | `/securities` | 銘柄マスタ登録 | `SecurityRead` |
| `POST` | `/securities/{ticker_code}/prices` | OHLCV 手入力 | `list[PriceBarRead]` |
| `POST` | `/securities/{ticker_code}/prices/sync` | J-Quants 日足同期 | `JobRunResponse` |
| `POST` | `/securities/{ticker_code}/financials` | 財務 snapshot 登録 | `FinancialSnapshotRead` |
| `POST` | `/securities/{ticker_code}/flow` | 需給 snapshot 登録 | `FlowSnapshotRead` |
| `POST` | `/securities/{ticker_code}/technical/rebuild` | テクニカル再計算 | `TechnicalFeatureRead` |
| `POST` | `/securities/{ticker_code}/score/recalculate` | score 再計算 | `ScoreRecalculateResponse` |
| `POST` | `/documents/import` | 文書手入力 | `DocumentImportResponse` |
| `POST` | `/documents/sync/edinet` | EDINET 同期 | `JobRunResponse` |
| `GET` | `/securities/{ticker_code}` | 個別銘柄 JSON | `SecurityDetailResponse` |
| `GET` | `/dashboard` | dashboard JSON | `DashboardResponse` |
| `GET` | `/screening` | screening 一覧 | `list[ScreeningResult]` |
| `POST` | `/screening/query` | screening 条件検索 | `list[ScreeningResult]` |
| `GET` | `/ui/dashboard` | top 画面 HTML shell | `text/html` |
| `GET` | `/ui/security/{ticker_code}` | detail 画面 HTML shell | `text/html` |
| `GET` | `/ui/security/{ticker_code}/chart` | chart 画面 HTML shell | `text/html` |
| `GET` | `/ui/dashboard/data` | UI view model | `DashboardExperienceResponse` |

## 3. `GET /ui/dashboard/data`

### request

- query:
  - `ticker_code: str | None`

### response

response model は `DashboardExperienceResponse` です。主な top-level field は次の通りです。

- `generated_at`
- `target_date`
- `mode`
- `disclaimer`
- `market_overview`
- `metrics`
- `status_counts`
- `priority_items`
- `important_alerts`
- `event_feed`
- `watchlist_items`
- `screening_items`
- `selected_ticker_code`
- `detail`

`detail` は `SecurityDetailPanel` を返し、次を含みます。

- 仮説カード
- factor split
- reference links
- `price_chart`
- technical summary / metrics
- flow summary / metrics
- materials
- warnings
- history

## 4. live mode の source ルール

### price chart

- live mode では UI 向け mock 補完を行わない
- `detail.price_chart` が空で `JQUANTS_API_KEY` がある場合のみ、J-Quants 日足同期を 1 回試す
- それでも不足している場合は空表示にする

### market overview

- `market_overview`、`market_headwind`、`factor_split.market` は J-Quants の `TOPIX(1306)` / `Nikkei225(1321)` proxy を使う
- proxy が取得できない場合は `未取得` とし、watchlist ヒューリスティックへ戻さない

### sector pulse

- watchlist 銘柄の `industry_33` / `industry_17` ごとの 5 日相対強弱を使う
- 比較に使える銘柄が不足している場合は sector pulse を省略する

## 5. guardrails

- 正式 source は J-Quants / EDINET API / YouTube Data API / allowlist IR を中心とする
- Yahoo! Finance や broker site は自動取得 source にしない
- 規約違反や robots 無視のスクレイピングは入れない
