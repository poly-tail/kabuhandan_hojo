# kabuhandan_hojo API Spec v1.6

## 1. scope

この版は v1.5 の API 契約を累積継承し、次を追加・更新する。

- 成功したcanonical個別銘柄AI回答のローカルSQL自動保存
- 保存回答をrequest IDで1件取得する `GET /api/ai/analyses/{request_id}`
- 保存回答を大きく表示する `GET /ui/analysis/results/{request_id}`
- 個別銘柄prompt sourceのv2026.08.17への更新

v1.5 の最小AI縦スライスと、legacy multi-mode stock AI review、Prompt Registry / Prompt Builder、mode別Structured Outputs、Web検索制御、JSON parse救済、ChatGPT手動投入用プロンプト生成は引き続き有効である。ただし、legacy機能はstock-review経路の契約であり、canonical個別銘柄AI経路には継承しない。

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
| `OPENAI_DAILY_REQUEST_LIMIT` | `50` |
| `OPENAI_DEFAULT_VERBOSITY` | `medium` |
| `OPENAI_CRITICAL_CONFIRMATION_REQUIRED` | `true` |

これらのmode別model、reasoning、Web検索、日次上限設定はlegacy stock-review用である。`POST /api/ai/analyses` が参照するのはサーバー側 `OPENAI_API_KEY` だけで、modelとpreset parameterは第12節の固定値を使う。

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
→ OpenAIResponsesClient
→ response.status / response.id / response.output_text検証
→ AiAnalysisRecordをlocal SQLへcommit
→ AiAnalysisResponse
```

この経路ではbackground、streaming、pollingを行わない。保存commitが失敗した場合はrollbackし、OpenAI回答をsuccessとして返さない。

## 10. `AiAnalysisResponse`

### 10.1 success

HTTP 200:

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
  "saved_at": "2026-08-17T12:34:56+00:00"
}
```

成功時の不変条件:

- `request_id` はリクエストごとに生成するUUID文字列である。
- `status` は `success` である。
- `answer_text` はtrim後に非空である。
- `error` は `null` である。
- `security` と `openai_response_id` は非nullである。
- `saved_at` はローカルSQLへcommitした日時であり、成功時は非nullである。
- `answer_text` はMarkdownやJSONとしてparseせず、OpenAI `response.output_text` のプレーンテキストとして扱う。

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
  "saved_at": null
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

OpenAI responseの検証後、`AiAnalysisRecord`へ次を保存してcommitする。

- `request_id`
- 銘柄コード、銘柄名、市場のrequest時snapshot
- ユーザー質問と検証済み`answer_text`
- preset、model、reasoning effort / mode、text verbosity
- OpenAI response ID
- prompt version、profile、compiler version、module ID / name、asset IDs、source SHA-256、compiled SHA-256
- 保存日時

APIキー、Authorization header、prompt全文、OpenAI provider raw response / raw error、stack traceは保存しない。SQL commitが失敗した場合はrollbackし、HTTP 500の`PERSISTENCE_ERROR`を返す。OpenAI APIまで成功していても、保存失敗をHTTP 200や`status=success`として扱わない。

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
| `temperature` | 未送信 |
| output token上限 | 明示設定なし |
| tools / Web search | 未送信 |
| Structured Outputs / JSON Schema | 未使用 |
| cache / mock / fallback | 未使用 |
| parse / JSON修復 | 未使用 |
| 再AI呼び出し | なし |

`OPENAI_MODEL`、`OPENAI_MODEL_SCANNER`等のlegacy環境変数で、新endpointのmodelを暗黙変更しない。回答presetとmodel選択は別軸であり、現在はmodel選択API/UIを持たない。

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
| common OS | `common_os@2026.08.17` | `1. 株判断共通OS` |
| common input | `common_input_rules@2026.08.17-mvp1` | `2. 共通入力テンプレート`のMVP必要部分 |
| execution constraints | `execution_constraints_no_tools@mvp1` | Web・外部市場データなしのアプリ制約 |
| task module | `individual_comprehensive@2026.08.17` | `3.1 総合的な個別銘柄分析` |

prompt versionは `2026.08.17`、profileは `individual_security_comprehensive`、compiler versionは `individual-security-v1`、module IDは `3.1` である。共通OSには、銘柄の表示・言及を原則「銘柄名（銘柄コード）」、外国銘柄は「会社名（ticker）」とする命名規則を含む。共通入力ruleは銘柄名と銘柄コードを別項目として扱う。

用途module 3.2〜3.14、アプリ向けJSON Schema、人間向け重複output templateはこのprofileへ含めない。

### 13.3 asset integrity

- manifestのcompile orderが固定順と一致しなければ失敗する。
- task moduleが正確に`3.1`でなければ失敗する。
- asset pathはpackage内の相対pathに限定し、absolute pathと`..`を拒否する。
- 各assetのbytesをmanifest SHA-256と照合する。
- UTF-8でdecodeできないasset、欠落asset、空assetを拒否する。
- prompt全文をアプリコード中の巨大な文字列として複製しない。

## 14. prompt trace

PromptCompilerは次のtraceを作り、OpenAI Responses requestの`metadata`へ文字列として渡す。

| metadata key | value |
|---|---|
| `prompt_version` | `2026.08.17` |
| `prompt_profile` | `individual_security_comprehensive` |
| `prompt_compiler` | `individual-security-v1` |
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
| 500 | `PERSISTENCE_ERROR` | OpenAI成功後のローカルSQL commit失敗。transactionはrollbackする |
| 500 | typed codeなし | prompt manifest/asset構成異常等の未処理内部error |

OpenAI失敗、parse失敗、空回答をmock、cache、raw response、別model、別promptへfallbackしてsuccessにはしない。

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
- 成功時だけ表示する`別ウィンドウで大きく表示`link

browserから `POST /api/ai/analyses` へ送るbodyは `security_code`、`question`、`preset`だけである。APIキー、model、reasoning設定、prompt全文、prompt traceをbrowserへ渡さない。

回答と検索結果は`textContent`で設定し、回答要素は`white-space: pre-wrap`を使う。Markdown renderer、HTML挿入、構造化カードを使わない。

成功linkは保存済み`request_id`を使って`/ui/analysis/results/{request_id}`を`target="_blank"`、`rel="noopener noreferrer"`で開く。失敗時、loading中、保存前には表示しない。

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
- canonical APIはvalidation responseを含めて、HTML shellは各routeから`Cache-Control: no-store`を返す。
- 出力は判断補助であり、断定的投資助言や自動売買指示として扱わない。

### 17.2 known deployment limitations

現行の `POST /api/ai/analyses` は次を実装していない。

- アプリ認証・認可
- endpoint固有のserver-side rate limit、daily quota、cost ceiling
- idempotency、同時送信のserver-side抑止
- TLS終端
- 保存回答の一覧・検索・削除・export・保持期限・自動purge

legacy stock-review用の `OPENAI_DAILY_REQUEST_LIMIT` は新endpointへ適用されない。また、API runnerの既定bind hostは `0.0.0.0` であり、loopback限定をコードで強制していない。

したがってこの版の新endpointはtrusted local development environment向けで、Internetや信頼できないLANへ直接公開してはならない。外部公開前に認証、rate limit/cost control、TLS、host設定、保存recordのaccess controlとretention policyを別フェーズで実装する必要がある。これらを実装済みとはみなさない。

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
- OpenAI requestが固定model、STANDARD parameter、timeout、metadataを使い、toolsを持たない
- completedかつ非空output textだけを成功とする
- empty、non-completed、timeout、SDK errorを失敗へ分類する
- endpointの正常、typed error、未知銘柄、未対応preset
- UI shellが`textContent`と`pre-wrap`を使い、APIキーを含まない
- 成功responseが同じrequest IDで`AiAnalysisRecord`へ保存され、POST responseに`saved_at`が入る
- 保存commit失敗がrollbackされ、HTTP 500の`PERSISTENCE_ERROR`になり、recordが残らない
- 保存recordが質問、回答、snapshot、生成設定、OpenAI response ID、prompt traceを持ち、APIキー、prompt全文、provider raw responseを持たない
- `GET /api/ai/analyses/{request_id}`の正常、`ANALYSIS_NOT_FOUND`、UUID validation、`Cache-Control: no-store`
- `/ui/analysis`の成功linkが`target="_blank"`と`rel="noopener noreferrer"`を持つ
- 大型回答shellが保存APIを呼び、loading、safe error、`textContent` / `pre-wrap`のplain-text表示を持つ
- 代表質問fixtureが買い判断、決算後、要因分離、モメンタム、需給、イベント、リスク、反証、情報不足、no-tradeを網羅する
- legacy stock-reviewの既存testを維持する

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
