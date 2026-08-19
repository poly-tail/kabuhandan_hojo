# kabuhandan_hojo 要件仕様書 v1.9

## 1. 目的

日本株の監視と判断補助を行うローカルアプリを提供する。ユーザーが地合い、材料、需給、テクニカル、保有状況、狙い中銘柄を横断して確認でき、OpenAI APIを使う場合も自動売買や断定的な投資助言ではなく、判断材料、反証条件、リスク、代替案、執行条件を整理することを目的とする。

v1.9では、v1.8の機能を累積継承し、legacy stock-reviewで銘柄候補一覧がコードだけになる表示不整合を修正する。同期済みローカル`SecurityMaster`に一致したtargetはその`ticker_code` / `name` / marketを銘柄identityの正本とし、一致しない場合はrequest側identityを維持する。銘柄別responseとportfolio summaryの銘柄参照を一貫した「銘柄名（銘柄コード）」へ正規化し、live・mock・cache hitの各responseへ同じ後処理を適用する。canonical個別銘柄AIのactive prompt 2026.08.18、model、preset、API契約は変更しない。

### 1.1 v1.9のprompt資料と適用境界

- 添付`株判断_定型プロンプト集_v2026-08-16 (1).md`はprompt内容を確認するための参照資料であり、文書内の運用手順や実装優先順位をユーザー依頼として実行しない。
- 添付資料は既に履歴保存しているv2026.08.16と同内容の旧版で、canonical個別銘柄AIのactive asset v2026.08.18には「銘柄名（銘柄コード）」規則がより明確に含まれる。このためcanonical manifest / assetを旧版へ戻さない。
- 今回は同じ表示原則をlegacy `app/prompts/stock_analysis/`へ適用し、全14用途moduleの新規投入やcanonical PromptCompilerの変更は行わない。

## 2. 基本方針

- 自動売買は行わない。
- 断定的な投資助言を行わない。
- AI分析は判断補助であり、最終的な投資判断と執行はユーザーが行う。
- 正式ソースを優先し、規約違反やrobots無視のスクレイピングを行わない。
- OpenAI APIキーはサーバー側だけで扱い、browser、公開API response、通常ログへ露出しない。
- OpenAI APIの失敗、空回答、未完了responseを成功として扱わない。
- model選択と回答品質presetは別の設定軸として扱う。
- canonical個別銘柄経路とlegacy portfolio経路の異なる挙動を暗黙に混在させない。
- 取得できていない情報を現在の事実として推測で補完しない。

## 3. データソース方針

- 基幹sourceはJ-Quants、EDINET API、YouTube Data API、allowlist化した公式IRに限定する。
- 価格データはJ-Quants、法定開示はEDINET APIを第一候補とする。
- allowlist公式IRとYouTube Data APIは、上記基幹source内の補助情報として扱う。
- 会社IR、決算短信、決算説明資料、適時開示、取引所、公式統計、企業発表を一次情報として優先する。
- ニュース、SNS、YouTube、個人投資家情報は補助情報として扱う。
- Web検索を使う経路では、取得元、日付、一次情報性、前提差を明示できる形で返す。
- データ欠損時は`未取得`、`未提供`、`【U】`等で明示し、取得済み情報と区別する。
- J-Quantsの完全な上場銘柄一覧は利用者自身の契約・APIキーで取得し、git管理外のローカルDBへだけ保存する。取得結果を公開repositoryへ同梱・再配布しない。
- J-Quants個人版の利用者は、自身のplanと最新の利用規約を確認し、個人の私的利用等の許諾範囲を守る。取得データそのものの第三者配信、または取得データを用いたserviceの第三者提供をこのアプリの標準運用にしない。本repositoryが公開するのはデータとAPIキーを含まないlocal-use codeだけとし、public hostや第三者向け提供には別途適切な契約・許諾を必要とする。
- 銘柄マスターの同期範囲はJ-Quants上場銘柄マスターが返す東証上場issueとし、普通株に加えてETF、REIT、優先株等もprovider responseに含まれる限り除外しない。地方取引所単独銘柄の網羅は保証しない。
- `source_as_of`はproviderが示す情報基準日であり、利用者のJ-Quants planに応じて遅延し得る。アプリ実行時刻またはリアルタイム時点と同一視しない。

canonical個別銘柄経路では、v1.4時点で新たなWeb検索、J-Quants同期、外部市場データ取得を実行しない。利用可能なcontextは、登録済み`security_master`の以下の項目に限定する。

- 銘柄コード
- 銘柄名
- 市場
- 17業種および33業種（登録されている場合）
- 上場日（登録されている場合）

現在価格、価格取得時刻、決算、コンセンサス、チャート、テクニカル、出来高、信用、空売り、指数、セクター相対強弱、為替、金利、マクロ、直近材料、今後のイベント、保有状況、許容損失、希望時間軸は、この経路では未提供情報として扱う。

## 4. 保有・監視・候補銘柄要件

- watchlistの登録、一覧、再利用ができる。
- portfolio holdingの登録、一覧、評価価格更新ができる。
- legacy portfolio経路の狙い中銘柄は、実DBが未整備でもmock candidatesでAI分析UIを検証できる。
- legacy portfolio経路では、実DBの保有銘柄、実DBの監視銘柄、ローカル保存データ、mock dataの順で利用する。
- canonical個別銘柄経路では、登録済みかつactiveな銘柄を1件選択する。
- canonical個別銘柄経路では、未登録またはinactiveな銘柄を別銘柄やmockへfallbackしない。

### 4.1 銘柄検索から保有入力への導線

- `GET /securities/search`は、登録済みmasterを銘柄名、数字コード、英字を含むコードで検索できる。
- 検索候補は同期済み`security_master`だけから返し、候補の名称・市場・業種等を補完するためのJ-Quants外部callを行わない。DB recordが存在するprofile解決でもJ-Quantsを呼ばず、ローカル値を正本とする。
- code、英語名、marketの照合は大文字・小文字を区別しない。結果順はticker完全一致、raw/local code完全一致、ticker prefix、raw/local code prefix、日本語名、英語名、marketの順を優先し、同順位はticker昇順とする。
- search responseの`ticker_code`は登録済みmasterのprimary identifierを維持する。raw/local codeで一致した場合も、優先株等の別issueを4桁普通株へ縮約したり、別recordへ推測変換したりしない。
- dashboardの検索結果は、同じ銘柄について「保有入力へ」と「詳細を見る」を別actionとして表示する。
- 「保有入力へ」は検索responseのraw `ticker_code`を保持したまま、英字を含む5文字末尾`0`形式では公開4文字コードへ変換してportfolio入力フォームへ反映し、フォームへscrollして数量欄へfocusするだけとする。検索またはprefillだけで`POST /portfolio`を呼ばない。
- 英字を含む5文字末尾`0`形式の検索結果は、利用者向けcode表示も公開4文字へ変換する。詳細画面actionのdata属性とURLには、存在するmasterを正確に参照できるよう検索responseのraw `ticker_code`を維持する。
- 保有登録では数量を必須とし、平均取得単価とメモは任意とする。保存は利用者が「保有を保存」を明示的に押した場合だけ実行する。
- `POST /portfolio`は、入力identifierと完全一致するactive/inactiveを問わない既存`security_master.ticker_code`を最優先する。
- 完全一致がなく、入力が4文字の数字・英字コードである場合だけ、`<入力コード>0`と一致する`ticker_code`または`local_code`を候補にする。銘柄master上で候補が一意な場合だけ、その既存`ticker_code`へ解決する。
- 例として、公開コード`285A`を送信し、既存J-Quants raw masterが`ticker_code=285A0`または`local_code=285A0`として存在する場合、保有recordは既存master identifier`285A0`へ紐付け、`285A`のplaceholder masterを重複作成しない。
- 既存の5文字raw identifierを直接送る入力も引き続き受理する。候補が0件または複数件の場合は、別銘柄へ推測解決しない。

### 4.2 東証/J-Quants上場銘柄マスター同期

- dashboardの`東証全銘柄を同期`は`POST /securities/master/sync?require_jquants=true`を呼び、J-Quants取得に失敗した場合や完全な現行snapshotを確認できない場合は成功表示しない。
- `GET /securities/master/status`は、最新の完全な現行J-Quants同期について`source_scope=tse_listed_issues`、`source_as_of`、`synced_at`、`complete`、ローカル有効件数、J-Quants由来有効件数を返す。APIキーその他のcredentialを返さない。
- 現行snapshotは、本番設定で取得件数4,000件以上かつ全recordの非nullな`source_as_of`が1日へ一致する場合だけ完全候補とする。さらに、同期前の`master_source=jquants`有効件数と、旧importer由来と判定した支配的legacy cohort件数を合算した基準件数に対して、取得件数が5%を超えて縮小する場合は完全候補でも拒否する。不完全・空・情報基準日不整合・過大縮小の場合は、既存masterへ変更を適用しない。小さい閾値の注入はunit testだけに限定する。
- 完全な現行snapshotだけが、今回の取得集合に存在しない`master_source=jquants`の既存recordをinactiveへ変更できる。`manual`、`local_seed`、所有元未確定の`legacy` recordは自動削除・無効化しない。
- `target_date`を指定したhistorical同期は、現行snapshotの有効状態を上書きせず、現行masterを欠落扱いで無効化せず、status画面の「最新の完全な現行同期」を置き換えない。historicalの`complete=true`には、完全性閾値・単一基準日に加えて`source_as_of=target_date`を必要とする。
- providerの`Date`は`source_as_of`へ保存し、明示的な`ListingDate` / `ListedDate`だけを`listed_date`として扱う。
- 5桁数字コードの末尾`0`は通常の4桁識別子へ正規化する一方、末尾が`0`でない5桁数字コードは優先株等の別issueとして保持する。英数字identifierはraw codeを保持する。正規化後に異なるraw provider codeが衝突する場合はsilent overwriteせず同期全体を失敗させる。
- 過去の正規化誤りにより、既存recordの`local_code`が今回取得の別issue identifierと一致するordinary/preferred等のidentity split候補では、`security_master.ticker_code`を参照する他tableの外部キーをDB metadataから確認する。参照recordが1件でもあれば自動rename・merge・上書きを行わず、同期全体をDB変更前に失敗させる。参照がない候補だけを通常upsertで修復できる。
- J-Quants masterのpaginationは全pageを取得し、pagination keyの循環と上限超過をfail closedとする。HTTP 429は`Retry-After`を尊重した有限回retryだけを行い、無限retryしない。
- 同期結果は`fetched_count`、`inserted_count`、`updated_count`、`reactivated_count`、`deactivated_count`、`active_total`、`jquants_active_count`を区別する。`upserted_count`は`inserted_count + updated_count`とし、seed件数とJ-Quants件数を重複加算しない。
- 同期runはcredentialや全銘柄payloadではなく、sync ID、source/scope、基準日、実行時刻、完全性、current/historical区分、集計件数だけを保存する。
- `data/security_master_jp.csv`の36件はbundled search seedに限定する。seed同期は存在しないrecordのinsertだけを行い、J-Quants由来の名称、市場、active状態、provenanceを上書きしない。検索操作そのものはseed同期を暗黙実行しない。
- 旧importerがproviderのsnapshot `Date`を`listed_date`へ格納した不具合は、`master_source=legacy`、active、同一の非null`listed_date`を持つ最頻cohortが本番完全性floorの4,000件以上の場合にだけ「支配的legacy snapshot cohort」と判定する。このcohortを検出した通常のUI/API current同期は、完全な取得結果であってもDB変更前にfail closedとし、CLI `scripts/sync_security_master.py --adopt-legacy`を案内する。
- `--adopt-legacy`はcurrent snapshotだけで利用でき、`--as-of`との同時指定を拒否する。明示採用では当該支配的cohortだけをJ-Quants所有としてreconcileし、無関係なmanual/local-seed/別listed-dateのlegacy recordを推測採用しない。
- connectorのtimeout、network error、invalid JSON、HTTP errorは、API/browser/CLIへprovider response body、transport例外detail、APIキーを露出しない安全な`ConnectorError`へ分類する。HTTP errorはstatus codeだけを公開可能情報とする。
- `scripts/sync_security_master.py --dry-run`はJ-Quants master同期transactionをrollbackするが、その前に`init_db()`が実行される。schema作成・migrationと、不足しているbundled 36件seedのbootstrapは先に永続化され得るため、dry-runをDB全体が無変更となるread-only modeとして扱わない。

## 5. AI経路の責務分離

v1.4では、次の2経路を独立して扱う。

| 項目 | canonical個別銘柄経路 | legacy portfolio / multi-mode経路 |
|---|---|---|
| 主endpoint | `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}` | `POST /api/ai/stock-review`および既存互換endpoint |
| 主UI | `GET /ui/analysis`、`GET /ui/analysis/results/{request_id}` | dashboardのPortfolio AI分析パネル |
| 対象 | 登録済み個別銘柄1件 | 保有、監視、候補、選択銘柄、portfolio全体 |
| preset / mode | `STANDARD`のみ | `scanner` / `analyst` / `judge` / `critical` / `prompt_only` |
| prompt管理 | `IndividualSecurityPromptCompiler`とversioned Markdown asset | 既存Prompt Registry / Prompt Builder |
| OpenAI出力 | `response.output_text`のプレーンテキスト | mode別Structured Outputsまたは既存parse経路 |
| Web検索 | OFF、tool未使用 | modeと設定に応じて既存機能を使用 |
| mock / cache / fallback | 使用しない | legacy専用。raw output救済は失敗statusのまま表示・履歴保存できるがcacheしない |

canonical個別銘柄経路とlegacy stock-review経路は引き続き分離する。v1.5のusage ledger、日次quota、概算額、dashboard表示はlegacy endpointだけに適用し、canonical経路のrequest、model、preset、保存、error契約へ適用しない。legacy endpoint、mode、Prompt Registry、mock、cache、historyは維持し、legacy parse処理だけを第13章の契約へ更新する。

## 6. canonical個別銘柄AI最小縦スライス

### 6.1 機能フロー

次の単一路を成立させる。

```text
登録済み個別銘柄1件
+
自由質問
+
STANDARD
↓
FastAPI
↓
OpenAI Responses API
↓
response.output_text
↓
browserへプレーンテキスト表示
```

route、service、OpenAI client、response validation、UI表示を分離し、OpenAI APIへは1分析につき1回だけrequestする。

### 6.2 request要件

`POST /api/ai/analyses`は次を受け取る。

- `security_code`: 入力時4〜10文字の登録銘柄コード。前後空白は除去し、空白だけの値は拒否する。
- `question`: 入力時1〜4,000文字の自由質問。前後空白を除去し、空白だけの質問は拒否する。
- `preset`: v1.4では`STANDARD`のみ。未指定時も`STANDARD`とする。

未知fieldは受け付けず、未対応presetはvalidation errorとする。

### 6.3 response要件

成功時は次を返す。

- `request_id`
- `status = success`
- 非空の`answer_text`
- `error = null`
- 銘柄コード、銘柄名、市場からなる`security` snapshot
- `openai_response_id`
- `persistence_status = saved | failed`
- 保存成功時だけ非nullとなる`saved_at`
- 保存失敗時だけユーザー向け説明を持つ`persistence_warning`

AI回答生成に成功した場合、ローカルSQL保存に失敗してもHTTP 200、`status = success`、非空`answer_text`を返す。生成失敗と保存失敗を同じstatusで表現しない。

失敗時は次を返す。

- `request_id`
- `status = error`
- `answer_text = null`
- 公開可能なcodeと簡潔なmessageからなる`error`
- 取得できている場合だけ`openai_response_id`
- `persistence_status = null`、`saved_at = null`、`persistence_warning = null`

prompt本文、ユーザー質問、APIキー、内部stack trace、OpenAI SDK例外本文は公開responseへ含めない。

### 6.4 service要件

- `security_master`から指定銘柄を解決する。
- 未登録またはinactiveな銘柄ではOpenAI APIを呼ばない。
- 銘柄contextと質問を`IndividualSecurityPromptCompiler`へ渡す。
- compilerが返す`instructions`、`input`、trace metadataを独立OpenAI clientへ渡す。
- OpenAIの検証済み`output_text`だけを`answer_text`としてrouteへ返す。

### 6.5 成功回答の永続保存要件

- `POST /api/ai/analyses`は、OpenAI response ID、`completed` status、非空`output_text`を検証した後、その成功結果をローカルSQLの`AiAnalysisRecord`として自動保存する。
- 保存keyは公開responseの`request_id`と同じUUIDとする。
- 保存対象は、質問、回答本文、銘柄snapshot、preset、model、reasoning / verbosity設定、OpenAI response ID、prompt version / profile / module / asset ID / hashからなるprompt trace、および生成日時とする。
- APIキー、Authorization header、prompt全文、provider raw response、provider raw error、内部stack traceは保存しない。
- 保存に失敗した場合はtransactionをrollbackするが、生成済み回答を捨てず、HTTP 200、`status=success`、`persistence_status=failed`、`saved_at=null`、安全な`persistence_warning`を返す。
- 保存失敗を理由にOpenAI APIを再呼び出さず、1回のユーザー送信に対するOpenAI callは最大1回とする。
- 保存成功時は`persistence_status=saved`、`saved_at`を設定し、`persistence_warning=null`とする。
- 保存失敗時はrecordが存在しないため、同じrequest IDの詳細GETはnot foundのままとする。
- OpenAI側のResponses Application State保存を`store=false`で無効化する。これはOpenAI API全体のZero Data Retentionを保証せず、組織のdata control設定やabuse monitoring logの扱いとは別である。
- OpenAI API側の保存をアプリ履歴の代替とせず、保存に成功したローカルSQL recordだけを再表示の正本とする。

### 6.6 保存回答の1件取得要件

- `GET /api/ai/analyses/{request_id}`はUUIDで保存済み成功回答を1件取得する。
- 存在しないrequest IDはsuccessや空回答へfallbackせず、not foundとして扱う。
- 回答一覧、検索、削除、export、保持期限管理は提供しない。
- canonical AIのPOST / GET responseには、FastAPIがhandler前に返すvalidation errorを含めて`Cache-Control: no-store`を付与する。

## 7. OpenAI APIと回答preset要件

canonical個別銘柄経路では、次を固定する。

```text
API: OpenAI Responses API
model: gpt-5.6-terra
preset: STANDARD
reasoning.effort: medium
reasoning.mode: 未送信
text.verbosity: medium
timeout: 60秒
```

- modelは回答preset定義へ含めず、runtime設定として分離する。
- `STANDARD`以外へ暗黙変換しない。
- 指定modelを利用できない場合、別model、mock、cacheへfallbackしない。
- `temperature`を主要UI制御項目にしない。
- Web search tool、その他tool、Structured Outputs、JSON Schema、streaming、backgroundをrequestへ追加しない。
- `store=false`を必ず明示し、`previous_response_id`を送信しない。
- `store=false`はResponses Application State保存を無効化する設定であり、Zero Data Retention全体の保証として表示・説明しない。
- SDK側の自動retryは使用しない。

## 8. IndividualSecurityPromptCompiler要件

### 8.1 asset管理

canonical個別銘柄経路のpromptは、PythonコードやUI内の巨大文字列として保持せず、`app/prompts/individual_security/`配下のversioned Markdown assetとmanifestで管理する。

v1.4で使用するactive prompt versionは`2026.08.18`、compilerは`individual-security-v2`とする。source titleは「株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）」、source SHA-256は`B1C0AF5B2C33D76E4F836A428380237383FB7EAEA8B6FEAFFD9CC82632416D30`とし、非送信の`assets/v2026_08_18/SOURCE.md`で検証する。v2026.08.17原資料のtitle/hashは`revision.base_source`として保持する。v2026.08.18はruntime canonicalizationと旧括弧ラベルのfail-closed検証を加えたreleaseであり、v2026.08.17 assetは履歴として変更しない。次のassetだけを組み込む。

1. 「1. 株判断共通OS」
2. 「2. 共通入力テンプレート」の個別銘柄MVPに必要な部分
3. Web検索・外部tool・追加市場データを利用できないことを明示するアプリ実行制約
4. 「3.1 総合的な個別銘柄分析」

用途module 3.2〜3.14、アプリ向け構造化出力schema、人間向けの重複出力templateは、この経路へ読み込まない。

原資料v2026.08.17の命名規則をactive prompt 2026.08.18へ継承し、銘柄の表示・言及は原則として「銘柄名（銘柄コード）」とする。外国銘柄を将来扱う場合は「会社名（ticker）」とする。共通入力では銘柄名と銘柄コードを別項目として扱うが、現行MVPのrequest fieldは互換性のため`security_code`を維持し、銘柄名は解決済み`security_master`から渡す。根拠ラベルは`【V】確認済み`、`【E】推定`、`【U】未確認`だけを正式表記とし、active compiled promptに旧括弧表記が含まれる場合はOpenAI APIを呼ばずfail closedとする。

### 8.2 manifestと整合性

manifestでは最低限次を追跡する。

- prompt version
- prompt profile ID
- compiler version
- source titleとsource SHA-256
- compile order
- asset ID、path、source section、asset SHA-256
- 使用module IDとmodule名

compilerはmanifest、compile order、module 3.1、asset path、UTF-8、非空内容、asset SHA-256を検証する。manifest不正、asset欠落、hash不一致ではOpenAI API呼び出しを行わず、旧minimal promptや別moduleへfallbackしない。

assetをPython packageへ含め、source tree実行とpackage実行で同じprompt bundleを読めるようにする。

### 8.3 合成順序

静的`instructions`は次の順で合成する。

1. 共通OS
2. 共通入力ルール
3. Web・外部市場データなしの実行制約
4. 用途module 3.1「総合的な個別銘柄分析」

実行時`input`は次の順で合成する。

1. `security_master`由来の銘柄context
2. 未提供contextの明示
3. ユーザー自由質問

質問は静的`instructions`へ混入させず、JSON文字列化した実行時dataとして区切る。

### 8.4 provenance

各compile結果で次を生成する。

- prompt version
- prompt profile ID
- compiler version
- module ID、module名
- 使用asset ID一覧
- source SHA-256
- compiled prompt SHA-256

これらの非機密識別子とhashをOpenAI Responses requestの`metadata`へ付与し、`openai_response_id`と関連付けられるようにする。prompt本文とユーザー質問はmetadataへ含めない。公開FastAPI responseとbrowserへprompt provenanceを追加しない。通常ログへはprompt本文、質問、秘密情報を出さず、安全な識別子とhashだけを記録できる。

## 9. 情報不足と分析品質要件

- 個別材料、fundamentals、株価momentum、technical、需給、信用状況、sector、市場全体、地合い、金利、為替、macro、決算、直近・今後のevent、市場の織り込み、強気・基準・弱気scenario、risk、反証条件、no-tradeを必要に応じて検討する。
- 全項目を埋めるために未提供の事実や数値を創作しない。
- 重要主張は、確認済み`【V】`、推定`【E】`、未確認`【U】`を区別する。
- `security_master`に存在する銘柄属性と、価格・市場・決算等の時事dataを混同しない。
- 根拠不足時は無理に買い・売りを断定せず、`insufficient_data`または`no_trade`を選択肢に含める。
- 「良い会社か」と「現在価格で買う価値があるか」、「良い材料か」と「株価が上がる材料か」を分離する。
- 短期、中期、中長期、長期を区別し、主因、補正項、反証条件、撤退条件、再評価条件を示す。
- 現在価格や最新dataがない場合、具体的な価格水準や現在の市場状態を確認済み事実として断定しない。

## 10. response検証とerror要件

OpenAI clientは次を検証する。

- OpenAI response IDが存在する。
- `response.status`が`completed`である。
- trim後の`response.output_text`が非空である。

最低限、次のOpenAI error codeを区別する。

- `AUTHENTICATION_ERROR`
- `MODEL_UNAVAILABLE`
- `INVALID_API_PARAMETERS`
- `RATE_LIMITED`
- `TIMEOUT`
- `NETWORK_ERROR`
- `EMPTY_RESPONSE`
- `UNKNOWN_OPENAI_ERROR`

アプリ固有errorとして、少なくとも次を区別する。

- `SECURITY_NOT_FOUND`
- `DATABASE_UNAVAILABLE`
- `PERSISTENCE_ERROR`（schema互換のため残すが、OpenAI成功後の通常の保存失敗には使用しない）

OpenAI失敗、timeout、未完了response、空回答をsuccessに変換しない。raw response表示、JSON修復、parse失敗時の再AI呼び出しも行わない。ユーザー向けmessageと開発用診断情報を分離し、APIキーや秘密情報をどちらにも含めない。

## 11. canonical最小AI画面要件

`GET /ui/analysis`はlegacy dashboardの巨大AI UIから独立した最小画面とし、次を備える。

- 銘柄コードまたは銘柄名による登録銘柄検索
- 個別銘柄1件の選択状態
- 自由質問textarea
- `STANDARD`で送信するbutton
- 送信中のloading表示
- 送信中の銘柄検索・銘柄選択・質問編集のロック
- 簡潔なerror表示
- 回答本文表示
- request IDとOpenAI response IDの診断表示
- 保存結果のwarning表示
- `persistence_status=saved`の場合だけ表示する`別ウィンドウで大きく表示`の導線

保存失敗でも生成済み回答本文を表示し、保存済み表示、`saved_at`、大型表示導線は表示しない。回答本文は`textContent`と`white-space: pre-wrap`によるプレーンテキスト表示とする。成功導線は保存済みrequest IDに対応する`GET /ui/analysis/results/{request_id}`を`target="_blank"`かつ`rel="noopener"`で開く。大型回答画面も`GET /api/ai/analyses/{request_id}`から保存済み回答を取得し、同じプレーンテキスト規則で表示する。Markdown renderer、HTML挿入、構造化cardを導入しない。browserからOpenAI APIを直接呼ばず、APIキーやprompt本文をbrowserへ送らない。

## 12. testと評価要件

canonical個別銘柄経路では、少なくとも次をunit testで固定する。

- PromptCompilerが共通OSを読み込む。
- PromptCompilerが用途module 3.1を読み込む。
- 銘柄contextと自由質問が実行時inputへ入る。
- 用途module 3.2〜3.14とJSON Schema指示が混入しない。
- prompt version、asset ID、module ID、hashを取得できる。
- trace metadataへprompt本文と質問が入らない。
- Web検索と外部toolを利用できない制約が入る。
- prompt assetの合成順序を維持する。
- OpenAI clientの正常系、空回答、未完了status、timeout、SDK例外分類が動作する。
- FastAPI endpointの正常系、OpenAI error、未知銘柄、未対応presetが動作する。
- 最小UIが銘柄選択、質問、`STANDARD`、loading、error、プレーンテキスト回答表示を持つ。
- OpenAI成功・保存成功では`persistence_status=saved`と`saved_at`を返す。
- OpenAI成功・保存失敗ではrollback後もHTTP 200、`status=success`、非空`answer_text`、`persistence_status=failed`、安全なwarningを返し、OpenAIを再呼び出さない。
- `GET /api/ai/analyses/{request_id}`が保存回答を1件返し、未知IDをnot foundにする。
- 成功時の別ウィンドウ導線が`target="_blank"`と`rel="noopener"`を持ち、大型回答画面が保存回答をプレーンテキスト表示する。
- canonical POST / GET responseに、validation errorを含めて`Cache-Control: no-store`が付く。

人間によるbefore / after比較用に、次の観点を網羅する5〜10件のversioned fixtureを保持する。

- 買い判断
- 決算後判断
- 市場要因と個別要因の分離
- momentum
- 需給
- event
- risk
- 反証条件
- 情報不足
- no-trade

評価dimensionは最低限、観点の広さ、反証条件、情報不足の扱い、冗長性とする。v1.4では投資判断の正しさを自動採点しない。

## 13. legacy portfolio / multi-mode AI要件

この章の要件はlegacy portfolio経路だけに適用し、canonical個別銘柄経路へ暗黙適用しない。

### 13.1 対象とPrompt Registry

legacy OpenAI API経路は次を扱う。

- 保有銘柄の一括分析
- 狙い中銘柄の一括分析
- 個別または少数銘柄の詳細分析
- portfolio全体の買い売り判断
- 重要局面分析
- ChatGPT手動投入用prompt生成

既存Prompt Registry / Prompt Builderは次の責務を分離する。

- `basePolicy`
- `analysisSections`
- `modeProfiles`
- `outputSchemas`
- `promptBuilder`
- `costControl`
- `webSearchPolicy`

ユーザー指定のlegacy株式分析prompt全文は`app/prompts/stock_analysis/user_stock_analysis_prompt_full.py`の`USER_STOCK_ANALYSIS_PROMPT_FULL`に保持する。`prompt_only`は全文を使い、API実行modeはmode profileに応じて必要章を選択・圧縮する。入力にない項目は`未入力`と明示する。

### 13.2 legacy mode

| mode | 目的 | Web検索 | 出力方針 |
|---|---|---|---|
| `scanner` | 保有・監視・候補銘柄を軽量分類する | OFF可 | 銘柄ごとに短く分類し、詳細分析や全体判断が必要か返す |
| `analyst` | 個別銘柄を詳細分析する | 原則ON | 市況、テーマ、fundamentals、需給、technical、執行案、反証条件を返す |
| `judge` | 複数銘柄とportfolioを横比較する | 原則ON | 買い候補、売り候補、減らす候補、資金配分、集中riskを返す |
| `critical` | 決算跨ぎ、大型position、急騰急落等を分析する | 強く推奨 | 強気・中立・弱気、期待値、position size、event跨ぎ、辛口checkを返す |
| `prompt_only` | ChatGPTへ手動copyするpromptを生成する | API検索なし | 全文promptとアプリ側入力JSONを返す |

### 13.3 legacy Web検索

- `analyst`、`judge`、`critical`は`include_web_search`未指定時にONを既定とする。
- `scanner`はWeb検索OFFでも実行できる。
- Web検索OFF時はwarningsに「最新Web確認なし」を入れ、重要主張は`【U】`または`【E】`として扱う。
- `prompt_only`はOpenAI API検索を行わず、生成prompt内で手動投入先にWeb確認を依頼する。
- `max_web_search_calls`と`OPENAI_MAX_WEB_SEARCH_CALLS`の小さい方を実効上限にする。

### 13.4 legacy Structured Outputs / JSON

- mode別JSON Schemaを使い、schemaが列挙するstock / portfolio summary fieldをPydantic response modelのfield以内へ収める。
- Structured Outputsのtop-level、`portfolio_summary`、各`stocks[]`では`additionalProperties=false`とし、未定義fieldを生成契約へ許可しない。
- providerが返すroot objectはrequest modeのJSON Schemaにあるfieldだけを受理する。`status`、`error`、`cache_hit`、`parse_failure_kind`等のservice-owned fieldをprovider出力から受理せず、含まれていれば`schema_validation`とする。
- `scanner`のstock schemaは軽量スキャンに必要な30項目未満へ縮小し、詳細分析用fieldを要求しない。`judgement`は`hold`、`buy_more_candidate`、`take_profit_candidate`、`reduce_risk`、`watch`、`avoid_new_buy`、`urgent_review`のenumとする。
- valid JSONのlegacy alias `portfolio_summary.concentration_comment`は`concentration_risk`へ、`portfolio_summary.summary_view`は`overall_view`へ正規化してaliasを除去する。canonical fieldが既に非空ならcanonical値を優先し、aliasで上書きしない。互換aliasが存在する場合はstringだけを許可し、配列・object・数値等は`schema_validation`とする。
- free-textのlegacy `judgement`は既知codeを優先し、`judgement_label`と本文の安全なkeyword対応でcanonical codeへ正規化する。対応不能時だけ`watch`とする。
- parse失敗は`parse_failure_kind`で`json_syntax`、`root_shape`、`schema_validation`へ分類する。valid JSON配列は内部objectを抽出せず`root_shape`とする。`stocks`の非object要素、存在する`judgement`の非string値、互換aliasの非string値、必須field・Pydantic不一致は`schema_validation`とし、`json_syntax`と表示しない。
- 長い不正応答は、Web検索なしのJSON整形retryで1回だけ救済できる。retryのprovider callはusageへ別に記録する。
- JSON整形retryにも失敗し、生応答を表示可能な場合はservice自身のparse経路だけがraw fallback状態を設定し、`status=json_parse_failed`、`error.code=json_parse_failed`、非空`raw_model_output`を返す。provider rootのstatus等に依存してfallback判定を行わない。このresponseは履歴へ保存できるが、分析成功とは扱わない。
- parse失敗時もlegacy UIを壊さず、`raw_model_output`、warning、失敗分類を保持する。validation warningは正常に構造化できたresponseの`warnings`へ出す。
- 銘柄別card、portfolio総合判断、執行案、反証条件、辛口checkをUI表示しやすいJSONで返す。

このfallback、alias正規化、JSON整形retryはcanonical個別銘柄経路では禁止する。

### 13.4.1 legacy銘柄identityと表示正規化

- legacy promptのBase Policy、full prompt、Output Policyは、Input JSONの`ticker`と`name`を正確に使い、銘柄を原則「銘柄名（銘柄コード）」で表示するよう要求する。コードだけ、名称だけ、入力にない銘柄名の推測を禁止する。
- `stocks[].ticker`はInput JSONのticker、`stocks[].name`はInput JSONのnameを正確に転記する生成契約とする。銘柄名をcodeで代用しない。
- `portfolio_summary.buy_candidates`、`sell_or_reduce_candidates`、`hold_priority`、`non_monitoring_reduce_candidates`、`core_position_candidates`、`exit_or_rotate_candidates`は`list[str]`を維持し、各要素を「銘柄名（銘柄コード）」の人間向け参照として返す。
- serviceはOpenAI出力を信頼して名称を確定せず、解決済みholdings / candidatesのidentityを正本として`stocks[].name`と上記6一覧を再照合する。コードだけの値、誤った名称付きcode、名称だけの値を解決できる場合は正本へ直す。
- requestにplaceholder名称またはlocal aliasがありsessionを利用できる場合は、同期済みactive `SecurityMaster`だけでcanonicalな`ticker_code`、銘柄名、市場を補完する。たとえば`local_code=285A0` / `ticker_code=285A`ならpromptとsnapshotは`285A`、`local_code=72030` / `ticker_code=7203`なら`7203`になる。候補表示のためにJ-Quantsその他のproviderへ追加callせず、DB primary keyや`local_code`を変更しない。
- canonical tickerへ揃えた後に重複targetを除き、同じ銘柄がholdingsとcandidatesの両方にあればholdingsを優先する。
- 英字4文字codeをJ-Quants raw形式が末尾`0`付きで保持する場合、人間向けsummaryとlegacy stock cardでは公開4文字へ変換する。例:`285A0`またはcanonical `285A`はsummaryで`キオクシアホールディングス（285A）`、card codeで`285A`と表示する。numeric 5文字code等を表示関数だけで一律短縮しない。
- 正本名称を解決できないコードはコードだけに戻さず`名称未登録（code）`とする。自由文のaction plan等は銘柄参照専用listではないため機械置換しない。
- 同じ正規化をlive response、local mock response、既存cache hitに適用する。cache hitのためにOpenAIを再呼び出さない。
- scannerは個別quick scanに加えてsection 8「建玉・ポートフォリオ影響」を含め、summary候補を銘柄名付きで返せる生成contextを持つ。全14用途moduleをscannerへ投入しない。

### 13.5 legacy UI

dashboardのPortfolio AI分析パネルでは次を選べる。

- 軽量scan
- 個別詳細分析
- 全体売買判断
- 重要局面分析
- ChatGPT投入用prompt生成

対象は保有銘柄、狙い中銘柄、監視銘柄、選択銘柄、テスト用仮銘柄から選べる。prompt入力欄が空でもPrompt Builder templateを適用し、高cost modeやWeb検索ONでは実行前に確認できる。warnings、sources、銘柄別card、portfolio総合判断、執行案、反証条件、辛口check、履歴・前回結果を表示する。`status=json_parse_failed`は成功色を使わず赤いerror cardとし、`schema_validation`は「JSON項目形式エラー」、`root_shape`は「JSONルート形式エラー」、`json_syntax`は「JSON構文エラー」と区別する。表示可能な`raw_model_output`は同じerror card内で確認できる。利用量panelには本日の`review_runs / daily_limit`、残数、本日概算、今月の`review_runs`と概算、未算定API call、v2開始前履歴が不完全である旨を表示する。

### 13.6 legacy mock / cache / history

- mock holdingsとmock candidatesを用意し、legacy UIを実DBが空でも検証できる。
- `mock_response=true`はOpenAI APIを呼ばず固定応答を返す。
- `target=mock`、`use_mock_holdings=true`、legacy DB未登録によるmock fallbackではOpenAI APIを呼ばない。
- 正常なlegacy AI分析結果はローカルJSON履歴と同一入力cacheに保存できる。
- `status=json_parse_failed`のraw output救済responseは`save_result=true`なら調査用にローカルJSON履歴へ保存できるが、cacheへ新規保存しない。既存cacheに同statusまたは非空`raw_model_output`を持つrecordがあってもcache hitとして返さない。

これらをcanonical個別銘柄経路へ接続しない。

### 13.7 legacy quota・usage・概算額

- `OPENAI_DAILY_REQUEST_LIMIT`の既定値は`300`とする。このquotaはlegacy stock-reviewの`review_runs`へだけ適用し、canonical `POST /api/ai/analyses`へ適用しない。
- `review_runs`は、銘柄数に関係なく、liveなtop-level一括reviewが成功したときに1増える。5銘柄を1 requestで分析した場合も1回である。
- mock、forced mock、cache hit、`prompt_only`、API key不足、target上限拒否、日次上限拒否、OpenAI error、最終parse失敗、`status=json_parse_failed`のraw output救済responseは`review_runs`を増やさない。
- `api_calls`はusageを取得できたOpenAI Responses provider responseの数を表し、`review_runs`とは別に記録する。JSON整形repairや、provider response取得後のparse失敗により`api_calls > review_runs`になり得る。
- 日次quotaの判定は`review_runs`を使う。`api_calls`、銘柄数、Web検索call数をquota回数へ混ぜない。
- この300回は成功したtop-level reviewの運用上限であり、provider API call数または費用のhard capではない。OpenAI errorと最終parse失敗は`review_runs`を消費せず、repair等で成功review 1件から複数provider callが生じ得る。
- `GET /api/ai/stock-review/usage`は、scope、timezone、daily limit、残数、JST当日・当月のreview/API/token/Web検索/概算額/未算定call、pricing provenanceを返す。
- v2 ledgerの正本はgit管理外の`data/ai_review_usage_v2.json`とする。version、timezone、scope、pricing catalog、JST日別bucketを保持し、通常の更新はprocess内lockと一時fileからのatomic replaceで行う。
- 旧`data/ai_review_usage.json`はtest実行により汚染され得るためv2へ移行しない。v2集計開始前の回数・金額は完全ではなく、API/UIで`incomplete_pre_v2_history=true`として明示する。
- ledger、usage API、通常logへAPIキー、prompt全文、自由質問、回答本文、銘柄context、provider raw responseを保存または公開しない。
- 概算額はproviderが返したinput、cached input、output tokenと実際のWeb検索tool call数を、versioned pricing catalogへ適用して算定する。reasoning tokenはoutput tokenの内訳であるため二重加算しない。
- unknown model、token欠損、cached token不整合等では価格を推測せず、該当件数を`unpriced_api_calls`へ記録する。
- 金額はUSDの参考概算であり、割引、batch/flex、契約条件、税、将来の価格変更等を完全には反映しない。OpenAI Platformの請求/Usage Dashboardを正本とする。
- pricing catalogは`openai-standard-2026-08-17`、pricing as-ofは`2026-08-17`とし、model別rateと公式source URLをAPIへ含める。
- unit testはusage/history/cache pathを一時directoryへ隔離し、開発者の`data/`配下を増加・上書きしない。

## 14. 非機能・security要件

- ローカルで起動できる。
- mock modeとlive modeを切り替えられる。
- live modeの通常UIではmock補完を行わない。
- canonical個別銘柄経路はlive modeと利用可能な銘柄DBを必要とする。
- `.env`はgit管理せず、`.env.example`だけを設定例として管理する。
- API responseやerror表示にAPIキー、内部stack trace、秘密情報を含めない。
- prompt全文と自由質問を通常ログへ出さない。
- canonical成功回答はローカルSQLへ保存を試みるが、APIキー、prompt全文、provider raw responseは保存しない。
- `create_app()`はDB初期化を行わず、通常起動時の`init_db()`はFastAPI lifespanから1回だけ呼ぶ。TestClientはcontext managerでlifespanを起動し、DBを直接使うunit testはfixtureで明示的に初期化する。
- SQLite / PostgreSQLのどちらでも同じ初期化責務とし、mock / live modeの既存境界を維持する。
- prompt assetはUTF-8でversion管理し、package buildにも含める。
- UIはOpenAI APIへ直接接続しない。
- usage ledgerはprompt、質問、回答、APIキーを持たず、集計metadataだけを保存する。
- usage UIの取得失敗とAI分析自体の成功・失敗を混同しない。
- 通信失敗とUI表示失敗を混同しない。

## 15. v1.9受け入れ条件

本版は、canonical個別銘柄経路、legacy stock-review、銘柄検索・master同期を含む次の条件をすべて満たしたとき受け入れ可能とする。

1. activeな登録銘柄1件、非空質問、`STANDARD`を送ると、OpenAI Responses APIを1回だけ呼ぶ。
2. 実OpenAI APIでresponse ID、`completed` status、非空`output_text`を取得できる。
3. FastAPI経由で`request_id`、`status=success`、非空`answer_text`、銘柄snapshot、OpenAI response IDを取得できる。
4. browserで銘柄検索・選択、質問入力、送信、loading、answer表示が成立する。
5. modelは`gpt-5.6-terra`、presetは`STANDARD`、`reasoning.effort`と`text.verbosity`は`medium`のままである。
6. model選択とpreset定義が分離され、別modelへのfallbackがない。
7. 共通OS、共通入力の必要部分、no-tools実行制約、用途module 3.1がmanifest記載順で実requestへ入る。
8. 銘柄contextと自由質問が分離して合成される。
9. 用途module 3.2〜3.14、Web tool、Structured Outputs、JSON Schemaがrequestへ混入しない。
10. 未提供の価格、決算、technical、需給、市場、macro、eventを現在の事実として補完しないようpromptで制約する。
11. prompt version、asset、module、hashを追跡でき、prompt本文と質問はmetadata、公開response、browserへ出ない。
12. manifest不正、asset欠落、hash不一致で別promptへfallbackしない。
13. OpenAI error、timeout、未完了response、空回答をsuccessにしない。
14. `AUTHENTICATION_ERROR`、`MODEL_UNAVAILABLE`、`INVALID_API_PARAMETERS`、`RATE_LIMITED`、`TIMEOUT`、`NETWORK_ERROR`、`EMPTY_RESPONSE`、`UNKNOWN_OPENAI_ERROR`を区別する。
15. canonical経路でmock、cache、raw-response fallback、Web検索、JSON修復、再AI呼び出し、streaming、backgroundを使わない。
16. legacy portfolio endpoint、Prompt Registry、mode、mock、cache、historyを維持する。
17. compiler、OpenAI client、FastAPI endpoint、最小UIのunit testが成功する。
18. 評価fixtureが指定された10観点を網羅し、人間がbefore / afterを比較できる。
19. 成功したcanonical回答が同じ`request_id`の`AiAnalysisRecord`としてローカルSQLへ保存される。
20. OpenAI成功後の保存失敗ではrollbackし、OpenAIを再呼び出さず、HTTP 200、`status=success`、非空`answer_text`、`persistence_status=failed`、`saved_at=null`、安全なwarningを返す。
21. `GET /api/ai/analyses/{request_id}`で保存済み回答を1件取得でき、存在しないIDをsuccess扱いしない。
22. `/ui/analysis`は保存成功時だけ大型表示導線と保存済み表示を出し、保存失敗時は回答本文とwarningだけを表示する。
23. 保存recordと公開responseへAPIキー、prompt全文、provider raw responseを含めない。
24. active prompt versionが`2026.08.18`、compilerが`individual-security-v2`で、共通OS、必要な共通入力rule、no-tools制約、module 3.1だけが実requestへ入り、根拠ラベルが`【V】`、`【E】`、`【U】`である。v18 source provenanceと`revision.base_source`のv17 provenanceを追跡できる。
25. OpenAI request kwargsに`store=false`が含まれ、`previous_response_id`とbackground modeがない。
26. APIの既定bindは`127.0.0.1`であり、`--host 0.0.0.0`を指定したときだけLAN到達可能になる。
27. 通常のFastAPI lifespan起動1回につき`init_db()`が1回だけ呼ばれ、`create_app()`自体はDB初期化を行わない。
28. legacy日次quotaの既定値が300で、5銘柄の一括review成功1件は`review_runs`を1だけ増やす。
29. mock、cache hit、prompt-only、limit拒否では`review_runs`が増えず、repairまたはparse失敗responseを含むprovider responseは`api_calls`へ別に記録される。
30. `GET /api/ai/stock-review/usage`がJSTの当日・当月集計、残数、pricing provenance、未算定callを返し、canonical経路の実行を集計しない。
31. tokenと実Web検索callに基づく概算額を表示し、算定不能なprovider callを0円と偽らず`unpriced_api_calls`として表示する。
32. dashboardに本日/今月の回数・概算・残数・不完全履歴注記を表示し、`database`等の内部値を利用者向け対象labelへ変換する。
33. v2 ledgerへAPIキー、prompt、質問、回答を保存せず、旧汚染counterを移行せず、testがrepositoryのusage/history/cacheを変更しない。
34. 銘柄検索が銘柄名、数字コード、英字を含むコードを受け付け、登録済みキオクシアホールディングスを銘柄名または`285A`で検索できる。
35. dashboardの検索結果に「保有入力へ」と「詳細を見る」があり、英字を含む5文字末尾`0`のraw identifierは公開4文字で表示・prefillする一方、詳細actionはraw identifierを維持し、数量へfocusするだけで保存しない。
36. 数量なしではportfolio保存を実行せず、数量入力後の明示的な保存操作でだけ`POST /portfolio`を呼ぶ。平均取得単価は未入力でもよい。
37. `POST /portfolio`へ公開コード`285A`を送ると、一意な既存raw master`285A0`へ解決され、`285A`のplaceholder masterを作らない。既存`285A0`入力も受理する。
38. 完全一致をaliasより優先し、alias候補が一意でない場合は別の既存銘柄へ推測解決しない。
39. 利用者自身の`JQUANTS_API_KEY`を使う完全な現行同期で、J-Quantsが返した東証上場issue（ETF、REIT、優先株等を含む）をprivateなローカルDBへ保存し、公開repositoryへ完全な一覧を追加しない。
40. J-Quants key未設定または取得失敗時、`require_jquants=true`はHTTP 400となり、36件seedだけを東証全件同期の成功として扱わない。
41. `GET /securities/master/status`がcredentialを含めず、scope、完全性、情報基準日、同期時刻、ローカル/J-Quants有効件数を返し、dashboardが未同期・同期済みを件数付きで区別する。
42. 不完全な現行snapshot、空snapshot、複数の`source_as_of`を含むsnapshotはDBを変更しない。
43. 完全な現行snapshotでだけ、欠落したJ-Quants所有recordをinactiveへ変更し、manual/local-seed/未採用legacy recordは維持する。
44. historical同期が現行recordのactive状態と最新現行statusを上書きせず、`deactivated_count=0`を維持する。
45. numeric普通株、非zero suffixの優先株等、英数字identifierを区別し、異なるraw codeの正規化衝突をsilent overwriteしない。
46. API/UIが取得・新規・更新・再有効化・無効化・ローカル有効・J-Quants有効の各件数と、planにより遅延し得る`source_as_of`を区別して表示する。
47. bundled seed同期がinsert-onlyで、既存J-Quants recordの名称、active状態、provenanceを上書きしない。
48. pagination循環、page上限、429 retry上限、current snapshot完全性、SQLite/PostgreSQL schema追加を自動testで確認する。
49. production currentのcomplete floorが4,000件で、既存active J-Quants件数と支配的legacy cohortの合算基準から5%を超える縮小はDB変更前に拒否される。
50. 旧snapshot日を`listed_date`へ誤格納した4,000件以上の支配的legacy cohortは通常UI/APIでfail closedとなり、current CLIの`--adopt-legacy`だけが明示reconcileできる。
51. ordinary/preferred等のidentity split候補に外部キー参照がある場合は同期を拒否し、参照なしの場合だけ安全に修復できる。
52. 銘柄検索が同期済みDBだけを使ってJ-Quantsを外部callせず、connector/API/browser/CLI errorへprovider body、transport detail、APIキーを露出しない。
53. CLI `--dry-run`がmaster同期をrollbackする一方、先行`init_db()`のschema/migration/不足seed bootstrapは永続化され得ることを運用文書で確認できる。
54. legacy軽量スキャンのmode別JSON Schemaがruntime Pydantic modelに存在しないfieldを列挙せず、top-level、portfolio summary、stock itemで`additionalProperties=false`となる。
55. scannerのstock schemaが30項目未満に縮小され、`judgement`を7つのcanonical code enumへ制限する。
56. valid JSONの`concentration_comment`と`summary_view`を、それぞれ`concentration_risk`と`overall_view`へ追加OpenAI callなしで正規化し、既存canonical値を上書きしない。
57. JSON構文不正、rootがobjectでない場合、field shapeまたはPydantic model不一致を`json_syntax`、`root_shape`、`schema_validation`として区別する。
58. repair後も構造化できない生応答は`status=json_parse_failed`のまま表示・必要に応じて履歴保存し、`review_runs`を増やさずcacheへ保存しない。provider responseとrepair callのusageは`api_calls`へ記録する。
59. dashboardが`json_parse_failed`を成功表示せず赤いerror cardにし、3つの`parse_failure_kind`を利用者向けlabelで区別する。
60. provider rootがmode schemaの許可fieldだけを受理し、service-ownedなstatus / error / cache / parse fieldを含む応答を`schema_validation`として拒否する。
61. valid JSON配列を`root_shape`とし、非object stock、非string judgement、非string互換aliasを`schema_validation`として拒否する。
62. raw output救済のquota/cache判定がservice-localなparse pathで決まり、provider出力のstatusに依存しない。
63. legacy promptがInput JSONの`ticker` / `name`を正本とし、`stocks[].name`をcodeで代用せず、summaryの6つの銘柄候補listを「銘柄名（銘柄コード）」で要求する。
64. request側名称またはtickerがplaceholder / local aliasでも、activeなlocal `SecurityMaster`に登録済みならprovider callなしでcanonical ticker・正式名称・市場へ補完される。
65. canonical tickerへ揃えた重複targetが除かれ、holdingsとcandidatesの重複ではholdingsが優先される。
66. live、mock、cache hitのいずれでも`stocks[].name`とsummary銘柄参照を同じidentity規則で正規化し、誤名称付きcodeを解決済みtarget正本へ直す。
67. local alias `285A0`がcanonical master `285A`へ解決され、summaryでは`キオクシアホールディングス（285A）`、legacy stock cardでは`285A`となる。`72030`もcanonical master `7203`へ解決される一方、未解決numeric 5文字codeを表示関数だけで誤って短縮しない。
68. 未登録codeは`名称未登録（code）`と表示し、コードだけの利用者向け候補表示を残さない。
69. scanner promptがsection 8のportfolio影響とquick scan短縮版を含み、個別詳細module全体を投入しない。
70. canonical active prompt 2026.08.18とmanifest、`gpt-5.6-terra`、`STANDARD`、`response.output_text`契約が変更されていない。
71. legacy response schema typeとDB master keyを変更せず、解決済みtarget identityと利用者向けcard/summary表記を正規化する。

## 16. v1.9の非対象

次はv1.4のcanonical個別銘柄経路へ実装しない。

- `LIGHT`、`HIGH`、`PRO`、`MAX` preset
- model選択UIとmodel切替
- 複数銘柄分析
- 市場全体分析
- 保有・監視銘柄と市場を組み合わせる総合分析
- 用途module 3.2〜3.14の投入
- Web検索
- J-Quants、EDINET、YouTube Data API、allowlist公式IR等の追加context統合
- Structured OutputsとJSON Schema
- JSON修復、parse retry、再AI呼び出し
- mock、cache、prompt cache
- background response、polling、streaming
- Markdown rendererと構造化card UI
- 回答内容または投資判断の自動採点
- 保存回答の一覧・検索・削除・export・共有
- 保存recordの保持期限設定と自動purge
- canonical画面/APIの認証・認可
- legacy portfolio AIの削除、廃止、統合、大規模refactor
- canonical個別銘柄AIへのlegacy quota/usage ledger適用
- OpenAI請求額との自動照合、請求上限の保証、為替換算
- 旧`ai_review_usage.json`のv2 ledgerへの移行
- `security_master` primary keyや既存参照tableを一括変換する大規模migration
- J-Quants connector全体の4文字canonical code正規化
- 検索結果から数量・平均取得単価を省略したワンクリック保有登録
- J-Quantsから取得した完全な銘柄一覧のrepository同梱、CSV export、第三者への再配布
- 名古屋・福岡・札幌等の地方取引所だけに上場する銘柄まで含む全取引所網羅の保証
- J-Quants APIキーの共有、代理提供、browser保存
- J-Quants個人版の契約範囲を超える取得データの第三者配信、data-backed service提供、無許諾public host運用
- 定期background同期、schedule、外部配布用security-master API

## 17. 既知制約

- legacy usage ledgerのprocess内lockとatomic replaceは、複数process/複数host間の厳密な分散quotaを保証しない。
- provider call開始前の原子的な予約、失敗attemptを含むhard call budget、hard cost ceiling、並行request間の厳密な上限保証は未実装で、follow-upとする。
- v2開始前のlegacy回数・概算額は集計対象外であり、月途中に開始した月間値は不完全である。
- 概算額は記録時点のversioned standard pricingとprovider usageに基づく参考値で、OpenAIの正式請求額ではない。token usageを取得できないcallや未登録modelは未算定として残る。
- canonical endpointにはアプリ独自の認証、利用者分離、server-side rate limit、daily quota、TLS終端がない。runnerの既定bind hostは`127.0.0.1`で、ローカルPCからだけ接続できる。LAN確認時は利用者が明示的に`python scripts/run_api.py --host 0.0.0.0`を指定できるが、信頼できる閉じたLANだけで利用し、Internetへ直接公開しない。Android対応や外部公開の前に認証、HTTPS、rate limitを実装する。
- prompt manifestやasset構成異常はfail closedになるが、現行routeは`PromptConfigurationError`をtyped `AiAnalysisError`へ変換せず、HTTP 500になり得る。
- generated OpenAPIはcanonical endpointの200 / 422以外の実行時error responseをまだ宣言していない。
- canonical個別銘柄経路の入力dataは主に`security_master`の識別情報であり、現在価格や最新市場dataを持たない。そのため、具体的な売買判断より`insufficient_data`、`no_trade`、確認項目、条件付きscenarioが中心になり得る。
- 共通OSは広い観点と標準出力を要求するため、単純な質問でも回答が冗長になる可能性がある。
- canonical経路は成功回答をローカルSQLへ保存するが、一覧、検索、削除、export、共有、保持期限、自動purgeを持たない。保存recordへのアクセス制御も未実装である。
- OpenAI側のmodel利用権限、billing、quota、rate limit、network状態により実API確認が失敗し得る。失敗時は別modelやmockで成功扱いにしない。
- 評価fixtureは人間比較用であり、回答の投資判断としての正しさを保証または自動採点しない。
- FastAPIを介さないsmoke scriptはOpenAI APIそのものの疎通確認用であり、PromptCompiler、銘柄DB、canonical endpoint、browser UIの確認を代替しない。
- canonical経路とlegacy経路ではWeb、Structured Outputs、mock、cache、fallbackの方針が異なる。この差異はv1.4時点の意図的な責務分離である。
- 現行schemaは`security_code`の4〜10文字制約をtrim前に評価するため、空白でpaddingした短いcodeがtrim後4文字未満になってもvalidationを通る場合がある。UIはtrim済みの検索結果codeを送るが、server-side正規化後の長さ再検証は未実装である。
- J-Quants listed masterの一部は、公開4文字コードに末尾`0`を付けた5文字raw identifierを`security_master.ticker_code`へ保持している。v1.6はportfolio登録時の一意alias解決で重複を防ぐが、master primary keyや他tableの既存参照を4文字へ移行しない。
- `GET /securities/search`が返す`ticker_code`は登録済みmaster identifierであり、キオクシアホールディングスでは`285A0`になり得る。dashboardはこのraw値を詳細action用に維持しつつ、表示と保有入力では公開コード`285A`へ変換する。このUI変換はmaster自体のmigrationではない。
- 銘柄マスターの対象はJ-Quantsが提供する東証上場issueであり、「日本法人すべて」「国内全取引所の全上場銘柄」と同義ではない。地方取引所単独銘柄は検索できない場合がある。
- `source_as_of`は利用者のJ-Quants planに応じて遅延し得る。dashboardの同期時刻はローカル取り込み時刻であり、情報のリアルタイム性を示さない。
- providerの一時的な429、network障害、plan権限、endpoint仕様変更により全件同期が失敗し得る。有限回retry後も失敗した場合、既存masterを維持して明示的なerrorを返す。
- 36件のbundled seedは初期検索用の限定集合で、完全性を示さない。完全なJ-Quants datasetはgit管理外の各利用者のローカルDBにしか存在しない。
- production floor 4,000と最大5%縮小guardは正当な大幅減少でも安全側に停止し得る。UIから閾値を緩和できない。
- 支配的legacy cohortの通常同期は停止しCLIの明示採用を必要とする。参照付きidentity splitの専用migrationは未実装で、参照recordを保全した個別reconciliationが必要である。
- CLI `--dry-run`は同期transactionだけのrollbackであり、先行`init_db()`によるschema/migration/不足36件seed bootstrapまでread-onlyにしない。
- J-Quants個人版の最新plan/利用規約の適合判断は利用者の責任であり、このrepositoryの公開ライセンスはprovider dataの第三者利用権を付与しない。
- legacyのJSON整形retry自体は継続するため、構造化に失敗した1回のreview attemptからprimaryとrepairの最大2 provider callが発生し得る。raw output救済は成功quotaを消費しないが、provider usageと概算額は発生し得る。

## 18. 文書内変更履歴

| version | 日付 | 概要 |
|---|---|---|
| v1.0 | 2026-04-22 | 日本株判断補助アプリの目的、基本機能、data source、live modeのno-mock方針を定義 |
| v1.1 | 2026-06-15 | legacy portfolio向けPrompt Registry / Prompt Builder、multi-mode AI、Web検索、Structured Outputs、mock、cache、history要件を追加 |
| v1.2 | 2026-08-17 | canonical個別銘柄AI最小縦スライス、固定`STANDARD`設定、versioned PromptCompiler、plain `output_text`、typed error、legacy経路との責務分離を追加 |
| v1.3 | 2026-08-17 | canonical成功回答のローカルSQL自動保存、UUIDによる1件取得、大型別ウィンドウ画面、prompt source v2026.08.17と銘柄名・コード併記規則を追加 |
| v1.4 | 2026-08-17 | OpenAI `store=false`、生成/保存結果の分離、保存失敗時の回答維持、loopback既定、lifespan-only DB初期化、active prompt 2026.08.18の正式根拠ラベルを追加 |
| v1.5 | 2026-08-17 | legacy stock-reviewの日次quota 300、review/API call分離、JST日次・月次v2 ledger、公式pricing由来概算、usage API/dashboard、test隔離を追加 |
| v1.6 | 2026-08-18 | 銘柄名・数字/英字コード検索、検索結果から保有入力への非保存prefill、4文字公開コードから一意なJ-Quants raw identifierへのportfolio alias解決を追加 |
| v1.7 | 2026-08-18 | BYOKによる東証/J-Quants上場issueのprivate local full sync、status/provenance/count、production 4,000件/5%縮小guard、支配的legacy明示採用、参照identity保護、DB-only検索、safe error、dry-run初期化境界、historical保護、preferred/raw code保持、契約/非再配布境界を追加 |
| v1.8 | 2026-08-19 | legacy軽量スキャンのalias正規化、provider root allowlist、厳格な型検証、JSON Schema/Pydantic一致、scanner schema縮小、judgement enum、parse失敗3分類、service-local raw output救済の失敗status・quota非加算・cache禁止・履歴保存可、dashboard赤表示を追加 |
| v1.9 | 2026-08-19 | 添付v2026.08.16を参照資料として確認しcanonical v2026.08.18を維持。legacy promptの銘柄名・code併記、local master identity補完、live/mock/cache共通のstock名・summary銘柄参照正規化、公開code表示、scanner portfolio影響sectionを追加 |
