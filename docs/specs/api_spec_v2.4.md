# kabuhandan_hojo API Spec v2.4

## 1. scope

この版はv2.3のAPI契約を累積継承し、dashboard legacy stock-reviewのローカル保存履歴を読み取る一覧・詳細・Markdown export APIを追加する。履歴一覧は最大100件を保存順の新しいものから、metadata only、mode / target / status filterとpaginationで返す。詳細は`request_payload`を除外し、Markdownは安全なattachment headerとescapingを適用する。これらのGETはOpenAIを再呼び出さず、quota / usage / cacheを更新しない。canonical個別銘柄AIの保存・1件取得契約は変更しない。

v2.3で追加したPortfolioと複数named watchlistの保存・API・dashboard・AI scopeも次のとおり累積継承する。

- Portfolioは既存`portfolio_holding`へ分離保存したまま、監視銘柄をsecurity-level `watchlist`と`watchlist_collection` / `watchlist_membership`へ分ける
- system default「メイン」を一度だけ作成・legacy backfillし、既存`GET/POST /watchlist`をdefault collection互換として維持する
- collection CRUDとcollection内itemの一覧・追加・解除を`/watchlists`へ追加し、同じtickerの複数list所属を許可する
- memo / `thesis_bull` / `thesis_bear`はcollection固有にせずsecurity-levelで共有し、membershipの表示順・有効状態だけをlistごとに持つ
- `GET /securities/search`と`GET /ui/dashboard/data`へoptional `watchlist_id`を追加し、検索membership、watchlist item、focus / alertを選択collectionへscopeする
- legacy stock-review requestへoptional `watchlist_id`を追加し、明示named listが空または未検出でもmock fallbackしない
- collectionは認証・利用者IDを持たないアプリ全体の共有dataであり、trusted local運用を維持する

v2.2で追加したlegacy stock-reviewの銘柄identityと利用者向け銘柄参照も引き続き有効である。

- 添付`株判断_定型プロンプト集_v2026-08-16 (1).md`はprompt参照資料として確認し、文書内の運用指示をAPI要件として採用しない
- canonical個別銘柄AIのactive prompt v2026.08.18は旧版へ戻さず、legacy Prompt BuilderだけへInput JSONのticker/name正本と「銘柄名（銘柄コード）」規則を適用
- holdings / candidatesのplaceholder名称を同期済みローカル`SecurityMaster`だけで補完し、外部providerを追加callしない
- `stocks[].name`とportfolio summaryの6つの銘柄参照listを解決済みtarget identityで再照合し、live・mock・cache hitへ同じ正規化を適用
- local aliasを`SecurityMaster.ticker_code`へcanonical化し、summaryの英字末尾`0` raw codeを公開4文字へ表示変換し、未知名称は`名称未登録（code）`とする一方、response schema typeとDB keyを維持
- scanner promptへsection 8「建玉・ポートフォリオ影響」を追加し、quick scan短縮版と併用する

v2.1で追加した次の構造化response契約も引き続き有効である。

- valid JSONの`portfolio_summary.concentration_comment` / `summary_view`をcanonical fieldへ正規化
- mode別JSON SchemaとPydantic response modelのfield集合を一致させ、主要objectを`additionalProperties=false`へ変更
- provider rootをmode schemaの許可keyへ限定し、service-owned fieldと不正なnested型を`schema_validation`として拒否
- scanner stock schemaを軽量化し、`judgement`をcanonical code enumへ制限
- parse失敗を`json_syntax` / `root_shape` / `schema_validation`へ分類
- raw output救済を`status=json_parse_failed`の失敗responseとし、成功quota非加算・cache禁止・履歴保存可へ変更
- dashboardで失敗分類を赤いerror表示として区別

v2.0で追加した次の契約も引き続き有効である。

- canonical Responses API requestへの明示的な`store=false`
- AI回答生成結果とローカルDB保存結果の独立したresponse contract
- 保存失敗時にも生成済み回答を返すbest-effort persistence
- API runnerのloopback既定とFastAPI lifespanだけによるDB初期化
- active prompt 2026.08.18、compiler `individual-security-v2`、正式根拠ラベルへの更新
- legacy stock-reviewの日次quota既定値300と、`review_runs` / provider `api_calls`の分離
- JST日次・月次usage v2 ledger、公式pricing provenance付き概算額、未算定call
- `GET /api/ai/stock-review/usage`とdashboard利用量表示
- `GET /securities/search`の銘柄名・数字/英字コード検索と、検索結果からportfolio入力へ進む画面契約
- `POST /portfolio`の4文字公開コードから一意なJ-Quants raw master identifierへのalias解決
- BYOKでJ-Quants上場銘柄マスターをprivateなローカルDBへ同期する`POST /securities/master/sync`
- 最新の完全な現行snapshotのprovenanceと件数を返す`GET /securities/master/status`
- 完全な現行snapshotだけのJ-Quants所有record無効化と、historical snapshotのcurrent status/active状態保護
- ETF、REIT、優先株等を除外しない東証/J-Quants listed-issue scope、provider code保持、`source_as_of`境界
- 本番4,000件のcomplete floor、既存J-Quants/支配的legacy基準から最大5%の縮小guard、明示legacy adoption、参照付きidentity splitのfail-closed保護
- DB-only銘柄検索、provider bodyを含まないconnector/browser error、CLI dry-runに先行するDB初期化境界

v1.7 の最小AI縦スライスと、legacy multi-mode stock AI review、Prompt Registry / Prompt Builder、mode別Structured Outputs、Web検索制御、JSON parse救済、ChatGPT手動投入用プロンプト生成は引き続き有効である。ただし、legacy機能はstock-review経路の契約であり、canonical個別銘柄AI経路には継承しない。raw output救済の成功扱いだけはv2.1の失敗契約で置き換える。

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
| `GET` | `/watchlist` | default watchlist「メイン」の互換一覧 | `list[WatchlistItem]` |
| `POST` | `/watchlist` | default watchlistへの追加 / 再有効化 | `WatchlistItem` |
| `GET` | `/watchlists` | activeなwatchlist collection一覧 | `list[WatchlistCollectionRead]` |
| `POST` | `/watchlists` | named watchlist作成 | `WatchlistCollectionRead` |
| `PATCH` | `/watchlists/{collection_id}` | collection名 / 表示順更新 | `WatchlistCollectionRead` |
| `DELETE` | `/watchlists/{collection_id}` | non-default collection削除 | `204 No Content` |
| `GET` | `/watchlists/{collection_id}/items` | collection内のactive item一覧 | `list[WatchlistItem]` |
| `POST` | `/watchlists/{collection_id}/items` | collectionへ銘柄追加 / 再有効化 | `WatchlistItem` |
| `DELETE` | `/watchlists/{collection_id}/items/{ticker_code}` | collectionからmembership解除 | `204 No Content` |
| `GET` | `/portfolio` | 保有銘柄一覧 | `list[PortfolioItem]` |
| `POST` | `/portfolio` | 保有銘柄登録 / 更新 | `PortfolioItem` |
| `POST` | `/portfolio/import/csv` | 保有銘柄CSV import | import result |
| `POST` | `/api/ai/analyses` | 個別銘柄AI縦スライス | `AiAnalysisResponse` |
| `GET` | `/api/ai/analyses/{request_id}` | 保存済み個別銘柄AI回答の1件取得 | `AiSavedAnalysisResponse` |
| `POST` | `/api/ai/stock-review` | multi-mode stock AI review | `PortfolioAiReviewResponse` |
| `GET` | `/api/ai/stock-review/usage` | legacy stock-reviewのJST日次・月次usageと概算額 | `PortfolioAiUsageSummary` |
| `GET` | `/api/ai/stock-review/history` | legacy保存履歴のfilterable metadata一覧 | `PortfolioAiReviewHistoryListResponse` |
| `GET` | `/api/ai/stock-review/history/{history_id}` | legacy保存履歴の安全な1件取得 | `PortfolioAiReviewHistoryDetail` |
| `GET` | `/api/ai/stock-review/history/{history_id}/export.md` | legacy保存履歴のUTF-8 Markdown attachment | `text/markdown` |
| `POST` | `/portfolio/ai-review` | 互換AIレビュー入口 | `PortfolioAiReviewResponse` |
| `POST` | `/api/portfolio/ai-review` | 互換AIレビュー入口 | `PortfolioAiReviewResponse` |
| `GET` | `/securities/search` | 銘柄名または数字・英字コード検索。optional `watchlist_id`でmembership判定をscope | `list[SecuritySearchResult]` |
| `POST` | `/sources/bootstrap` | source registry 初期化 | `JobRunResponse` |
| `GET` | `/securities/master/status` | 最新の完全な現行J-Quants銘柄マスター同期状態 | `SecurityMasterStatusResponse` |
| `POST` | `/securities/master/sync` | J-Quants上場銘柄マスターをprivate local DBへ同期 | `SecurityMasterSyncResponse` |
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
| `GET` | `/ui/dashboard/data` | optional `watchlist_id`付きUI view model | `DashboardExperienceResponse` |

### 2.1 `GET /securities/search`

query parameterは`q`、`limit`、optional `watchlist_id`である。

| parameter | type | default | validation / meaning |
|---|---|---|---|
| `q` | `string` | - | 必須、1〜100文字。前後空白を除去して検索する |
| `limit` | `integer` | `10` | 1〜50 |
| `watchlist_id` | `integer \| null` | `null` | 1以上。指定collectionに対する`in_watchlist`判定。nullはdefault collection |

`q`は登録済み`security_master`の次の値へ照合する。

このendpointはローカルDBだけを検索する。各候補について`SecurityProfileService`やJ-Quants profile APIを呼ばず、DBに存在するname、market、industry等をそのまま返す。DB recordがない銘柄をproviderへ問い合わせて検索結果へ補完しない。

- `ticker_code`のprefix
- `local_code`のprefix
- 日本語名または英語名の部分一致

数字4桁に限定せず、英字を含む公開コード（例:`285A`）と、登録済みraw identifier（例:`285A0`）を検索できる。code、英語名、marketは大文字・小文字を区別せず、ticker完全一致、local/raw code完全一致、ticker prefix、local/raw code prefix、日本語名部分一致、英語名部分一致、market部分一致の順で優先し、同順位はticker昇順とする。

返却する`SecuritySearchResult.ticker_code`は、該当する`security_master`のprimary identifierである。raw/local codeで一致しても、優先株等の別issueを普通株へ縮約しない。`in_watchlist`は指定collection内にactive membershipがある場合だけtrueで、同じtickerが別collectionにあることだけではtrueにしない。`watchlist_id`が存在しないまたはinactiveな場合はHTTP 404、0以下は422とする。dashboardは英字を含む5文字末尾`0`形式だけを公開4文字へ変換して表示・portfolio入力し、detail actionのdata属性とURLには返却identifierを維持する。検索は保有recordを作成せず、検索結果の選択だけで`POST /portfolio`を呼ばない。

### 2.2 `POST /portfolio` identifier解決

requestの主要fieldは次のとおりである。

| field | type | required | rule |
|---|---|---:|---|
| `ticker_code` | `string` | yes | 4〜10文字。前後空白を除去し大文字化して解決する |
| `quantity` | `number` | yes | 0より大きい |
| `average_cost` | `number \| null` | no | 指定時は0より大きい |
| `note` | `string \| null` | no | 任意メモ |

identifierは次の順序で解決する。

1. 正規化済み入力と`security_master.ticker_code`が完全一致する場合、その既存masterを使う。
2. 完全一致がなく、入力が`[0-9A-Z]{4}`に一致する場合だけ、`<入力>0`と一致する`ticker_code`または`local_code`を検索する。
3. master上の候補が一意なら、その候補の`ticker_code`をportfolio holding identifierとして使う。
4. 候補が0件または複数件なら別の既存銘柄へ推測解決しない。従来の未登録コード処理を維持する。

したがって、J-Quants masterに`ticker_code=285A0`または`local_code=285A0`のキオクシアホールディングスが一意に存在するとき、`ticker_code=285A`のrequestは既存`285A0`へ紐付き、`285A`のplaceholder masterを追加しない。`ticker_code=285A0`の完全一致requestも従来どおり受理する。

このaliasはportfolio登録境界だけの互換処理である。`security_master` primary key、既存参照record、J-Quants connectorの返却値を一括して4文字へ変換しない。

`POST /portfolio/import/csv`の各行も同じ`PortfolioService.upsert_item()`を通るため、4文字公開コードには同じ一意alias解決を適用する。

### 2.3 `GET /securities/master/status`

credentialを送らず、ローカルDBに記録された最新の完全な現行J-Quants同期と現在の有効件数を確認する。

```json
{
  "source": "jquants",
  "source_scope": "tse_listed_issues",
  "source_as_of": "2026-05-26",
  "sync_id": "b46000b7-70d4-4b8a-8d33-e4f50f45d708",
  "synced_at": "2026-08-18T09:30:00Z",
  "complete": true,
  "active_total": 4430,
  "jquants_active_count": 4430
}
```

| field | type | rule |
|---|---|---|
| `source` | `string` | 現行完全同期のsource。通常は`jquants` |
| `source_scope` | `string` | `tse_listed_issues`。J-Quants masterが返す東証上場issueで、普通株だけでなくETF、REIT、優先株等もprovider responseに含まれる限り対象 |
| `source_as_of` | `date \| null` | providerが示した情報基準日。利用者planに応じて遅延し得るため、`synced_at`やリアルタイム時点と同一視しない |
| `sync_id` | `string \| null` | 完全な現行同期runの識別子。未確認時はnull |
| `synced_at` | `datetime \| null` | ローカル取り込み時刻。市場情報の基準日ではない |
| `complete` | `boolean` | 完全な現行snapshotを記録済みか。36件seedだけの状態はfalse |
| `active_total` | `integer >= 0` | sourceを問わない現在のローカル有効master総数 |
| `jquants_active_count` | `integer >= 0` | `master_source=jquants`かつactiveな現在件数 |

完全な現行runがまだない場合もHTTP 200を返し、`complete=false`、`source_as_of=null`、`sync_id=null`、`synced_at=null`と現在件数を返す。historical runはこのstatusの正本を置き換えない。APIキー、provider payload、銘柄全件、database URLをresponseへ含めない。

### 2.4 `POST /securities/master/sync`

query parameterは次のとおりである。

| parameter | type | default | rule |
|---|---|---|---|
| `target_date` | `date \| null` | null | nullは現行snapshot。指定時はhistorical snapshot |
| `require_jquants` | `boolean` | false | trueではkey未設定、connector error、空response、現行snapshot不完全をHTTP 400としてrollbackする |

dashboardの`東証全銘柄を同期`は常に`require_jquants=true`を使う。成功例は次のとおりである。

```json
{
  "source": "jquants",
  "source_scope": "tse_listed_issues",
  "source_as_of": "2026-05-26",
  "sync_id": "b46000b7-70d4-4b8a-8d33-e4f50f45d708",
  "synced_at": "2026-08-18T09:30:00Z",
  "complete": true,
  "active_total": 4430,
  "jquants_active_count": 4430,
  "job_name": "sync_security_master",
  "processed_count": 4430,
  "fetched_count": 4430,
  "upserted_count": 4430,
  "inserted_count": 100,
  "updated_count": 4330,
  "reactivated_count": 10,
  "deactivated_count": 2,
  "detail": "Synchronized a complete current J-Quants TSE listed-issues snapshot: ...",
  "executed_at": "2026-08-18T09:30:00Z"
}
```

countの意味は次のとおりである。

- `fetched_count`: pagination、必須identifier/name検査、code正規化、重複・衝突検査を通ってconnectorがserviceへ返したlisted issue数
- `inserted_count`: 新規master数
- `updated_count`: 既存masterへのupsert対象数。field値が変わらない同一snapshotの再同期も含む
- `upserted_count`: `inserted_count + updated_count`
- `processed_count`: `upserted_count`と同値。seed件数とJ-Quants件数を重複加算しない
- `reactivated_count`: 今回の完全な現行snapshotでactiveへ戻した件数
- `deactivated_count`: 完全な現行snapshotに存在せずinactiveへ変更したJ-Quants所有record数
- `active_total` / `jquants_active_count`: transaction内の同期反映後の現在件数

現行snapshotは、本番で`fetched_count >= 4000`かつ全recordの非nullな`source_as_of`が1日へ一致した場合だけ完全候補となる。さらに、同期前のactiveな`master_source=jquants`件数と、支配的legacy snapshot cohort件数を合算した`previous_provider_count`に対し、`fetched_count >= ceil(previous_provider_count * 0.95)`を満たさなければDB変更前に失敗する。つまり既存provider母数から5%を超える縮小は、形式上4,000件以上でも受理しない。不完全、空、複数基準日、過大縮小を含む現行snapshotは、既存J-Quants masterと同期runを変更せず、`require_jquants=true`ではHTTP 400とする。完全な現行snapshotだけが、取得集合にない`master_source=jquants`のrecordをinactiveへ変更する。`manual`、`local_seed`、所有元未採用の`legacy` recordを欠落扱いにしない。unit testはservice constructorへ小さいfloorを明示注入できるが、production既定値は4,000である。

`target_date`を指定したhistorical同期は、現行masterを無効化せず、既存active状態を上書きせず、新規historical recordをactiveな現行銘柄として扱わず、最新の完全な現行statusを置き換えない。historicalの`complete=true`には、完全性閾値と単一基準日に加えて`source_as_of=target_date`を必要とする。responseは取得内容に応じて`complete=false`でもよいが、0件は`require_jquants=true`でHTTP 400とする。

`require_jquants=false`でkey未設定またはconnector errorの場合だけ、36件のbundled search seedをinsert-onlyで適用し、HTTP 200、`source=local_seed`、`source_scope=bundled_search_seed_only`、`complete=false`を返す。このfallbackを全件同期成功と解釈してはならない。seedは既存J-Quants recordを上書きしない。

provider codeは次の境界で扱う。

- 5桁数字かつ末尾`0`の普通株identifierは既存互換の4桁`ticker_code`へ正規化し、raw値を`local_code`へ保持する。
- 5桁数字で末尾が`0`でないidentifierは優先株等の別issueとして保持する。
- 英数字identifierはraw値を維持する。
- 異なるraw provider codeが同じ正規化identifierへ衝突した場合は、優先順位で片方を捨てず`ConnectorError`とする。
- 既存recordの`local_code`が今回取得の別issue identifierへ一致し、ordinary/preferred等のidentity splitが必要な候補では、DB metadataから`security_master.ticker_code`への全外部キー参照を確認する。参照recordがある場合はprimary keyのrename、merge、silent overwriteを行わず、同期開始前のJ-Quants master状態を維持し、`require_jquants=true`ではHTTP 400とする。参照がない候補だけを通常upsertで修復する。

J-Quants masterのpagination key循環とsafe page上限はfail closedとし、HTTP 429は`Retry-After`を尊重する最大2回のbounded retry後に失敗する。timeout、network error、invalid JSONはprovider/transportのraw detailを含まない分類済み`ConnectorError`へ変換し、HTTP errorはstatus codeだけを含めてprovider response bodyを捨てる。`require_jquants=true`のHTTP 400とdashboard errorへもprovider body、APIキー、request headerを転送しない。

旧importerがprovider snapshot `Date`を`listed_date`へ誤格納した可能性は、activeかつ`master_source=legacy`で同一の非null`listed_date`を持つ最頻cohortが4,000件以上の場合だけ「支配的legacy snapshot cohort」と判定する。このcohortが存在する通常API/UI current同期は、完全な取得結果でもJ-Quants master変更前にfail closedとし、dashboardが使う`require_jquants=true`ではHTTP 400、`python scripts/sync_security_master.py --adopt-legacy`による明示reconciliationを要求する。`--adopt-legacy`はcurrent snapshotだけで使え、`--as-of`との同時指定を拒否し、manual/local-seed/別listed-dateのlegacy recordは採用しない。

CLIの`--dry-run`はserviceが行うJ-Quants master同期transactionをrollbackし、集計値だけをstdoutへ出す。ただしCLIはtransaction開始前に`init_db()`を呼ぶため、schema作成・migrationと不足36件seed bootstrapは永続化され得る。したがって`--dry-run`はDB全体に対するread-only保証ではない。CLIのconnector failureは固定されたsafe errorだけを出し、provider/transport detailをstdoutへ出さない。

同期runは`security_master_sync_run`へ非secret provenanceと集計値だけを保存する。完全な銘柄datasetは利用者自身のJ-Quants契約・APIキーでprivateなgit管理外DBへ保存し、public repositoryへ同梱・再配布しない。scopeは東証/J-Quants listed issuesで、地方取引所単独銘柄の網羅を保証しない。

### 2.5 watchlist collection data modelと起動migration

Portfolioは従来どおり`portfolio_holding`を使い、次のwatchlist tableへ統合しない。

| table | responsibility / key fields |
|---|---|
| `watchlist` | 1 tickerにつき1つのsecurity-level監視record。`memo`、`thesis_bull`、`thesis_bear`は全collectionで共有。legacy `sort_order` / `is_active`も互換のため保持 |
| `watchlist_collection` | named list。`id`、`name` (VARCHAR 80)、`normalized_name` (VARCHAR 256, unique)、nullable unique `system_key`、`sort_order`、`is_active`、timestamps |
| `watchlist_membership` | collectionと`watchlist.id`の関連。`collection_id`、`watchlist_item_id`、list固有`sort_order` / `is_active`、timestamps。組合せunique、item / active index |

system default collectionは`system_key=default`で、初期表示名は`メイン`である。同じtickerは1つのsecurity-level rowを複数membershipから参照するため、複数named listへ同時に所属できる。memo / thesisをlist別に複製しない。

起動時の`init_db()`はtable作成後、次の互換migrationを行う。

1. `watchlist`、`watchlist_collection`、`watchlist_membership`がすべて存在する場合だけ処理する。
2. `system_key=default`が既にあればactiveへ戻して終了し、全legacy rowを再backfillしない。
3. defaultがなければ、正規化名`メイン`の既存collectionへsystem keyを付けるか、新規作成する。
4. 同じ初回transaction内でlegacy `watchlist` rowをdefault membershipへbackfillする。同tickerの複数legacy rowはactive、更新時刻、IDの決定順で代表を選ぶが、legacy row自体を削除・mergeしない。
5. commit後の再実行ではnamed-only itemをdefaultへ追加しない。

この処理はSQLite / PostgreSQLの双方で同じ論理を使う。正式migration frameworkの導入や既存Portfolio rowの変換は行わない。

### 2.6 watchlist collection CRUD

#### `GET /watchlists`

active collectionをdefault、`sort_order`、作成時刻の順で返す。defaultが未作成ならserviceが「メイン」を作成して返す。

```json
[
  {
    "id": 1,
    "name": "メイン",
    "is_default": true,
    "sort_order": 0,
    "item_count": 5,
    "created_at": "2026-08-19T06:00:00Z",
    "updated_at": "2026-08-19T06:00:00Z"
  }
]
```

`item_count`はactive collection内のactive membershipかつactive security-level item数である。`normalized_name`と`system_key`は公開schemaへ出さない。

#### `POST /watchlists`

HTTP 201でcollectionを作成する。

```json
{
  "name": "半導体",
  "sort_order": 20
}
```

| field | type | required | default / rule |
|---|---|---:|---|
| `name` | `string` | yes | NFKC正規化とtrim後1〜80文字。display nameにも正規化後値を使う |
| `sort_order` | `integer` | no | `100` |

identityはNFKC・trim・casefoldで一意にする。`ＴＥＣＨ`と`tech`等の重複はHTTP 409とし、DB unique constraint競合も同じsafe errorへ変換する。

#### `PATCH /watchlists/{collection_id}`

bodyは`name`、`sort_order`のどちらか1つ以上を必要とする。成功はHTTP 200と更新後`WatchlistCollectionRead`である。default collectionもname / sort orderを更新できるが、`system_key`はrequest fieldにせず変更させない。missing / inactive IDは404、正規化後の重複nameは409、空bodyまたはfield validation違反は422とする。

#### `DELETE /watchlists/{collection_id}`

non-default collectionとそのmembershipを削除し、HTTP 204の空bodyを返す。default collectionはHTTP 409、missing / inactive IDは404である。削除対象以外のcollection、security master、Portfolioを削除しない。security-level `watchlist.is_active`は他のactive collection membershipが残る場合true、最後のmembershipがなくなった場合falseへ更新する。undo / trash / restoreは提供しない。

### 2.7 collection item APIとlegacy default互換

#### `GET /watchlists/{collection_id}/items`

指定collectionのactive membershipとactive security-level itemをmembershipの`sort_order`、membership作成時刻順で返す。missing / inactive collectionは404である。

#### `POST /watchlists/{collection_id}/items`

既存`WatchlistCreate` bodyを受け、HTTP 201で`WatchlistItem`を返す。

```json
{
  "ticker_code": "7203",
  "name": "トヨタ自動車",
  "market": "TSE",
  "memo": "共通メモ",
  "thesis_bull": "共通の強気仮説",
  "thesis_bear": null,
  "sort_order": 3
}
```

- `ticker_code`は4〜10文字で必須。既存security masterを使い、必要な場合は従来のmanual security作成境界を維持する。
- security-level `watchlist` rowがなければ作成し、あれば再利用する。memo / thesisはbodyへ明示されたfieldだけを更新し、他collectionでも同じ値を参照する。
- collection内membershipがなければ作成し、inactiveなら再有効化する。`sort_order`はmembership固有値として更新する。
- responseは既存fieldにnullable `collection_id`を加え、named / defaultのどちらでも解決済みcollection IDを返す。`sort_order`はmembership値である。
- missing / inactive collectionは404、body validation違反は422である。

#### `DELETE /watchlists/{collection_id}/items/{ticker_code}`

指定collectionのactive membershipだけをinactiveにし、HTTP 204の空bodyを返す。別collectionの同tickerとPortfolioは維持する。collectionまたはactive membershipがない場合は404である。最後のactive collection membershipを外した場合、security-level `watchlist.is_active`をfalseへするがrowと共有memo / thesisは削除しない。

#### legacy `GET/POST /watchlist`

`GET /watchlist`と`POST /watchlist`は`system_key=default` collectionへ委譲する互換入口として維持する。responseの`collection_id`にはdefault IDを返す。既存request schemaとHTTP 200 / 201契約を維持し、named collection IDはこのpathから指定しない。

### 2.8 dashboard view modelとnavigation scope

`GET /ui/dashboard/data`は既存`ticker_code`に加え、optionalなpositive integer `watchlist_id`を受ける。

```json
{
  "portfolio_items": [],
  "watchlist_collections": [
    {
      "id": 1,
      "name": "メイン",
      "is_default": true,
      "sort_order": 0,
      "item_count": 5,
      "created_at": "2026-08-19T06:00:00Z",
      "updated_at": "2026-08-19T06:00:00Z"
    }
  ],
  "selected_watchlist_id": 1,
  "watchlist_items": []
}
```

- `watchlist_collections`はactive collection全件、`selected_watchlist_id`は実際に解決したcollection IDである。
- request IDがactive collectionなら、そのcollectionの`watchlist_items`、watchlist由来dashboard rows、Focus Board、alertsを構築する。
- `watchlist_id`がnull、missing、inactiveの場合はdefault collectionへfallbackする。これはUI state回復用のview-model契約で、collection / item CRUDと検索のmissing ID 404とは異なる。
- `portfolio_items`はcollection scopeにかかわらず`portfolio_holding`から独立して返す。
- named list選択中にdetail / chartへ進むUI URLは`?watchlist_id={id}`を保持する。detail / chart shellも同じqueryでdashboard dataを読み、戻るlinkとwatchlist追加 / 仮説保存を同じcollectionへscopeする。queryなしのPortfolio起点はlegacy `/watchlist` default互換を使う。
- browserは各dashboard fetchのrequested `watchlist_id`をrequest IDと一緒に保持し、response到着時に現在activeなmanagement scopeと一致する場合だけ採用する。Portfolioへ戻る場合も`watchlist_id`なしでdashboard dataを再取得し、default monitoring scopeへ戻す。これはclient consistency規則でresponse schemaを増やさない。
- `/ui/dashboard?watchlist_id={id}`の初期表示は指定named listで、AI targetも`watchlist`へ初期化する。queryなしではPortfolio / `holdings`を既定とする。

## 3. legacy `POST /api/ai/stock-review`

この節から第8節まではv1.4のlegacy stock-review契約を継承する。ここで定義するmock、cache、Web検索、Structured Outputs、JSON parse救済、raw output fallbackは `POST /api/ai/analyses` には適用しない。

### 3.1 request

```json
{
  "mode": "analyst",
  "target": "watchlist",
  "watchlist_id": 3,
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
| `watchlist_id` | `int \| null` | `null` | 1以上。`target=watchlist`時にnamed collectionを明示する。nullはlegacy default互換 |
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

`target=watchlist`かつ`watchlist_id`が非nullの場合、指定collectionだけからtargetを解決する。collectionが空、missing、inactiveでもmock holdingsへfallbackせず、`holdings_source=watchlist`かつ`status=no_holdings`を返す。API route自体はこのAI target未検出を404へ変換しない。`watchlist_id=null`のlegacy callerはdefault collectionを使い、defaultが空なら従来のmock fallback互換を維持する。`target!=watchlist`では`watchlist_id`をtarget解決に使わない。

named listのcheckboxで1件以上を選択したbrowserは、既存の`target=selected`と`holdings` / `tickers` fieldを使って選択銘柄を送る。全解除時にmanual tickerがなければclientは`target=watchlist`へ戻す。この自動切替は新しいAPI fieldを追加せず、list全体targetと選択targetを同じrequest schemaで区別する。

UIはrequest開始時のcollection名をclient-side context snapshotとして保持し、loading / summary label / client-only reader titleへ使う。collection名snapshotはこのAPI request / response、history、cache、DBへ追加せず、renameやselector切替後に進行中responseのlabelを再解決しない。selector切替、collection作成、active collection削除、active membership mutation、checkbox変更時はclient側request generationを進めて既存結果と旧responseを無効化するが、取消APIや追加OpenAI callは発生させない。

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

### 3.5 legacy銘柄identity正規化

1. request/DB/mockからtargetを解決し、DB sessionがある場合はactiveな`SecurityMaster.ticker_code` / `local_code`を完全一致または英字4文字と末尾`0` aliasで検索する。一致したtargetはmasterの`ticker_code`、正式`name`、登録marketを正本とする。一致しないtargetはrequest側identityを維持する。J-Quantsその他のproviderへ追加requestしない。
2. local aliasはmasterのcanonical `ticker_code`へ揃える。例として`local_code=285A0` / `ticker_code=285A`はprompt・holdings snapshotで`285A`、`local_code=72030` / `ticker_code=7203`は`7203`になる。これはDB primary keyや`local_code`のmutationではない。
3. canonical tickerへ揃えたholdings / candidatesをticker単位でdedupeし、両方にある銘柄はholdingsを優先する。
4. OpenAIの`stocks[].ticker`に対応する解決済みtarget identityがあれば、`stocks[].name`を正式名称へ戻す。modelがcodeまたは誤名称を返してもそのまま利用者向け正本にしない。
5. 次の`portfolio_summary` fieldは型を`list[str]`のまま維持し、各要素を「銘柄名（公開コード）」へ正規化する。

```text
buy_candidates
sell_or_reduce_candidates
hold_priority
non_monitoring_reduce_candidates
core_position_candidates
exit_or_rotate_candidates
```

6. codeだけ、`誤名称（code）`、または正式名称だけの要素は、identityを解決できる場合に正式な「銘柄名（公開コード）」へ置換する。解決不能なcodeだけの要素は`名称未登録（code）`とし、銘柄参照でない自由文は変更しない。
7. 英字を含む5文字末尾`0` raw codeだけをsummaryの公開4文字へ変換する。例:`285A0`またはcanonical `285A`は`キオクシアホールディングス（285A）`となる。未解決numeric 5文字codeを表示関数だけで一律短縮しない。
8. live response、mock response、保存前response、cache hitの読出しへ同じ処理を適用する。cache hitの正規化でOpenAIを呼び直さない。

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
  "parse_failure_kind": null,
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
| `json_parse_failed` | OpenAI応答を構造化responseへ確定できない。`parse_failure_kind`で原因を区別する |
| `openai_api_error` | OpenAI API エラー |
| `openai_sdk_missing` | OpenAI Python SDK 未導入 |
| `no_holdings` | 対象銘柄なし |
| `target_limit_exceeded` | 対象銘柄数上限超過 |
| `daily_limit_exceeded` | 日次実行回数上限超過 |

`parse_failure_kind`は`status=json_parse_failed`の原因を次の3値で表す。正常responseでは`null`である。

| `parse_failure_kind` | meaning |
|---|---|
| `json_syntax` | JSON decoderが構文として読めない |
| `root_shape` | JSON自体は有効だがrootがobjectではない。配列内にobjectがあっても抽出しない |
| `schema_validation` | root objectは有効だが許可key、必須field、field shape、またはPydantic modelに一致しない |

parserはfence除去後の本文全体を先に`json.loads()`する。有効なJSON配列はその時点で`root_shape`となり、配列内の最初のobjectをprovider rootとして採用しない。本文全体がJSON構文として不正な場合だけ既存のobject部分抽出を試み、抽出後も構文不正なら`json_syntax`とする。

長い不正応答は、Web検索なしのJSON整形リトライを1回実行する。救済に成功した場合は`status=success`とし、`warnings`に元の失敗分類と整形リトライ実行を記録する。

整形リトライにも失敗した場合でも、応答が`{` / `[`で始まる、または十分な長さがある場合は、調査可能性のためraw output救済responseをHTTP 200で返せる。ただし分析成功へ変換せず、`status=json_parse_failed`、`error.code=json_parse_failed`、原因別`parse_failure_kind`、非空`raw_model_output`、`portfolio_summary.market_temperature=raw_output_fallback`とする。raw fallback状態はservice自身がparse failure branchで生成した場合だけ設定し、provider rootの`status`等から推測しない。`save_result=true`ならローカル履歴へ保存できるがcacheへ保存しない。短く表示対象外の失敗も`status=json_parse_failed`とする。

この節のretry、alias正規化、raw output救済はlegacy stock-reviewだけの挙動である。`POST /api/ai/analyses`は同じ挙動を持たない。

日次quotaの`review_runs`は、銘柄数に関係なく構造化に成功したtop-level live review 1件を1回とする。mock、forced mock、cache hit、`prompt_only`、事前拒否、OpenAI error、最終parse失敗、raw output救済の`status=json_parse_failed`は増やさない。provider usageを取得できたResponses responseはparse結果と独立して`api_calls`へ記録し、JSON整形repairにより成功reviewまたは失敗attemptのいずれでも最大2 callsになる場合がある。

## 6. legacy Prompt Builder contract

legacy stock-reviewのOpenAI API実行時は次の順で処理する。

1. `PortfolioAiReviewService.review()` が `target`を解決する。`target=watchlist`かつ非null`watchlist_id`では指定collectionだけを読み、空またはmissingでもmockへfallbackしない
2. `build_stock_analysis_prompt()` が Base Policy、mode profile、必要章、入力JSON、mode別schemaを組み立てる
3. `call_open_ai_for_stock_review()` が Responses APIへ送信する
4. `parse_ai_review_result()` がJSONをparseし、互換aliasとlegacy judgementをcanonical field / codeへ正規化してPydantic responseへ検証する
5. `validate_stock_analysis_response()` が不足フィールドをwarning化する
6. serviceがrequest側identityを使って`stocks[].name`とportfolio summaryの銘柄参照listを正規化する
7. `save_ai_review_result()` が必要に応じて履歴保存する

`prompt_only` mode は `build_prompt_only_text()` を使い、OpenAI APIを呼ばない。

mode別output schemaは、列挙fieldを`PortfolioAiSummary` / `PortfolioAiStockAnalysis`のfield以内に保つ。top-level、`portfolio_summary`、`stocks[].items`は`additionalProperties=false`とする。`scanner`はstock fieldを30項目未満へ縮小し、詳細mode固有fieldを生成契約から外す。`judgement`は次のenumだけを許可する。

provider rootで許可するのは、request mode schemaの`generated_at`、`mode`、`input_summary`、`market_summary`、`portfolio_summary`、`stocks`、`action_plan`、`critical_warnings`、`sources`、`warnings`、`raw_model_output`だけである。FastAPI/service response用の`status`、`error`、`cache_hit`、`parse_failure_kind`、`manual_prompt`、model/usage/snapshot/request field等をproviderが返した場合は`schema_validation`とする。

```text
hold
buy_more_candidate
take_profit_candidate
reduce_risk
watch
avoid_new_buy
urgent_review
```

parse前の互換正規化では、`portfolio_summary.concentration_comment`を`concentration_risk`へ、`portfolio_summary.summary_view`を`overall_view`へ移してaliasを除去する。canonical fieldが既に非空ならcanonical値を優先する。互換aliasが存在する場合はstringだけを許可する。`stocks`の各要素はobject、存在する`judgement`はstringでなければならず、不一致は黙って破棄・変換せず`schema_validation`とする。既知codeでないfree-text `judgement`は`judgement_label`も含むkeyword対応でcanonical codeへ変換し、対応不能時は`watch`とする。この正規化だけを理由に追加OpenAI callを行わない。

## 7. legacy mode profiles

| mode | model env | reasoning env | web policy | sections |
|---|---|---|---|---|
| `scanner` | `OPENAI_MODEL_SCANNER` | `OPENAI_REASONING_SCANNER` | `optional` | Base, 0, 1, 2 summary, 3 summary, 5.5 short, 8, 9, 13 short, 14 short。stock outputは30項目未満の軽量schema |
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

- `review_runs`: 構造化された`status=success`まで完了したlive一括review数。5銘柄をまとめた1 requestも1回。`status=json_parse_failed`のraw output救済は含めない。
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

正常なlegacy responseのcache機能とrequest contractは変更しない。cache hitしたrequestはOpenAIを呼ばず、`review_runs`と`api_calls`を増やさない。`status!=success`または非空`raw_model_output`のresponseはcacheへ保存せず、既存cacheに残っていてもcache hitとして返さない。

### 8.2 legacy保存履歴API

#### 8.2.1 保存条件とlocal storage

- `POST /api/ai/stock-review`は`save_result=true`で新しいresponseを生成した場合だけ、git管理外の`data/ai_review_history.json`へ追加する。`save_result=false`は保存せず、cache hitは`save_result=true`でも新規履歴を作らない。
- `status=success`のlive / mock / forced mock、`prompt_only`、調査可能な`json_parse_failed`は保存対象になり得る。対象銘柄なし、API key不足、quota拒否、provider error等、保存可能な結果を生成する前に返した失敗は保存しない。
- prompt / mock / live / raw fallbackの保存に失敗しても生成済みresponseは返し、APIを再呼び出さず、安全な固定warningを`warnings`へ1回だけ追加する。失敗responseをcacheへ保存せず、破損したhistory rootは上書きしない。
- 最大100 recordを保持し、新規保存時に古いrecordから上限外へ送る。appendは同一process内の`RLock`と同一directoryの一時file、flush / fsync、`os.replace`を使う。複数process / 複数host間のhard guaranteeではない。
- 履歴IDは保存entryのcanonical JSONから作る64文字の小文字SHA-256 hexである。安定したlookup keyであり、認証情報や推測不能なaccess tokenではない。

#### 8.2.2 `GET /api/ai/stock-review/history`

保存順の新しいものからmetadata-only一覧を返す。回答本文、manual prompt、`request_payload`、position detail、provider raw responseは一覧へ含めない。responseは`Cache-Control: no-store`と`X-Content-Type-Options: nosniff`を持つ。

| query | type | default | validation / meaning |
|---|---|---|---|
| `mode` | `scanner \| analyst \| judge \| critical \| prompt_only` | omitted | 分析方法filter |
| `target` | `holdings \| watchlist \| candidates \| selected \| mock \| unknown` | omitted | 保存時に導出した対象filter |
| `status` | `ReviewStatus` | omitted | 保存responseのstatus filter |
| `limit` | integer | `100` | 1〜100 |
| `offset` | integer | `0` | 0以上 |

response fields:

| field | meaning |
|---|---|
| `items` | filter後、offset / limit適用済みで、保存順の新しいものから並ぶmetadata |
| `total` | filter後、pagination前の有効件数 |
| `stored_count` | history rootに保存されている全entry数。不正entryも含み得る |
| `invalid_count` | schema不一致entry、または不正rootとして読み飛ばした件数 |
| `mode_counts` | filter前の有効entry全体をmode別に数えたmap。0件modeも含む |
| `retention_limit` | 固定保持上限`100` |
| `limit`, `offset` | requestへ適用したpagination値 |

各`items[]`は次のmetadataだけを持つ。

- `history_id`, `generated_at`
- `mode`, `mode_label`, `analysis_mode`
- `target`, `target_label`, `status`, `status_label`, `holdings_source`
- `stock_count`, 最大3件の`stocks_preview`
- `summary`: model回答本文ではなく、mode / status / 件数から作る決定的な表示文
- `model`, `watchlist_id`
- `include_web_search`, `web_search_used`, `mock_response`, `cache_hit`
- `estimated_cost_usd`

`mode_counts`はfilter前、`total`はfilter後、`items`はさらにpagination後である。不正entryは正常entryの一覧を妨げず`invalid_count`へ計上する。不正rootは空一覧相当として読み、後続saveで既存fileを上書きしない。

#### 8.2.3 `GET /api/ai/stock-review/history/{history_id}`

- validな履歴はHTTP 200で`{"history_id":"<64hex>","review":{...}}` envelopeを返す。
- `review`は保存済み`PortfolioAiReviewResponse`の表示用projectionで、`request_payload` keyを必ず除外する。
- 過去のcode-only銘柄参照はread時だけ同期済みローカルmasterにより正式名称・公開codeへ補完する。履歴file自体は変更しない。
- IDが64hexでない場合と一致recordがない場合はいずれもsafeなHTTP 404とし、内部pathや保存内容を返さない。
- 成功・404とも`Cache-Control: no-store`と`X-Content-Type-Options: nosniff`を持つ。

#### 8.2.4 `GET /api/ai/stock-review/history/{history_id}/export.md`

- validな履歴は`Content-Type: text/markdown; charset=utf-8`のsemantic Markdownを返す。
- `Content-Disposition`は`attachment; filename="ai-review-YYYYMMDD-HHMMSS-<mode>-<id先頭8文字>.md"`形式の安全なASCII filenameとする。
- `Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`を付ける。
- heading、metadata、portfolio / stock sections、warnings、source、raw fallbackをMarkdownへ対応付ける。可変textはHTMLとMarkdown control文字をescapeし、source URLは`http` / `https`だけをclickable linkにする。raw textは内容中のbacktick runより長いfenceで囲む。
- 保存recordだけから生成し、OpenAI、外部source、usage ledger、cacheへアクセスしない。missing / invalid IDはdetailと同じsafeな404とする。

#### 8.2.5 named watchlist context

保存recordがpositive integerの`watchlist_id`を持つ場合はmetadataへ返せるが、実行時のnamed watchlist名は旧recordへ保存していない。履歴read時に現行collection名を推測して補わず、一般的な対象labelと保存済みIDだけを扱う。rename / delete後も過去名を復元する契約はない。

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

両canonical HTML shellのresponseは`Cache-Control: no-store`と`Referrer-Policy: no-referrer`を持つ。canonical保存回答の一覧・検索・削除・export UIは提供しない。第8.2節のlegacy履歴UI/APIはこのcanonical非対象を変更しない。

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
- `JQUANTS_API_KEY`はサーバー側だけで読み、銘柄マスターstatus/sync response、browser、通常ログへ出さない。
- 完全なJ-Quants銘柄一覧はgit管理外のprivate local DBへだけ保存し、repositoryには36件の限定seed以外を同梱・再配布しない。
- current snapshotが完全性検査に失敗した場合は既存masterを変更せず、完全なcurrent snapshotだけがJ-Quants所有recordを無効化できる。
- collection名はNFKC / trim後の長さを検証し、casefold identityとDB unique constraintで重複を拒否する。collection / membership IDはpositive integerとしてvalidationする。
- named collection削除はdefaultを409で拒否し、対象collection以外のmembership、Portfolio、security masterを削除しない。
- legacy履歴一覧はmetadataだけを返し、詳細から`request_payload`を除外する。履歴GET / exportはno-store / nosniffを持ち、Markdown exportはさらにno-referrer、安全なASCII filename、可変text / link / fenceのescapingを適用する。
- history append失敗時は生成回答を維持して固定warningを追加し、不正rootを上書きしない。通常更新は同一process内lockとatomic replaceを使う。
- 出力は判断補助であり、断定的投資助言や自動売買指示として扱わない。

### 17.2 known deployment limitations

現行の `POST /api/ai/analyses` は次を実装していない。

- アプリ認証・認可
- endpoint固有のserver-side rate limit、daily quota、cost ceiling
- idempotency、同時送信のserver-side抑止
- TLS終端
- 保存回答の一覧・検索・削除・export・保持期限・自動purge

legacy stock-review用の `OPENAI_DAILY_REQUEST_LIMIT` は新endpointへ適用されない。API runnerの既定bind hostは`127.0.0.1`であり、既定ではローカルPCだけから到達できる。

named watchlist API、dashboard view model、detail操作にも認証・利用者分離・owner fieldはない。collection、membership、security-level memo / thesisはアプリDBへ接続できる利用者間で共有される。loopback既定は同一PC内の利用者を分離しない。

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
- promptがInput JSONのticker/name正本、「銘柄名（銘柄コード）」、scanner section 8を含み、不要な個別詳細sectionをscannerへ投入しないことを確認する
- local `SecurityMaster`だけでplaceholder名称を補完し、provider追加callなしでselected / request holdingの正式名称を得られることを確認する
- live parse、mock、cache hitで`stocks[].name`とsummaryの6つの銘柄参照listを同じ規則へ正規化し、`285A0`をsummaryで`キオクシアホールディングス（285A）`へ表示できることを確認する
- unknown codeを`名称未登録（code）`とし、local aliasをcanonical master tickerへ解決し、未解決numeric 5文字codeとresponse schema typeを維持することを確認する
- canonical tickerでtargetをdedupeし、holdings / candidatesの重複ではholdingsを優先することを確認する
- quota既定300、1 batch=1 review、mock/cache/prompt-only/limit拒否の非加算、repair/parse-failed provider responseのapi call加算を確認する
- scanner schemaがPydantic modelのfield以内で、top-level、portfolio summary、stock itemの`additionalProperties=false`、stock field 30項目未満、`judgement` 7値enumであることを確認する
- valid JSONの`concentration_comment` / `summary_view`が追加OpenAI callなしでcanonical fieldへ正規化されることを確認する
- parse失敗が`json_syntax` / `root_shape` / `schema_validation`へ分類され、schema mismatchを構文エラーと表示しないことを確認する
- provider rootのmode schema外key、valid JSON array root、非object stock、非string judgement、非string互換aliasをそれぞれ`schema_validation`または`root_shape`として拒否することを確認する
- raw fallback判定がservice-localなparse pathに限定され、providerのstatus / cache / parse fieldを受理しないことを確認する
- raw output救済が`status=json_parse_failed`を維持し、`review_runs`非加算、cache保存・読出し禁止、`save_result=true`での履歴保存可能という境界を確認する
- dashboard HTMLが3つの`parse_failure_kind`を異なる赤いerror labelへ変換することを確認する
- JST日/月summary、pricing formula、unknown model/token欠損の未算定、旧counter非移行、atomic ledger formatを確認する
- usage/history/cacheを一時pathへ隔離し、repositoryのlocal dataをtestが変更しないことを確認する
- 銘柄名、数字コード、英字を含むコードで登録済み銘柄を検索できることを確認する
- dashboard検索結果の「保有入力へ」が、英字5文字末尾`0`では返却identifierを公開4文字へ変換してprefillするだけで、数量入力と保存操作までは`POST /portfolio`を呼ばないことを確認する
- `POST /portfolio`の完全一致優先、一意な`<4文字>0` alias解決、既存5文字identifier受理、公開コードplaceholder非作成を確認する
- master code正規化がnumeric普通株の末尾`0`だけを4桁化し、非zero suffixの優先株等と英数字raw identifierを保持し、異なるraw codeの衝突をfail closedにすることを確認する
- listed masterの全page取得、pagination key循環拒否、safe page上限、`Retry-After`を尊重するbounded 429 retryを確認する
- 不完全current snapshotがDBを変更せず、完全current snapshotだけがJ-Quants所有recordをinactiveにし、manual/local-seed/未採用legacy recordを維持することを確認する
- historical snapshotがcurrent active状態を上書きせず、欠落deactivationを行わず、最新complete/current statusを置き換えないことを確認する
- `GET /securities/master/status`のcomplete/incomplete、scope、`source_as_of`、同期時刻、ローカル/J-Quants有効件数とcredential非露出を確認する
- `POST /securities/master/sync`がfetch/upsert/insert/update/reactivate/deactivate件数を区別し、required J-Quants失敗とoptional seed fallbackを異なるstatusとして返すことを確認する
- seed同期がinsert-onlyで既存J-Quants metadataを上書きせず、SQLite/PostgreSQLの既存DBへprovenance列とsync-run tableを追加できることを確認する
- startup migrationがdefault「メイン」を一度だけ作成・legacy backfillし、再実行でnamed-only itemをdefaultへ漏らさないことをSQLiteで確認する
- collection一覧 / 作成 / 更新 / non-default削除、default削除409、missing 404、NFKC・trim・casefold重複409、post-normalization長さ422を確認する
- 同tickerを複数collectionへ追加でき、security-level memo / thesisを共有しながらmembership順序と解除をlistごとに分離することを確認する
- legacy `GET/POST /watchlist`がdefault collectionを読み書きし、`WatchlistItem.collection_id`へdefault IDを返すことを確認する
- `GET /securities/search?watchlist_id=`の`in_watchlist`がcollectionごとに異なり、missing IDを404とすることを確認する
- `/ui/dashboard/data?watchlist_id=`がcollection一覧、解決済みID、scoped items / focus / alertsを返し、missing IDはdefaultへfallbackすることを確認する
- legacy AIがnamed `watchlist_id`をserviceへ渡し、明示named listの空 / missingをmock fallbackせず`no_holdings`にすることを確認する
- mock modeでもcollection CRUD、membership、search/dashboard scope、named AI targetの外部契約を維持することを確認する
- dashboard clientがrequested scopeとactive scopeの不一致responseを破棄し、Portfolio復帰時に`watchlist_id`なしでdefault monitoring dataをreloadすることを確認する
- URL `?watchlist_id=`初期表示が`target=watchlist`、checkbox選択が既存`target=selected` request、全解除かつmanual tickerなしが`target=watchlist`となることを確認する
- request開始時のlist名がsummary / reader titleのclient snapshotとなり、API / history / cache / DB fieldを増やさずrename後も当該結果のlabelを維持することを確認する
- scope / collection / membership / checkbox mutationで既存結果と進行中responseを無効化し、取消API、追加OpenAI call、quota mutationを発生させないことを確認する
- legacy履歴保存が`save_result=true`の新規生成時だけ行われ、`save_result=false`とcache hitでは増えず、prompt / mock / live / raw fallbackの保存失敗時は回答を維持してsafe warningを1回追加しcacheへ保存しないことを確認する
- history appendの最大100件、同一process thread-safe / atomic replace、invalid entry skip/count、破損rootの上書き拒否を確認する
- listが保存順の新しいものから並ぶmetadata-only、filterable / pageableで、`mode_counts`・`total`・`stored_count`・`invalid_count`のcount境界と決定的summaryを守ることを確認する
- detailが`request_payload`を除外し、invalid / missing IDをsafeな404とし、過去のcode-only参照をfile非変更でread-time補完することを確認する
- Markdown exportがsemantic section、安全なASCII filename、no-store / nosniff / no-referrer、HTML / Markdown escape、HTTP(S) link allowlist、可変長raw fenceを守ることを確認する
- history list / detail / exportがOpenAI再呼び出し、quota / usage / cache mutationを発生させないことを確認する

### 19.2 live checks

- `scripts/smoke_openai_response.py` はFastAPI/browserなしで固定model、STANDARD、completed status、OpenAI response ID、非空output textを確認する。
- live FastAPI checkは `POST /api/ai/analyses` がHTTP 200、`status=success`、OpenAI response ID、非空answer textを返すことを確認する。
- live browser checkは銘柄検索、選択、質問、送信、loading、実endpoint response、answer表示、error非表示、別ウィンドウ導線、保存回答の大型表示を確認する。

live checkは実APIキーと課金を伴うため、秘密情報をfixture、test output、通常ログへ保存せず、通常のunit testで暗黙実行しない。

## 20. guardrails

- 正式 source は J-Quants / EDINET API / YouTube Data API / allowlist IR を中心とする。
- J-Quants完全masterは利用者自身のAPIキーでprivate local DBへ同期し、public repositoryへ同梱・再配布しない。
- master scopeは東証/J-Quants listed issuesであり、地方取引所単独銘柄まで含む国内全取引所網羅を標榜しない。
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
- J-Quants listed master由来の一部銘柄は、公開4文字コードではなく末尾`0`付きの5文字raw identifierを`security_master.ticker_code`に保持する。v1.9は`POST /portfolio`の一意alias解決だけを追加し、master primary keyや既存参照tableのmigration、connector全体のcanonical化は行わない。
- 検索responseの`ticker_code`は登録済みmaster identifierであり、公開コードと常に同じ長さとは限らない。dashboardの公開code表示はUI境界の変換であり、API responseやmaster identifierは変更しない。
- J-Quants masterの`source_as_of`は利用者planに応じて遅延し得る。`synced_at`はローカル取込時刻であり、情報のリアルタイム性を保証しない。
- `tse_listed_issues`はJ-Quants masterが返す東証上場issueのscopeで、地方取引所単独銘柄を保証しない。完全datasetは各利用者のgit管理外DBにだけ存在する。
- J-Quants 429、network、plan/entitlement、endpoint変更により同期は失敗し得る。bounded retry後は既存masterを維持してerrorとし、seed fallbackを全件同期成功として扱わない。
- 本番4,000件/5%縮小guardは壊れた全件取得や急減を保護する保守的条件であり、東証上場issueが正当に5%超減る特殊局面でもcurrent同期を停止し得る。閾値をUIから緩和する機能はない。
- 支配的legacy cohortと参照付きidentity splitは安全側に停止する。通常UI/APIだけではreconcileできず、前者はCLIの明示`--adopt-legacy`、後者は参照recordを考慮した個別identity migrationが必要である。
- CLI `--dry-run`より前の`init_db()`はschema/migration/不足seedを永続化し得る。完全なread-only監査が必要な場合はDB backupまたは隔離copyを用いる。
- named watchlistのmemo / thesisはcollection固有ではない。同tickerを含む全collectionから同じsecurity-level値を参照する。
- non-default collection削除はhard deleteで、membership配置のundo / trash / restoreを提供しない。security-level rowは残りmembershipの有無に応じてactive状態だけを更新する。
- dashboard view modelはmissing / inactive `watchlist_id`をdefaultへfallbackするが、collection CRUD、item API、scoped検索は404となる。
- `watchlist_id`を持たないlegacy `target=watchlist`はdefaultが空のときmock fallbackする既存互換を残す。明示named listだけがempty / missingを`no_holdings`としてfail closedにする。
- named collection、membership、memo / thesisにはowner IDとaccess controlがなく、trusted local利用に限定する。
- default collectionの初回migrationは単一application processでの起動を前提とする。未初期化PostgreSQLへ複数processが同時起動した場合のdefault unique競合をserialize / retryする契約とtestはないため、初回初期化は1 processで行う。
- legacy履歴は最大100件固定で、削除、全文検索、pin、期限、自動purge、共有URL、cloud同期、認証・利用者別access controlを持たない。
- history appendの`RLock`は同一processだけをserializeし、複数process / 複数host間の同時書き込みhard guaranteeを持たない。
- legacy履歴に当時のnamed watchlist名は保存されない。`watchlist_id`だけではrename / delete前の名称を復元できない。
- APIはMarkdownを生成するがPDF fileを生成しない。PDF保存はdashboard readerをbrowser印刷する操作に依存する。

## 22. revision history

### v2.4 — 2026-08-19

- v2.3を累積継承し、legacy stock-reviewの最大100件のローカル保存履歴へmetadata一覧、詳細、UTF-8 Markdown export APIを追加した。
- listのmode / target / status / limit / offset、保存順の新しいものからの順序、filter前`mode_counts`、filter後pagination前`total`、invalid entry count、model本文を使わない決定的summaryを定義した。
- detail envelopeから`request_payload`を除外し、旧code-only参照を履歴file非変更でread-time補完する契約を追加した。
- Markdown attachmentのASCII filename、no-store / nosniff / no-referrer、HTML / Markdown escape、HTTP(S) source link、可変長raw fenceを定義した。
- `save_result=true`だけの保存、cache hit非保存、履歴保存失敗時の生成回答維持とsafe warning、不正root上書き拒否、同一process lock / atomic replace、OpenAI非再呼出を明記した。
- 過去のnamed watchlist名が保存されず、現行名を推測復元しない制約を記録した。

### v2.3 — 2026-08-19

- v2.2を累積継承し、`watchlist_collection` / `watchlist_membership`、system default「メイン」、初回だけのlegacy backfill、Portfolio別storage、security-level memo / thesis共有を追加した。
- `GET/POST/PATCH/DELETE /watchlists`とcollection item一覧・追加・解除を追加し、同tickerの複数list所属、default削除409、NFKC / trim / casefold name identity、204 deleteを定義した。
- legacy `GET/POST /watchlist`をdefault collection互換として維持し、`GET /securities/search`と`GET /ui/dashboard/data`へoptional `watchlist_id`を追加した。
- dashboard responseへ`watchlist_collections` / `selected_watchlist_id`を追加し、named listのitems / focus / alerts、detail / chart navigationと詳細保存scopeを定義した。
- legacy stock-review requestへoptional `watchlist_id`を追加し、明示named listのempty / missingでmock fallbackしない`no_holdings`契約を追加した。
- dashboardのrequested / active scope照合、Portfolio復帰時のdefault monitoring reload、URL query由来の初期AI target、checkboxによる既存`selected` target自動切替を定義した。
- request開始時のlist名をAPI / DBへ増やさないclient context snapshotとしてsummary / reader titleへ使い、scope・collection・membership・checkbox mutationで旧結果 / 旧responseを無効化する規則を追加した。
- collectionは認証・owner IDを持たないapp-global dataであり、loopback / trusted-local境界を維持した。

### v2.2 — 2026-08-19

- v2.1を累積継承し、legacy promptへInput JSONのticker/name正本と「銘柄名（銘柄コード）」規則を追加した。
- holdings/candidatesをローカル`SecurityMaster`でcanonical化し、modelの`stocks[].name`とsummaryの6つの銘柄参照listを解決済みtarget identityで正規化する契約を追加した。
- live・mock・cache hitへ同じ正規化を適用し、local aliasのmaster ticker canonical化、重複targetのholdings優先、英字末尾`0` raw codeの公開表示、未知名称label、schema type維持を定義した。
- scannerへsection 8「建玉・ポートフォリオ影響」を追加し、canonical active prompt v2026.08.18を旧添付v2026.08.16へ戻さない境界を明記した。

### v2.1 — 2026-08-19

- v2.0の契約を累積継承した。
- legacy軽量スキャンの`concentration_comment` / `summary_view` alias正規化とfree-text judgementのcanonical code化を追加した。
- mode別JSON SchemaとPydantic modelのfield集合を一致させ、主要objectの`additionalProperties=false`、scanner schema縮小、judgement enumを追加した。
- provider rootをmode schemaの許可keyへ限定し、service-owned field、valid JSON array root、stock / judgement / aliasの不正型を厳格に拒否する契約を追加した。
- parse失敗を`json_syntax` / `root_shape` / `schema_validation`へ分類した。
- raw output救済をservice-localなparse pathで判定して`status=json_parse_failed`へ変更し、成功quota非加算、cache保存・読出し禁止、履歴保存可、dashboard赤表示を明文化した。

### v2.0 — 2026-08-18

- v1.9の契約を累積継承した。
- `GET /securities/master/status`と拡張`POST /securities/master/sync`のprovenance、complete/current/historical、count契約を追加した。
- BYOKによるprivate local sync、full dataset非同梱・非再配布、東証/J-Quants listed-issue scope、地方取引所単独銘柄非保証、plan遅延し得る`source_as_of`を明文化した。
- 完全な現行snapshotだけのJ-Quants所有record無効化、historical status/active状態保護、seed insert-only、explicit legacy adoptionを追加した。
- production floor 4,000、既存J-Quants/支配的legacy基準に対する最大5%縮小guard、支配的legacy cohortの通常UI/API fail-closedとcurrent CLI明示採用を追加した。
- ordinary/preferred/alphanumeric issue code保持、参照付きidentity splitと正規化衝突のfail-closed、pagination guard、bounded 429 retry、取得/永続化件数分離を追加した。
- DB-only銘柄検索、provider body/transport detailを除外するsafe error、`--dry-run`より前のschema/seed初期化境界を明文化した。

### v1.9 — 2026-08-18

- v1.8の契約を累積継承した。
- `GET /securities/search`が銘柄名、数字コード、英字を含むコードを検索できることを明文化した。
- dashboardの検索結果からportfolioフォームへ公開codeをprefillする非保存導線を追加し、英字5文字末尾`0`のraw identifierはdetail actionに維持した。
- `POST /portfolio`で完全一致を優先し、4文字公開コードを一意な末尾`0`付きJ-Quants raw masterへ解決してplaceholder重複を防ぐ契約を追加した。
- 既存5文字identifierを維持し、master primary key migrationとJ-Quants connector全体のcanonical化を非対象とした。

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
