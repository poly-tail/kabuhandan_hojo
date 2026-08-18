# kabuhandan_hojo API Spec v1.8

## 1. scope

この版は v1.7 の API 契約を累積継承し、次を追加・更新する。

- canonical Responses API requestへの明示的な`store=false`
- AI回答生成結果とローカルDB保存結果の独立したresponse contract
- 保存失敗時にも生成済み回答を返すbest-effort persistence
- API runnerのloopback既定とFastAPI lifespanだけによるDB初期化
- active prompt 2026.08.18、compiler `individual-security-v2`、正式根拠ラベルへの更新
- legacy stock-reviewの日次quota既定値300と、`review_runs` / provider `api_calls`の分離
- JST日次・月次usage v2 ledger、公式pricing provenance付き概算額、未算定call
- `GET /api/ai/stock-review/usage`とdashboard利用量表示

v1.7 の最小AI縦スライスと、legacy multi-mode stock AI review、Prompt Registry / Prompt Builder、mode別Structured Outputs、Web検索制御、JSON parse救済、ChatGPT手動投入用プロンプト生成は引き続き有効である。ただし、legacy機能はstock-review経路の契約であり、canonical個別銘柄AI経路には継承しない。

### 1.1 AI経路の境界

| 項目 | 個別銘柄AI縦スライス | legacy stock-review |
|---|---|---|
| canonical path | `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}` | `POST /api/ai/stock-review` |
| 対象 | 登録済み個別銘柄1件 | holdings / watchlist / candidates / selected / mock |
| response | `response.output_text` のプレーンテキスト | mode別の構造化review response |
| model | `gpt-5.6-terra` 固定 | mode別環境設定 |
| answer preset | `STANDARD` のみ | scanner / analyst / judge / critical / prompt_only |
| Web検索 | なし | modeとrequestにより利用 |
| Structured Outputs | なし | 利用する経路あり |
| mock / cache / fallback | なし | v1.4契約どおり利用する経路あり |
| prompt | versioned individual-security assets | legacy Prompt Registry / Builder |
| app quota / usage | legacy quotaの対象外 | 成功一括reviewを`review_runs`、provider responseを`api_calls`として別集計 |

一方の経路のmodel、prompt、error、fallback、Web検索、cache、mockの規則を、もう一方へ暗黙適用してはならない。旧endpointの廃止・非推奨化はこの版の対象外である。

## 2. endpoints

| method | path | purpose | response |
|---|---|---|---|
| `GET` | `/health` | アプリ状態確認 | `HealthResponse` |
| `GET` | `/watchlist` | watchlist 一覧 | `list[WatchlistItem]` |
| `POST` | `/watchlist` | watchlist 追加 / 再有効化 | `WatchlistItem` |
| `GET` | `/portfolio` | 保有銘柄一覧 | `list[PortfolioItem]` |
| `POST` | `/portfolio` | 保有銘柄登録 / 更新 | `PortfolioItem` |
| `POST` | `/portfolio/import/csv` | 保有銘柄CSV import | import result |
| `POST` | `/api/ai/analyses` | 個別銘柄AI縦スライス | `AiAnalysisResponse` |
| `GET` | `/api/ai/analyses/{request_id}` | 保存済み個別銘柄AI回答の1件取得 | `AiSavedAnalysisResponse` |
| `POST` | `/api/ai/stock-review` | multi-mode stock AI review | `PortfolioAiReviewResponse` |
| `GET` | `/api/ai/stock-review/usage` | legacy stock-reviewのJST日次・月次usageと概算額 | `PortfolioAiUsageSummary` |
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
| `GET` | `/ui/analysis` | 個別銘柄AI最小画面 HTML shell | `text/html` |
| `GET` | `/ui/analysis/results/{request_id}` | 保存済みAI回答の大型表示 HTML shell | `text/html` |
| `GET` | `/ui/dashboard` | top 画面 HTML shell | `text/html` |
| `GET` | `/ui/security/{ticker_code}` | detail 画面 HTML shell | `text/html` |
| `GET` | `/ui/security/{ticker_code}/chart` | chart 画面 HTML shell | `text/html` |
| `GET` | `/ui/dashboard/data` | UI view model | `DashboardExperienceResponse` |

## 3. legacy `POST /api/ai/stock-review`

この節から第8節まではv1.4のlegacy stock-review契約を継承する。ここで定義するmock、cache、Web検索、Structured Outputs、JSON parse救済、raw output fallbackは `POST /api/ai/analyses` には適用しない。

### 3.1 request

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

### 3.2 request fields

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

### 3.3 `PortfolioAiHolding`

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

### 3.4 `PortfolioAiCandidate`

```json
{
  "ticker": "6857",
  "name": "アドバンテスト",
  "market": "TSE",
  "candidate_reason": "半導体テーマの主力候補",
  "watch_condition": "出来高を伴う上抜け、または押し目形成"
}
```

## 4. legacy stock-review response

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
    "cached_input_tokens": null,
    "output_tokens": null,
    "reasoning_tokens": null,
    "web_search_calls": 0,
    "api_calls": 0
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

## 5. legacy stock-review status / error handling

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

この節のretryとsuccess fallbackはlegacy stock-reviewだけの挙動である。`POST /api/ai/analyses` は同じ挙動を持たない。

日次quotaの`review_runs`は、銘柄数に関係なく成功したtop-level live review 1件を1回とする。mock、forced mock、cache hit、`prompt_only`、事前拒否、OpenAI error、最終parse失敗は増やさない。raw output fallbackを含む`status=success`は1回増やす。provider usageを取得できたResponses responseはparse結果と独立して`api_calls`へ記録し、JSON整形repairにより1 reviewで2 callsになる場合がある。

## 6. legacy Prompt Builder contract

legacy stock-reviewのOpenAI API実行時は次の順で処理する。

1. `PortfolioAiReviewService.review()` が `target` を解決する
2. `build_stock_analysis_prompt()` が Base Policy、mode profile、必要章、入力JSON、mode別schemaを組み立てる
3. `call_open_ai_for_stock_review()` が Responses APIへ送信する
4. `parse_ai_review_result()` がJSONをparseし、Pydantic responseへ正規化する
5. `validate_stock_analysis_response()` が不足フィールドをwarning化する
6. `save_ai_review_result()` が必要に応じて履歴保存する

`prompt_only` mode は `build_prompt_only_text()` を使い、OpenAI APIを呼ばない。

## 7. legacy mode profiles

| mode | model env | reasoning env | web policy | sections |
|---|---|---|---|---|
| `scanner` | `OPENAI_MODEL_SCANNER` | `OPENAI_REASONING_SCANNER` | `optional` | Base, 0, 1, 2 summary, 3 summary, 9, 13 short, 14 short |
| `analyst` | `OPENAI_MODEL_ANALYST` | `OPENAI_REASONING_ANALYST` | `required` | Base, 0-14 |
| `judge` | `OPENAI_MODEL_JUDGE` | `OPENAI_REASONING_JUDGE` | `required` | Base, 0,1,2,3,5,8,9,10,11,12,13,14 |
| `critical` | `OPENAI_MODEL_CRITICAL` | `OPENAI_REASONING_CRITICAL` | `strongly_recommended` | Base, 0-14 |
| `prompt_only` | no API call | no API call | `manual_only` | full prompt |

## 8. legacy stock-review environment

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
| `OPENAI_DAILY_REQUEST_LIMIT` | `300` |
| `OPENAI_DEFAULT_VERBOSITY` | `medium` |
| `OPENAI_CRITICAL_CONFIRMATION_REQUIRED` | `true` |

これらのmode別model、reasoning、Web検索、日次上限設定はlegacy stock-review用である。`POST /api/ai/analyses` が参照するのはサーバー側 `OPENAI_API_KEY` だけで、modelとpreset parameterは第12節の固定値を使う。

### 8.1 `GET /api/ai/stock-review/usage`

このGETはlegacy stock-reviewだけのローカルusageを返す。canonical `POST /api/ai/analyses`、mock、cache hit、`prompt_only`は集計対象外である。responseへ`Cache-Control: no-store`を付ける。

```json
{
  "scope": "legacy_stock_review",
  "timezone": "Asia/Tokyo",
  "daily_limit": 300,
  "remaining_today": 298,
  "today": {
    "period": "2026-08-17",
    "review_runs": 2,
    "api_calls": 3,
    "input_tokens": 12000,
    "cached_input_tokens": 1000,
    "output_tokens": 3000,
    "reasoning_tokens": 1800,
    "web_search_calls": 1,
    "estimated_cost_usd": 0.0825,
    "unpriced_api_calls": 0
  },
  "month": {
    "period": "2026-08",
    "review_runs": 18,
    "api_calls": 20,
    "input_tokens": 120000,
    "cached_input_tokens": 10000,
    "output_tokens": 30000,
    "reasoning_tokens": 18000,
    "web_search_calls": 5,
    "estimated_cost_usd": 0.825,
    "unpriced_api_calls": 1
  },
  "pricing": {
    "version": "openai-standard-2026-08-17",
    "as_of": "2026-08-17",
    "currency": "USD",
    "estimate_only": true,
    "web_search_usd_per_call": 0.01,
    "models": {
      "gpt-5.4": {
        "input_usd_per_million": 2.5,
        "cached_input_usd_per_million": 0.25,
        "output_usd_per_million": 15.0,
        "long_context_threshold_tokens": 272000,
        "long_context_input_multiplier": 2.0,
        "long_context_output_multiplier": 1.5
      },
      "gpt-5.5": {
        "input_usd_per_million": 5.0,
        "cached_input_usd_per_million": 0.5,
        "output_usd_per_million": 30.0,
        "long_context_threshold_tokens": 272000,
        "long_context_input_multiplier": 2.0,
        "long_context_output_multiplier": 1.5
      },
      "gpt-5.6-terra": {
        "input_usd_per_million": 2.0,
        "cached_input_usd_per_million": 0.2,
        "output_usd_per_million": 12.0,
        "long_context_threshold_tokens": null,
        "long_context_input_multiplier": null,
        "long_context_output_multiplier": null
      }
    },
    "source_urls": [
      "https://developers.openai.com/api/docs/models/gpt-5.4",
      "https://developers.openai.com/api/docs/models/gpt-5.5",
      "https://developers.openai.com/api/docs/models/gpt-5.6-terra",
      "https://developers.openai.com/api/docs/pricing"
    ]
  },
  "incomplete_pre_v2_history": true,
  "official_billing_is_authoritative": true
}
```

`today.period`はJSTの`YYYY-MM-DD`、`month.period`はJSTの`YYYY-MM`である。`remaining_today=max(0,daily_limit-today.review_runs)`とする。

#### 8.1.1 count semantics

- `review_runs`: `status=success`まで完了したlive一括review数。5銘柄をまとめた1 requestも1回。
- `api_calls`: usageを取得できたprovider Responses response数。primary response、JSON repair response、後段parseに失敗したresponseを含み得る。
- `input_tokens` / `cached_input_tokens` / `output_tokens`: provider usageの合計。
- `reasoning_tokens`: output tokenの内訳として追跡するが、価格計算で別に加算しない。
- `web_search_calls`: response outputに現れた実際の`web_search_call`数。設定上限値ではない。
- `unpriced_api_calls`: unknown model、usage token欠損、負値、cached tokenがinput tokenを超える等により価格を推測しなかったprovider call数。

`daily_limit=300`は成功top-level reviewの運用quotaであり、provider call数や費用のhard capではない。OpenAI errorと最終parse失敗は`review_runs`を消費しない一方、usageを取得できたparse失敗responseは`api_calls`へ残る。provider attempt開始前のatomic reservation、失敗attemptを含むhard call budget、hard cost ceiling、複数process間の厳密な上限は実装しない。

#### 8.1.2 pricing and estimate

standard processingのUSD / 1M token rateは次のversioned catalogを使う。

| model | input | cached input | output | long-context rule |
|---|---:|---:|---:|---|
| `gpt-5.4` | 2.50 | 0.25 | 15.00 | input tokens > 272,000でinput/cached 2倍、output 1.5倍 |
| `gpt-5.5` | 5.00 | 0.50 | 30.00 | input tokens > 272,000でinput/cached 2倍、output 1.5倍 |
| `gpt-5.6-terra` | 2.00 | 0.20 | 12.00 | input tokens > 272,000でinput/cached 2倍、output 1.5倍 |

Web検索toolはresponseに現れた実call 1件につきUSD 0.01を加算する。基本式は`(uncached_input × input_rate + cached_input × cached_rate + output × output_rate) / 1,000,000 + actual_web_search_calls × 0.01`である。reasoning tokenはoutput tokenへ含まれるため二重加算しない。

この値はprovider usageと2026-08-17時点の公開standard priceによる参考概算であり、請求書ではない。Batch / Flex、契約割引、無料枠、税、価格改定、provider側の丸め等を保証しない。`official_billing_is_authoritative=true`のとおり、OpenAI PlatformのUsage Dashboardと請求情報を正本とする。算定不能なcallは0円扱いせず`unpriced_api_calls`へ出す。

公式確認元:

- [GPT-5.4 model](https://developers.openai.com/api/docs/models/gpt-5.4)
- [GPT-5.5 model](https://developers.openai.com/api/docs/models/gpt-5.5)
- [GPT-5.6 Terra model](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

#### 8.1.3 local ledger

- 正本pathは`data/ai_review_usage_v2.json`。Git管理しない。
- rootは`version=2`、`timezone=Asia/Tokyo`、`scope=legacy_stock_review`、`pricing_catalog`、`days`を持つ。
- `days[YYYY-MM-DD]`は`review_runs`、`api_calls`、token totals、`web_search_calls`、Decimal文字列の`estimated_cost_usd`、`unpriced_api_calls`、`pricing_versions`を持つ。
- 更新はprocess内`RLock`と同一directoryの一時fileからの`os.replace`で行う。
- 旧`data/ai_review_usage.json`はtestで汚染された可能性があるため移行しない。`incomplete_pre_v2_history=true`は、v2開始前の月間回数・金額が完全でないことを表す。
- ledgerとusage responseへAPIキー、prompt、質問、回答、銘柄context、provider raw responseを含めない。
- testはusage/history/cache pathを一時directoryへ差し替え、repositoryのlocal dataを変更しない。

#### 8.1.4 cache hit

legacyのcache機能とrequest contractは変更しない。cache hitしたrequestはOpenAIを呼ばず、`review_runs`と`api_calls`を増やさない。

## 9. `POST /api/ai/analyses`

登録済みでactiveな `security_master` 1件と自由質問を、versioned promptでOpenAI Responses APIへ1回だけ送る。成功時は `response.output_text` をプレーンテキストのまま返す。

### 9.1 request

```json
{
  "security_code": "7203",
  "question": "現在与えられている情報だけで、この銘柄は今買い候補ですか。",
  "preset": "STANDARD"
}
```

### 9.2 request fields

| field | type | required | default | validation / meaning |
|---|---|---:|---|---|
| `security_code` | `string` | yes | - | 入力時4〜10文字。trim後に非空とし、`security_master.ticker_code`として解決する |
| `question` | `string` | yes | - | 入力時1〜4000文字。trim後に非空とするユーザー自由質問 |
| `preset` | enum | no | `STANDARD` | 現在有効な値は `STANDARD` のみ |

- request bodyの未知fieldは拒否する。
- `security_id` は現行契約に含まれない。
- `HIGH` 等の未実装preset、blank、長さ違反、未知fieldはFastAPI/Pydantic標準のHTTP 422 validation responseになる。
- inactiveな銘柄は未登録と同様に扱い、OpenAI APIを呼ばない。

### 9.3 service path

```text
FastAPI route
→ active security_master解決
→ IndividualSecurityPromptCompiler
→ OpenAIResponsesClient（store=false）
→ response.status / response.id / response.output_text検証
→ AiAnalysisRecordをlocal SQLへ1回だけ保存試行
→ 生成結果と保存結果を分けたAiAnalysisResponse
```

この経路ではbackground、streaming、polling、`previous_response_id`を使用しない。OpenAI callは1ユーザー送信につき最大1回で、保存commit失敗を理由に再呼び出さない。

## 10. `AiAnalysisResponse`

### 10.1 success

OpenAI生成成功時は、保存結果にかかわらずHTTP 200と`status=success`を返す。

保存成功:

```json
{
  "request_id": "8a5c23cd-e405-42e4-b1d2-0ca2a7f8be89",
  "status": "success",
  "answer_text": "プレーンテキストの分析回答",
  "error": null,
  "security": {
    "security_code": "7203",
    "name": "トヨタ自動車",
    "market": "東証プライム"
  },
  "openai_response_id": "resp_...",
  "persistence_status": "saved",
  "saved_at": "2026-08-17T12:34:56+00:00",
  "persistence_warning": null
}
```

保存失敗:

```json
{
  "request_id": "8a5c23cd-e405-42e4-b1d2-0ca2a7f8be89",
  "status": "success",
  "answer_text": "プレーンテキストの分析回答",
  "error": null,
  "security": {
    "security_code": "7203",
    "name": "トヨタ自動車",
    "market": "東証プライム"
  },
  "openai_response_id": "resp_...",
  "persistence_status": "failed",
  "saved_at": null,
  "persistence_warning": "回答は生成されましたが、ローカルDBへ保存できませんでした。大画面での再表示は利用できません。"
}
```

生成成功時の不変条件:

- `request_id`はリクエストごとに生成するUUID文字列である。
- `status`は`success`、`answer_text`はtrim後に非空、`error`は`null`である。
- `security`と`openai_response_id`は非nullである。
- 保存成功では`persistence_status=saved`、`saved_at`は非null、`persistence_warning=null`である。
- 保存失敗では`persistence_status=failed`、`saved_at=null`、`persistence_warning`は上記のsafeな定型文である。
- `answer_text`はMarkdownやJSONとしてparseせず、OpenAI `response.output_text`のプレーンテキストとして扱う。

### 10.2 typed error

```json
{
  "request_id": "8a5c23cd-e405-42e4-b1d2-0ca2a7f8be89",
  "status": "error",
  "answer_text": null,
  "error": {
    "code": "TIMEOUT",
    "message": "OpenAI APIの応答がタイムアウトしました。"
  },
  "security": null,
  "openai_response_id": null,
  "persistence_status": null,
  "saved_at": null,
  "persistence_warning": null
}
```

typed error時の不変条件:

- `status` は `error` である。
- `answer_text` は `null` で、失敗を回答本文として返さない。
- `error` はsafeな`code`とユーザー向け`message`を含む。
- OpenAI response IDを取得できた非completed/空回答等では、`openai_response_id`が非nullになる場合がある。
- OpenAI SDKのexception type、provider raw message、stack trace、APIキーは公開responseへ含めない。

入力validationのHTTP 422はFastAPI標準 `HTTPValidationError` であり、このenvelopeではない。

### 10.3 成功回答の保存契約

OpenAI responseの検証後、`AiAnalysisRecord`へ次を1回だけ保存試行する。

- `request_id`
- 銘柄コード、銘柄名、市場のrequest時snapshot
- ユーザー質問と検証済み`answer_text`
- preset、model、reasoning effort / mode、text verbosity
- OpenAI response ID
- prompt version、profile、compiler version、module ID / name、asset IDs、source SHA-256、compiled SHA-256
- 保存日時

APIキー、Authorization header、prompt全文、OpenAI provider raw response / raw error、stack traceは保存しない。

legacy usage v2 ledgerは回数、token、tool call、概算、pricing versionだけを持ち、prompt、質問、回答、銘柄context、APIキーを保存しない。

SQL commitが失敗した場合はrollbackし、同じrequest内でOpenAIを再呼び出さない。生成済み回答をHTTP 200のsuccess responseで返し、保存結果だけを`persistence_status=failed`、`saved_at=null`、safeな`persistence_warning`として表す。内部logにはrequest ID、OpenAI response ID、例外型などの安全な識別情報だけを残し、質問、回答、prompt全文、APIキー、raw DB例外詳細を含めない。

保存失敗requestのrecordは存在しないため、同じrequest IDの詳細GETは従来どおり`ANALYSIS_NOT_FOUND`となる。保存成功recordだけを再表示の正本とする。

### 10.4 `GET /api/ai/analyses/{request_id}`

path parameterはUUIDとする。保存済み成功回答が存在する場合はHTTP 200で`AiSavedAnalysisResponse`を返す。

```json
{
  "request_id": "8a5c23cd-e405-42e4-b1d2-0ca2a7f8be89",
  "status": "success",
  "saved_at": "2026-08-17T12:34:56+00:00",
  "security": {
    "security_code": "7203",
    "name": "トヨタ自動車",
    "market": "東証プライム"
  },
  "question": "現在与えられている情報だけで、この銘柄は今買い候補ですか。",
  "answer_text": "プレーンテキストの分析回答",
  "preset": "STANDARD",
  "model": "gpt-5.6-terra",
  "openai_response_id": "resp_..."
}
```

- validだが存在しないUUIDはHTTP 404の`ANALYSIS_NOT_FOUND` error envelopeを返す。
- UUIDでないpathはFastAPI標準HTTP 422とする。
- DB dependencyを利用できない場合はHTTP 503の`DATABASE_UNAVAILABLE`を返す。
- 取得responseにはreasoning設定とprompt traceを公開しない。それらはローカルrecord内の監査情報として保持する。
- 一覧、検索、削除、export、共有、保持期限管理はこのAPI契約に含めない。
- POSTとGETの成功・error responseはいずれも`Cache-Control: no-store`とする。FastAPIがroute handler前に生成するHTTP 422 validation responseもmiddlewareで対象にする。

## 11. security context

`AiAnalysisService` はactiveな `SecurityMaster` から次をPromptCompilerへ渡す。

- `security_code`
- `name`
- `market`
- `industry_17`
- `industry_33`
- `listed_date`

公開responseの `AiSecuritySnapshot` は `security_code`、`name`、`market` だけを返す。industryとlisted dateはprompt内部contextであり、公開snapshotには含めない。

runtime inputでは次を明示する。

- request生成日時（JST）
- `market_data_as_of` は未提供
- 利用可能contextは登録済みsecurity masterの上記項目だけ
- 現在価格、決算、コンセンサス、チャート、テクニカル、出来高、信用、空売り、資金フロー、市場地合い、為替、金利、イベント、保有状況、許容損失、希望時間軸は未提供

新しいJ-Quants取得、Web検索、外部市場contextの取得はこのendpointの処理に含まれない。

## 12. OpenAI Responses API contract

| item | exact value / behavior |
|---|---|
| API | OpenAI Responses API |
| model | `gpt-5.6-terra` |
| preset | `STANDARD` |
| `reasoning.effort` | `medium` |
| `reasoning.mode` | 未送信 (`None`) |
| `text.verbosity` | `medium` |
| timeout | 60秒 |
| SDK `max_retries` | `0` |
| instructions | versioned static prompt assets |
| input | security contextとユーザー質問 |
| metadata | 第14節のprompt traceだけ |
| `store` | `false`（必ず明示） |
| `previous_response_id` | 未送信 |
| `temperature` | 未送信 |
| output token上限 | 明示設定なし |
| tools / Web search | 未送信 |
| Structured Outputs / JSON Schema | 未使用 |
| cache / mock / fallback | 未使用 |
| parse / JSON修復 | 未使用 |
| 再AI呼び出し | なし |

`OPENAI_MODEL`、`OPENAI_MODEL_SCANNER`等のlegacy環境変数で、新endpointのmodelを暗黙変更しない。回答presetとmodel選択は別軸であり、現在はmodel選択API/UIを持たない。

`store=false`はResponses APIのApplication State保存を無効化する。この指定はHTTP responseの`Cache-Control: no-store`とは別であり、OpenAI API全体のZero Data Retentionを保証しない。abuse monitoring log等の扱いは組織のdata control設定に従う。background modeは追加しない。

1回のOpenAI call後、次をすべて満たした場合だけ成功とする。

1. `response.status == "completed"`
2. `response.id` が非空
3. trim後の `response.output_text` が非空

いずれかを満たさない場合、raw responseや途中本文をsuccessとして返さない。

## 13. individual-security PromptCompiler contract

### 13.1 compile order

OpenAI `instructions` は次の順で合成する。

1. `common_os`
2. `common_input_rules`
3. `execution_constraints`
4. `task_module`

OpenAI `input` は次の順で合成する。

1. `<security_context>`: 実行時security contextと未提供context
2. `<user_question>`: JSON化したユーザー自由質問

ユーザー質問は分析対象データであり、共通OSやexecution constraintsを書き換える命令として扱わない。

### 13.2 selected assets

| role | asset ID | source section |
|---|---|---|
| common OS | `common_os@2026.08.18` | `1. 株判断共通OS` |
| common input | `common_input_rules@2026.08.18-mvp1` | `2. 共通入力テンプレート`のMVP必要部分 |
| execution constraints | `execution_constraints_no_tools@mvp1` | Web・外部市場データなしのアプリ制約 |
| task module | `individual_comprehensive@2026.08.18` | `3.1 総合的な個別銘柄分析` |

active prompt versionは `2026.08.18`、profileは `individual_security_comprehensive`、compiler versionは `individual-security-v2`、module IDは `3.1` である。source titleは「株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）」、source SHA-256は`B1C0AF5B2C33D76E4F836A428380237383FB7EAEA8B6FEAFFD9CC82632416D30`で、非送信の`assets/v2026_08_18/SOURCE.md`を検証する。v2026.08.17原資料のtitle/hashは`revision.base_source`として保持し、immutableなv2026.08.17 assetを変更しない。共通OSには、銘柄の表示・言及を原則「銘柄名（銘柄コード）」、外国銘柄は「会社名（ticker）」とする命名規則を含む。共通入力ruleは銘柄名と銘柄コードを別項目として扱う。

用途module 3.2〜3.14、アプリ向けJSON Schema、人間向け重複output templateはこのprofileへ含めない。

### 13.3 asset integrity

- manifestのcompile orderが固定順と一致しなければ失敗する。
- task moduleが正確に`3.1`でなければ失敗する。
- asset pathはpackage内の相対pathに限定し、absolute pathと`..`を拒否する。
- 各assetのbytesをmanifest SHA-256と照合する。
- UTF-8でdecodeできないasset、欠落asset、空assetを拒否する。
- prompt全文をアプリコード中の巨大な文字列として複製しない。
- active runtime contextとassetでは根拠ラベルを`【V】確認済み`、`【E】推定`、`【U】未確認`に統一する。
- active compiled promptに旧括弧ラベルが残る場合はOpenAI APIを呼ばずfail closedとする。

## 14. prompt trace

PromptCompilerは次のtraceを作り、OpenAI Responses requestの`metadata`へ文字列として渡す。

| metadata key | value |
|---|---|
| `prompt_version` | `2026.08.18` |
| `prompt_profile` | `individual_security_comprehensive` |
| `prompt_compiler` | `individual-security-v2` |
| `prompt_module` | `3.1` |
| `prompt_assets` | 使用asset IDをcomma区切りで連結 |
| `prompt_source_sha256` | 原資料provenance hash |
| `prompt_sha256` | `instructions + input`のcompiled SHA-256 |

通常ログの成功記録は、アプリrequest ID、OpenAI response ID、prompt version、module ID、asset IDs、compiled prompt SHA-256を含む。

次はOpenAI metadata、通常ログ、FastAPI response、browserへ出さない。

- APIキー
- prompt全文
- ユーザー質問本文

`AiAnalysisResponse`と`AiSavedAnalysisResponse`へprompt traceを公開しない。成功時は同じtraceを`AiAnalysisRecord`へ保存し、request IDとOpenAI response IDに関連付ける。OpenAI側の保持をアプリ履歴の正本にせず、ローカルSQL recordを再表示と監査相関の正本とする。prompt全文はローカルrecordにも保存しない。

## 15. `POST /api/ai/analyses` HTTP / error mapping

| HTTP | error code | trigger |
|---:|---|---|
| 200 | - | completed、response IDあり、非空output text |
| 404 | `SECURITY_NOT_FOUND` | security masterに存在しない、またはinactive |
| 422 | FastAPI validation error | request schema違反、未対応preset、未知field |
| 429 | `RATE_LIMITED` | OpenAI rate limit / quota error |
| 502 | `MODEL_UNAVAILABLE` | OpenAI NotFound / PermissionDenied / `model_not_found` |
| 502 | `INVALID_API_PARAMETERS` | OpenAI BadRequest / UnprocessableEntity。ただし`model_not_found`を除く |
| 502 | `NETWORK_ERROR` | OpenAI connection errorまたは`OSError` |
| 502 | `EMPTY_RESPONSE` | completedだがtrim後output textが空 |
| 502 | `UNKNOWN_OPENAI_ERROR` | その他OpenAI error、非completed、response ID欠落 |
| 503 | `DATABASE_UNAVAILABLE` | database dependencyを利用できない |
| 503 | `AUTHENTICATION_ERROR` | APIキー未設定またはOpenAI認証失敗 |
| 504 | `TIMEOUT` | OpenAI timeout |
| 500 | typed codeなし | prompt manifest/asset構成異常等の未処理内部error |

OpenAI失敗、parse失敗、空回答をmock、cache、raw response、別model、別promptへfallbackしてsuccessにはしない。OpenAI成功後のローカル保存失敗はこのerror mappingではなく、HTTP 200の生成成功response内の`persistence_status=failed`で表す。`PERSISTENCE_ERROR`はschema互換のため残るが、この通常経路では返さない。

### 15.1 `PromptConfigurationError` の現行境界

manifest unreadable、compile order不正、module不正、asset欠落、hash mismatch、UTF-8不正、空asset等では `PromptConfigurationError` が発生する。現行ではservice dependency構築中またはcompile中のこの例外をrouteのtyped error envelopeへ変換しておらず、HTTP 500の内部errorとなる。

`PROMPT_CONFIGURATION_ERROR`という公開error codeは未実装であり、この版の正式schemaへ追加しない。将来typed化する場合は、コード実装、response schema、OpenAPI response、testを同時に更新する。

### 15.2 `GET /api/ai/analyses/{request_id}` HTTP / error mapping

| HTTP | error code | trigger |
|---:|---|---|
| 200 | - | 保存済み成功recordを取得 |
| 404 | `ANALYSIS_NOT_FOUND` | valid UUIDに対応するrecordがない |
| 422 | FastAPI validation error | pathがUUIDでない |
| 503 | `DATABASE_UNAVAILABLE` | database dependencyを利用できない |

## 16. `GET /ui/analysis`

依存ライブラリなしのHTML/CSS/JavaScript shellで、次だけを提供する。

- `/securities/search`を使う登録済み銘柄検索と1件選択
- 自由質問textarea
- `STANDARD`固定送信
- loading表示。送信中は銘柄検索・銘柄選択・質問編集を無効化し、request対象と表示対象を固定する
- safeなerror表示
- `answer_text`のプレーンテキスト表示
- 保存結果warning
- `persistence_status=saved`の場合だけ表示する`別ウィンドウで大きく表示`link

browserから `POST /api/ai/analyses` へ送るbodyは `security_code`、`question`、`preset`だけである。APIキー、model、reasoning設定、prompt全文、prompt traceをbrowserへ渡さない。

回答と検索結果は`textContent`で設定し、回答要素は`white-space: pre-wrap`を使う。Markdown renderer、HTML挿入、構造化カードを使わない。

保存成功linkは保存済み`request_id`を使って`/ui/analysis/results/{request_id}`を`target="_blank"`、`rel="noopener noreferrer"`で開く。`persistence_status=failed`では回答本文とwarningを表示するが、保存済み表示、`saved_at`、reader linkは表示しない。OpenAI失敗時、loading中、保存前にもlinkを表示しない。

`GET /ui/analysis/results/{request_id}`は大型の読み取り専用HTML shellである。browserから同じoriginの`GET /api/ai/analyses/{request_id}`を`cache: "no-store"`で呼び、保存日時、銘柄、質問、preset、model、回答本文を表示する。回答と質問は`textContent`で反映し、回答は`white-space: pre-wrap`とする。loading、not foundを含むsafeなerror表示を持ち、prompt trace、APIキー、provider raw responseは表示しない。

両HTML shellのresponseは`Cache-Control: no-store`と`Referrer-Policy: no-referrer`を持つ。保存回答の一覧・検索・削除・export UIは提供しない。

## 17. security and privacy

### 17.1 implemented controls

- `OPENAI_API_KEY`はサーバー側設定からのみ読み、request、response、browser、通常ログ、OpenAI metadataへ出さない。
- ユーザー質問は最大4000文字で、未知request fieldを拒否する。
- DB検索は入力文字列のSQL直結ではなくORM lookupで行う。
- ユーザー質問をpromptの事実・確認済みデータとして扱わない。
- execution constraintsでprompt assetをユーザー質問より上位に置く。
- tools、Web検索、自動売買、外部actionを実行しない。
- OpenAI回答をHTMLとして解釈せず`textContent`で表示する。
- provider raw error、exception stack、APIキー、prompt全文、質問全文を公開response/通常ログへ出さない。
- 成功した質問、回答、銘柄snapshot、生成設定、OpenAI response ID、prompt traceだけをローカルSQLへ保存し、APIキー、prompt全文、provider raw responseは保存しない。
- canonical OpenAI requestへ`store=false`を明示し、Responses Application State保存を無効化する。これはZero Data Retention全体の保証ではない。
- canonical APIはvalidation responseを含めて、HTML shellは各routeから`Cache-Control: no-store`を返す。
- DB初期化はFastAPI lifespanだけから通常起動1回につき1回行い、`create_app()`では実行しない。TestClientはcontext managerでlifespanを起動し、DB直結unit testはfixtureで初期化する。
- 出力は判断補助であり、断定的投資助言や自動売買指示として扱わない。

### 17.2 known deployment limitations

現行の `POST /api/ai/analyses` は次を実装していない。

- アプリ認証・認可
- endpoint固有のserver-side rate limit、daily quota、cost ceiling
- idempotency、同時送信のserver-side抑止
- TLS終端
- 保存回答の一覧・検索・削除・export・保持期限・自動purge

legacy stock-review用の `OPENAI_DAILY_REQUEST_LIMIT` は新endpointへ適用されない。API runnerの既定bind hostは`127.0.0.1`であり、既定ではローカルPCだけから到達できる。

LANまたはAndroid端末から確認する場合は、利用者が明示的に`python scripts/run_api.py --host 0.0.0.0`を指定できる。`0.0.0.0`はLAN内の他端末から到達可能になるため、認証・利用者分離・rate limitがない現状では信頼できる閉じたnetworkに限定し、Internetへ直接公開してはならない。Android対応や外部公開の前に認証、HTTPS、rate limit、保存recordのaccess controlとretention policyを別フェーズで実装する必要がある。

## 18. OpenAPI declaration gap

現行FastAPI routeの自動生成OpenAPIは、`POST /api/ai/analyses`と`GET /api/ai/analyses/{request_id}`について200と422を中心に宣言する。実装が返す404、429、500、502、503、504は、第15節の実行時契約には存在するが、route decoratorの`responses`としてOpenAPIへまだ網羅的に宣言されていない。

この版はその差を既知のdocumentation/code-generation gapとして記録する。OpenAPIへ未宣言のstatusを、実行時に返さないという意味ではない。将来routeへresponse定義を追加するときは、この表とgenerated OpenAPIの一致をtestで固定する。

## 19. verification contract

### 19.1 automated tests

最低限、次を維持する。

- PromptCompilerが共通OS、共通入力ルール、execution constraints、module 3.1を順序どおり読む
- security contextと自由質問がruntime inputへ含まれる
- module 3.2〜3.14とJSON Schema固有指示が混入しない
- prompt version、asset IDs、module、hashを取得できる
- prompt/question全文がmetadataへ入らない
- OpenAI requestが固定model、STANDARD parameter、timeout、metadata、`store=false`を使い、tools、`previous_response_id`、backgroundを持たない
- completedかつ非空output textだけを成功とする
- empty、non-completed、timeout、SDK errorを失敗へ分類する
- endpointの正常、typed error、未知銘柄、未対応preset
- UI shellが`textContent`と`pre-wrap`を使い、APIキーを含まない
- 保存成功responseが同じrequest IDで`AiAnalysisRecord`へ保存され、`persistence_status=saved`と`saved_at`が入る
- 保存commit失敗がrollbackされ、recordを残さず、OpenAIを再呼び出さず、HTTP 200、非空`answer_text`、`persistence_status=failed`、safe warningを返す
- 保存失敗の通常logに質問、回答、prompt全文、APIキー、raw DB例外詳細が含まれない
- 保存recordが質問、回答、snapshot、生成設定、OpenAI response ID、prompt traceを持ち、APIキー、prompt全文、provider raw responseを持たない
- `GET /api/ai/analyses/{request_id}`の正常、`ANALYSIS_NOT_FOUND`、UUID validation、`Cache-Control: no-store`
- `/ui/analysis`は保存成功時だけ`target="_blank"`と`rel="noopener noreferrer"`のreader linkを表示し、保存失敗時は回答とwarningだけを表示する
- 大型回答shellが保存APIを呼び、loading、safe error、`textContent` / `pre-wrap`のplain-text表示を持つ
- 代表質問fixtureが買い判断、決算後、要因分離、モメンタム、需給、イベント、リスク、反証、情報不足、no-tradeを網羅する
- legacy stock-reviewの既存testを維持する
- quota既定300、1 batch=1 review、mock/cache/prompt-only/limit拒否の非加算、repair/parse-failed provider responseのapi call加算を確認する
- JST日/月summary、pricing formula、unknown model/token欠損の未算定、旧counter非移行、atomic ledger formatを確認する
- usage/history/cacheを一時pathへ隔離し、repositoryのlocal dataをtestが変更しないことを確認する

### 19.2 live checks

- `scripts/smoke_openai_response.py` はFastAPI/browserなしで固定model、STANDARD、completed status、OpenAI response ID、非空output textを確認する。
- live FastAPI checkは `POST /api/ai/analyses` がHTTP 200、`status=success`、OpenAI response ID、非空answer textを返すことを確認する。
- live browser checkは銘柄検索、選択、質問、送信、loading、実endpoint response、answer表示、error非表示、別ウィンドウ導線、保存回答の大型表示を確認する。

live checkは実APIキーと課金を伴うため、秘密情報をfixture、test output、通常ログへ保存せず、通常のunit testで暗黙実行しない。

## 20. guardrails

- 正式 source は J-Quants / EDINET API / YouTube Data API / allowlist IR を中心とする。
- Yahoo! Finance や broker site は自動取得 source にしない。
- 規約違反や robots 無視のスクレイピングを入れない。
- APIキーや内部stack traceをresponseやUIに出さない。
- AI応答は投資助言の断定ではなく、判断補助の材料として扱う。
- 情報不足を推測で補完せず、必要に応じて `insufficient_data` または `no_trade` とする。

### 20.1 official OpenAI references

- [`gpt-5.6-terra` model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra): Responses API対応と`reasoning.effort`対応値の確認元。
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model): `reasoning.effort`、`reasoning.mode`、`text.verbosity`を独立して扱う際の確認元。
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint): Responses Application State、`store=false`、abuse monitoring logs、Zero Data Retentionの区別の確認元。

この版の固定値は2026-08-17時点の実装契約である。公式仕様または導入SDKを変更するときは、コード、test、API仕様を同じ変更単位で更新する。

## 21. known functional limitations of the new vertical slice

- 個別銘柄1件だけを扱う。
- presetは`STANDARD`だけである。
- model選択UI/APIはない。
- 現在価格、財務、決算、チャート、テクニカル、需給、市場、為替、金利、イベントを新規取得しない。
- Web検索を行わない。
- Structured Outputs、JSON Schema、JSON修復、Markdown rendererを使わない。
- cache、background、streaming、polling、fallbackを使わない。
- prompt traceは通常responseへ公開せず、成功record内だけへ永続保存する。
- 保存回答を1件ずつrequest IDで取得できるが、一覧、検索、削除、export、共有、保持期限、自動purgeはない。
- 保存回答API/UIにアプリ認証・認可はないため、trusted local環境以外へ公開しない。
- legacy AI endpointの削除・統合・migrationは行わない。
- 現行Pydantic schemaは`security_code`の4〜10文字制約をtrim前に評価する。空白でpaddingした短い値がtrim後4文字未満でも通る場合があり、正規化後の長さ再検証は未実装である。通常UIは検索結果のtrim済みcodeを送る。

## 22. revision history

### v1.8 — 2026-08-17

- v1.7の契約を累積継承した。
- legacy stock-reviewの日次quota既定値を50から300へ変更し、銘柄数に依存しない成功一括reviewを`review_runs`として定義した。
- provider responseの`api_calls`、token、実Web検索callをreview quotaから分離し、repairやparse失敗後もusageを追跡できるようにした。
- JST日次・月次v2 ledgerと`GET /api/ai/stock-review/usage`を追加し、旧汚染counterを移行しない境界を定義した。
- 2026-08-17時点の公式standard pricing、pricing source、token由来概算、未算定call、正式請求との境界を追加した。
- test local-data隔離、dashboard usage panelと利用者向けholdings-source labelを追加した。
- canonical `POST /api/ai/analyses`のmodel、STANDARD preset、quota、保存、prompt契約は変更しない。

### v1.7 — 2026-08-17

- v1.6の契約を累積継承した。
- canonical Responses API requestへ`store=false`を必須化し、Application State保存の無効化とZero Data Retention全体の保証を区別した。
- AI生成成功とローカル保存結果を分離し、保存失敗でもHTTP 200、生成済み回答、`persistence_status=failed`、safe warningを返す契約へ変更した。
- reader linkと保存済み表示を保存成功時だけに限定した。
- API runnerの既定bindを`127.0.0.1`へ変更し、明示的な`--host 0.0.0.0`だけをtrusted LAN確認用とした。
- DB初期化をFastAPI lifespanだけへ一本化した。
- active prompt 2026.08.18、compiler `individual-security-v2`、非送信`SOURCE.md`、正式根拠ラベルとlegacy bracket fail-closedを追加し、v2026.08.17 assetとbase source provenanceを履歴として維持した。

### v1.6 — 2026-08-17

- v1.5のcanonical個別銘柄AI縦スライスとlegacy multi-mode契約を累積継承した。
- 成功回答を`AiAnalysisRecord`へ自動保存し、保存失敗をrollbackした上で`PERSISTENCE_ERROR`にする契約を追加した。
- request IDによる保存回答1件取得`GET /api/ai/analyses/{request_id}`と`AiSavedAnalysisResponse`を追加した。
- `/ui/analysis`の大型表示導線と`GET /ui/analysis/results/{request_id}`を追加した。
- API/HTML responseの`Cache-Control: no-store`、保存対象と非保存機密情報、一覧・削除等の非対象を明記した。
- prompt sourceをv2026.08.17へ更新し、「銘柄名（銘柄コード）」命名規則と銘柄名・コードの分離入力を反映した。

### v1.5 — 2026-08-17

- v1.4のlegacy multi-mode stock AI review契約を累積継承した。
- 登録済み個別銘柄1件を扱う `POST /api/ai/analyses` と最小画面 `GET /ui/analysis` を追加した。
- `gpt-5.6-terra`、`STANDARD`、`reasoning.effort=medium`、`text.verbosity=medium`によるResponses API契約を追加した。
- `response.output_text`のプレーンテキスト表示と、non-completed・空回答を失敗とするfail-closed契約を追加した。
- 共通OS、共通入力ルール、no-tools execution constraints、用途module 3.1、security context、自由質問のPromptCompiler契約を追加した。
- prompt version、asset、module、source/compiled SHA-256のtrace方式を追加した。
- 新endpointでmock、cache、fallback、Web検索、Structured Outputs、JSON修復、再AI呼び出しを使わないことを明記した。
- legacy stock-reviewのmock/cache/Web/Structured/JSON fallback契約を新endpointへ適用しない境界を明記した。
- PromptConfigurationErrorのuntyped HTTP 500、OpenAPIのerror response宣言不足、アプリ認証・rate limitなし、trusted local限定を既知制約として記録した。

### v1.4 — 2026-06-15

- multi-mode stock AI review、Prompt Registry / Builder、mode別Structured Outputs、Web検索制御、JSON parse救済、ChatGPT手動投入用prompt契約を追加した。
