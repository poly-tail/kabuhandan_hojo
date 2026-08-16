# kabuhandan_hojo Phase 0-2

## 2026-08-17 仕様baseline更新

- 現行正本を要件 v1.2、API v1.5、画面 v1.7へ更新し、個別銘柄AI最小縦スライス、定型prompt、legacy Portfolio AIとの境界を反映しました。
- 仕様版の対応、変更理由、互換性、非対象、既知制約は `docs/spec_change_history.md` で追跡します。
- 旧versioned文書と旧AI endpointは履歴・互換機能として保持し、今回の文書更新ではコードを変更していません。

## 2026-08-17 定型prompt最小統合

- `POST /api/ai/analyses` の既存縦スライスへ、添付 `株判断プロジェクト｜定型プロンプト集 v2026.08.16` の「1. 株判断共通OS」と「3.1 総合的な個別銘柄分析」だけを統合しました。3.2〜3.14は送信しません。
- `app/prompts/individual_security/` がversioned Markdown asset、manifest、`IndividualSecurityPromptCompiler`を管理します。合成順は共通OS、共通入力ルール、Web・外部市場データなしの実行制約、3.1用途module、銘柄context、自由質問です。
- OpenAI requestの`instructions`へ共通規則と3.1、`input`へ銘柄contextと質問を渡します。prompt version、使用asset、module ID、compiled SHA-256はOpenAI response metadataへ記録し、prompt全文・質問はmetadata、公開API response、browserへ出しません。
- 固定model `gpt-5.6-terra`、`STANDARD`、`reasoning.effort=medium`、`text.verbosity=medium`、`response.output_text`方式を維持します。Web検索、Structured Outputs、JSON修復、fallbackは追加していません。
- 比較用の代表質問10件は `tests/fixtures/ai_analysis/individual_security_questions_v2026_08_16.json` にあります。

## 2026-08-17 AI最小縦スライス

- `GET /ui/analysis` に、登録済み銘柄1件、自由質問、`STANDARD` だけを扱う独立画面を追加しました。
- canonical API は `POST /api/ai/analyses` です。`route -> service -> OpenAI Responses client -> response.output_text` の単一路で、回答本文をプレーンテキスト表示します。
- この縦スライスはモデルを `gpt-5.6-terra` に固定し、`STANDARD` を `reasoning.effort=medium`、`text.verbosity=medium` に割り当てます。モデル選択と回答presetは別の設定軸です。
- この経路では mock、cache、fallback、Web検索、Structured Outputs、streaming を使用しません。OpenAI失敗と空回答は成功にせず、型付きエラーとして返します。
- APIキーはサーバー側だけで読み込みます。OpenAI単体疎通は `python scripts/smoke_openai_response.py` で確認でき、キー、prompt本文、回答本文は出力しません。

## 2026-06-15 multi-mode stock AI review addendum

- dashboard のAI分析パネルで `軽量スキャン` / `個別詳細分析` / `全体売買判断` / `重要局面分析` を選べるようにしました。
- `POST /api/ai/stock-review` を追加しました。既存の `POST /portfolio/ai-review` と `POST /api/portfolio/ai-review` は互換入口として残します。
- `mode` は `scanner` / `analyst` / `judge` / `critical` / `prompt_only`、`target` は `holdings` / `watchlist` / `candidates` / `selected` / `mock` を受け付けます。
- `app/prompts/stock_analysis/` に Prompt Registry / Prompt Builder を追加し、ユーザー指定の株式分析プロンプト全文、Base Policy、mode別章選択、mode別JSON Schema、Web検索ポリシー、コスト見積もりを分離しました。
- `prompt_only` は Prompt Registry の全文を使い、OpenAI API を呼ばず、ChatGPTへ手動で貼り付けるプロンプトだけを生成します。ChatGPT Web画面の自動操作、自動投稿、回答取得は実装していません。
- 用途別に `OPENAI_MODEL_SCANNER` / `OPENAI_MODEL_ANALYST` / `OPENAI_MODEL_JUDGE` / `OPENAI_MODEL_CRITICAL` と対応する `OPENAI_REASONING_*` を設定できます。
- `OPENAI_ENABLE_WEB_SEARCH=true` を既定にし、`analyst` / `judge` / `critical` はWeb検索ONを標準にします。`scanner` はOFFでも実行でき、その場合は「最新Web確認なし」のwarningを返します。
- 1回あたりの対象銘柄数、日次実行回数、推定コスト、同一入力キャッシュ、ローカルJSON履歴保存を追加しました。
- mock holdings は 7011 / 6758 / 9984 / 7974 / 4063 / 6857 / 3397 の7件、mock candidates は 6857 / 4063 の2件です。実DB保有銘柄がある場合は実DBを優先します。
- `target=mock` と mock fallback はOpenAI APIを呼ばず、課金なしのローカルサンプル応答を返します。

## 2026-05-23 portfolio AI review addendum

- dashboard の Portfolio パネルに `保有銘柄を一括AI分析` を追加しました。実DBの保有銘柄を優先し、未登録時やテスト時はサーバー側の mock holdings を使えます。
- dashboard の Watchlist パネルに `選択ウォッチリストをAI分析` を追加しました。チェックしたwatchlist銘柄を既存AIレビューAPIへ渡して分析できます。
- `POST /portfolio/ai-review` は OpenAI Responses API をバックエンドから呼び、`OPENAI_API_KEY` と `OPENAI_MODEL` は環境変数から読みます。`mock_response=true` では API を呼ばず表示確認用JSONを返します。
- AIレビューは `OPENAI_REASONING_EFFORT=high` をデフォルトにし、Responses API の `reasoning.effort` に渡します。UIカードには model と reasoning effort を表示します。
- `include_web_search=false` ではWeb検索なしの簡易分析として扱い、`include_web_search=true` では Responses API の `web_search` ツールを有効化します。Web検索ありではAPI制約によりStructured Outputs指定を外し、JSON文字列をparseします。

### AI分析オプション

- `最新ニュースも検索（OpenAI API使用）`: `include_web_search=true`。OpenAI API の web_search を使って最新公開情報も探します。通常のAPI呼び出しより遅く、利用量も増えやすいです。
- `APIなしのサンプル表示（課金なし）`: `mock_response=true`。OpenAI APIを呼ばず、固定のサンプル結果だけ返します。UI確認用であり、実分析ではありません。
- サンプル表示をOFFにすると、OpenAI APIを実行します。OpenAI Platform の billing / quota が有効でない場合は `insufficient_quota` エラーになります。

## 2026-04-23 manual refresh addendum

- dashboard の各セクション内に手動更新ボタンを配置し、`Market Overview` は市場価格、`Materials` は EDINET / TDnet、`Search` は銘柄DB、`Portfolio` は評価価格、`Screening` / `Watchlist` / `Alerts` はスコア再計算を個別に実行できます。
- detail / chart 画面もまとめ更新パネルではなく、`Factor Split`、`Materials`、`Technical`、`Flow`、スコア表示、チャート表示の各カード内ボタンから該当データだけを手動取得します。
- 手動取得で API エラーになった場合は、押したボタンのあるセクション内に失敗理由を表示します。価格・信用需給のような必須データは 0 件取得もエラー扱いにしますが、EDINET / TDnet / YouTube の対象なしは正常終了として表示します。
- `POST /documents/sync/youtube/monitored` を追加し、`YOUTUBE_MONITORED_CHANNELS` に登録した銘柄別チャンネルを UI から同期できます。

## 2026-04-23 local master addendum

- 銘柄検索は `data/security_master_jp.csv` のローカル日本語銘柄マスタを起動時と検索時に `security_master` へ同期します。
- dashboard の銘柄検索欄に `銘柄DB更新` ボタンを追加しました。UI からの更新は `POST /securities/master/sync?require_jquants=true` を叩き、J-Quants V2 `/equities/master` から全上場銘柄を取得できない場合は失敗として表示します。
- `JQUANTS_API_KEY` が無い環境でもローカルCSVの最低限検索は動きますが、全上場銘柄検索には `.env` または起動環境の `JQUANTS_API_KEY` が必要です。
- Market Overview は `price_daily` の `1306` と `1321` を見ます。空の場合に dashboard 読み込みで自動同期は行わず、`市場価格更新` ボタンから J-Quants の `equities/bars/daily` を明示実行します。
- dashboard の Market Overview に `市場価格更新` ボタンを追加し、`1306` / `1321` の価格同期を必要時だけ手動で試せるようにしました。市場proxy の lookback は 60 日です。

`kabuhandan_hojo` は、日本株の判断補助に特化したローカルアプリです。自動売買は行わず、テクニカル、需給、材料、開示情報を並べて「今どこを見るべきか」を整理する用途を想定しています。

## ガードレール

- 本アプリは投資助言や売買執行を目的としません。
- 基幹ソースは `J-Quants`、`EDINET API`、`YouTube Data API`、allowlist 化した IR サイトに限定します。
- 規約違反や `robots.txt` 無視を前提にしたスクレイピングは実装しません。
- Yahoo! Finance や証券会社サイトは、UI 上の参照リンクや手動確認先として扱い、自動取得の基幹ソースにはしません。

情報源の詳細は [docs/information_sources.md](docs/information_sources.md) を参照してください。

## 技術スタック

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0
- Pydantic / pydantic-settings
- SQLite または PostgreSQL
- Uvicorn
- OpenAI Python SDK

ローカルの既定 DB は SQLite です。`DATABASE_URL` を未設定の場合は `./data/kabuhandan_hojo.db` を使います。

## 主要ディレクトリ

```text
app/                      FastAPI 側の API / UI shell
src/kabuhandan_hojo/      Connector / feature / scoring / ingestion の本体
docs/                     仕様書、設計メモ、運用ドキュメント
scripts/                  リポジトリ運用スクリプト
tests/                    unit / integration test
data/                     SQLite などのローカルデータ
```

より詳しい構成は [docs/folder_structure.md](docs/folder_structure.md) を参照してください。

## セットアップ

1. 依存関係を入れます。

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

2. `.env.example` を `.env` にコピーします。

`.env` と `.env.*`（`.env.example` を除く）はGit管理対象外です。APIキーやパスワードの実値は`.env`または実行環境のsecret storeだけに置き、README、ログ、テストfixture、browser responseへ記録しないでください。

3. 必要に応じて環境変数を設定します。

- `APP_USE_MOCK=false`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-5.5`
- `OPENAI_REASONING_EFFORT=high`
- `OPENAI_MODEL_SCANNER=gpt-5.4`
- `OPENAI_MODEL_ANALYST=gpt-5.4`
- `OPENAI_MODEL_JUDGE=gpt-5.5`
- `OPENAI_MODEL_CRITICAL=gpt-5.5`
- `OPENAI_REASONING_SCANNER=low`
- `OPENAI_REASONING_ANALYST=medium`
- `OPENAI_REASONING_JUDGE=high`
- `OPENAI_REASONING_CRITICAL=xhigh`
- `OPENAI_ENABLE_WEB_SEARCH=true`
- `OPENAI_MAX_WEB_SEARCH_CALLS=5`
- `OPENAI_MAX_STOCKS_PER_REQUEST=20`
- `OPENAI_DAILY_REQUEST_LIMIT=50`
- `OPENAI_DEFAULT_VERBOSITY=medium`
- `OPENAI_CRITICAL_CONFIRMATION_REQUIRED=true`
- `JQUANTS_API_KEY=...`
- `EDINET_API_KEY=...`
- `TDNET_API_KEY=...`
- `YOUTUBE_API_KEY=...`
- `YOUTUBE_MONITORED_CHANNELS={"7203":["UCxxxxxxxxxx"]}`
- `IR_ALLOWLIST_DOMAINS=["global.toyota","ssl4.eir-parts.net"]`

4. API を起動します。

```bash
python scripts/run_api.py --reload
```

`--reload` は開発用です。不要なら外して構いません。
`scripts/` ディレクトリから `py -3 run_api.py --reload` で起動しても、runner が repo ルートへ移動してから設定を読み込みます。

## 起動モード

### live mode

```bash
python scripts/run_api.py --reload
```

- `--mock` を付けない通常起動です。
- 価格データが不足していて `JQUANTS_API_KEY` がある場合、UI 用の `price_chart` 取得時に J-Quants の日足同期を 1 回試します。
- それでも取得できない項目は、mock 補完せず `未取得` または空表示にします。

### mock mode

```bash
python scripts/run_api.py --reload --mock
```

- DB がなくても UI と API の確認ができます。
- `/health` の `database` は `"mock"` を返します。

## 主なエンドポイント

### API

- `GET /health`
- `POST /api/ai/analyses`
  - 個別銘柄1件の最小AI分析入口です。現在は `preset=STANDARD` のみ受け付けます。
- `GET /watchlist`
- `POST /watchlist`
- `GET /portfolio`
- `POST /portfolio`
- `POST /portfolio/import/csv`
- `POST /api/ai/stock-review`
  - 5モードのAI分析入口です。`prompt_only` ではOpenAI APIを呼ばず、手動投入用プロンプトを返します。
- `POST /portfolio/ai-review`
  - 互換入口です。内部的には multi-mode AI review service を使います。
- `DELETE /portfolio/{ticker_code}`
- `GET /securities/search`
- `POST /sources/bootstrap`
- `POST /securities/master/sync`
  - UI の `銘柄DB更新` は `require_jquants=true` を付け、J-Quants V2 `/equities/master` の全件取得を必須にします。
- `POST /securities`
- `POST /securities/{ticker_code}/prices`
- `POST /securities/{ticker_code}/prices/sync`
- `POST /securities/{ticker_code}/financials`
- `POST /securities/{ticker_code}/flow`
- `POST /securities/{ticker_code}/flow/sync`
- `POST /securities/{ticker_code}/technical/rebuild`
- `POST /securities/{ticker_code}/score/recalculate`
- `POST /documents/import`
- `POST /documents/import/ir`
- `POST /documents/sync/edinet`
- `POST /documents/sync/tdnet`
- `POST /documents/sync/youtube`
- `POST /documents/sync/youtube/monitored`
- `GET /securities/{ticker_code}`
- `GET /dashboard`
- `GET /screening`
- `POST /screening/query`

### 2026-04-23 addendum

- 銘柄検索は seed catalog 依存をやめ、`POST /securities/master/sync` で J-Quants の listed master を `security_master` に同期してから DB-only で検索します。
- portfolio panel は watchlist 代替ではなく、`/portfolio` API と dashboard 内の手入力フォーム、`/portfolio/import/csv` で保持します。
- detail の信用需給は `flow` が空のとき J-Quants margin data を試行し、取得できれば `FlowSnapshot` を補完します。
- TDnet は JPX の official paid API connector を追加し、`POST /documents/sync/tdnet` で event 化できます。detail では `TDNET_API_KEY` があると当日分の自動同期も試行します。
- sector pulse / factor split の sector 比較は watchlist 内比較ではなく、`security_master` と `price_daily` から同業全体の 5 日 breadth を集計して使います。

- YouTube 補助観測は `POST /documents/sync/youtube` と `YOUTUBE_MONITORED_CHANNELS` で正式 route 化し、detail では recent 動画が無いときだけ auto sync を試します。
- 公式 IR は `POST /documents/import/ir` で allowlist domain の URL だけ event 化できるようにし、YouTube / IR も raw document と event の構造化シグナルに載せます。

### UI

- `GET /ui/analysis`
- `GET /ui/dashboard`
- `GET /ui/dashboard/data`
- `GET /ui/review`
- `GET /ui/security/{ticker_code}`
- `GET /ui/security/{ticker_code}/chart`

## UI の現状

- top 画面は `market_overview`、priority card、alerts、event feed、watchlist、screening 候補を表示します。
- 検索の下には、watchlist 未登録の高スコア候補を表示します。
- dashboard から個別銘柄画面へは新しいタブで開き、元のタブは遷移しません。
- 個別銘柄画面には、仮説メモ、地合い分離、テクニカル、需給、材料履歴、参考リンク、直近チャートプレビューを表示します。
- チャート詳細画面では、20日 / 40日 / 全期間の切替、MA 5 / 25 / 75 の重ね描画、RSI / MACD の補助表示に対応しています。

## 市場地合いの扱い

- live mode の `market_overview`、`market_headwind`、`factor_split.market` は、J-Quants で取得する `TOPIX(1306)` と `Nikkei225(1321)` の proxy データを使って組み立てます。
- これらが取れない場合は、watchlist の雰囲気推定へ戻さず `未取得` にします。

## ドキュメント

- [docs/context.md](docs/context.md)
- [docs/requirements/current.md](docs/requirements/current.md)
- [docs/information_sources.md](docs/information_sources.md)
- [docs/source_overview.md](docs/source_overview.md)
- [docs/project_guide.md](docs/project_guide.md)
- [docs/specs/current.md](docs/specs/current.md)
- [docs/screen_specs/current.md](docs/screen_specs/current.md)
- [docs/spec_change_history.md](docs/spec_change_history.md)
- [docs/changelog.md](docs/changelog.md)

## 典型的な確認コマンド

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/watchlist
curl http://127.0.0.1:8000/dashboard
curl "http://127.0.0.1:8000/securities/search?q=7203"
```

ブラウザ確認先:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/ui/analysis`
- `http://127.0.0.1:8000/ui/dashboard`
- `http://127.0.0.1:8000/ui/security/7203`
- `http://127.0.0.1:8000/ui/security/7203/chart`
