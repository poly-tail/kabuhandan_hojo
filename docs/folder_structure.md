# Folder Structure

## 2026-08-17 specification docs addendum

- `docs/spec_change_history.md`: 要件・API・画面仕様の版対応、変更理由、互換性、既知制約の横断履歴。
- `docs/requirements/requirements_v1.3.md`: canonical回答保存を含む要件正本。
- `docs/specs/api_spec_v1.6.md`: 保存詳細APIを含むAPI正本。
- `docs/screen_specs/screen_spec_v1.8.md`: 独立AI分析画面と大画面readerを含む画面正本。

## 2026-08-17 individual-security PromptCompiler addendum

- `app/prompts/individual_security/compiler.py`: 共通asset、銘柄context、質問を合成する独立Compiler。
- `app/prompts/individual_security/manifest.json`: prompt/source/compiler version、asset、3.1 module、hash、合成順。
- `app/prompts/individual_security/assets/v2026_08_17/`: 現行の共通OS、銘柄名・コード分離入力、実行制約、`modules/individual_comprehensive.md`。v2026.08.16も再現用に保持。
- `tests/unit/test_individual_security_prompt_compiler.py`: asset読込、3.1選択、3.2〜3.14除外、context・質問・traceのテスト。
- `tests/fixtures/ai_analysis/individual_security_questions_v2026_08_17.json`: 現行promptの人手比較用代表質問10件。
- `.md` / `.json` assetは`pyproject.toml`のpackage-dataへ明示し、wheelでも同梱します。

## 2026-08-17 AI最小縦スライス addendum

- `app/ai/`: 固定モデル、`STANDARD` preset、公開エラーコード。モデル選択と回答品質presetは分離。
- `app/integrations/openai_responses.py`: OpenAI Responses APIだけを扱う独立client。
- `app/schemas/ai_analysis.py`: AI分析POST、browser-safe保存詳細、typed error schema。
- `app/models/ai_analysis_record.py`: 成功回答・生成設定・prompt traceのローカルDB record。
- `app/services/ai_analysis.py`: 個別銘柄解決、prompt合成、OpenAI呼び出し、成功回答保存の調停。
- `app/services/ai_analysis_records.py`: 保存transaction、rollback、UUID詳細取得。
- `app/api/routes/ai_analysis.py`: `POST /api/ai/analyses` と `GET /api/ai/analyses/{request_id}`。
- `app/api/routes/analysis_ui.py`: `GET /ui/analysis` と大画面 `GET /ui/analysis/results/{request_id}`。
- `scripts/smoke_openai_response.py`: FastAPIを介さない実OpenAI疎通確認。
- `tests/unit/test_openai_responses_client.py`、`test_ai_analysis_records.py`、`test_ai_analysis_api.py`、`test_analysis_ui.py`: client、保存transaction、API、UI shellの回帰テスト。

## 2026-06-15 multi-mode stock AI review addendum

- `app/schemas/portfolio_ai.py`: multi-mode stock AI review のrequest / response schema。旧portfolio AI review schemaも互換維持。
- `app/prompts/stock_analysis/`: ユーザー指定プロンプト全文、Base Policy、analysisSections、modeProfiles、outputSchemas、Prompt Builder、コスト/Web検索ポリシー。
- `app/services/portfolio_ai_review.py`: OpenAI Responses API、mock holdings、watchlist/portfolio target解決、market snapshot抽象化、prompt_only、キャッシュ/履歴/コスト制御のサービス層。
- `data/ai_review_history.json` / `data/ai_review_cache.json` / `data/ai_review_usage.json`: AI分析のローカル履歴、同一入力キャッシュ、日次実行カウント。`data/` はローカルデータとしてgit管理しません。

## 2026-05-25 user docs addendum

- `docs/user/`: 利用者向け仕様書・取扱説明書のHTML原稿とPDF出力。

## 2026-05-23 portfolio AI review addendum

- `app/schemas/portfolio_ai.py`: 保有銘柄AIレビューのrequest / response schema。
- `app/services/portfolio_ai_review.py`: DB保有銘柄、mock holdings、market snapshot、OpenAI Responses API呼び出しのサービス層。
- `tests/unit/test_portfolio_ai_review.py`: APIキー未設定、mock_response、DB保有銘柄優先、JSON parse失敗のテスト。

## 2026-04-23 local master addendum

- `data/security_master_jp.csv`: local Japanese security master seed.
- `app/services/security_master_catalog.py`: CSV loader and DB upsert service for `security_master`.

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
data/                    SQLite などのローカルデータ
assets/                  補助アセット
```

## 運用ルール

- API / UI shell は `app/` に置きます。
- source 固有の取得、特徴量、scoring は `src/kabuhandan_hojo/` に寄せます。
- one-shot の補助操作は `scripts/` に置き、`cli/` は互換ラッパ中心にします。
- 版付き docs を追加・昇格したら `scripts/sync_current_files.py` で `current.md` を同期します。
