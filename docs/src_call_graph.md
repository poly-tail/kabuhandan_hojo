# Source Call Graph

## 2026-08-17 定型prompt統合

1. `AiAnalysisService` -> `security_master` のcode / name / market / industry / listed dateを `SecurityPromptContext` へ変換
2. `IndividualSecurityPromptCompiler` -> manifestとasset SHA-256を検証
3. `instructions` -> 共通OS -> 共通入力ルール -> Web・外部市場データなし制約 -> module `3.1 総合的な個別銘柄分析`
4. `input` -> 銘柄context（未提供データを`【U】`で明示） -> JSON化した自由質問
5. `PromptTrace` -> version / profile / compiler / module / asset IDs / source hash / compiled hashをOpenAI metadataへ変換（本文・質問なし）
6. `OpenAIResponsesClient` -> 従来どおり `gpt-5.6-terra` / `medium` / `medium` でResponses APIを1回呼び出し、`response.output_text`を検証
7. `answer_text` -> 既存FastAPI response -> browser `textContent` / `white-space: pre-wrap`

この経路には3.2〜3.14、Web tool、Structured Outputs、JSON parse/repair、再呼び出し、fallbackを接続しません。旧portfolio AI call graphも変更しません。

## 2026-08-17 AI最小縦スライス

1. ブラウザが `GET /ui/analysis` を開く
2. 銘柄検索 -> `GET /securities/search` -> 登録済み銘柄を1件選択
3. 質問送信 -> `POST /api/ai/analyses` (`security_code`, `question`, `preset=STANDARD`)
4. `AiAnalysisService` -> `security_master` から銘柄snapshotを解決 -> `IndividualSecurityPromptCompiler`でpromptを合成
5. `OpenAIResponsesClient` -> `gpt-5.6-terra` / `reasoning.effort=medium` / `text.verbosity=medium` で Responses APIを1回呼び出す
6. `response.status=completed`、response ID、非空の `response.output_text` を検証 -> APIの `answer_text`
7. UI -> `answer_text` を `textContent` でプレーンテキスト表示
8. OpenAI失敗、timeout、空回答 -> 分類済みerror response -> UIのerror領域（mockやraw-response fallbackなし）

## 2026-06-15 multi-mode stock AI review addendum

1. dashboard AI分析パネル -> `POST /api/ai/stock-review` -> `PortfolioAiReviewService.review()`
2. `review()` -> `target` に応じて DB holdings / watchlist / candidates / selected holdings / mock holdings / mock candidates を解決 -> `get_market_snapshot()`
3. `analyze_portfolio_with_openai()` -> `app.prompts.stock_analysis.build_stock_analysis_prompt()` -> Base Policy / modeProfiles / selected analysisSections / mode別outputSchema / webSearchPolicy を組み立て
4. `analyze_portfolio_with_openai()` -> 用途別 `OPENAI_MODEL_*` / `OPENAI_REASONING_*` -> cost / cache / daily limit / web search limit を判定
5. `mode=prompt_only` -> `build_prompt_only_text()` がユーザー指定プロンプト全文とアプリ入力JSONを結合 -> UI のテキストエリアとコピー操作
6. OpenAI実行時 -> Responses API with optional `web_search` / `reasoning.effort` / JSON Schema format -> validation warning補完 -> ローカル履歴/キャッシュ保存
7. missing API key / parse failure / limit exceeded -> `PortfolioAiReviewResponse.status` -> UI state card without exposing secrets

## 2026-05-23 portfolio AI review addendum

1. dashboard Portfolio panel -> `POST /portfolio/ai-review` -> `PortfolioAiReviewService.review()`
2. `PortfolioAiReviewService.review()` -> request holdings / DB `PortfolioService.list_items()` / server mock holdings -> mock market snapshots
3. `analyze_portfolio_with_openai()` -> `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_REASONING_EFFORT` -> OpenAI Responses API with optional `web_search` and `reasoning.effort` -> structured JSON parse
4. parse failure or missing API key -> `PortfolioAiReviewResponse.status` (`json_parse_failed`, `missing_api_key`) -> UI state card without exposing secrets
5. dashboard Watchlist panel checkbox selection -> request `holdings` payload with `quantity=1` -> same `POST /portfolio/ai-review` flow -> Watchlist AI Review cards

## 2026-04-23 manual refresh addendum

1. dashboard section buttons -> market proxy / portfolio prices / security master / EDINET / TDnet / score recalculation endpoints
2. detail / chart card buttons -> selected ticker prices / flow / technical rebuild / score recalc / TDnet / YouTube sync endpoints
3. `/documents/sync/youtube/monitored` -> settings `YOUTUBE_MONITORED_CHANNELS` -> `IngestionService.sync_youtube_documents()`

## 2026-04-23 local master addendum

1. app startup / search / `/securities/master/sync` -> `LocalSecurityMasterCatalog.sync_to_db()` -> `security_master`
2. dashboard `銘柄DB更新` button -> `POST /securities/master/sync?require_jquants=true` -> local CSV sync plus required J-Quants V2 `/equities/master` sync
3. dashboard `市場価格更新` button -> `POST /securities/1306/prices/sync?lookback_days=60` and `POST /securities/1321/prices/sync?lookback_days=60` -> J-Quants daily bars -> `price_daily`

## 2026-04-23 YouTube / IR addendum

1. `/documents/sync/youtube` or detail live build -> `YouTubeConnector.fetch_channel_videos()` -> `RawDocument` / `EventFact` / `video_item`
2. `/documents/import/ir` -> allowlist domain validation -> `RawDocument` / `EventFact`

## 2026-04-23 addendum

1. `/securities/master/sync` -> `IngestionService.sync_security_master_from_jquants()` -> `JQuantsConnector.fetch_listed_issues()` -> J-Quants V2 `/equities/master` -> `security_master`
2. `/portfolio` -> `PortfolioService` -> `portfolio_holding` -> `/ui/dashboard/data`
3. detail live build -> TDnet auto sync (today, selected ticker) -> `RawDocument` / `EventFact`
4. detail live build -> J-Quants margin sync when `latest_flow` is missing -> `flow_snapshot`
5. market overview / factor split -> sector breadth snapshot from `security_master` + `price_daily`

## 全体像

### 1. dashboard UI

1. ブラウザが `/ui/dashboard` を開く
2. UI shell が `/ui/dashboard/data` を読む
3. `app/services/dashboard_experience.py` が watchlist、dashboard、screening、detail 候補を集約する
4. 既存の J-Quants proxy 価格があれば市場地合いを計算する

### 2. detail UI

1. ブラウザが `/ui/security/{ticker_code}` を開く
2. 同じ `/ui/dashboard/data?ticker_code=...` を読む
3. detail panel に仮説、factor split、materials、technical、flow、chart preview を組み立てる
4. `price_chart` が空で live mode かつ `JQUANTS_API_KEY` があれば、J-Quants 日足同期を 1 回試す

### 3. chart UI

1. ブラウザが `/ui/security/{ticker_code}/chart` を開く
2. detail と同じ JSON を読む
3. client-side で 20日 / 40日 / 全期間切替と MA overlay、RSI、MACD を描画する

## API 側の主な流れ

### watchlist / search

- `app/api/routes/watchlist.py`
- live mode では `app/services/watchlist.py`
- mock mode では `app/services/mock_watchlist.py`

### monitoring

- `app/api/routes/monitoring.py`
- `src/kabuhandan_hojo/services/ingestion.py`
- `src/kabuhandan_hojo/services/securities.py`
- `src/kabuhandan_hojo/services/insights.py`

### UI view model

- `app/api/routes/ui.py`
- `app/services/dashboard_experience.py`
- `app/services/security_profile.py`

## market proxy の流れ

1. dashboard experience が `TOPIX(1306)` / `Nikkei225(1321)` の最新価格系列を確認
2. 足りなければ J-Quants 同期を試す
3. 1日、5日、20日変化率と 20 日平均位置をもとに市場スコアを作る
4. `market_overview` と `market_headwind`、`factor_split.market` に反映する
