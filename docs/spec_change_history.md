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
| 要件仕様 | v1.7 | `docs/requirements/requirements_v1.7.md` | 2026-08-18 |
| API仕様 | v2.0 | `docs/specs/api_spec_v2.0.md` | 2026-08-18 |
| 画面仕様 | v2.2 | `docs/screen_specs/screen_spec_v2.2.md` | 2026-08-18 |

この3版は同じ変更単位 `SC-2026-08-18-02` を表します。どれか1つだけを旧版へ戻して運用することは想定しません。

## 3. SC-2026-08-18-02 — 東証/J-Quants上場銘柄マスターのprivate local full sync

### 3.1 変更理由

bundled masterは36件の検索seedに限られ、J-Quants由来recordがローカルDBに存在していても情報基準日、取得範囲、完全性、所有sourceを確認できませんでした。利用者がキオクシア等を含む東証上場issueを検索対象へ追加できるようにしつつ、公開repositoryへprovider datasetを同梱・再配布せず、不完全取得やhistorical取得で既存の現行masterを破壊しない同期境界が必要でした。

### 3.2 source・scope・配布境界

- 完全な銘柄一覧は利用者自身のJ-Quants契約・`JQUANTS_API_KEY`で取得し、git管理外のprivate local DBへだけ保存します。APIキー、full response、全銘柄CSVをpublic repository、browser、通常logへ出しません。
- J-Quants個人版は個人の私的利用等の契約条件があるため、利用者自身がplan/最新規約を確認します。取得データまたはdata-backed serviceを第三者へ配信せず、公開するrepositoryはデータ/APIキーを含まないlocal-use codeだけとします。public hostや第三者向け提供には別途適切な契約・許諾が必要です。
- scopeは`source_scope=tse_listed_issues`です。J-Quantsの上場銘柄masterが返す東証上場issueを対象とし、普通株に加えてETF、REIT、優先株等もprovider responseに含まれる限り除外しません。
- 「全日本銘柄」「国内全取引所」を保証しません。名古屋・福岡・札幌等の地方取引所単独銘柄はscope外になり得ます。
- bundled `data/security_master_jp.csv`の36件は初期検索用seedです。full datasetの代替ではなく、insert-onlyで既存J-Quants metadataを上書きしません。
- `source_as_of`はproviderが示す情報基準日で、利用者planにより遅延し得ます。`synced_at`はローカル取込時刻で、リアルタイム性の証明ではありません。

### 3.3 code・pagination・取得境界

- numeric 5桁末尾`0`の普通株codeだけを既存互換の4桁identifierへ正規化し、raw codeを`local_code`へ残します。非zero suffixの5桁numeric codeは優先株等の別issueとして保持し、英数字identifierもraw値を維持します。
- 異なるraw provider codeが同じ正規化identifierへ衝突した場合は、priorityで片方を捨てたりsilent overwriteしたりせず同期を失敗させます。
- ordinary/preferred等のidentity split候補では、`security_master.ticker_code`を参照する全外部キーをDB metadataから確認し、参照recordがあれば自動rename/merge/upsertを行わずDB変更前に失敗させます。参照がない候補だけを通常upsertで修復します。
- paginationを全pageたどり、pagination key循環とsafe page上限をfail closedにします。429は`Retry-After`を尊重する最大2回のbounded retryだけを行います。
- providerの`Date`を`source_as_of`へ、明示的な`ListingDate` / `ListedDate`だけを`listed_date`へ保存し、snapshot基準日を上場日として誤記録しません。
- timeout/network/invalid JSONはprovider/transport raw detailを含まない分類済みerrorへ、HTTP errorはstatusだけを含むerrorへ変換し、provider response bodyをAPI/browser/CLIへ出しません。

### 3.4 complete/current/historical・所有source

- 現行snapshotは、本番4,000件以上で、全recordの非nullな`source_as_of`が1日へ一致する場合だけcomplete候補です。同期前のactive J-Quants件数と支配的legacy cohort件数の合算基準から5%を超えて縮小する場合もDB変更前に拒否します。不完全、空、基準日不整合、過大縮小ではJ-Quants master変更を適用しません。
- 完全な現行snapshotだけが、取得集合に存在しない`master_source=jquants` recordをinactiveへ変更できます。manual、local-seed、所有元未採用legacy recordを自動deactivateしません。
- historical同期は現行recordのactive状態を上書きせず、欠落deactivationを行わず、最新complete/current statusを置き換えません。historicalのcomplete判定では`source_as_of=target_date`も検証します。
- 旧importerがprovider snapshot `Date`を`listed_date`へ誤格納した支配的legacy cohortは、activeなlegacy recordの同一非null date最頻cohortが本番floor 4,000件以上の場合だけ検出します。検出時の通常API/UI current同期はfail closedとし、current syncの`python scripts/sync_security_master.py --adopt-legacy`だけで明示reconcileします。`--as-of`との同時指定は拒否し、無関係なmanual/local-seed/別date legacyを採用しません。
- `security_master_sync_run`へsync ID、source/scope、情報基準日、同期時刻、complete/current区分、取得/永続化件数だけを保存します。

### 3.5 API・画面契約

- `GET /securities/search`は同期済みDBだけで英数字codeをcase-insensitiveに照合し、ticker完全一致、raw/local code完全一致、各prefix、名称、marketの既存priorityを維持します。返却identifierは登録済みprimary codeで、優先株等の別issueを普通株へ縮約せず、候補ごとのJ-Quants profile callを行いません。
- `GET /securities/master/status`を追加し、最新complete/current runのscope、`source_as_of`、`synced_at`、complete、ローカル有効件数、J-Quants有効件数をcredentialなしで返します。
- `POST /securities/master/sync`は取得、新規、更新、再有効化、無効化、ローカル/J-Quants有効件数を分けます。`upserted_count=inserted_count+updated_count`で、seed件数とJ-Quants件数を重複加算しません。
- dashboard buttonを`東証全銘柄を同期`へ変更し、`require_jquants=true`で実行します。同期前/取得中/完全/未確認/errorを分け、情報基準日、同期時刻、各件数を表示します。
- key未設定やconnector error時、required同期はHTTP 400です。optional APIだけが36件seedを`source=local_seed`、`complete=false`で返し、全件同期成功とは表現しません。
- 通常UI/APIは支配的legacy cohortや参照付きidentity splitを検出するとsafe errorで停止します。provider response body、transport detail、credentialを画面へ出しません。

### 3.6 互換性・非対象・既知制約

- 既存の検索、portfolio alias、canonical/legacy AI契約を維持します。full master同期はAI request内の市場context取得ではありません。
- master primary keyの一括migration、地方取引所専用connector、full dataset export/配布、定期background同期、APIキーの共有は実装しません。
- provider rate limit、network、plan entitlement、endpoint変更により同期は失敗し得ます。bounded retry後は既存masterを維持し、別sourceへ暗黙fallbackしません。
- 本番4,000件/5%縮小guardは正当な大幅減少でも安全側に停止し得ます。UIから閾値を緩和せず、参照付きidentity splitの専用migrationもこの変更には含めません。
- CLI `--dry-run`はmaster同期transactionをrollbackしますが、先行する`init_db()`のschema初期化・migrationと不足36件seed bootstrapは永続化され得るため、DB全体のread-only保証ではありません。
- PostgreSQL/SQLiteの既存DBへprovenance列とsync-run tableを追加しますが、正式なmigration framework導入はこの変更の対象外です。

### 3.7 受け入れ確認

- ordinary/preferred/alphanumeric code保持、source/listing date分離、pagination guard、429 retry、provider body/transport detail非露出をconnector testで確認します。
- production floor 4,000、5%縮小guard、incomplete currentの無変更、complete currentだけのJ-Quants所有record deactivate、historical保護、支配的legacyの通常同期拒否/明示採用、参照付きidentity split拒否、seed insert-onlyをservice testで確認します。
- status/sync APIのcomplete/incomplete、required failure、optional seed fallback、各count、credential非露出をAPI testで確認します。
- DB-only検索でprovider callが起きないこと、dashboardが同期状態、情報基準日、J-Quants/ローカル件数、取得/新規/更新/再有効化/無効化を表示し、safeな失敗を成功表示しないことをtestで確認します。

## 4. SC-2026-08-18-01 — 銘柄検索から保有入力への導線とJ-Quants code alias

### 4.1 変更理由

dashboardの銘柄検索結果は詳細画面を開くだけで、見つけた銘柄を保有入力へ引き継げませんでした。キオクシアホールディングスは登録済みJ-Quants masterではraw identifier`285A0`として存在し、公開コード`285A`をportfolioフォームへ直接入力すると、別のplaceholder masterを作る可能性もありました。検索可能であることと、検索結果から安全に保有登録へ進めることを同じ導線で成立させる必要がありました。

### 4.2 変更前

- `GET /securities/search`は登録済みmasterの銘柄名、ticker/local codeを検索できましたが、dashboardの案内は「銘柄名か4桁コード」で、英字コードを検索できることが伝わりませんでした。
- dashboardの検索結果actionは`詳細を見る`だけでした。
- Portfolio panelの入力フォームは検索と独立し、利用者が銘柄identifierを手入力する必要がありました。
- `POST /portfolio`は入力tickerの完全一致だけをmasterへ照合し、`285A`と既存raw identifier`285A0`を同一銘柄として解決しませんでした。

### 4.3 検索・画面導線

- 検索labelを`銘柄名か銘柄コード（数字・英字）で検索`、placeholderを`7203 / 285A / トヨタ / キオクシア`へ変更します。
- 各検索結果に`保有入力へ`と`詳細を見る`を別buttonで表示します。
- 英字を含む5文字末尾`0`形式では、検索結果のcode表示と`保有入力へ`のprefill値を公開4文字へ変換します。キオクシアのraw `285A0`は`285A`と表示・入力します。
- buttonのdata属性と`詳細を見る`のURLには検索responseのraw `ticker_code`を維持し、登録済みmasterのdetailを正確に開きます。
- この操作だけでは保存せず、数量を入力して`保有を保存`を押す必要があることをfeedback表示します。数量は必須、平均取得単価とメモは任意です。
- `詳細を見る`の既存action、watchlist、canonical個別銘柄AI検索は変更しません。

### 4.4 portfolio identifier alias

- `POST /portfolio`はtrim・大文字化した入力と`security_master.ticker_code`の完全一致を最優先します。
- 完全一致がなく、入力が4文字の数字・英字コードの場合だけ、`<入力>0`に一致する`ticker_code`または`local_code`を候補にします。
- 候補が一意な場合だけ、その既存masterの`ticker_code`へ解決します。候補が0件または複数件なら別の既存銘柄へ推測解決しません。
- 例として、`285A`は一意な既存master`285A0`へ解決し、`285A`のplaceholder masterを重複作成しません。既存5文字identifier`285A0`の直接入力も受理します。
- aliasはportfolio登録境界だけに限定し、検索responseは登録済みmaster identifierを返します。公開4文字への短縮はdashboardの表示・入力境界だけで行います。

### 4.5 互換性・非対象

- `/securities/search`、`POST /portfolio`のrequest/response schemaと既存5文字入力を維持します。
- legacy/canonical AI、watchlist、detail、J-Quants同期endpointの契約は変更しません。
- `security_master` primary key、既存参照recordを4文字へ一括変換するmigrationは行いません。
- J-Quants connector全体の4文字canonical化は行いません。
- 検索結果から数量を推測し、ワンクリックで保有登録する機能は追加しません。

### 4.6 受け入れ確認と既知制約

- 銘柄名と`285A`の両方でキオクシアホールディングスを検索できることを確認します。
- UI shellで`保有入力へ`/`詳細を見る`、prefill、scroll、数量focus、非自動保存のfeedbackを確認します。
- `POST /portfolio`で`285A`が既存`285A0`へ紐付き、`285A`のplaceholderを作らないこと、`285A0`直接入力を維持することを確認します。
- master identifier自体とportfolio responseは5文字のまま残り得ます。dashboard検索結果と保有入力は公開`285A`、detail actionとAPIのraw identifierは`285A0`という境界を維持します。

## 5. SC-2026-08-17-04 — legacy stock-review quota・usage・概算額

### 5.1 変更理由

dashboardで5銘柄の軽量scanを少数回試した際、アプリ内日次上限50回へ到達した表示が出ました。現行counterは銘柄数ではなく成功review単位でしたが、fake OpenAIを使うunit testがrepositoryの`data/ai_review_usage.json`を共有し、本物のOpenAI APIを呼ばずcounterを増やしていました。また、1成功reviewとprovider Responses API call、token使用量、月間概算を区別できず、UIの`database`表示もquotaの保存先と誤認し得る状態でした。

### 5.2 quotaとcount定義

- legacy stock-reviewの`OPENAI_DAILY_REQUEST_LIMIT`既定値を50から300へ変更します。
- quota対象の`review_runs`は、銘柄数に関係なく正常完了したtop-level live一括review 1件を1回とします。5銘柄をまとめた1 requestも1回です。
- mock、forced mock、cache hit、`prompt_only`、API key不足、target上限拒否、日次上限拒否、OpenAI error、最終parse失敗は`review_runs`を増やしません。raw output fallbackを含むsuccessは1回です。
- provider usageを取得できたResponses responseは`api_calls`へ別に記録します。primary response、JSON整形repair、後段parseに失敗したresponseを含み得るため、`api_calls > review_runs`になり得ます。
- 日次quotaは`review_runs`だけを使い、provider call数、Web検索数、銘柄数を混ぜません。
- 300回は成功reviewの運用上限で、provider call数または費用のhard capではありません。OpenAI error/最終parse失敗は`review_runs`を消費せず、repair等で1 reviewから複数provider callが生じ得ます。
- このquota/usageはlegacy `/api/ai/stock-review`、`/portfolio/ai-review`、`/api/portfolio/ai-review`の共有serviceだけに適用します。canonical `/api/ai/analyses`は対象外です。

### 5.3 usage v2 ledgerとAPI

- `app/services/ai_usage.py`がgit管理外の`data/ai_review_usage_v2.json`を管理します。
- ledger rootは`version=2`、`timezone=Asia/Tokyo`、`scope=legacy_stock_review`、`pricing_catalog`、`days`を持ちます。
- 日別bucketは`review_runs`、`api_calls`、input/cached input/output/reasoning token、実Web検索call、概算USD、未算定call、pricing versionを持ちます。
- 更新はprocess内`RLock`と、同一directoryのtemporary fileをflush/fsync後に`os.replace`する方式です。
- 旧`data/ai_review_usage.json`はtest汚染の可能性があるため移行しません。`incomplete_pre_v2_history=true`により、v2開始前の回数・金額が当月集計へ含まれないことを明示します。
- `GET /api/ai/stock-review/usage`は`PortfolioAiUsageSummary`としてscope、timezone、daily limit、残数、JST当日・当月集計、pricing provenance、不完全履歴flag、正式請求優先flagを返します。responseは`Cache-Control: no-store`です。
- ledger、usage API、通常logへAPIキー、prompt、質問、回答、銘柄context、provider raw responseを保存または公開しません。

### 5.4 pricingと概算

- pricing versionは`openai-standard-2026-08-17`、as-ofは`2026-08-17`、currencyはUSDです。
- standard USD / 1M tokenは、gpt-5.4=`2.50 / 0.25 cached / 15.00 output`、gpt-5.5=`5.00 / 0.50 / 30.00`、gpt-5.6-terra=`2.00 / 0.20 / 12.00`です。
- gpt-5.4 / gpt-5.5 / gpt-5.6-terraはinput tokensが272,000を超えるとinput/cached inputを2倍、outputを1.5倍にします。
- 実際のWeb検索tool callはUSD 0.01/callを加算します。設定上限値ではなくprovider response outputの実callを数えます。
- reasoning tokenはoutput tokenの内訳として追跡し、価格へ二重加算しません。
- unknown model、token欠損/負値、cached token不整合では推測せず`unpriced_api_calls`へ記録します。
- 概算はprovider usageと公開standard priceによる参考値で、正式な請求額ではありません。Batch / Flex、契約割引、税、価格改定等を保証せず、OpenAI PlatformのUsage Dashboardと請求情報を正本とします。
- sourceはOpenAI Developersのgpt-5.4、gpt-5.5、gpt-5.6-terra model pageとAPI pricing pageです。

### 5.5 dashboard表示

- dashboard初期化時とPortfolio / Watchlist AI review終了時にusage APIを読みます。
- 本日は成功review数/300、残数、OpenAI呼出数、概算を表示し、今月も成功review数、OpenAI呼出数、概算を表示します。
- `unpriced_api_calls`があれば本日・今月の未算定件数をwarning表示します。
- 旧形式counterを移行しておらず、更新前の回数・金額を含まないことを表示します。
- 送信前のheuristicは「今回の事前概算」と表示し、provider token由来の事後概算と区別します。
- `holdings_source=database`等は「対象: 実DB保有銘柄」等へ変換し、quota種別や保存先に見えないようにします。
- usage表示の取得失敗はAI分析結果の成功・失敗と分離します。

### 5.6 cache・test隔離

- legacyのcache hitはOpenAIを呼ばず、review/API countを増やしません。cache contract自体は変更しません。
- unit testはusage/history/cache pathを一時directoryへ隔離し、開発者のrepository local dataを変更しません。
- quota、review/API count分離、JST日/月、pricing/long-context/Web fee、未算定、no-store、UI文言とsource labelを回帰testで固定します。

### 5.7 互換性と既知制約

- canonical `gpt-5.6-terra`、`STANDARD`、`reasoning.effort=medium`、`text.verbosity=medium`、`store=false`、plain output、保存結果分離は変更しません。
- legacy Prompt Registry、mode、Structured Outputs、mock、history、raw fallbackは維持します。
- process内lockは複数process/複数hostの厳密な分散quotaを保証しません。
- provider attemptのatomic reservation、失敗attemptを含むhard call budget、hard cost ceilingは未実装のfollow-upです。
- v2開始前の月間集計は復元せず、概算額は請求上限や請求額を保証しません。

## 6. SC-2026-08-17-03 — canonical AI安全性・保存結果分離・loopback既定・prompt 2026.08.18

### 6.1 変更理由

canonical個別銘柄AIでは、OpenAI Responses Application Stateの保存可否、AI回答生成の成否、ローカルDB保存の成否、保存回答readerの可用性を別の状態として扱う必要がありました。また、保存回答APIに認証・利用者分離がない現状で既定bindが全interface向けであること、DB初期化が複数経路から実行されること、prompt根拠ラベルの表記揺れを予防する必要がありました。

### 6.2 OpenAI requestの安全性

- canonical `OpenAIResponsesClient`は`responses.create()`へ`store=false`を必ず送ります。
- `previous_response_id`、background mode、Web検索、Structured Outputs、cache、mock、fallbackは追加しません。
- `store=false`はResponses APIのApplication State保存を無効化する設定です。HTTP responseの`Cache-Control: no-store`とは別であり、OpenAI API全体のZero Data Retentionを保証しません。abuse monitoring log等は組織のdata control設定に従います。
- model=`gpt-5.6-terra`、preset=`STANDARD`、`reasoning.effort=medium`、`reasoning.mode`未送信、`text.verbosity=medium`は変更しません。
- APIキー、prompt全文、質問、回答本文を通常logへ追加しません。

### 6.3 生成成功と保存結果の分離

- OpenAI生成成功は`status=success`と非空`answer_text`で表し、ローカル保存結果は`persistence_status=saved|failed`、`saved_at`、`persistence_warning`で独立して表します。
- 保存成功はHTTP 200、`persistence_status=saved`、非null`saved_at`、`persistence_warning=null`です。
- 保存失敗も生成が成功していればHTTP 200、`status=success`、非空`answer_text`、`persistence_status=failed`、`saved_at=null`、safeな定型warningを返します。
- 保存失敗時はtransactionをrollbackし、OpenAI APIを再呼び出しません。1ユーザー送信あたりのOpenAI callは最大1回です。
- 内部logにはrequest ID、OpenAI response ID、例外型などの安全な識別情報だけを記録し、質問、回答、prompt全文、APIキー、raw DB例外詳細を記録しません。
- `GET /api/ai/analyses/{request_id}`は保存済みrecordだけを返す現行仕様を維持します。保存失敗requestのGETはnot foundです。
- `/ui/analysis`は保存失敗時にも回答とwarningを表示し、保存済み表示、`saved_at`、reader linkを表示しません。保存成功時だけreader linkを表示します。

### 6.4 起動境界

- `API_HOST`と`scripts/run_api.py --host`の既定値を`127.0.0.1`へ変更し、既定ではローカルPCだけから接続できるようにします。
- LANまたはAndroid端末で確認するときだけ、利用者が明示的に`python scripts/run_api.py --host 0.0.0.0`を指定できます。
- `0.0.0.0`はLAN内の他端末から到達可能です。認証、利用者分離、rate limit、TLSがない現状では信頼できる閉じたnetworkに限定し、Internetへ直接公開しません。
- Android対応や外部公開の前に認証、HTTPS、rate limitを実装する必要があります。
- DB初期化の正本はFastAPI lifespanだけとし、`create_app()`は`init_db()`を呼びません。通常のapp起動1回につき初期化は1回です。
- TestClientはcontext managerでlifespanを起動し、DBを直接使うunit testはfixture側で明示的に準備します。

### 6.5 prompt 2026.08.18

- v2026.08.17 assetはimmutableな履歴として変更しません。
- active prompt versionを`2026.08.18`、compilerを`individual-security-v2`へ更新します。
- asset IDsは`common_os@2026.08.18`、`common_input_rules@2026.08.18-mvp1`、`execution_constraints_no_tools@mvp1`、`individual_comprehensive@2026.08.18`です。
- v2026.08.18 asset bytesはformal labelを持つv2026.08.17と同一で、asset SHA-256も同一です。v18 source titleは「株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）」、SHA-256は`B1C0AF5B2C33D76E4F836A428380237383FB7EAEA8B6FEAFFD9CC82632416D30`で、非送信`assets/v2026_08_18/SOURCE.md`を検証します。
- v2026.08.17原資料のtitle/hashは`revision.base_source`として保持し、v2026.08.17 assetを変更しません。
- v2026.08.18はruntime canonicalizationと旧括弧ラベルのstatic fail-closed検証を追加するreleaseです。
- active runtime contextとcompiled promptの根拠ラベルを`【V】確認済み`、`【E】推定`、`【U】未確認`へ統一します。旧括弧ラベルがactive compiled promptへ混入した場合はOpenAI APIを呼びません。
- prompt provenanceと保存recordはactive prompt version、compiler、asset IDs、source/compiled SHA-256を記録し、prompt全文を公開responseや通常logへ出しません。

### 6.6 互換性と非対象

- legacy `/api/ai/stock-review`、`/portfolio/ai-review`、`/api/portfolio/ai-review`、`portfolio_ai_review.py`、legacy Prompt Registry、legacy mock/cacheは変更しません。
- `PERSISTENCE_ERROR`はschema互換のため残りますが、OpenAI成功後の通常の保存失敗には使用しません。
- 認証、利用者分離、rate limit、HTTPSそのものは今回実装しません。
- 回答一覧、削除、export、保持期限、Web検索、Structured Outputs、background、streamingは追加しません。

### 6.7 受け入れ確認

- fake Responses APIでrequest kwargsの`store=false`、固定model/preset/reasoning/verbosity、`previous_response_id`とbackgroundの非送信を確認します。
- OpenAI成功・保存成功、OpenAI成功・保存失敗、OpenAI失敗を分けて確認します。
- 保存失敗でもHTTP 200と回答本文を返し、OpenAI callが1回、recordが0件、GETがnot found、安全なlogであることを確認します。
- UIは保存成功時だけreader linkを出し、保存失敗時は回答とwarningだけを出すことを確認します。
- app lifespan起動1回につき`init_db()`が1回であることをspyで確認します。
- active prompt version、compiler、asset IDs、正式根拠ラベル、旧括弧ラベル非混入、immutable v2026.08.17を確認します。

### 6.8 既知制約

- loopback既定は同一PC上の無認証アクセスを防ぐものではありません。
- 明示的に`0.0.0.0`へbindした場合、同じLANから保存回答APIへ到達できます。
- `store=false`だけではOpenAI API全体のZero Data Retentionを保証しません。
- 保存失敗した回答は現在画面にだけ表示され、readerで再表示できません。

## 7. SC-2026-08-17-02 — canonical AI回答保存・大型表示・prompt v2026.08.17

### 7.1 変更理由

canonical個別銘柄AIの回答を生成直後の画面だけでなく再表示でき、長文を大きな読み取り専用画面で確認できるようにする必要がありました。同時に、添付prompt sourceの最新版に含まれる銘柄名・コード併記規則を、既存の最小prompt構成を広げず反映します。

### 7.2 変更前

- `POST /api/ai/analyses`の成功回答はbrowserへ表示するだけで、canonical専用SQL recordを持ちませんでした。
- `/ui/analysis`の回答領域だけで表示し、別ウィンドウの大型readerはありませんでした。
- prompt sourceはv2026.08.16でした。

### 7.3 変更後

- 成功したPOSTは、同じ`request_id`で`AiAnalysisRecord`をローカルSQLへ自動保存します。
- 保存対象は質問、回答、銘柄snapshot、model/preset/reasoning設定、OpenAI response ID、prompt traceです。
- 保存commit失敗時はrollbackし、HTTP 500の`PERSISTENCE_ERROR`としてsuccessを返しません。
- `GET /api/ai/analyses/{request_id}`は保存済み成功回答をUUIDで1件取得します。未知recordは`ANALYSIS_NOT_FOUND`です。
- `/ui/analysis`の成功時に`別ウィンドウで大きく表示`を出し、`target="_blank"`と`rel="noopener noreferrer"`で`/ui/analysis/results/{request_id}`を開きます。
- 大型画面は保存回答APIから1件を取得し、質問と回答を`textContent` / `white-space: pre-wrap`で表示します。
- AI送信中は銘柄検索・選択と質問編集をロックし、応答待ちのrequest対象と表示対象を固定します。
- canonical APIはFastAPI validation errorを含め、HTML shellは各routeから`Cache-Control: no-store`を返します。

### 7.4 prompt更新

- sourceを「株判断プロジェクト｜定型プロンプト集 v2026.08.17」へ更新しました。
- 使用範囲は共通OS、必要な共通入力rule、no-tools実行制約、module 3.1だけで、3.2〜3.14やJSON Schemaは追加しません。
- 銘柄の表示・言及を原則「銘柄名（銘柄コード）」とし、共通入力で銘柄名と銘柄コードを分離します。
- model=`gpt-5.6-terra`、preset=`STANDARD`、reasoning effort=`medium`、text verbosity=`medium`、plain`response.output_text`は変更しません。

### 7.5 保存・秘密情報

- ローカルSQL recordは再表示とprompt trace相関の正本です。OpenAI側の保持をアプリ保存の代替にしません。
- APIキー、Authorization header、prompt全文、provider raw response / raw error、stack traceは保存しません。
- prompt traceはrecordへ保存しますが、公開API responseとbrowserへ出しません。
- 一覧、検索、削除、export、共有、保持期限、自動purge、認証・認可は追加しません。

### 7.6 互換性と受け入れ

- legacy stock-review endpoint、UI、mock/cache/Web/Structured Outputs/JSON fallbackは変更しません。
- canonical POSTの既存request fieldとplain-text回答を維持し、成功responseへ`saved_at`だけを追加します。
- POST保存正常/失敗rollback、GET正常/not-found/validation no-store、送信中の入力ロック、別ウィンドウlink、大型画面のloading/error/plain-text表示、v2026.08.17 asset選択を自動testで確認します。
- 実OpenAI確認では従来どおりcompleted status、response ID、非空output textを確認し、その成功recordを同じrequest IDで取得できることを確認します。

### 7.7 既知制約

- 保存recordにaccess controlとretention policyがないため、引き続きtrusted local環境限定です。
- request IDを知る利用者は保存回答を取得できます。Internetへ直接公開しません。
- 保存commitが失敗するとOpenAI利用分は発生済みでもresponseは失敗になります。暗黙retryは行いません。

## 8. SC-2026-08-17-01 — 個別銘柄AI最小縦スライスと定型prompt最小統合

### 8.1 変更理由

旧Portfolio AI経路はmulti-mode、Web検索、Structured Outputs、JSON解析、mock、cache、fallbackを同時に扱います。OpenAI APIとの最小通信経路を単独で切り分け、個別銘柄回答の品質をversioned promptで改善するには、より小さいcanonical経路が必要でした。

### 8.2 変更前

- 要件仕様 v1.1、API仕様 v1.4、画面仕様 v1.6は、主にdashboardのmulti-mode Portfolio AI分析を定義していました。
- `POST /api/ai/stock-review` では、mode別model、Web検索、Structured Outputs、JSON parse救済、mock/cache/historyを扱いました。
- 独立した個別銘柄1件のplain-text endpointと画面は、versioned仕様の正本に未記載でした。

### 8.3 変更後

- canonical endpointとして `POST /api/ai/analyses` を追加しました。
- 独立画面として `GET /ui/analysis` を追加しました。
- 対象はactiveな登録済み個別銘柄1件、入力は自由質問、回答設定は `STANDARD` 固定です。
- OpenAI Responses APIを1回呼び、`response.status=completed`、response ID、trim後に非空の `response.output_text` を満たす場合だけ成功とします。
- 回答はbrowserの `textContent` と `white-space: pre-wrap` でプレーンテキスト表示します。
- 新経路ではmock、cache、fallback、Web検索、Structured Outputs、JSON修復、再AI呼び出し、streaming、backgroundを使用しません。

### 8.4 model・回答設定

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

### 8.5 prompt変更

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

### 8.6 trace・秘密情報

- OpenAI metadataへ保存するのはprompt version、profile、compiler、module、asset ID、source SHA-256、compiled SHA-256だけです。
- prompt全文、質問全文、APIキーはOpenAI metadata、通常ログ、公開FastAPI response、browserへ出しません。
- 公開responseは `request_id` と、取得できた場合の `openai_response_id` を返します。
- 永続audit tableは未実装であり、長期追跡可能性はOpenAI metadataとログの保持期間に依存します。

### 8.7 互換性

- `POST /api/ai/stock-review`、`POST /portfolio/ai-review`、`POST /api/portfolio/ai-review` は変更しません。
- 旧 `app/prompts/stock_analysis/`、multi-mode、Web検索、Structured Outputs、mock、cache、history、raw output fallbackも旧経路に限って維持します。
- 新経路は旧経路のfallbackや設定を共有しません。
- 既存endpointの削除やdeprecationはありません。

### 8.8 非対象

- `LIGHT` / `HIGH` / `PRO` / `MAX`
- model選択UI
- 複数銘柄、市場全体、総合分析
- Web検索、J-Quants等の追加context取得
- Structured Outputs、JSON Schema、JSON修復
- Markdown renderer、構造化card
- mock、cache、fallback、streaming、background、polling
- prompt全14用途moduleの投入
- 旧Portfolio AI経路の削除・再設計

### 8.9 既知制約

- `POST /api/ai/analyses` にはアプリ独自の認証とrate limitがありません。
- `scripts/run_api.py` の既定hostは `0.0.0.0` で、アプリはTLSを提供しません。現状はtrusted local環境限定で、Internetへ直接公開しません。
- OpenAPI自動生成は現時点で実際の404 / 429 / 502 / 503 / 504 response modelを網羅していません。
- prompt manifestやasset構成異常はtyped `AiAnalysisError`ではなく、現状はHTTP 500になり得ます。
- promptへ渡す実データは主に銘柄masterであり、価格、決算、チャート、需給、市場、マクロ、イベント、保有条件は未提供です。そのため回答が `insufficient_data` / `no_trade` 寄りになる場合があります。
- 共通OSの標準出力は、情報が少ない質問では回答を冗長にする場合があります。

### 8.10 受け入れ確認

- compiler、OpenAI client、FastAPI endpoint、UI shellのunit testを維持します。
- 代表質問fixture 10件で、買い判断、決算後、要因分離、モメンタム、需給、イベント、リスク、反証、情報不足、no-tradeを比較できます。
- 実OpenAI確認ではcompleted status、response ID、非空output textを確認します。
- 実browser確認では、銘柄選択、質問入力、loading、成功回答、error非表示、plain-text描画を確認します。

## 9. 直前baseline

| 適用日 | 要件 | API | 画面 | 主な範囲 |
|---|---:|---:|---:|---|
| 2026-08-18 | v1.6 | v1.9 | v2.1 | SC-2026-08-18-01: 銘柄検索から保有入力への導線とJ-Quants code alias |
| 2026-08-17 | v1.5 | v1.8 | v2.0 | SC-2026-08-17-04: legacy stock-review quota・usage・概算額 |
| 2026-08-17 | v1.4 | v1.7 | v1.9 | SC-2026-08-17-03: canonical AI安全性・保存失敗処理・prompt表記正規化 |
| 2026-08-17 | v1.3 | v1.6 | v1.8 | SC-2026-08-17-02: canonical AI回答保存・大型表示・prompt v2026.08.17 |
| 2026-08-17 | v1.2 | v1.5 | v1.7 | SC-2026-08-17-01: canonical個別銘柄AI最小縦スライスと定型prompt最小統合 |

直前baselineの完全な内容は各versioned fileに残します。新baselineはcanonical AI、legacy usage、検索からPortfolio入力への導線を維持したまま、BYOKによる東証/J-Quants上場issueのprivate local full syncと、安全な完全性・provenance・count表示を追加したものです。

## 10. 更新ルール

1. 要件、API、画面のどこが変わるかを特定する。
2. 過去版を保持し、影響するversioned fileの次版を追加する。
3. 変更理由、互換性、非対象、既知制約をこの文書へ追記する。
4. `python scripts/sync_current_files.py --write` を実行する。
5. 各 `current.md` の日付、変更概要、主な内容を手動確認する。
6. `python scripts/sync_current_files.py --check` を実行する。
7. 実装・運用・文書変更を `docs/changelog.md` へ追記する。
