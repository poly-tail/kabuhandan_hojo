# Source Overview

## 2026-08-17 specification baseline addendum

- `docs/requirements/requirements_v1.3.md`、`docs/specs/api_spec_v1.6.md`、`docs/screen_specs/screen_spec_v1.8.md` を、個別銘柄AI回答保存、大画面reader、versioned PromptCompilerを含む現行仕様の正本とします。
- `docs/spec_change_history.md` は要件・API・画面仕様の版対応、変更理由、互換性、既知制約を横断して追跡します。実装変更の時系列は引き続き `docs/changelog.md` を正本とします。
- `current.md` は最新版へのpointerと短い概要に限定し、完全な契約はversioned fileへ保持します。

## 2026-08-17 individual-security PromptCompiler addendum

- `app/prompts/individual_security/manifest.json` はprompt version `2026.08.17`、source hash、4つのasset ID/hash、選択module `3.1`、compile orderを正本化します。
- `assets/v2026_08_17/common_os.md` は添付第1章本文を保持し、「銘柄名（銘柄コード）」の併記規則を含みます。`modules/individual_comprehensive.md` は「3.1 総合的な個別銘柄分析」だけを保持し、共通入力では銘柄名とコードを分離します。旧v2026.08.16 assetは再現用に残します。
- `IndividualSecurityPromptCompiler` は共通OS -> 共通入力ルール -> 実行制約 -> 3.1 -> `security_master` context -> 自由質問の順に合成します。3.2〜3.14、アプリ向けJSON Schema、人間向け重複templateは読み込みません。
- `app/services/ai_analysis.py` はcompiler出力を既存clientへ渡します。OpenAI `instructions`には静的規則、`input`には実行時context、`metadata`にはversion・asset・module・hashだけを入れ、公開FastAPI responseにはprompt情報を追加しません。
- 旧 `app/prompts/stock_analysis/` とportfolio AI経路は変更していません。新経路もWeb検索、Structured Outputs、cache、fallbackを使用しません。

## 2026-08-17 AI最小縦スライス

- `app/ai/` は固定モデル、`STANDARD` の回答品質設定、公開エラーコードを管理します。モデル選択はpreset定義へ含めません。
- `app/integrations/openai_responses.py` は Responses APIを1回だけ呼び、timeout、`response.status`、response ID、非空の `response.output_text` を検証します。SDK例外は安全な分類へ変換し、raw例外本文をブラウザへ返しません。
- `app/services/ai_analysis.py` は登録済み銘柄1件を解決し、最小promptを組み立てます。`app/api/routes/ai_analysis.py` の `POST /api/ai/analyses` がcanonical routeです。
- `app/api/routes/analysis_ui.py` は既存の巨大UIから独立した最小画面を返します。回答は `textContent` と `white-space: pre-wrap` で描画し、AI送信中は銘柄検索・選択と質問編集をロックします。
- `app/main.py` のcanonical AI middlewareは、route handler前のFastAPI validation errorを含む `/api/ai/analyses` 配下の全responseへ `Cache-Control: no-store` を付与します。
- `scripts/smoke_openai_response.py` はFastAPIやブラウザを介さず実OpenAI APIを確認します。この縦スライスにはmock、cache、fallback、Web検索、Structured Outputs、streamingを接続しません。
- `app/models/ai_analysis_record.py` はcanonical成功回答、銘柄snapshot、生成設定、prompt provenanceをローカルDBへ保存します。APIキー、prompt全文、provider raw response / errorは列に持ちません。
- `app/services/ai_analysis_records.py` は保存transactionとUUID詳細取得を分離します。commit失敗はrollbackして `PERSISTENCE_ERROR` とし、旧JSON履歴へfallbackしません。
- `GET /api/ai/analyses/{request_id}` が保存済み回答1件を返し、`GET /ui/analysis/results/{request_id}` が大画面readerを返します。どちらも `Cache-Control: no-store` です。

## 2026-06-25 long-term non-monitoring carry risk addendum

- `app/prompts/stock_analysis/` の Prompt Registry に `【5.5. 中長期持ち越し・非監視期間リスク】` を追加しました。`scanner` は簡易版、`analyst` / `judge` / `critical` は詳細版、`prompt_only` は全文プロンプトで扱います。
- `app/schemas/portfolio_ai.py` と Prompt Builder の output schema は `long_term_carry_check`、`non_monitoring_hold_risk`、`needs_long_term_carry_check` を扱い、翌営業日のギャップ要因を見る持ち越しイベント判定とは分離します。
- `app/api/routes/ui.py` のAI分析結果カードは、中長期持ち越し・非監視期間リスク、必要アラート、確認イベント、期間別保有可否、最終判断、日本語ラベル、非監視リスク警告を表示します。

## 2026-06-15 multi-mode stock AI review addendum

- `app/api/routes/portfolio.py` に `POST /api/ai/stock-review` を追加しました。既存の `/portfolio/ai-review` と `/api/portfolio/ai-review` は互換入口として同じ service を呼びます。
- `app/schemas/portfolio_ai.py` は `scanner` / `analyst` / `judge` / `critical` / `prompt_only` と `holdings` / `watchlist` / `candidates` / `selected` / `mock` を扱うrequest / response schemaへ拡張しました。
- `app/prompts/stock_analysis/` に Prompt Registry / Prompt Builder を追加し、ユーザー指定プロンプト全文、Base Policy、modeProfiles、analysisSections、outputSchemas、costControl、webSearchPolicyを分離しました。
- `app/services/portfolio_ai_review.py` は Prompt Builder 出力を OpenAI Responses API へ渡し、用途別model/reasoning、Web検索ON/OFF、検索回数上限、対象銘柄数上限、日次上限、同一入力キャッシュ、ローカルJSON履歴、prompt_only生成、JSON parse fallbackを扱います。
- `app/api/routes/ui.py` のAI分析パネルは5モード実行、対象選択、狙い中銘柄、ユーザー仮説、建玉意図、推定コスト、結果保存、前回結果再表示、ChatGPT投入用プロンプト生成/コピー、warnings/sourcesを表示します。ChatGPT Web画面の自動操作は行いません。

## 2026-05-23 portfolio AI review addendum

- `app/api/routes/portfolio.py` に `POST /portfolio/ai-review` と互換用 `POST /api/portfolio/ai-review` を追加し、保有銘柄の一括AI分析を返します。
- `app/services/portfolio_ai_review.py` は `get_holdings()` / `get_mock_holdings()` / `get_market_snapshot()` / `analyze_portfolio_with_openai()` を分離し、DB保有銘柄、サーバーmock、OpenAI Responses API呼び出し、`reasoning.effort` 指定、Web検索あり時のJSON parse fallbackを扱います。
- `app/api/routes/ui.py` の Portfolio / Watchlist パネルは、APIキー未設定、JSON parse失敗、Web検索なし簡易分析、mock_response の状態をカード表示します。Watchlist はチェック選択した銘柄を `holdings` 指定でAIレビューAPIへ渡します。

## 2026-04-23 manual refresh addendum

- `app/api/routes/ui.py` の手動更新は global / selected ticker のまとめパネルではなく、Market / Portfolio / Materials / Screening / Search / detail 各カード内のボタンに分散しました。
- 手動更新の失敗理由は、押したボタンと同じセクション内の feedback 領域に表示します。0 件取得は、価格・信用需給など必須データだけ失敗扱いにします。
- `app/api/routes/monitoring.py` に `POST /documents/sync/youtube/monitored` を追加し、UI から銘柄別 YouTube monitored channel sync を実行できるようにしました。

## 2026-04-23 local master addendum

- `data/security_master_jp.csv` を追加し、銘柄コードと日本語銘柄名のローカル正本として扱います。
- `app/services/security_master_catalog.py` が CSV を `security_master` に upsert し、`app/services/watchlist.py` の検索前にも同期します。
- `POST /securities/master/sync` はローカルCSVを必ず同期します。UI の `銘柄DB更新` は `require_jquants=true` を付けるため、J-Quants V2 `/equities/master` から全上場銘柄を取得できない場合は失敗表示になります。
- `app/api/routes/ui.py` に `銘柄DB更新` と `市場価格更新` ボタンを追加しました。Market Overview は dashboard 読み込み時に J-Quants を自動で叩かず、ボタンからだけ市場proxy価格を同期します。

## 2026-04-23 YouTube / IR addendum

- `src/kabuhandan_hojo/connectors/youtube.py` を追加し、`POST /documents/sync/youtube` から YouTube Data API observation を raw document / event / video_item に同期できるようにしました。
- `src/kabuhandan_hojo/services/ingestion.py` に allowlist IR import を追加し、`POST /documents/import/ir` で公式 IR URL を event 化できるようにしました。

## 2026-04-23 addendum

- `app/api/routes/portfolio.py` と `app/services/portfolio.py` を追加し、portfolio panel は `portfolio_holding` を正本にしました。
- `src/kabuhandan_hojo/connectors/jquants.py` は V2 `/equities/master` の listed master、daily bars、margin data の取得を持ち、`src/kabuhandan_hojo/services/ingestion.py` から `security_master` / `price_daily` / `flow_snapshot` へ同期します。
- `src/kabuhandan_hojo/connectors/tdnet.py` を追加し、`POST /documents/sync/tdnet` から TDnet API を event import へ流せるようにしました。
- `app/services/dashboard_experience.py` は portfolio items、market-wide sector breadth、detail 時の TDnet auto sync、flow auto sync を UI view model に組み込みます。

## 概要

HTTP の入口は `app/` にあり、source 固有の処理、特徴量計算、score 計算、ingestion は `src/kabuhandan_hojo/` に寄せています。

## package ごとの役割

| path | 役割 |
|---|---|
| `app/main.py` | FastAPI app の起動点とcanonical AI responseの`no-store` middleware |
| `app/ai/` | 最小AI縦スライスの固定モデル、回答preset、エラーコード |
| `app/prompts/individual_security/` | 個別銘柄MVPのversioned prompt assets / manifest / compiler |
| `app/api/routes/ai_analysis.py` | canonical分析POSTと保存済み回答UUID詳細GET |
| `app/api/routes/analysis_ui.py` | `GET /ui/analysis` と保存済み回答の大画面reader |
| `app/integrations/openai_responses.py` | Responses APIの最小clientと例外分類 |
| `app/services/ai_analysis.py` | 銘柄解決、PromptCompiler呼び出し、Responses client連携 |
| `app/services/ai_analysis_records.py` | canonical成功回答のtransaction保存とUUID詳細取得 |
| `app/models/ai_analysis_record.py` | 保存済みcanonical AI回答とprompt provenanceのORM |
| `app/api/routes/health.py` | health endpoint |
| `app/api/routes/watchlist.py` | watchlist と `/securities/search` |
| `app/api/routes/monitoring.py` | monitoring 系 API |
| `app/api/routes/ui.py` | lightweight HTML UI shell と `/ui/dashboard/data` |
| `app/services/dashboard_experience.py` | UI 用 view model の組み立て |
| `app/services/portfolio_ai_review.py` | multi-mode AI分析のOpenAI連携、prompt_only、mock応答、キャッシュ/履歴 |
| `app/prompts/stock_analysis/` | stock AI review のPrompt Registry / Prompt Builder / mode別schema |
| `app/services/security_profile.py` | 銘柄プロファイルと表示名の補完 |
| `app/services/mock_*` | mock mode の返却データ |
| `src/kabuhandan_hojo/connectors/` | J-Quants / EDINET connector |
| `src/kabuhandan_hojo/features/technical.py` | テクニカル特徴量計算 |
| `src/kabuhandan_hojo/scoring/engine.py` | explainable weighted scoring |
| `src/kabuhandan_hojo/services/` | ingestion / insights / query / watchlist |

## 最近の重要点

### 2026-04-23: J-Quants code retry

- `src/kabuhandan_hojo/connectors/jquants.py` は、日足取得時に raw API の `code` 表記差分を吸収する
- 4 桁コードで空振りした場合、5 桁末尾 `0` の候補も再試行する
- dashboard の market proxy (`1306` / `1321`) や live price sync の取りこぼしを減らす

### 2026-04-23: search/detail fallback fix

- `app/services/watchlist.py` の銘柄検索は、任意の 4 桁コードを placeholder 候補として返さない
- `app/services/dashboard_experience.py` の detail 画面は、未知コード指定時に別銘柄へフォールバックしない
- search は DB 既存銘柄、seed catalog、または J-Quants で解決できた銘柄だけを返す

### 2026-04-21: no-mock live UI

- live mode では UI 向け mock 補完を廃止
- `price_chart` が空なら J-Quants 日足同期を 1 回だけ試す
- 取得できない項目は `未取得` または空表示

### 2026-04-21: 市場地合い proxy

- `market_overview`
- `detail.market_headwind`
- `detail.factor_split.market`

上記は watchlist 雰囲気推定ではなく、J-Quants の `TOPIX(1306)` / `Nikkei225(1321)` proxy に基づいて組み立てます。

### 2026-04-20: UI 3 画面構成

- `/ui/dashboard`
- `/ui/security/{ticker_code}`
- `/ui/security/{ticker_code}/chart`

3 画面はすべて `GET /ui/dashboard/data` の view model を共通利用します。

## 参考リンクの扱い

detail 画面の `reference_links` は、次の種類を表示できます。

- Yahoo! Finance Japan
- 公式 IR
- 最新の disclosure / source URL
- TDnet / 日経 / Reuters / Bloomberg / 株探 / みんかぶ / SBI証券 / 楽天証券 / X / StockTwits のラベル解決

ただし、後者は手動参照スタックであり、connector backed source ではありません。
