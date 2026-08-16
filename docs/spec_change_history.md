# 仕様変更履歴

## 1. この文書の役割

この文書は、要件仕様、API仕様、画面仕様の版対応と、仕様変更の理由・互換性・既知制約を横断して追跡する正本です。

- 完全な契約は各versioned fileに保持します。
- `current.md` は最新版へのpointerと短い概要です。
- コード・運用・文書変更の時系列は `docs/changelog.md` に保持します。
- 過去版は履歴として残し、同じ版を後から書き換えません。

## 2. 現在の仕様baseline

| 種別 | 現在版 | 正本 | 適用日 |
|---|---:|---|---|
| 要件仕様 | v1.3 | `docs/requirements/requirements_v1.3.md` | 2026-08-17 |
| API仕様 | v1.6 | `docs/specs/api_spec_v1.6.md` | 2026-08-17 |
| 画面仕様 | v1.8 | `docs/screen_specs/screen_spec_v1.8.md` | 2026-08-17 |

この3版は同じ変更単位 `SC-2026-08-17-02` を表します。どれか1つだけを旧版へ戻して運用することは想定しません。

## 3. SC-2026-08-17-02 — canonical AI回答保存・大型表示・prompt v2026.08.17

### 3.1 変更理由

canonical個別銘柄AIの回答を生成直後の画面だけでなく再表示でき、長文を大きな読み取り専用画面で確認できるようにする必要がありました。同時に、添付prompt sourceの最新版に含まれる銘柄名・コード併記規則を、既存の最小prompt構成を広げず反映します。

### 3.2 変更前

- `POST /api/ai/analyses`の成功回答はbrowserへ表示するだけで、canonical専用SQL recordを持ちませんでした。
- `/ui/analysis`の回答領域だけで表示し、別ウィンドウの大型readerはありませんでした。
- prompt sourceはv2026.08.16でした。

### 3.3 変更後

- 成功したPOSTは、同じ`request_id`で`AiAnalysisRecord`をローカルSQLへ自動保存します。
- 保存対象は質問、回答、銘柄snapshot、model/preset/reasoning設定、OpenAI response ID、prompt traceです。
- 保存commit失敗時はrollbackし、HTTP 500の`PERSISTENCE_ERROR`としてsuccessを返しません。
- `GET /api/ai/analyses/{request_id}`は保存済み成功回答をUUIDで1件取得します。未知recordは`ANALYSIS_NOT_FOUND`です。
- `/ui/analysis`の成功時に`別ウィンドウで大きく表示`を出し、`target="_blank"`と`rel="noopener noreferrer"`で`/ui/analysis/results/{request_id}`を開きます。
- 大型画面は保存回答APIから1件を取得し、質問と回答を`textContent` / `white-space: pre-wrap`で表示します。
- AI送信中は銘柄検索・選択と質問編集をロックし、応答待ちのrequest対象と表示対象を固定します。
- canonical APIはFastAPI validation errorを含め、HTML shellは各routeから`Cache-Control: no-store`を返します。

### 3.4 prompt更新

- sourceを「株判断プロジェクト｜定型プロンプト集 v2026.08.17」へ更新しました。
- 使用範囲は共通OS、必要な共通入力rule、no-tools実行制約、module 3.1だけで、3.2〜3.14やJSON Schemaは追加しません。
- 銘柄の表示・言及を原則「銘柄名（銘柄コード）」とし、共通入力で銘柄名と銘柄コードを分離します。
- model=`gpt-5.6-terra`、preset=`STANDARD`、reasoning effort=`medium`、text verbosity=`medium`、plain`response.output_text`は変更しません。

### 3.5 保存・秘密情報

- ローカルSQL recordは再表示とprompt trace相関の正本です。OpenAI側の保持をアプリ保存の代替にしません。
- APIキー、Authorization header、prompt全文、provider raw response / raw error、stack traceは保存しません。
- prompt traceはrecordへ保存しますが、公開API responseとbrowserへ出しません。
- 一覧、検索、削除、export、共有、保持期限、自動purge、認証・認可は追加しません。

### 3.6 互換性と受け入れ

- legacy stock-review endpoint、UI、mock/cache/Web/Structured Outputs/JSON fallbackは変更しません。
- canonical POSTの既存request fieldとplain-text回答を維持し、成功responseへ`saved_at`だけを追加します。
- POST保存正常/失敗rollback、GET正常/not-found/validation no-store、送信中の入力ロック、別ウィンドウlink、大型画面のloading/error/plain-text表示、v2026.08.17 asset選択を自動testで確認します。
- 実OpenAI確認では従来どおりcompleted status、response ID、非空output textを確認し、その成功recordを同じrequest IDで取得できることを確認します。

### 3.7 既知制約

- 保存recordにaccess controlとretention policyがないため、引き続きtrusted local環境限定です。
- request IDを知る利用者は保存回答を取得できます。Internetへ直接公開しません。
- 保存commitが失敗するとOpenAI利用分は発生済みでもresponseは失敗になります。暗黙retryは行いません。

## 4. SC-2026-08-17-01 — 個別銘柄AI最小縦スライスと定型prompt最小統合

### 4.1 変更理由

旧Portfolio AI経路はmulti-mode、Web検索、Structured Outputs、JSON解析、mock、cache、fallbackを同時に扱います。OpenAI APIとの最小通信経路を単独で切り分け、個別銘柄回答の品質をversioned promptで改善するには、より小さいcanonical経路が必要でした。

### 4.2 変更前

- 要件仕様 v1.1、API仕様 v1.4、画面仕様 v1.6は、主にdashboardのmulti-mode Portfolio AI分析を定義していました。
- `POST /api/ai/stock-review` では、mode別model、Web検索、Structured Outputs、JSON parse救済、mock/cache/historyを扱いました。
- 独立した個別銘柄1件のplain-text endpointと画面は、versioned仕様の正本に未記載でした。

### 4.3 変更後

- canonical endpointとして `POST /api/ai/analyses` を追加しました。
- 独立画面として `GET /ui/analysis` を追加しました。
- 対象はactiveな登録済み個別銘柄1件、入力は自由質問、回答設定は `STANDARD` 固定です。
- OpenAI Responses APIを1回呼び、`response.status=completed`、response ID、trim後に非空の `response.output_text` を満たす場合だけ成功とします。
- 回答はbrowserの `textContent` と `white-space: pre-wrap` でプレーンテキスト表示します。
- 新経路ではmock、cache、fallback、Web検索、Structured Outputs、JSON修復、再AI呼び出し、streaming、backgroundを使用しません。

### 4.4 model・回答設定

| 項目 | 現在値 |
|---|---|
| model | `gpt-5.6-terra` |
| preset | `STANDARD` |
| `reasoning.effort` | `medium` |
| `reasoning.mode` | 未送信 |
| `text.verbosity` | `medium` |
| timeout | 60秒 |
| SDK retry | 0 |

model選択と回答品質presetは別の設定軸です。`STANDARD`はmodel名を内包しません。

### 4.5 prompt変更

添付 `株判断プロジェクト｜定型プロンプト集 v2026.08.16` は、アプリを操作する指示ではなく、モデルへ送るpromptのsource assetとして扱います。

組み込む範囲は次だけです。

1. `1. 株判断共通OS`
2. `2. 共通入力テンプレート` の個別銘柄MVPに必要な規則
3. Web・外部市場データなしのアプリ実行制約
4. `3.1 総合的な個別銘柄分析`
5. `security_master` 由来の銘柄context
6. ユーザーの自由質問

3.2〜3.14、アプリ向けJSON Schema、人間向け重複template、資料内の実装優先順位はrequestへ入れません。

`app/prompts/individual_security/manifest.json` はprompt version、profile、compiler version、module、asset ID、source/asset hash、compile orderを保持します。asset欠落やhash不一致はfail closedとし、旧promptへfallbackしません。

### 4.6 trace・秘密情報

- OpenAI metadataへ保存するのはprompt version、profile、compiler、module、asset ID、source SHA-256、compiled SHA-256だけです。
- prompt全文、質問全文、APIキーはOpenAI metadata、通常ログ、公開FastAPI response、browserへ出しません。
- 公開responseは `request_id` と、取得できた場合の `openai_response_id` を返します。
- 永続audit tableは未実装であり、長期追跡可能性はOpenAI metadataとログの保持期間に依存します。

### 4.7 互換性

- `POST /api/ai/stock-review`、`POST /portfolio/ai-review`、`POST /api/portfolio/ai-review` は変更しません。
- 旧 `app/prompts/stock_analysis/`、multi-mode、Web検索、Structured Outputs、mock、cache、history、raw output fallbackも旧経路に限って維持します。
- 新経路は旧経路のfallbackや設定を共有しません。
- 既存endpointの削除やdeprecationはありません。

### 4.8 非対象

- `LIGHT` / `HIGH` / `PRO` / `MAX`
- model選択UI
- 複数銘柄、市場全体、総合分析
- Web検索、J-Quants等の追加context取得
- Structured Outputs、JSON Schema、JSON修復
- Markdown renderer、構造化card
- mock、cache、fallback、streaming、background、polling
- prompt全14用途moduleの投入
- 旧Portfolio AI経路の削除・再設計

### 4.9 既知制約

- `POST /api/ai/analyses` にはアプリ独自の認証とrate limitがありません。
- `scripts/run_api.py` の既定hostは `0.0.0.0` で、アプリはTLSを提供しません。現状はtrusted local環境限定で、Internetへ直接公開しません。
- OpenAPI自動生成は現時点で実際の404 / 429 / 502 / 503 / 504 response modelを網羅していません。
- prompt manifestやasset構成異常はtyped `AiAnalysisError`ではなく、現状はHTTP 500になり得ます。
- promptへ渡す実データは主に銘柄masterであり、価格、決算、チャート、需給、市場、マクロ、イベント、保有条件は未提供です。そのため回答が `insufficient_data` / `no_trade` 寄りになる場合があります。
- 共通OSの標準出力は、情報が少ない質問では回答を冗長にする場合があります。

### 4.10 受け入れ確認

- compiler、OpenAI client、FastAPI endpoint、UI shellのunit testを維持します。
- 代表質問fixture 10件で、買い判断、決算後、要因分離、モメンタム、需給、イベント、リスク、反証、情報不足、no-tradeを比較できます。
- 実OpenAI確認ではcompleted status、response ID、非空output textを確認します。
- 実browser確認では、銘柄選択、質問入力、loading、成功回答、error非表示、plain-text描画を確認します。

## 5. 直前baseline

| 適用日 | 要件 | API | 画面 | 主な範囲 |
|---|---:|---:|---:|---|
| 2026-08-17 | v1.2 | v1.5 | v1.7 | SC-2026-08-17-01: canonical個別銘柄AI最小縦スライスと定型prompt最小統合 |

直前baselineの完全な内容は各versioned fileに残します。新baselineは旧機能を削除せず、個別銘柄AIの独立経路を追加して適用範囲を明確化したものです。

## 6. 更新ルール

1. 要件、API、画面のどこが変わるかを特定する。
2. 過去版を保持し、影響するversioned fileの次版を追加する。
3. 変更理由、互換性、非対象、既知制約をこの文書へ追記する。
4. `python scripts/sync_current_files.py --write` を実行する。
5. 各 `current.md` の日付、変更概要、主な内容を手動確認する。
6. `python scripts/sync_current_files.py --check` を実行する。
7. 実装・運用・文書変更を `docs/changelog.md` へ追記する。
