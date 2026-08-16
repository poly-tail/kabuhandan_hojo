# kabuhandan_hojo API Spec v1.4

## 1. scope

この版は、multi-mode stock AI review、Prompt Registry / Prompt Builder、mode別Structured Outputs、Web検索制御、JSON parse救済、ChatGPT手動投入用プロンプト生成を含む API 契約を対象にします。

## 2. endpoints

| method | path | purpose | response |
|---|---|---|---|
| `GET` | `/health` | アプリ状態確認 | `HealthResponse` |
| `GET` | `/watchlist` | watchlist 一覧 | `list[WatchlistItem]` |
| `POST` | `/watchlist` | watchlist 追加 / 再有効化 | `WatchlistItem` |
| `GET` | `/portfolio` | 保有銘柄一覧 | `list[PortfolioItem]` |
| `POST` | `/portfolio` | 保有銘柄登録 / 更新 | `PortfolioItem` |
| `POST` | `/portfolio/import/csv` | 保有銘柄CSV import | import result |
| `POST` | `/api/ai/stock-review` | multi-mode stock AI review | `PortfolioAiReviewResponse` |
| `POST` | `/portfolio/ai-review` | 互換AIレビュー入口 | `PortfolioAiReviewResponse` |
| `POST` | `/api/portfolio/ai-review` | 互換AIレビュー入口 | `PortfolioAiReviewResponse` |
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
| `POST` | `/documents/import/ir` | allowlist IR import | `DocumentImportResponse` |
| `POST` | `/documents/sync/edinet` | EDINET 同期 | `JobRunResponse` |
| `POST` | `/documents/sync/tdnet` | TDnet 同期 | `JobRunResponse` |
| `POST` | `/documents/sync/youtube` | YouTube同期 | `JobRunResponse` |
| `POST` | `/documents/sync/youtube/monitored` | monitored channel YouTube同期 | `JobRunResponse` |
| `GET` | `/securities/{ticker_code}` | 個別銘柄 JSON | `SecurityDetailResponse` |
| `GET` | `/dashboard` | dashboard JSON | `DashboardResponse` |
| `GET` | `/screening` | screening 一覧 | `list[ScreeningResult]` |
| `POST` | `/screening/query` | screening 条件検索 | `list[ScreeningResult]` |
| `GET` | `/ui/dashboard` | top 画面 HTML shell | `text/html` |
| `GET` | `/ui/security/{ticker_code}` | detail 画面 HTML shell | `text/html` |
| `GET` | `/ui/security/{ticker_code}/chart` | chart 画面 HTML shell | `text/html` |
| `GET` | `/ui/dashboard/data` | UI view model | `DashboardExperienceResponse` |

## 3. `POST /api/ai/stock-review`

### request

```json
{
  "mode": "analyst",
  "target": "selected",
  "tickers": ["7011"],
  "use_mock_holdings": false,
  "holdings": [],
  "candidates": [],
  "include_web_search": true,
  "risk_preference": "balanced",
  "max_web_search_calls": 5,
  "save_result": true,
  "use_cache": true,
  "mock_response": false,
  "user_hypothesis": "防衛テーマと決算期待で上値余地があるが、短期過熱も気になる",
  "position_intent": "short_and_mid"
}
```

### request fields

| field | type | default | note |
|---|---|---|---|
| `mode` | enum | `judge` | `scanner` / `analyst` / `judge` / `critical` / `prompt_only` |
| `target` | enum | `holdings` | `holdings` / `watchlist` / `candidates` / `selected` / `mock` |
| `tickers` | `list[str]` | `[]` | selected対象またはfilterに使う |
| `holdings` | `list[PortfolioAiHolding]` | `[]` | request指定がある場合はDBより優先 |
| `candidates` | `list[PortfolioAiCandidate]` | `[]` | 狙い中銘柄。未指定で `target=candidates` の場合はmock candidates |
| `include_web_search` | `bool | null` | `null` | nullならmode既定値。`analyst` / `judge` / `critical` はON |
| `max_web_search_calls` | `int` | `5` | 環境変数上限と比較して小さい方を使う |
| `save_result` | `bool` | `true` | ローカル履歴へ保存 |
| `use_cache` | `bool` | `true` | 同一入力キャッシュを利用 |
| `mock_response` | `bool` | `false` | trueならOpenAI APIを呼ばない |
| `user_hypothesis` | `str | null` | `null` | 空の場合はPrompt Builderで「未入力」 |
| `position_intent` | `str | null` | `null` | 短期玉、中期玉、コア玉、追加玉など |

`target=mock`、`use_mock_holdings=true`、または対象解決が `holdings_source=mock` になった場合は、`mock_response=false` でもOpenAI APIを呼ばない。レスポンスは `mock_response=true`、`estimated_cost_usd=0` とする。

### `PortfolioAiHolding`

```json
{
  "ticker": "7011",
  "name": "三菱重工業",
  "market": "TSE",
  "quantity": 100,
  "average_price": 2900,
  "position_type": "core_and_short"
}
```

### `PortfolioAiCandidate`

```json
{
  "ticker": "6857",
  "name": "アドバンテスト",
  "market": "TSE",
  "candidate_reason": "半導体テーマの主力候補",
  "watch_condition": "出来高を伴う上抜け、または押し目形成"
}
```

## 4. response

```json
{
  "generated_at": "2026-06-15T13:00:00+09:00",
  "mode": "analyst",
  "analysis_mode": "daily",
  "model": "gpt-5.4",
  "reasoning_effort": "medium",
  "include_web_search": true,
  "web_search_policy": "required",
  "estimated_cost_usd": 0.0,
  "actual_usage": {
    "input_tokens": null,
    "output_tokens": null,
    "reasoning_tokens": null,
    "web_search_calls": 0
  },
  "input_summary": {},
  "market_summary": {},
  "portfolio_summary": {},
  "stocks": [],
  "action_plan": [],
  "critical_warnings": [],
  "sources": [],
  "warnings": [],
  "raw_model_output": null,
  "manual_prompt": null,
  "status": "success",
  "error": null,
  "holdings_source": "database",
  "web_search_used": true,
  "mock_response": false,
  "cache_hit": false,
  "holdings_snapshot": [],
  "candidates_snapshot": [],
  "market_snapshot": [],
  "request_payload": {}
}
```

## 5. status / error handling

| status | meaning |
|---|---|
| `success` | 正常終了 |
| `missing_api_key` | `OPENAI_API_KEY` 未設定 |
| `json_parse_failed` | OpenAI応答をJSONとして解析できない |
| `openai_api_error` | OpenAI API エラー |
| `openai_sdk_missing` | OpenAI Python SDK 未導入 |
| `no_holdings` | 対象銘柄なし |
| `target_limit_exceeded` | 対象銘柄数上限超過 |
| `daily_limit_exceeded` | 日次実行回数上限超過 |

長い非JSON応答は、Web検索なしのJSON整形リトライを1回実行する。救済に成功した場合は `status=success` とし、`warnings` に整形リトライ実行を記録する。

整形リトライにも失敗した場合でも、応答が `{` / `[` で始まる、または十分な長さがある場合は、OpenAIから分析本文が返っているものとして `status=success` の raw output fallback response を返す。この場合、`raw_model_output` に生応答を保持し、`portfolio_summary.market_temperature` は `raw_output_fallback` とする。短い完全失敗応答は `json_parse_failed` とする。

## 6. Prompt Builder contract

OpenAI API実行時は次の順で処理する。

1. `PortfolioAiReviewService.review()` が `target` を解決する
2. `build_stock_analysis_prompt()` が Base Policy、mode profile、必要章、入力JSON、mode別schemaを組み立てる
3. `call_open_ai_for_stock_review()` が Responses APIへ送信する
4. `parse_ai_review_result()` がJSONをparseし、Pydantic responseへ正規化する
5. `validate_stock_analysis_response()` が不足フィールドをwarning化する
6. `save_ai_review_result()` が必要に応じて履歴保存する

`prompt_only` mode は `build_prompt_only_text()` を使い、OpenAI APIを呼ばない。

## 7. mode profiles

| mode | model env | reasoning env | web policy | sections |
|---|---|---|---|---|
| `scanner` | `OPENAI_MODEL_SCANNER` | `OPENAI_REASONING_SCANNER` | `optional` | Base, 0, 1, 2 summary, 3 summary, 9, 13 short, 14 short |
| `analyst` | `OPENAI_MODEL_ANALYST` | `OPENAI_REASONING_ANALYST` | `required` | Base, 0-14 |
| `judge` | `OPENAI_MODEL_JUDGE` | `OPENAI_REASONING_JUDGE` | `required` | Base, 0,1,2,3,5,8,9,10,11,12,13,14 |
| `critical` | `OPENAI_MODEL_CRITICAL` | `OPENAI_REASONING_CRITICAL` | `strongly_recommended` | Base, 0-14 |
| `prompt_only` | no API call | no API call | `manual_only` | full prompt |

## 8. environment

| env | default/example |
|---|---|
| `OPENAI_API_KEY` | empty |
| `OPENAI_MODEL_SCANNER` | `gpt-5.4` |
| `OPENAI_MODEL_ANALYST` | `gpt-5.4` |
| `OPENAI_MODEL_JUDGE` | `gpt-5.5` |
| `OPENAI_MODEL_CRITICAL` | `gpt-5.5` |
| `OPENAI_REASONING_SCANNER` | `low` |
| `OPENAI_REASONING_ANALYST` | `medium` |
| `OPENAI_REASONING_JUDGE` | `high` |
| `OPENAI_REASONING_CRITICAL` | `xhigh` |
| `OPENAI_ENABLE_WEB_SEARCH` | `true` |
| `OPENAI_MAX_WEB_SEARCH_CALLS` | `5` |
| `OPENAI_MAX_STOCKS_PER_REQUEST` | `20` |
| `OPENAI_DAILY_REQUEST_LIMIT` | `50` |
| `OPENAI_DEFAULT_VERBOSITY` | `medium` |
| `OPENAI_CRITICAL_CONFIRMATION_REQUIRED` | `true` |

## 9. guardrails

- 正式 source は J-Quants / EDINET API / YouTube Data API / allowlist IR を中心とする
- Yahoo! Finance や broker site は自動取得 source にしない
- 規約違反や robots 無視のスクレイピングは入れない
- APIキーや内部スタックトレースをレスポンスやUIに出さない
- AI応答は投資助言の断定ではなく、判断補助の材料として扱う
