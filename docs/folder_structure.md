# Folder Structure

## 2026-08-19 Portfolio・複数named watchlist addendum

- `app/models/watchlist.py` / `src/kabuhandan_hojo/models/entities.py`: ticker-level item、collection、membership entity。memo / thesisはitem共有、sort / activeはmembership固有。
- `app/db/session.py`: default「メイン」の初回作成と一度だけのlegacy membership backfill。
- `app/schemas/watchlist.py` / `src/kabuhandan_hojo/schemas/watchlists.py`: collection read / create / updateと`collection_id`付きitem schema。
- `app/services/watchlist.py` / `src/kabuhandan_hojo/services/watchlists.py`: collection CRUD、membership upsert / remove、default compatibility、list-scoped search。
- `app/api/routes/watchlist.py`: `/watchlists` collection / item API、legacy `/watchlist` default endpoint、`/securities/search?watchlist_id=`。
- `app/services/mock_watchlist.py`: mock modeのcollection / membership parity。
- `app/schemas/ui_dashboard.py` / `app/services/dashboard_experience.py`: collection一覧、selected list、list-scoped dashboard view model。
- `app/api/routes/ui.py`: 単一management space、selector、collection操作、検索追加、detail / chart queryとdetail保存scope、checkbox target同期、list名context snapshot、stale dashboard / AI response無効化、default monitoring reload。
- `app/schemas/portfolio_ai.py` / `app/services/portfolio_ai_review.py`: optional `watchlist_id`とnamed empty時のmock非fallback。
- `tests/unit/test_watchlist_collections.py` / `test_mock_ui.py` / `test_portfolio_ai_review.py`: data/API、migration、mock、UI、AI scopeの回帰test。
- `docs/requirements/requirements_v2.0.md` / `docs/specs/api_spec_v2.3.md` / `docs/screen_specs/screen_spec_v2.7.md`: `SC-2026-08-19-05`の新しい累積baseline。旧versioned文書は不変で保持する。

## 2026-08-19 legacy AI銘柄identity addendum

- `app/prompts/stock_analysis/builder.py` / `user_stock_analysis_prompt_full.py`: legacy AIのticker/name正本、名称・code併記、scanner portfolio影響section。
- `app/services/portfolio_ai_review.py`: local master canonical identity補完、dedupe/holdings優先、live/mock/cache共通のstock名・summary参照正規化。
- `app/api/routes/ui.py`: legacy stock cardの公開code表示。
- `tests/unit/test_stock_analysis_prompt_builder.py` / `test_portfolio_ai_review.py` / `test_mock_ui.py`: prompt、service identity、UI表示の回帰test。
- `docs/requirements/requirements_v1.9.md` / `docs/specs/api_spec_v2.2.md` / `docs/screen_specs/screen_spec_v2.4.md`: `SC-2026-08-19-02`時点の累積仕様baselineとして不変で履歴保持する。

## 2026-08-19 legacy scanner validation addendum

- `app/prompts/stock_analysis/builder.py`: Pydantic field以内のmode別JSON Schema、scanner軽量field、judgement enum。
- `app/schemas/portfolio_ai.py`: legacy responseのnullable `parse_failure_kind`。
- `app/services/portfolio_ai_review.py`: summary alias / judgement正規化、parse失敗3分類、raw output救済のquota/cache/history境界。
- `app/api/routes/ui.py`: `json_parse_failed`の赤いerror cardと原因別label。
- `tests/unit/test_stock_analysis_prompt_builder.py`、`test_portfolio_ai_review.py`、`test_mock_ui.py`: schema、service、usage/cache/history、UI回帰test。

## 2026-08-18 J-Quants銘柄マスター同期 addendum

- `app/schemas/security_master_sync.py`: `GET /securities/master/status`と`POST /securities/master/sync`のscope、provenance、完全性、件数schema。
- `app/api/routes/monitoring.py`: status取得、required J-Quants同期、optional seed fallbackのHTTP境界。
- `app/api/routes/ui.py`: `東証全銘柄を同期`、完全/未確認status、情報基準日、同期時刻、J-Quants/ローカル件数、同期結果feedback。
- `app/services/security_master_catalog.py`: 36件のbundled seedを不足recordだけへinsertし、J-Quants recordを上書きしないcatalog。
- `app/models/security.py` / `src/kabuhandan_hojo/models/entities.py`: master source/as-of/sync IDと`security_master_sync_run` provenance/count entity。
- `src/kabuhandan_hojo/connectors/jquants.py`: listed master pagination、ordinary/preferred/alphanumeric code保持、source/listing date分離、bounded 429 retry、provider bodyを除くsafe error変換。
- `src/kabuhandan_hojo/services/ingestion.py`: 本番4,000件/5%縮小guard、complete/current/historical判定、J-Quants ownership限定deactivation、FK参照identity collision拒否、status/count集計、explicit legacy adoption。
- `scripts/sync_security_master.py`: browserなしのcurrent/historical/dry-runと明示legacy adoption。dry-run前にも`init_db()`によるschema/seed初期化が起こり得る。
- `tests/unit/test_jquants_connector.py`、`test_security_master_sync.py`、`test_security_master_status_api.py`、`test_security_master_provenance_migration.py`: connector、service、API、SQLite/PostgreSQL互換provenanceの回帰test。
- `tests/unit/test_security_profile_master_mapping.py`、`test_security_search_case_insensitive.py`、`test_sync_security_master_script.py`、`test_mock_ui.py`: source/listing date分離、DB-only検索/no-provider-call、CLI safe error、UI contractの回帰test。
- `data/security_master_jp.csv`: 36件のbundled search seedだけを追跡。完全なJ-Quants datasetとローカルDBは`/data/*`でgitignoreし、public repositoryへ同梱・再配布しない。

## 2026-08-18 search / portfolio addendum

- `app/api/routes/ui.py`: dashboard検索結果の`保有入力へ` / `詳細を見る`、公開code表示、portfolioフォームprefill。
- `app/services/watchlist.py`: ticker/local codeと銘柄名による登録master検索。
- `app/services/portfolio.py`: 4文字公開codeから一意な末尾`0`付きJ-Quants raw masterへのportfolio alias解決。
- `tests/unit/test_mock_ui.py`: 検索結果action、公開code表示/prefill、数量focus、非自動保存のUI contract。
- `tests/unit/test_phase0_api.py`: portfolio API/CSVの公開4文字alias、既存raw masterへの紐付け、placeholder非作成を確認します。

## 2026-08-19 specification docs addendum

- `docs/requirements/requirements_v1.8.md`: v1.7を累積し、legacy scannerのschema/runtime一致、失敗status、quota/cache/history境界を追加。
- `docs/specs/api_spec_v2.1.md`: v2.0を累積し、alias正規化、parse失敗3分類、scanner output schemaを追加。
- `docs/screen_specs/screen_spec_v2.3.md`: v2.2を累積し、`json_parse_failed`の赤いerror cardと分類labelを追加。
- `docs/spec_change_history.md`: `SC-2026-08-19-01`の変更理由、互換性、非対象、既知制約。`SC-2026-08-18-02`以前は履歴として維持。

## 2026-08-17 specification docs addendum

- `docs/spec_change_history.md`: 要件・API・画面仕様の版対応、変更理由、互換性、既知制約の横断履歴。
- `docs/requirements/requirements_v1.5.md`: canonical安全性を累積し、legacy usage/quota/概算を含む2026-08-17要件baseline。
- `docs/specs/api_spec_v1.8.md`: canonical契約とlegacy `GET /api/ai/stock-review/usage`を含む2026-08-17 API baseline。
- `docs/screen_specs/screen_spec_v2.0.md`: canonical reader契約とlegacy AI usage panelを含む2026-08-17画面baseline。

## 2026-08-17 individual-security PromptCompiler addendum

- `app/prompts/individual_security/compiler.py`: 共通asset、銘柄context、質問を合成する独立Compiler。
- `app/prompts/individual_security/manifest.json`: prompt/source/compiler version、asset、3.1 module、hash、合成順。
- `app/prompts/individual_security/assets/v2026_08_18/`: 現行の非送信`SOURCE.md`、共通OS、銘柄名・コード分離入力、実行制約、`modules/individual_comprehensive.md`。v2026.08.16 / v2026.08.17も再現用に保持。
- `tests/unit/test_individual_security_prompt_compiler.py`: asset読込、3.1選択、3.2〜3.14除外、context・質問・traceのテスト。
- `tests/fixtures/ai_analysis/individual_security_questions_v2026_08_18.json`: 現行promptの人手比較用代表質問10件。旧版fixtureも比較用に保持。
- `.md` / `.json` assetは`pyproject.toml`のpackage-dataへ明示し、wheelでも同梱します。

## 2026-08-17 AI最小縦スライス addendum

- `app/ai/`: 固定モデル、`STANDARD` preset、公開エラーコード。モデル選択と回答品質presetは分離。
- `app/integrations/openai_responses.py`: OpenAI Responses APIだけを扱う独立client。
- `app/schemas/ai_analysis.py`: AI分析POST、生成結果と分離した保存status、browser-safe保存詳細、typed error schema。
- `app/models/ai_analysis_record.py`: 成功回答・生成設定・prompt traceのローカルDB record。
- `app/services/ai_analysis.py`: 個別銘柄解決、prompt合成、OpenAI呼び出し、回答生成と保存結果を分離する調停。
- `app/services/ai_analysis_records.py`: 保存transaction、rollback、UUID詳細取得。
- `app/api/routes/ai_analysis.py`: `POST /api/ai/analyses` と `GET /api/ai/analyses/{request_id}`。
- `app/api/routes/analysis_ui.py`: `GET /ui/analysis` と大画面 `GET /ui/analysis/results/{request_id}`。
- `scripts/smoke_openai_response.py`: FastAPIを介さない実OpenAI疎通確認。
- `tests/unit/test_openai_responses_client.py`、`test_ai_analysis_records.py`、`test_ai_analysis_api.py`、`test_analysis_ui.py`、`test_app_startup.py`: client、保存transaction、API、UI shell、lifespan DB初期化の回帰テスト。

## 2026-06-15 multi-mode stock AI review addendum

- `app/schemas/portfolio_ai.py`: multi-mode stock AI reviewのrequest / responseと、legacy usage期間集計・pricing response schema。
- `app/prompts/stock_analysis/`: ユーザー指定プロンプト全文、Base Policy、analysisSections、modeProfiles、outputSchemas、Prompt Builder、コスト/Web検索ポリシー。
- `app/services/portfolio_ai_review.py`: OpenAI Responses API、target解決、prompt_only、legacy cache、履歴、成功review quota、provider usage連携のサービス層。
- `app/services/ai_usage.py`: legacy stock-reviewの`review_runs`、provider `api_calls`、token/Web検索、公式pricing由来概算をJST日別に集計するv2 ledger。
- `data/ai_review_history.json` / `data/ai_review_cache.json`: AI分析のローカル履歴と同一入力cache。
- `data/ai_review_usage_v2.json`: version 2 / Asia-Tokyo / legacy scopeの日別usageとpricing catalog。旧`data/ai_review_usage.json`は移行しません。`data/` はローカルデータとしてgit管理しません。
- `tests/unit/test_ai_usage.py` / `tests/unit/test_portfolio_ai_review.py`: pricing、日/月集計、quota count、endpoint/UI連携と、usage/history/cacheの一時path隔離。

## 2026-05-25 user docs addendum

- `docs/user/`: 利用者向け仕様書・取扱説明書のHTML原稿とPDF出力。

## 2026-05-23 portfolio AI review addendum

- `app/schemas/portfolio_ai.py`: 保有銘柄AIレビューのrequest / response schema。
- `app/services/portfolio_ai_review.py`: DB保有銘柄、mock holdings、market snapshot、OpenAI Responses API呼び出しのサービス層。
- `tests/unit/test_portfolio_ai_review.py`: APIキー未設定、mock_response、DB保有銘柄優先、JSON parse失敗のテスト。

## 2026-04-23 local master addendum

- `data/security_master_jp.csv`: 36件のlocal Japanese security search seed。full masterではない。
- `app/services/security_master_catalog.py`: CSV loader and insert-only seed service for `security_master`.

## 2026-04-23 YouTube / IR addendum

- `src/kabuhandan_hojo/connectors/youtube.py`: YouTube Data API connector for monitored channel observations.

## 2026-04-23 addendum

- `app/api/routes/portfolio.py`: portfolio CRUD endpoints.
- `app/models/portfolio.py`: `portfolio_holding` ORM.
- `app/services/portfolio.py`: portfolio aggregation for API and dashboard.
- `src/kabuhandan_hojo/connectors/tdnet.py`: JPX TDnet API connector.
- `src/kabuhandan_hojo/connectors/jquants.py`: listed master / margin data sync support.

## 主要ディレクトリ

```text
app/
  ai/                    AI runtime / answer preset / error code
  api/
    routes/              FastAPI endpoint と UI shell
  core/                  設定ロード
  db/                    DB session / init
  integrations/          外部API client adapter
  models/                Phase 0 側 ORM
  prompts/               AI機能のPrompt Registry / versioned assets / Compiler
  schemas/               FastAPI request / response schema
  services/              UI view model / mock / watchlist 補助

src/kabuhandan_hojo/
  connectors/            J-Quants / EDINET connector
  core/                  共通設定
  features/              テクニカル特徴量計算
  models/                監視系 entity
  normalizers/           文書正規化
  scoring/               explainable scoring
  schemas/               domain schema
  services/              ingestion / insights / query

docs/
  analysis/              backlog と設計メモ
  requirements/          要件文書
  specs/                 API 仕様書
  screen_specs/          画面仕様書
  templates/             文書テンプレート
  spec_change_history.md 要件・API・画面仕様の横断変更履歴

scripts/                 運用・同期スクリプト
tests/                   unit / integration test
data/                    SQLite・provider同期結果等のgit管理外ローカルデータと、例外的に追跡する36件seed
assets/                  補助アセット
```

## 運用ルール

- API / UI shell は `app/` に置きます。
- source 固有の取得、特徴量、scoring は `src/kabuhandan_hojo/` に寄せます。
- one-shot の補助操作は `scripts/` に置き、`cli/` は互換ラッパ中心にします。
- 版付き docs を追加・昇格したら `scripts/sync_current_files.py` で `current.md` を同期します。
