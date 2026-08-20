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
| 要件仕様 | v2.1 | `docs/requirements/requirements_v2.1.md` | 2026-08-19 |
| API仕様 | v2.4 | `docs/specs/api_spec_v2.4.md` | 2026-08-19 |
| 画面仕様 | v2.8 | `docs/screen_specs/screen_spec_v2.8.md` | 2026-08-19 |

要件v2.1、API仕様v2.4、画面仕様v2.8はそれぞれ直前版を累積継承し、legacy stock-reviewの保存履歴一覧・詳細・Markdown export・browser印刷によるPDF保存を扱う変更単位`SC-2026-08-19-06`を追加します。複数named watchlistの`SC-2026-08-19-05`、画面仕様v2.6のclient-only現在回答reader、canonical個別銘柄AIの既存契約も維持します。

## 2.1. SC-2026-08-19-06 — legacy保存済みAI結果・Markdown / PDF印刷表示

### 2.1.1 変更理由

legacy stock-reviewはローカルJSON履歴へ結果を保存できましたが、画面から保存済み結果を分類して探し、詳細を安全に再表示し、持ち出し可能なMarkdownまたは印刷用PDFとして確認する正式導線がありませんでした。現在回答だけのclient-side Blob readerは保存済み履歴の復元手段ではなく、dashboard reload後や後日の比較に使えません。OpenAIを再呼び出さず、秘密情報と大きな回答本文を一覧へ露出せず、破損historyでも既存dataを守るread-only契約が必要です。

### 2.1.2 保存条件・保持・失敗境界

- `save_result=true`で新しく生成したlegacy responseだけをgit管理外の`data/ai_review_history.json`へ保存します。`save_result=false`とcache hitは新しいhistory entryを作りません。
- `status=success`のlive / mock / forced mock、`prompt_only`、`json_parse_failed`のraw fallbackは保存対象になり得ます。保存可能なresponse生成前のAPI key / quota / target / provider errorは保存しません。
- 最大100 recordを保持し、新規追加で古いrecordを上限外へ送ります。entryのcanonical JSONから64文字の小文字SHA-256 history IDを決定的に作ります。
- 保存失敗時も生成回答を返し、OpenAIを再呼び出さず、`warnings`へsafeな固定文を1回だけ追加します。そのresponseをcacheへ保存せず、履歴保存済みとも表示しません。
- invalid entryはread時にskipして件数を返し、root自体が不正なら既存fileを上書きしません。通常appendは同一process `RLock`とtemp / flush / fsync / `os.replace`でatomicに更新します。複数worker / 複数host間のlost updateを防ぐhard guaranteeではありません。

### 2.1.3 history list / detail API

- `GET /api/ai/stock-review/history`は`mode`、`target`、`status`、`limit`（1〜100、既定100）、`offset`を受け、保存順の新しいものからmetadataだけを返します。
- itemはhistory ID、日時、mode / target / status label、analysis mode、holdings source、銘柄数 / 最大3件preview、model、watchlist ID、Web / mock / cache flag、概算額を持ちます。`summary`はmodel本文を使わず、successは`N銘柄の保存済み結果`、prompt-onlyは`ChatGPT投入用プロンプト`、failureはstatus labelから決定的に作ります。
- `mode_counts`はfilter前の有効全件、`total`はfilter後かつpagination前、`items`はpagination後です。`stored_count`と`invalid_count`も別に返します。一覧へ回答本文、prompt、position detail、`request_payload`、provider raw responseを含めません。
- `GET /api/ai/stock-review/history/{history_id}`は`{history_id, review}` envelopeを返し、`review`から`request_payload`を除外します。invalid / missing IDはsafeな404です。
- 過去のcode-only参照は同期済みローカルmasterによりread時だけ正式名称・公開codeへ補完し、history fileは書き換えません。

### 2.1.4 Markdown export・response安全性

- `GET /api/ai/stock-review/history/{history_id}/export.md`は主要typed fields、portfolio / stock / carry / theme / risk flag、warning、source、raw fallbackをsemanticなUTF-8 Markdownへ出力します。
- attachment filenameは`ai-review-YYYYMMDD-HHMMSS-<mode>-<id8>.md`形式のASCIIだけとし、可変textをHTML / Markdownとしてescapeします。sourceはHTTP(S)だけをlink化し、raw outputは内容より長いbacktick fenceで囲みます。
- list / detail / exportは`Cache-Control: no-store`と`X-Content-Type-Options: nosniff`を持ち、Markdownは`Referrer-Policy: no-referrer`も持ちます。
- これらは保存済みlocal recordを読むだけで、OpenAI、外部source、quota、usage ledger、cache、DB writeを発生させません。

### 2.1.5 dashboard・Markdown / PDF印刷

- dashboardへ`保存済みAI結果`を追加し、直近100件をAPIの保存順どおり新しいものからmode別にgroup化します。`generated_at`でclient再sortしません。画面filterはmodeを扱い、loading、empty、API error、invalid entry countを区別します。
- 各itemは`結果を見る`、`Markdown保存`を持ち、prompt-only以外は`別タブ表示・PDF保存`も持ちます。detailは既存safe structured renderer、`OpenAI API非呼び出し`と示すprompt-onlyのescaped plain prompt、失敗時の赤いraw fallbackを使い分けます。現在結果でもprompt-onlyをOpenAI実行済みと誤表示しません。
- 別タブ表示はdetail DOMのrestricted-CSP Blob snapshotで、browserの印刷からPDFへ保存します。server-side PDF生成、外部resource / script / form、Web Storage保存はありません。
- raw fallbackは画面先頭20,000文字までに省略でき、省略時は全文をMarkdown保存で確認できると明示します。印刷cloneでは`details.ai-raw-output`をopenにして、画面に出ているrawをPDFから欠落させません。
- 保存済み`watchlist_id`は表示できますが、旧recordは実行時のnamed watchlist名を保存していません。現行collection名から過去名を推測せず、一般的な対象labelまたは保存済みIDだけを使います。

### 2.1.6 SC-2026-08-19-04との関係・非対象

SC-2026-08-19-04がclient-only現在回答readerの非対象として記録した「server-side legacy履歴reader、saved-result ID、一覧、download、export」は、legacy保存履歴に限り本SC-2026-08-19-06が置き換えます。SC-04の現在回答Blob snapshot、`save_result=false` / mock / cache hitでも使えること、no API / DB / Web Storage / OpenAI再呼び出し、reload非復元はそのまま有効です。canonical `/ui/analysis`の保存履歴一覧・exportも追加しません。

次は非対象です。

- 履歴削除、全文検索、pin、保持期限、自動purge、共有URL、cloud同期
- 認証、owner ID、利用者別access control
- server-side PDF生成、PDF file保存、印刷layout保証
- 旧recordに存在しないnamed watchlist名の推測復元
- 複数process / 複数host間のhistory write hard guarantee

### 2.1.7 受け入れ確認

- 保存条件、cache hit非保存、最大100件、save失敗warning / cache非保存、invalid / corrupt root、thread-safe atomic appendをunit testで固定します。
- 保存順の新しいものからの順序、filter / pagination、metadata-only、count境界、決定的summary、detailの`request_payload`除外、safe 404、旧identity read-time補完を確認します。
- Markdownの主要section、ASCII filename、no-store / nosniff / no-referrer、escape、HTTP(S) allowlist、可変長raw fenceを確認します。
- dashboardのmode別一覧、detail、prompt-only、Markdown、別タブ印刷、raw 20,000文字省略 / 全文案内 / details open、safe rendererを確認します。
- 履歴read / export / printでOpenAI、quota、usage、cache、Web Storageが変化せず、旧named list名を推測しないことを確認します。

## 2.2. SC-2026-08-19-05 — Portfolio・複数named watchlist管理

### 2.2.1 変更理由

従来dashboardはPortfolioと単一Watchlistを別panelとして扱い、同じ銘柄群を目的別に分けて保存・比較できませんでした。個別listを増やすだけでは、検索、Focus Board、alerts、詳細 / chart遷移、AI対象、旧`/watchlist`互換のscopeが曖昧になります。Portfolioを独立storageのまま維持し、複数named watchlistのcollection / membershipを明示的に分離しながら、1つの管理spaceで安全に切り替える契約が必要です。

### 2.2.2 data modelとstartup migration

- `watchlist_collection`は`id`、表示名、NFKC + trim + casefoldした一意identity、nullableな一意`system_key`、並び順、active状態、時刻を保持します。`system_key=default`のcollectionがlegacy互換のdefault「メイン」です。
- `watchlist_membership`はcollectionと既存`watchlist` itemを関連付け、membership固有の並び順とactive状態を保持します。同じcollection / itemの組は一意で、同じtickerは複数collectionへ登録できます。
- 既存`watchlist`はtickerごとに1 rowを維持し、memo / thesisはsecurity-level共有値です。collectionごとの別memo / thesisは作りません。
- startup migrationはdefaultがまだ存在しない最初のtransactionだけで「メイン」を作成し、その時点のlegacy itemをactive状態ごとmembershipへbackfillします。再起動時はbackfillを繰り返さず、後からnamed listだけへ追加したitemをdefaultへ漏らしません。
- non-default collection削除はそのmembershipだけを除去し、Portfolioと他collectionを維持します。default collectionは削除できません。

### 2.2.3 collection・item・検索API

- `GET /watchlists`と`POST /watchlists`でcollection一覧 / 作成、`PATCH /watchlists/{collection_id}`と`DELETE /watchlists/{collection_id}`で名前・並び順更新 / non-default削除を行います。collection readは`id`、`name`、`is_default`、`sort_order`、`item_count`、`created_at`、`updated_at`を返します。
- nameはNFKC + trim後1〜80文字、identityはcasefoldして一意です。重複は409、missing / inactiveは404、default削除は409、成功したDELETEは204です。default名の変更と並び順更新は可能です。
- `GET` / `POST /watchlists/{collection_id}/items`と`DELETE /watchlists/{collection_id}/items/{ticker_code}`でlist別membershipを取得・upsert / reactivate・解除します。item responseは`collection_id`を持ちます。
- 既存`GET /watchlist`と`POST /watchlist`はdefault collection互換として維持します。Portfolio保存とは統合しません。
- `GET /securities/search`はoptional `watchlist_id`を受け、指定時の`in_watchlist`をそのcollection membershipへscopeします。missing / inactive IDは404です。
- `GET /ui/dashboard/data`はoptional `watchlist_id`を受け、item、Focus Board、alerts等をscopeします。指定IDが不正、missing、inactiveならdefaultへfallbackする既存dashboard可用性境界を採用します。

### 2.2.4 dashboard・detail・chart

- dashboardのPortfolio / Watchlist二分割を、native selectorで`portfolio`または`watchlist:{id}`へ切り替える全幅「保有・ウォッチリスト管理」spaceへ統合します。queryなしの既定表示はPortfolioです。
- named listはinlineで作成・名前変更・non-default削除できます。default削除buttonはdisabledです。選択listが空なら専用empty stateを出し、mock itemを補完しません。
- 検索結果からactive named listへ追加し、cardからそのmembershipだけを外します。checkbox選択はcollection IDごとに分離し、reload時は現在membershipに合わせてpruneします。1件以上の選択は共通AI targetを`selected`へ自動変更し、全解除かつmanual tickerなしでは`watchlist`へ戻します。Web Storageへ永続化しません。
- named list選択中の検索、Focus Board、alerts、detail / chartリンクは`watchlist_id`を維持します。detailのdashboard戻り、chart往復、`watchlistに追加`、仮説保存も同じcollectionへscopeします。
- queryなしのPortfolio detailではlegacy default `/watchlist`を使います。Portfolioそのものとdefault watchlistは別storageのままです。
- memo / thesisが同tickerを含む他collectionにも反映されるsecurity-level共有値であることを、list固有値と誤認させない表示にします。
- URL `?watchlist_id=`から開くdashboardは指定named listと`target=watchlist`を初期状態にします。Portfolioへ戻る場合は`watchlist_id`なしでdashboard dataをreloadし、default monitoring scopeへ戻します。
- dashboard fetchはrequest IDとrequested `watchlist_id`をactive scopeへ照合し、切替前の遅いresponseを破棄します。

### 2.2.5 legacy AI targetと互換性

- named list選択時のlegacy AIは`target=watchlist`と`watchlist_id`を送り、そのcollectionだけを対象にします。明示したnamed listが空、missing、inactiveの場合は`no_holdings`で終了し、テスト用mock holdingsへfallbackしません。
- AI request開始時のcollection名をclient context snapshotとしてloading / summary / Blob reader titleへ使います。rename / switch後に現行collection名で書き換えず、API、DB、history、cache、Web Storageへsnapshot fieldを追加しません。
- selector切替、collection作成、active collection削除、active membership追加・解除、checkbox変更は現在結果とreader actionを無効化し、client request generationで進行中の旧responseも破棄します。cancel API、追加OpenAI call、quota mutationは行いません。
- `watchlist_id`なしのlegacy default targetは従来のdefault互換と、空時の既存mock fallbackを維持します。Portfolio AIは`target=holdings`のままです。
- 1回の実行、quota、usage、model、reasoning、Web policy、Structured Outputs、JSON repair、cache/history契約は変更しません。list切替だけではOpenAIを呼びません。
- v2.6のclient-only Blob reader、canonical個別銘柄AI、active prompt v2026.08.18、J-Quants master同期も変更しません。
- mock modeは同じcollection / membership APIとdashboard scopeを提供し、明示named empty時の非fallbackをlive modeと一致させます。

### 2.2.6 security・非対象・既知制約

- collectionとmembershipは認証・利用者分離のないapp-global dataです。同じappへ接続できる利用者間でlistを分離しません。既定loopbackとtrusted local環境を前提とし、Internetへ直接公開しません。
- collection名、memo、thesis、検索結果はescapeして描画し、API key、prompt全文、質問、回答本文を通常logへ追加しません。
- 認証、利用者ownership、権限、共有招待、rate limit、list固有memo / thesis、Portfolio自動同期、default削除、undo / trash、export、drag-and-drop並べ替えは非対象です。
- dashboard dataのinvalid IDはdefaultへfallbackしますが、collection / item / search APIは404またはvalidation errorを返し得ます。collection削除にundoはありません。
- default collectionの初回migrationは単一application processを前提とします。未初期化PostgreSQLへ複数processが同時起動する場合のunique競合serialize / retryは未実装・未検証です。

### 2.2.7 受け入れ確認

- startup migrationがdefault「メイン」を一度だけ作成・backfillし、再起動後にnamed-only itemをdefaultへ混入させないことを確認します。
- collection名の正規化、重複409、missing / inactive 404、default削除409、DELETE 204、同tickerの複数list所属を確認します。
- legacy `/watchlist`がdefault互換で、Portfolio storageと分離され、memo / thesisだけがsecurity-levelで共有されることを確認します。
- dashboard selector、作成 / 名前変更 / 削除、empty state、検索追加、membership解除、collection別checkbox state、Focus Board / alerts scopeを確認します。
- named listからdetail / chartへ進み戻るquery、detail追加 / 仮説保存のscope、Portfolio contextのlegacy default endpointを確認します。
- 明示named emptyでmock fallbackせず`no_holdings`となり、legacy no-ID fallback、quota、usage、reader、canonical AIが変わらないことを確認します。
- URL query初期target、checkboxのselected / watchlist自動切替、Portfolio復帰時のdefault monitoring reload、requested / active scope不一致responseの破棄を確認します。
- request開始時list名snapshotがsummary / reader titleへ残り、scope・collection・membership・checkbox mutationで旧結果と進行中responseが無効化され、API / DB / Web Storage / OpenAI callを追加しないことを確認します。
- app-global / 認証なしの境界を文書と画面で明示し、HTML / collection名を実行しないことを確認します。

## 2.3. SC-2026-08-19-04 — legacy AI現在回答の別タブ大画面表示

### 2.3.1 変更理由

legacy Portfolio / Watchlistの構造化回答はdashboard内で読みやすく表示できるようになりましたが、銘柄数や分析項目が多い回答を広い画面で集中して読む導線がありませんでした。canonical個別銘柄AIには保存済みSQL recordをrequest IDで読むreaderがありますが、legacy経路は保存ON/OFF、mock、cache、parse失敗時の生応答を含む異なる契約です。既存APIや保存範囲を広げず、現在画面にある結果だけを一時的に大きく表示する必要があります。

### 2.3.2 表示条件とsnapshot

- Portfolio保有分析とWatchlist分析の現在結果に共通の`回答を別タブ／ウィンドウで大きく表示`action linkを追加します。
- `status=success`かつ`mode!=prompt_only`、または`status=json_parse_failed`かつtrim後の`raw_model_output`が非空の場合だけaction linkを表示します。idle、loading、通信失敗、data欠落、prompt-only、生応答なしerrorでは表示しません。
- 現在描画したbrowser stateから静的HTMLを作り、client-onlyのBlob URLで新しい閲覧contextへ開きます。親画面の後続分析で、既に開いたsnapshotを変更しません。
- successはv2.5のsummary / stock / list / callout / source共通rendererと順序を再利用します。parse失敗は赤いerror表示、原因label、escape済みplain raw outputを維持し、成功へ読み替えません。
- mock response、cache hit、`save_result=false`でも現在の表示条件を満たせば利用できます。`manual_prompt`は既存textareaだけで扱い、readerには含めません。

### 2.3.3 client-only境界

- readerを開く操作は既存または新規のAPIを呼ばず、DB、legacy JSON history/cache、`localStorage`、`sessionStorage`、IndexedDB、cookieへsnapshotを保存しません。
- `POST /api/ai/stock-review`、互換API、usage API、OpenAI Responses APIを呼び直さず、review quota、provider call、token、Web検索、概算額を増やしません。
- snapshotをURL query / fragmentへ埋め込まず、共有可能な恒久URL、bookmark、一覧、検索、再取得APIを提供しません。readerのreload、閉じた後の復元、別端末共有は保証しません。
- canonical `/ui/analysis/results/{request_id}`は保存済みSQL record用readerのままです。legacy Blob readerをcanonical保存経路へ接続しません。

### 2.3.4 安全性・accessibility

- Blob documentは静的HTMLと表示用inline CSSだけを持ち、script、外部resource、formを含めません。restrictiveなContent Security Policyを付け、必要なinline style以外を既定拒否します。
- action linkは`target="_blank"`と`rel="noopener noreferrer"`で新しい閲覧contextを開き、親画面への`window.opener`参照を渡しません。許可済み`http:` / `https:` source linkだけをanchorにし、同じ属性を付けます。
- model、mock、cache、history由来textは既存escape処理を通し、HTML / Markdownとして実行しません。API key、Authorization header、prompt全文、`manual_prompt`、成功responseにないprovider raw dataを含めません。
- readerは固定の日本語titleと画面見出しを持ちます。successでは複製元summaryの対象、mode、生成時刻を維持し、`json_parse_failed`では複製元error cardの失敗labelと対象labelを維持します。semantic heading / list / details、広いmain領域、mobile 1column、chip折返し、長文・code・URLのoverflow対策を保ちます。
- browserがtab/windowのどちらで開くかは利用者設定に従います。browser policyで新規contextを開けない場合も元の結果は維持され、通常操作またはcontext menuからaction linkを再試行できます。block検出や専用feedbackは保証しません。

### 2.3.5 互換性・非対象・既知制約

- legacy request / response schema、status、OpenAI request、model/reasoning、quota、usage、cache/historyの保存契約を変更しません。
- 要件v1.9、API v2.2、canonical個別銘柄AI、active prompt v2026.08.18、J-Quants銘柄masterを変更しません。
- このSC-04単独ではserver-side legacy reader route、保存結果ID、共有URL、Web Storageによる復元、回答一覧、download、export、編集を追加しませんでした。このうち保存済みlegacy履歴のID / reader / 一覧 / download / export非対象は後続SC-2026-08-19-06が置き換えます。共有URL、Web Storage復元、編集は引き続き非対象です。
- Blob readerはbrowser memory上の一時snapshotであり、reloadやbookmarkで復元できません。browser policyにより新規contextを開けない場合がありますが、元画面の回答は維持します。

### 2.3.6 受け入れ確認

- Portfolio / Watchlistのsuccess（prompt-only除外）と非空raw parse failureだけでaction linkが表示されることを確認します。
- success readerがv2.5の共通rendererを使い、raw parse failureがplain escaped error表示のままであることを確認します。
- HTML / Markdown風文字列、unsafe source URL、長文を含むfixtureでXSS、opener、CSP、mobile overflowを確認します。
- action linkの準備・openでfetch / API / DB / Web Storage / OpenAI call / usage mutationが起きず、現在結果のsnapshotが親stateの後続変更から独立することを確認します。
- 新規contextを開けない場合も元結果が維持されること、block検出や専用feedbackを保証しないこと、reader reloadを復元契約にしていないことを確認します。

## 2.4. SC-2026-08-19-03 — legacy AI構造化回答の可読表示

### 2.4.1 変更理由

legacy軽量スキャンは有効なStructured Outputs JSONを返していましたが、summaryの全体所見、risk、行動、候補、warning等の意味区分が弱く、利用者には長い平坦な文章のように見えていました。これはOpenAIからMarkdownが返った問題ではなく、既知JSON fieldを画面上のsemanticな構造へ十分対応付けていない表示上の問題です。

### 2.4.2 構造化表示

- legacy成功responseを汎用Markdownとしてparseせず、既知fieldをsummary、risk、action、candidate、warning、portfolio補足、stock detail、sourceへ明示的に対応付けます。
- 各groupへ利用者向けの日本語見出しを付け、配列は`ul` / `li`、重要項目はlabel付きcalloutとして表示します。空値だけのsectionを省略し、同じlist内のtrim後完全一致だけを除きます。
- 銘柄別cardはidentityとjudgementを先頭に置き、短評、時間軸、risk、technical、材料、地合い、需給、執行条件、scenario、反証条件、不確実性を意味別に配置します。
- Portfolio保有分析とWatchlist分析は共通のsummary、stock、list、callout、source helperを使い、利用可能fieldだけを同じ順序と安全規則で表示します。

### 2.4.3 安全性・根拠・accessibility

- model、mock、cache、history由来textを必ずescapeし、Markdown記号やHTML tagを実行しません。正式根拠label`【V】`、`【E】`、`【U】`はtextを伴うbadgeとして表示し、色だけで意味を伝えません。
- sourceはURLとして妥当な`http:` / `https:`だけをlinkにします。unsafeまたは非Web schemeはanchorへせずescapeしたtextにし、新規tab linkは`noopener noreferrer`を維持します。
- `json_parse_failed`のraw outputは成功cardへ変換せず、赤いerror card内のescape済みplain `pre`として表示します。nativeな`details` / `summary`を使う場合もMarkdown再解釈や追加OpenAI callを行いません。
- heading、list、callout、detailsをsemanticにし、keyboardとscreen readerで意味を追えるようにします。狭い画面では1columnと折返しを使い、長文やURLによる横overflowを防ぎます。

### 2.4.4 互換性・非対象

- `POST /api/ai/stock-review`のrequest / response schema、field、status、OpenAI request、model / reasoning、quota、usage、cache/historyは変更しません。
- canonical `POST /api/ai/analyses`、plain `response.output_text`、active prompt v2026.08.18、保存readerを変更しません。
- general-purpose Markdown renderer、model HTML、新しいfrontend dependency、OpenAI再呼び出しは追加しません。このため要件仕様v1.9とAPI仕様v2.2は昇格しません。

### 2.4.5 受け入れ確認

- summaryの全体所見、主要risk、行動、候補、重要警告、通常警告が見出しとsemantic list / calloutで区別でき、空sectionと同じlist内の重複を表示しないことを確認します。
- Portfolio / Watchlistが共通helperを使い、stock cardの名称・公開code・judgementと詳細groupを維持することを確認します。
- HTML / Markdown風文字列が実行されず、根拠badgeがtextでも判別でき、unsafe source URLがlinkにならないことを確認します。
- raw fallbackがplain escaped表示のままで、mobile幅、loading / error / success、API payload、OpenAI call回数が変わらないことを確認します。

## 2.5. SC-2026-08-19-02 — legacy stock-reviewの銘柄identityと名称・code併記

### 2.5.1 変更理由

legacy軽量スキャンの銘柄別cardは名称を持っていても、portfolio summaryの非監視縮小候補、core候補、入替候補等が`285A0`、`7011`のようなcodeだけになっていました。model promptへ名称併記を求めるだけでは、model逸脱、mock、過去cache、request側placeholder名称を確実に補正できません。Input/DB側の銘柄identityを正本にして生成契約とservice後処理を揃える必要がありました。

### 2.5.2 添付promptの扱い

- 添付`株判断_定型プロンプト集_v2026-08-16 (1).md`はprompt内容を照合する参照sourceであり、文書内の運用手順や実装優先順位をユーザー依頼として実行しません。
- 添付は既に履歴保存しているv2026.08.16と同内容です。canonical個別銘柄AIのactive asset v2026.08.18には、より明確な「銘柄名（銘柄コード）」と正式根拠label規則があるため、canonical manifest / assetを旧版へ戻しません。
- 今回はlegacy Prompt Builder / full promptへ名称併記原則を反映し、全14用途moduleの一括投入やcanonical PromptCompiler変更を行いません。

### 2.5.3 promptとscanner

- Base PolicyはInput JSONの`ticker` / `name`を正確に使い、銘柄を原則「銘柄名（銘柄コード）」で表示し、codeだけ・名称だけ・名称推測を避けるよう要求します。
- `stocks[].ticker` / `stocks[].name`のschema descriptionとOutput PolicyへInput JSONからの正確な転記を追加します。
- portfolio summaryの6つの銘柄参照listへ「銘柄名（銘柄コード）」を要求します。field typeは`list[str]`のままです。
- scannerは既存のlight sectionsとquick scan短縮版にsection 8「建玉・ポートフォリオ影響」を加えます。全詳細sectionを追加しません。

### 2.5.4 local master identityと重複解消

- DB sessionがあるlegacy reviewはactiveなlocal `SecurityMaster.ticker_code` / `local_code`を照合します。一致targetはmasterのcanonical `ticker_code`、正式名称、marketへ揃え、J-Quantsその他のproviderを追加callしません。
- `local_code=285A0` / `ticker_code=285A`ならpromptとsnapshotは`285A`、`local_code=72030` / `ticker_code=7203`なら`7203`となります。これはDB primary keyやlocal codeのmutationではありません。
- canonical tickerでholdings / candidatesをdedupeし、同じ銘柄が両方にあればholdingsを優先します。

### 2.5.5 responseと画面表示

- `stocks[].name`と`portfolio_summary.buy_candidates`、`sell_or_reduce_candidates`、`hold_priority`、`non_monitoring_reduce_candidates`、`core_position_candidates`、`exit_or_rotate_candidates`を解決済みtarget identityで再照合します。
- codeだけ、誤名称付きcode、正式名称だけのsummary値を「銘柄名（公開コード）」へ正規化します。unknown codeは`名称未登録（code）`とし、銘柄参照でない自由文は変更しません。
- live、mock、保存前、cache hitへ同じ後処理を適用します。cache hitの補正でOpenAIを再呼び出ししません。
- Portfolio / Watchlistのlegacy stock cardは公開codeを表示します。cacheに`285A0`が残っていても`285A`と表示できます。

### 2.5.6 互換性・非対象・既知制約

- legacy responseのfield type、endpoint、mode、model/reasoning、Web、quota、history/cache契約を維持します。target identity値はlocal masterへ一致した場合にcanonical tickerへ揃います。
- canonical `POST /api/ai/analyses`のactive prompt v2026.08.18、`gpt-5.6-terra`、`STANDARD`、plain `response.output_text`、保存契約を変更しません。
- local masterに名称が無いcodeは`名称未登録`となり、名称の外部推測やprovider照会を行いません。
- 過去history JSON自体の一括書換え、master primary key migration、全module prompt再設計は対象外です。

### 2.5.7 受け入れ確認

- promptに名称・code併記、Input JSON転記、scanner section 8が入り、不要な詳細sectionがscannerへ混入しないことを確認します。
- local master aliasからcanonical ticker/name/marketへ補完し、dedupeとholdings優先が働き、provider追加callがないことを確認します。
- live/model parse、mock、cache hitでstock名と6 summary listが正規化され、`285A0`が`キオクシアホールディングス（285A）`、unknownが`名称未登録（code）`になることを確認します。
- legacy cardが公開codeを使い、canonical AIと旧versioned prompt assetが変更されていないことを確認します。

## 3. SC-2026-08-19-01 — legacy軽量スキャンの構造化response契約と失敗分類

### 3.1 変更理由

5銘柄の軽量スキャンでOpenAIが返した本文は有効なJSONでしたが、`portfolio_summary.concentration_comment`または`summary_view`がruntime Pydantic modelに存在せず、`extra=forbid`でschema validationに失敗しました。一方、生成用JSON Schemaは`additionalProperties=true`として未定義fieldを許可していました。さらにPydantic `ValidationError`が広い`ValueError`処理へ入り、構文は正しい応答まで「JSONとして解析できない」と表示され、整形retry後のraw output救済が成功回数とcacheへ混入していました。生成契約、runtime契約、利用者向けstatusを一致させる必要がありました。

### 3.2 alias正規化とjudgement code

- valid JSONの`portfolio_summary.concentration_comment`を`concentration_risk`へ、`portfolio_summary.summary_view`を`overall_view`へ移し、legacy aliasを除去してからPydantic検証します。
- canonical fieldが既に非空ならcanonical値を優先し、aliasで上書きしません。alias互換だけを理由にOpenAIを再呼び出ししません。
- stock `judgement`は既知のcanonical codeを優先し、free-textの場合は`judgement_label`と本文のkeywordから安全に`hold`、`buy_more_candidate`、`take_profit_candidate`、`reduce_risk`、`watch`、`avoid_new_buy`、`urgent_review`へ正規化します。対応不能時は`watch`です。

### 3.3 JSON SchemaとPydanticの一致

- mode別JSON Schemaが列挙するportfolio summary / stock fieldをruntime Pydantic modelのfield以内に保ちます。
- top-level、`portfolio_summary`、`stocks[].items`を`additionalProperties=false`とし、生成時点で未定義fieldを許可しません。
- `scanner` stock schemaは30項目未満の軽量fieldへ縮小し、詳細分析用fieldを生成契約から外します。
- scannerを含む`judgement`は7つのcanonical code enumに制限します。

### 3.4 parse失敗分類・status・保存境界

- `parse_failure_kind=json_syntax`はJSON構文不正、`root_shape`は有効JSONだがrootがobjectでない場合、`schema_validation`は必須field・field shape・Pydantic model不一致を表します。
- 長い不正応答に対するWeb検索なしのJSON整形retryは1回だけ維持します。repair後に構造化できれば`status=success`です。
- repair後も構造化できず生応答を表示できる場合、HTTP 200でも`status=json_parse_failed`、`error.code=json_parse_failed`、原因別`parse_failure_kind`、非空`raw_model_output`を返します。raw本文の可視化を分析成功へ読み替えません。
- `save_result=true`なら調査用に失敗responseをローカルJSON履歴へ保存できます。cacheへは保存せず、既存cacheの非successまたはraw output recordもcache hitとして返しません。

### 3.5 quota・usage・UI

- `status=json_parse_failed`のraw output救済は`review_runs`を増やしません。primaryとrepairでusageを取得したprovider responseは従来どおり`api_calls`へ記録するため、成功回数0でもOpenAI呼出数と概算額が増え得ます。
- dashboardは`json_parse_failed`を成功色へ変換せず赤いerror cardにします。`schema_validation`は「JSON項目形式エラー」、`root_shape`は「JSONルート形式エラー」、`json_syntax`または分類欠落は「JSON構文エラー」と表示します。
- 表示可能な`raw_model_output`、warning、対象labelはerror card内で維持し、APIキー、prompt、内部例外detailを表示しません。

### 3.6 互換性・非対象・既知制約

- endpoint、request schema、mode、model/reasoning設定、Web検索方針、JSON整形retry、local historyを維持します。
- canonical `POST /api/ai/analyses`の`gpt-5.6-terra`、`STANDARD`、plain `response.output_text`、`store=false`、保存結果分離へこのlegacy仕様を適用しません。
- legacy responseへnullableな`parse_failure_kind`を追加します。過去historyにfieldがなくても読み込め、UIは安全な既定labelを使います。
- Structured Outputsでもmodel出力またはrepair結果が契約外になる可能性は残ります。1 review attemptで最大2 provider callが発生し得ます。

### 3.7 受け入れ確認

- `concentration_comment`と`summary_view`のvalid JSONをrepairなしで受理し、canonical fieldとjudgement codeへ正規化できることを確認します。
- schema fieldがPydantic model以内で、主要objectの`additionalProperties=false`、scanner field 30項目未満、judgement enum 7値であることを確認します。
- 構文、root shape、schema validationを区別し、repair失敗のraw output救済が`status=json_parse_failed`、成功回数非加算、cache禁止、履歴保存可となることを確認します。
- dashboard HTMLが3つの利用者向け失敗labelと赤いerror cardを使い、通常logへraw outputや内部例外detailを出さないことを確認します。

## 4. SC-2026-08-18-02 — 東証/J-Quants上場銘柄マスターのprivate local full sync

### 4.1 変更理由

bundled masterは36件の検索seedに限られ、J-Quants由来recordがローカルDBに存在していても情報基準日、取得範囲、完全性、所有sourceを確認できませんでした。利用者がキオクシア等を含む東証上場issueを検索対象へ追加できるようにしつつ、公開repositoryへprovider datasetを同梱・再配布せず、不完全取得やhistorical取得で既存の現行masterを破壊しない同期境界が必要でした。

### 4.2 source・scope・配布境界

- 完全な銘柄一覧は利用者自身のJ-Quants契約・`JQUANTS_API_KEY`で取得し、git管理外のprivate local DBへだけ保存します。APIキー、full response、全銘柄CSVをpublic repository、browser、通常logへ出しません。
- J-Quants個人版は個人の私的利用等の契約条件があるため、利用者自身がplan/最新規約を確認します。取得データまたはdata-backed serviceを第三者へ配信せず、公開するrepositoryはデータ/APIキーを含まないlocal-use codeだけとします。public hostや第三者向け提供には別途適切な契約・許諾が必要です。
- scopeは`source_scope=tse_listed_issues`です。J-Quantsの上場銘柄masterが返す東証上場issueを対象とし、普通株に加えてETF、REIT、優先株等もprovider responseに含まれる限り除外しません。
- 「全日本銘柄」「国内全取引所」を保証しません。名古屋・福岡・札幌等の地方取引所単独銘柄はscope外になり得ます。
- bundled `data/security_master_jp.csv`の36件は初期検索用seedです。full datasetの代替ではなく、insert-onlyで既存J-Quants metadataを上書きしません。
- `source_as_of`はproviderが示す情報基準日で、利用者planにより遅延し得ます。`synced_at`はローカル取込時刻で、リアルタイム性の証明ではありません。

### 4.3 code・pagination・取得境界

- numeric 5桁末尾`0`の普通株codeだけを既存互換の4桁identifierへ正規化し、raw codeを`local_code`へ残します。非zero suffixの5桁numeric codeは優先株等の別issueとして保持し、英数字identifierもraw値を維持します。
- 異なるraw provider codeが同じ正規化identifierへ衝突した場合は、priorityで片方を捨てたりsilent overwriteしたりせず同期を失敗させます。
- ordinary/preferred等のidentity split候補では、`security_master.ticker_code`を参照する全外部キーをDB metadataから確認し、参照recordがあれば自動rename/merge/upsertを行わずDB変更前に失敗させます。参照がない候補だけを通常upsertで修復します。
- paginationを全pageたどり、pagination key循環とsafe page上限をfail closedにします。429は`Retry-After`を尊重する最大2回のbounded retryだけを行います。
- providerの`Date`を`source_as_of`へ、明示的な`ListingDate` / `ListedDate`だけを`listed_date`へ保存し、snapshot基準日を上場日として誤記録しません。
- timeout/network/invalid JSONはprovider/transport raw detailを含まない分類済みerrorへ、HTTP errorはstatusだけを含むerrorへ変換し、provider response bodyをAPI/browser/CLIへ出しません。

### 4.4 complete/current/historical・所有source

- 現行snapshotは、本番4,000件以上で、全recordの非nullな`source_as_of`が1日へ一致する場合だけcomplete候補です。同期前のactive J-Quants件数と支配的legacy cohort件数の合算基準から5%を超えて縮小する場合もDB変更前に拒否します。不完全、空、基準日不整合、過大縮小ではJ-Quants master変更を適用しません。
- 完全な現行snapshotだけが、取得集合に存在しない`master_source=jquants` recordをinactiveへ変更できます。manual、local-seed、所有元未採用legacy recordを自動deactivateしません。
- historical同期は現行recordのactive状態を上書きせず、欠落deactivationを行わず、最新complete/current statusを置き換えません。historicalのcomplete判定では`source_as_of=target_date`も検証します。
- 旧importerがprovider snapshot `Date`を`listed_date`へ誤格納した支配的legacy cohortは、activeなlegacy recordの同一非null date最頻cohortが本番floor 4,000件以上の場合だけ検出します。検出時の通常API/UI current同期はfail closedとし、current syncの`python scripts/sync_security_master.py --adopt-legacy`だけで明示reconcileします。`--as-of`との同時指定は拒否し、無関係なmanual/local-seed/別date legacyを採用しません。
- `security_master_sync_run`へsync ID、source/scope、情報基準日、同期時刻、complete/current区分、取得/永続化件数だけを保存します。

### 4.5 API・画面契約

- `GET /securities/search`は同期済みDBだけで英数字codeをcase-insensitiveに照合し、ticker完全一致、raw/local code完全一致、各prefix、名称、marketの既存priorityを維持します。返却identifierは登録済みprimary codeで、優先株等の別issueを普通株へ縮約せず、候補ごとのJ-Quants profile callを行いません。
- `GET /securities/master/status`を追加し、最新complete/current runのscope、`source_as_of`、`synced_at`、complete、ローカル有効件数、J-Quants有効件数をcredentialなしで返します。
- `POST /securities/master/sync`は取得、新規、更新、再有効化、無効化、ローカル/J-Quants有効件数を分けます。`upserted_count=inserted_count+updated_count`で、seed件数とJ-Quants件数を重複加算しません。
- dashboard buttonを`東証全銘柄を同期`へ変更し、`require_jquants=true`で実行します。同期前/取得中/完全/未確認/errorを分け、情報基準日、同期時刻、各件数を表示します。
- key未設定やconnector error時、required同期はHTTP 400です。optional APIだけが36件seedを`source=local_seed`、`complete=false`で返し、全件同期成功とは表現しません。
- 通常UI/APIは支配的legacy cohortや参照付きidentity splitを検出するとsafe errorで停止します。provider response body、transport detail、credentialを画面へ出しません。

### 4.6 互換性・非対象・既知制約

- 既存の検索、portfolio alias、canonical/legacy AI契約を維持します。full master同期はAI request内の市場context取得ではありません。
- master primary keyの一括migration、地方取引所専用connector、full dataset export/配布、定期background同期、APIキーの共有は実装しません。
- provider rate limit、network、plan entitlement、endpoint変更により同期は失敗し得ます。bounded retry後は既存masterを維持し、別sourceへ暗黙fallbackしません。
- 本番4,000件/5%縮小guardは正当な大幅減少でも安全側に停止し得ます。UIから閾値を緩和せず、参照付きidentity splitの専用migrationもこの変更には含めません。
- CLI `--dry-run`はmaster同期transactionをrollbackしますが、先行する`init_db()`のschema初期化・migrationと不足36件seed bootstrapは永続化され得るため、DB全体のread-only保証ではありません。
- PostgreSQL/SQLiteの既存DBへprovenance列とsync-run tableを追加しますが、正式なmigration framework導入はこの変更の対象外です。

### 4.7 受け入れ確認

- ordinary/preferred/alphanumeric code保持、source/listing date分離、pagination guard、429 retry、provider body/transport detail非露出をconnector testで確認します。
- production floor 4,000、5%縮小guard、incomplete currentの無変更、complete currentだけのJ-Quants所有record deactivate、historical保護、支配的legacyの通常同期拒否/明示採用、参照付きidentity split拒否、seed insert-onlyをservice testで確認します。
- status/sync APIのcomplete/incomplete、required failure、optional seed fallback、各count、credential非露出をAPI testで確認します。
- DB-only検索でprovider callが起きないこと、dashboardが同期状態、情報基準日、J-Quants/ローカル件数、取得/新規/更新/再有効化/無効化を表示し、safeな失敗を成功表示しないことをtestで確認します。

## 5. SC-2026-08-18-01 — 銘柄検索から保有入力への導線とJ-Quants code alias

### 5.1 変更理由

dashboardの銘柄検索結果は詳細画面を開くだけで、見つけた銘柄を保有入力へ引き継げませんでした。キオクシアホールディングスは登録済みJ-Quants masterではraw identifier`285A0`として存在し、公開コード`285A`をportfolioフォームへ直接入力すると、別のplaceholder masterを作る可能性もありました。検索可能であることと、検索結果から安全に保有登録へ進めることを同じ導線で成立させる必要がありました。

### 5.2 変更前

- `GET /securities/search`は登録済みmasterの銘柄名、ticker/local codeを検索できましたが、dashboardの案内は「銘柄名か4桁コード」で、英字コードを検索できることが伝わりませんでした。
- dashboardの検索結果actionは`詳細を見る`だけでした。
- Portfolio panelの入力フォームは検索と独立し、利用者が銘柄identifierを手入力する必要がありました。
- `POST /portfolio`は入力tickerの完全一致だけをmasterへ照合し、`285A`と既存raw identifier`285A0`を同一銘柄として解決しませんでした。

### 5.3 検索・画面導線

- 検索labelを`銘柄名か銘柄コード（数字・英字）で検索`、placeholderを`7203 / 285A / トヨタ / キオクシア`へ変更します。
- 各検索結果に`保有入力へ`と`詳細を見る`を別buttonで表示します。
- 英字を含む5文字末尾`0`形式では、検索結果のcode表示と`保有入力へ`のprefill値を公開4文字へ変換します。キオクシアのraw `285A0`は`285A`と表示・入力します。
- buttonのdata属性と`詳細を見る`のURLには検索responseのraw `ticker_code`を維持し、登録済みmasterのdetailを正確に開きます。
- この操作だけでは保存せず、数量を入力して`保有を保存`を押す必要があることをfeedback表示します。数量は必須、平均取得単価とメモは任意です。
- `詳細を見る`の既存action、watchlist、canonical個別銘柄AI検索は変更しません。

### 5.4 portfolio identifier alias

- `POST /portfolio`はtrim・大文字化した入力と`security_master.ticker_code`の完全一致を最優先します。
- 完全一致がなく、入力が4文字の数字・英字コードの場合だけ、`<入力>0`に一致する`ticker_code`または`local_code`を候補にします。
- 候補が一意な場合だけ、その既存masterの`ticker_code`へ解決します。候補が0件または複数件なら別の既存銘柄へ推測解決しません。
- 例として、`285A`は一意な既存master`285A0`へ解決し、`285A`のplaceholder masterを重複作成しません。既存5文字identifier`285A0`の直接入力も受理します。
- aliasはportfolio登録境界だけに限定し、検索responseは登録済みmaster identifierを返します。公開4文字への短縮はdashboardの表示・入力境界だけで行います。

### 5.5 互換性・非対象

- `/securities/search`、`POST /portfolio`のrequest/response schemaと既存5文字入力を維持します。
- legacy/canonical AI、watchlist、detail、J-Quants同期endpointの契約は変更しません。
- `security_master` primary key、既存参照recordを4文字へ一括変換するmigrationは行いません。
- J-Quants connector全体の4文字canonical化は行いません。
- 検索結果から数量を推測し、ワンクリックで保有登録する機能は追加しません。

### 5.6 受け入れ確認と既知制約

- 銘柄名と`285A`の両方でキオクシアホールディングスを検索できることを確認します。
- UI shellで`保有入力へ`/`詳細を見る`、prefill、scroll、数量focus、非自動保存のfeedbackを確認します。
- `POST /portfolio`で`285A`が既存`285A0`へ紐付き、`285A`のplaceholderを作らないこと、`285A0`直接入力を維持することを確認します。
- master identifier自体とportfolio responseは5文字のまま残り得ます。dashboard検索結果と保有入力は公開`285A`、detail actionとAPIのraw identifierは`285A0`という境界を維持します。

## 6. SC-2026-08-17-04 — legacy stock-review quota・usage・概算額

### 6.1 変更理由

dashboardで5銘柄の軽量scanを少数回試した際、アプリ内日次上限50回へ到達した表示が出ました。現行counterは銘柄数ではなく成功review単位でしたが、fake OpenAIを使うunit testがrepositoryの`data/ai_review_usage.json`を共有し、本物のOpenAI APIを呼ばずcounterを増やしていました。また、1成功reviewとprovider Responses API call、token使用量、月間概算を区別できず、UIの`database`表示もquotaの保存先と誤認し得る状態でした。

### 6.2 quotaとcount定義

- legacy stock-reviewの`OPENAI_DAILY_REQUEST_LIMIT`既定値を50から300へ変更します。
- quota対象の`review_runs`は、銘柄数に関係なく正常完了したtop-level live一括review 1件を1回とします。5銘柄をまとめた1 requestも1回です。
- mock、forced mock、cache hit、`prompt_only`、API key不足、target上限拒否、日次上限拒否、OpenAI error、最終parse失敗は`review_runs`を増やしません。raw output fallbackを含むsuccessは1回です。
- provider usageを取得できたResponses responseは`api_calls`へ別に記録します。primary response、JSON整形repair、後段parseに失敗したresponseを含み得るため、`api_calls > review_runs`になり得ます。
- 日次quotaは`review_runs`だけを使い、provider call数、Web検索数、銘柄数を混ぜません。
- 300回は成功reviewの運用上限で、provider call数または費用のhard capではありません。OpenAI error/最終parse失敗は`review_runs`を消費せず、repair等で1 reviewから複数provider callが生じ得ます。
- このquota/usageはlegacy `/api/ai/stock-review`、`/portfolio/ai-review`、`/api/portfolio/ai-review`の共有serviceだけに適用します。canonical `/api/ai/analyses`は対象外です。

### 6.3 usage v2 ledgerとAPI

- `app/services/ai_usage.py`がgit管理外の`data/ai_review_usage_v2.json`を管理します。
- ledger rootは`version=2`、`timezone=Asia/Tokyo`、`scope=legacy_stock_review`、`pricing_catalog`、`days`を持ちます。
- 日別bucketは`review_runs`、`api_calls`、input/cached input/output/reasoning token、実Web検索call、概算USD、未算定call、pricing versionを持ちます。
- 更新はprocess内`RLock`と、同一directoryのtemporary fileをflush/fsync後に`os.replace`する方式です。
- 旧`data/ai_review_usage.json`はtest汚染の可能性があるため移行しません。`incomplete_pre_v2_history=true`により、v2開始前の回数・金額が当月集計へ含まれないことを明示します。
- `GET /api/ai/stock-review/usage`は`PortfolioAiUsageSummary`としてscope、timezone、daily limit、残数、JST当日・当月集計、pricing provenance、不完全履歴flag、正式請求優先flagを返します。responseは`Cache-Control: no-store`です。
- ledger、usage API、通常logへAPIキー、prompt、質問、回答、銘柄context、provider raw responseを保存または公開しません。

### 6.4 pricingと概算

- pricing versionは`openai-standard-2026-08-17`、as-ofは`2026-08-17`、currencyはUSDです。
- standard USD / 1M tokenは、gpt-5.4=`2.50 / 0.25 cached / 15.00 output`、gpt-5.5=`5.00 / 0.50 / 30.00`、gpt-5.6-terra=`2.00 / 0.20 / 12.00`です。
- gpt-5.4 / gpt-5.5 / gpt-5.6-terraはinput tokensが272,000を超えるとinput/cached inputを2倍、outputを1.5倍にします。
- 実際のWeb検索tool callはUSD 0.01/callを加算します。設定上限値ではなくprovider response outputの実callを数えます。
- reasoning tokenはoutput tokenの内訳として追跡し、価格へ二重加算しません。
- unknown model、token欠損/負値、cached token不整合では推測せず`unpriced_api_calls`へ記録します。
- 概算はprovider usageと公開standard priceによる参考値で、正式な請求額ではありません。Batch / Flex、契約割引、税、価格改定等を保証せず、OpenAI PlatformのUsage Dashboardと請求情報を正本とします。
- sourceはOpenAI Developersのgpt-5.4、gpt-5.5、gpt-5.6-terra model pageとAPI pricing pageです。

### 6.5 dashboard表示

- dashboard初期化時とPortfolio / Watchlist AI review終了時にusage APIを読みます。
- 本日は成功review数/300、残数、OpenAI呼出数、概算を表示し、今月も成功review数、OpenAI呼出数、概算を表示します。
- `unpriced_api_calls`があれば本日・今月の未算定件数をwarning表示します。
- 旧形式counterを移行しておらず、更新前の回数・金額を含まないことを表示します。
- 送信前のheuristicは「今回の事前概算」と表示し、provider token由来の事後概算と区別します。
- `holdings_source=database`等は「対象: 実DB保有銘柄」等へ変換し、quota種別や保存先に見えないようにします。
- usage表示の取得失敗はAI分析結果の成功・失敗と分離します。

### 6.6 cache・test隔離

- legacyのcache hitはOpenAIを呼ばず、review/API countを増やしません。cache contract自体は変更しません。
- unit testはusage/history/cache pathを一時directoryへ隔離し、開発者のrepository local dataを変更しません。
- quota、review/API count分離、JST日/月、pricing/long-context/Web fee、未算定、no-store、UI文言とsource labelを回帰testで固定します。

### 6.7 互換性と既知制約

- canonical `gpt-5.6-terra`、`STANDARD`、`reasoning.effort=medium`、`text.verbosity=medium`、`store=false`、plain output、保存結果分離は変更しません。
- legacy Prompt Registry、mode、Structured Outputs、mock、history、raw fallbackは維持します。
- process内lockは複数process/複数hostの厳密な分散quotaを保証しません。
- provider attemptのatomic reservation、失敗attemptを含むhard call budget、hard cost ceilingは未実装のfollow-upです。
- v2開始前の月間集計は復元せず、概算額は請求上限や請求額を保証しません。

## 7. SC-2026-08-17-03 — canonical AI安全性・保存結果分離・loopback既定・prompt 2026.08.18

### 7.1 変更理由

canonical個別銘柄AIでは、OpenAI Responses Application Stateの保存可否、AI回答生成の成否、ローカルDB保存の成否、保存回答readerの可用性を別の状態として扱う必要がありました。また、保存回答APIに認証・利用者分離がない現状で既定bindが全interface向けであること、DB初期化が複数経路から実行されること、prompt根拠ラベルの表記揺れを予防する必要がありました。

### 7.2 OpenAI requestの安全性

- canonical `OpenAIResponsesClient`は`responses.create()`へ`store=false`を必ず送ります。
- `previous_response_id`、background mode、Web検索、Structured Outputs、cache、mock、fallbackは追加しません。
- `store=false`はResponses APIのApplication State保存を無効化する設定です。HTTP responseの`Cache-Control: no-store`とは別であり、OpenAI API全体のZero Data Retentionを保証しません。abuse monitoring log等は組織のdata control設定に従います。
- model=`gpt-5.6-terra`、preset=`STANDARD`、`reasoning.effort=medium`、`reasoning.mode`未送信、`text.verbosity=medium`は変更しません。
- APIキー、prompt全文、質問、回答本文を通常logへ追加しません。

### 7.3 生成成功と保存結果の分離

- OpenAI生成成功は`status=success`と非空`answer_text`で表し、ローカル保存結果は`persistence_status=saved|failed`、`saved_at`、`persistence_warning`で独立して表します。
- 保存成功はHTTP 200、`persistence_status=saved`、非null`saved_at`、`persistence_warning=null`です。
- 保存失敗も生成が成功していればHTTP 200、`status=success`、非空`answer_text`、`persistence_status=failed`、`saved_at=null`、safeな定型warningを返します。
- 保存失敗時はtransactionをrollbackし、OpenAI APIを再呼び出しません。1ユーザー送信あたりのOpenAI callは最大1回です。
- 内部logにはrequest ID、OpenAI response ID、例外型などの安全な識別情報だけを記録し、質問、回答、prompt全文、APIキー、raw DB例外詳細を記録しません。
- `GET /api/ai/analyses/{request_id}`は保存済みrecordだけを返す現行仕様を維持します。保存失敗requestのGETはnot foundです。
- `/ui/analysis`は保存失敗時にも回答とwarningを表示し、保存済み表示、`saved_at`、reader linkを表示しません。保存成功時だけreader linkを表示します。

### 7.4 起動境界

- `API_HOST`と`scripts/run_api.py --host`の既定値を`127.0.0.1`へ変更し、既定ではローカルPCだけから接続できるようにします。
- LANまたはAndroid端末で確認するときだけ、利用者が明示的に`python scripts/run_api.py --host 0.0.0.0`を指定できます。
- `0.0.0.0`はLAN内の他端末から到達可能です。認証、利用者分離、rate limit、TLSがない現状では信頼できる閉じたnetworkに限定し、Internetへ直接公開しません。
- Android対応や外部公開の前に認証、HTTPS、rate limitを実装する必要があります。
- DB初期化の正本はFastAPI lifespanだけとし、`create_app()`は`init_db()`を呼びません。通常のapp起動1回につき初期化は1回です。
- TestClientはcontext managerでlifespanを起動し、DBを直接使うunit testはfixture側で明示的に準備します。

### 7.5 prompt 2026.08.18

- v2026.08.17 assetはimmutableな履歴として変更しません。
- active prompt versionを`2026.08.18`、compilerを`individual-security-v2`へ更新します。
- asset IDsは`common_os@2026.08.18`、`common_input_rules@2026.08.18-mvp1`、`execution_constraints_no_tools@mvp1`、`individual_comprehensive@2026.08.18`です。
- v2026.08.18 asset bytesはformal labelを持つv2026.08.17と同一で、asset SHA-256も同一です。v18 source titleは「株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）」、SHA-256は`B1C0AF5B2C33D76E4F836A428380237383FB7EAEA8B6FEAFFD9CC82632416D30`で、非送信`assets/v2026_08_18/SOURCE.md`を検証します。
- v2026.08.17原資料のtitle/hashは`revision.base_source`として保持し、v2026.08.17 assetを変更しません。
- v2026.08.18はruntime canonicalizationと旧括弧ラベルのstatic fail-closed検証を追加するreleaseです。
- active runtime contextとcompiled promptの根拠ラベルを`【V】確認済み`、`【E】推定`、`【U】未確認`へ統一します。旧括弧ラベルがactive compiled promptへ混入した場合はOpenAI APIを呼びません。
- prompt provenanceと保存recordはactive prompt version、compiler、asset IDs、source/compiled SHA-256を記録し、prompt全文を公開responseや通常logへ出しません。

### 7.6 互換性と非対象

- legacy `/api/ai/stock-review`、`/portfolio/ai-review`、`/api/portfolio/ai-review`、`portfolio_ai_review.py`、legacy Prompt Registry、legacy mock/cacheは変更しません。
- `PERSISTENCE_ERROR`はschema互換のため残りますが、OpenAI成功後の通常の保存失敗には使用しません。
- 認証、利用者分離、rate limit、HTTPSそのものは今回実装しません。
- 回答一覧、削除、export、保持期限、Web検索、Structured Outputs、background、streamingは追加しません。

### 7.7 受け入れ確認

- fake Responses APIでrequest kwargsの`store=false`、固定model/preset/reasoning/verbosity、`previous_response_id`とbackgroundの非送信を確認します。
- OpenAI成功・保存成功、OpenAI成功・保存失敗、OpenAI失敗を分けて確認します。
- 保存失敗でもHTTP 200と回答本文を返し、OpenAI callが1回、recordが0件、GETがnot found、安全なlogであることを確認します。
- UIは保存成功時だけreader linkを出し、保存失敗時は回答とwarningだけを出すことを確認します。
- app lifespan起動1回につき`init_db()`が1回であることをspyで確認します。
- active prompt version、compiler、asset IDs、正式根拠ラベル、旧括弧ラベル非混入、immutable v2026.08.17を確認します。

### 7.8 既知制約

- loopback既定は同一PC上の無認証アクセスを防ぐものではありません。
- 明示的に`0.0.0.0`へbindした場合、同じLANから保存回答APIへ到達できます。
- `store=false`だけではOpenAI API全体のZero Data Retentionを保証しません。
- 保存失敗した回答は現在画面にだけ表示され、readerで再表示できません。

## 8. SC-2026-08-17-02 — canonical AI回答保存・大型表示・prompt v2026.08.17

### 8.1 変更理由

canonical個別銘柄AIの回答を生成直後の画面だけでなく再表示でき、長文を大きな読み取り専用画面で確認できるようにする必要がありました。同時に、添付prompt sourceの最新版に含まれる銘柄名・コード併記規則を、既存の最小prompt構成を広げず反映します。

### 8.2 変更前

- `POST /api/ai/analyses`の成功回答はbrowserへ表示するだけで、canonical専用SQL recordを持ちませんでした。
- `/ui/analysis`の回答領域だけで表示し、別ウィンドウの大型readerはありませんでした。
- prompt sourceはv2026.08.16でした。

### 8.3 変更後

- 成功したPOSTは、同じ`request_id`で`AiAnalysisRecord`をローカルSQLへ自動保存します。
- 保存対象は質問、回答、銘柄snapshot、model/preset/reasoning設定、OpenAI response ID、prompt traceです。
- 保存commit失敗時はrollbackし、HTTP 500の`PERSISTENCE_ERROR`としてsuccessを返しません。
- `GET /api/ai/analyses/{request_id}`は保存済み成功回答をUUIDで1件取得します。未知recordは`ANALYSIS_NOT_FOUND`です。
- `/ui/analysis`の成功時に`別ウィンドウで大きく表示`を出し、`target="_blank"`と`rel="noopener noreferrer"`で`/ui/analysis/results/{request_id}`を開きます。
- 大型画面は保存回答APIから1件を取得し、質問と回答を`textContent` / `white-space: pre-wrap`で表示します。
- AI送信中は銘柄検索・選択と質問編集をロックし、応答待ちのrequest対象と表示対象を固定します。
- canonical APIはFastAPI validation errorを含め、HTML shellは各routeから`Cache-Control: no-store`を返します。

### 8.4 prompt更新

- sourceを「株判断プロジェクト｜定型プロンプト集 v2026.08.17」へ更新しました。
- 使用範囲は共通OS、必要な共通入力rule、no-tools実行制約、module 3.1だけで、3.2〜3.14やJSON Schemaは追加しません。
- 銘柄の表示・言及を原則「銘柄名（銘柄コード）」とし、共通入力で銘柄名と銘柄コードを分離します。
- model=`gpt-5.6-terra`、preset=`STANDARD`、reasoning effort=`medium`、text verbosity=`medium`、plain`response.output_text`は変更しません。

### 8.5 保存・秘密情報

- ローカルSQL recordは再表示とprompt trace相関の正本です。OpenAI側の保持をアプリ保存の代替にしません。
- APIキー、Authorization header、prompt全文、provider raw response / raw error、stack traceは保存しません。
- prompt traceはrecordへ保存しますが、公開API responseとbrowserへ出しません。
- 一覧、検索、削除、export、共有、保持期限、自動purge、認証・認可は追加しません。

### 8.6 互換性と受け入れ

- legacy stock-review endpoint、UI、mock/cache/Web/Structured Outputs/JSON fallbackは変更しません。
- canonical POSTの既存request fieldとplain-text回答を維持し、成功responseへ`saved_at`だけを追加します。
- POST保存正常/失敗rollback、GET正常/not-found/validation no-store、送信中の入力ロック、別ウィンドウlink、大型画面のloading/error/plain-text表示、v2026.08.17 asset選択を自動testで確認します。
- 実OpenAI確認では従来どおりcompleted status、response ID、非空output textを確認し、その成功recordを同じrequest IDで取得できることを確認します。

### 8.7 既知制約

- 保存recordにaccess controlとretention policyがないため、引き続きtrusted local環境限定です。
- request IDを知る利用者は保存回答を取得できます。Internetへ直接公開しません。
- 保存commitが失敗するとOpenAI利用分は発生済みでもresponseは失敗になります。暗黙retryは行いません。

## 9. SC-2026-08-17-01 — 個別銘柄AI最小縦スライスと定型prompt最小統合

### 9.1 変更理由

旧Portfolio AI経路はmulti-mode、Web検索、Structured Outputs、JSON解析、mock、cache、fallbackを同時に扱います。OpenAI APIとの最小通信経路を単独で切り分け、個別銘柄回答の品質をversioned promptで改善するには、より小さいcanonical経路が必要でした。

### 9.2 変更前

- 要件仕様 v1.1、API仕様 v1.4、画面仕様 v1.6は、主にdashboardのmulti-mode Portfolio AI分析を定義していました。
- `POST /api/ai/stock-review` では、mode別model、Web検索、Structured Outputs、JSON parse救済、mock/cache/historyを扱いました。
- 独立した個別銘柄1件のplain-text endpointと画面は、versioned仕様の正本に未記載でした。

### 9.3 変更後

- canonical endpointとして `POST /api/ai/analyses` を追加しました。
- 独立画面として `GET /ui/analysis` を追加しました。
- 対象はactiveな登録済み個別銘柄1件、入力は自由質問、回答設定は `STANDARD` 固定です。
- OpenAI Responses APIを1回呼び、`response.status=completed`、response ID、trim後に非空の `response.output_text` を満たす場合だけ成功とします。
- 回答はbrowserの `textContent` と `white-space: pre-wrap` でプレーンテキスト表示します。
- 新経路ではmock、cache、fallback、Web検索、Structured Outputs、JSON修復、再AI呼び出し、streaming、backgroundを使用しません。

### 9.4 model・回答設定

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

### 9.5 prompt変更

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

### 9.6 trace・秘密情報

- OpenAI metadataへ保存するのはprompt version、profile、compiler、module、asset ID、source SHA-256、compiled SHA-256だけです。
- prompt全文、質問全文、APIキーはOpenAI metadata、通常ログ、公開FastAPI response、browserへ出しません。
- 公開responseは `request_id` と、取得できた場合の `openai_response_id` を返します。
- 永続audit tableは未実装であり、長期追跡可能性はOpenAI metadataとログの保持期間に依存します。

### 9.7 互換性

- `POST /api/ai/stock-review`、`POST /portfolio/ai-review`、`POST /api/portfolio/ai-review` は変更しません。
- 旧 `app/prompts/stock_analysis/`、multi-mode、Web検索、Structured Outputs、mock、cache、history、raw output fallbackも旧経路に限って維持します。
- 新経路は旧経路のfallbackや設定を共有しません。
- 既存endpointの削除やdeprecationはありません。

### 9.8 非対象

- `LIGHT` / `HIGH` / `PRO` / `MAX`
- model選択UI
- 複数銘柄、市場全体、総合分析
- Web検索、J-Quants等の追加context取得
- Structured Outputs、JSON Schema、JSON修復
- Markdown renderer、構造化card
- mock、cache、fallback、streaming、background、polling
- prompt全14用途moduleの投入
- 旧Portfolio AI経路の削除・再設計

### 9.9 既知制約

- `POST /api/ai/analyses` にはアプリ独自の認証とrate limitがありません。
- `scripts/run_api.py` の既定hostは `0.0.0.0` で、アプリはTLSを提供しません。現状はtrusted local環境限定で、Internetへ直接公開しません。
- OpenAPI自動生成は現時点で実際の404 / 429 / 502 / 503 / 504 response modelを網羅していません。
- prompt manifestやasset構成異常はtyped `AiAnalysisError`ではなく、現状はHTTP 500になり得ます。
- promptへ渡す実データは主に銘柄masterであり、価格、決算、チャート、需給、市場、マクロ、イベント、保有条件は未提供です。そのため回答が `insufficient_data` / `no_trade` 寄りになる場合があります。
- 共通OSの標準出力は、情報が少ない質問では回答を冗長にする場合があります。

### 9.10 受け入れ確認

- compiler、OpenAI client、FastAPI endpoint、UI shellのunit testを維持します。
- 代表質問fixture 10件で、買い判断、決算後、要因分離、モメンタム、需給、イベント、リスク、反証、情報不足、no-tradeを比較できます。
- 実OpenAI確認ではcompleted status、response ID、非空output textを確認します。
- 実browser確認では、銘柄選択、質問入力、loading、成功回答、error非表示、plain-text描画を確認します。

## 10. 直前baseline

| 適用日 | 要件 | API | 画面 | 主な範囲 |
|---|---:|---:|---:|---|
| 2026-08-19 | v2.0 | v2.3 | v2.7 | SC-2026-08-19-05: Portfolio・複数named watchlist管理 |
| 2026-08-19 | v1.9 | v2.2 | v2.6 | SC-2026-08-19-04: legacy AI現在回答のclient-only別タブ大画面表示 |
| 2026-08-19 | v1.9 | v2.2 | v2.5 | SC-2026-08-19-03: legacy Structured Outputs JSONの安全でsemanticな可読表示 |
| 2026-08-19 | v1.9 | v2.2 | v2.4 | SC-2026-08-19-02: legacy stock-reviewの銘柄identityと名称・code併記 |
| 2026-08-19 | v1.8 | v2.1 | v2.3 | SC-2026-08-19-01: legacy軽量スキャンの構造化response契約と失敗分類 |
| 2026-08-18 | v1.7 | v2.0 | v2.2 | SC-2026-08-18-02: 東証/J-Quants上場銘柄マスターのprivate local full sync |
| 2026-08-18 | v1.6 | v1.9 | v2.1 | SC-2026-08-18-01: 銘柄検索から保有入力への導線とJ-Quants code alias |
| 2026-08-17 | v1.5 | v1.8 | v2.0 | SC-2026-08-17-04: legacy stock-review quota・usage・概算額 |
| 2026-08-17 | v1.4 | v1.7 | v1.9 | SC-2026-08-17-03: canonical AI安全性・保存失敗処理・prompt表記正規化 |
| 2026-08-17 | v1.3 | v1.6 | v1.8 | SC-2026-08-17-02: canonical AI回答保存・大型表示・prompt v2026.08.17 |
| 2026-08-17 | v1.2 | v1.5 | v1.7 | SC-2026-08-17-01: canonical個別銘柄AI最小縦スライスと定型prompt最小統合 |

直前baselineの完全な内容は各versioned fileに残します。新baselineは要件v2.1、API v2.4、画面v2.8で、legacy保存履歴の最大100件、metadata一覧、detail、Markdown export、browser印刷 / PDF表示を追加するSC-2026-08-19-06です。認証・利用者分離、履歴削除・全文検索・共有、server-side PDF生成、過去のnamed list名復元は追加しません。

## 11. 更新ルール

1. 要件、API、画面のどこが変わるかを特定する。
2. 過去版を保持し、影響するversioned fileの次版を追加する。
3. 変更理由、互換性、非対象、既知制約をこの文書へ追記する。
4. `python scripts/sync_current_files.py --write` を実行する。
5. 各 `current.md` の日付、変更概要、主な内容を手動確認する。
6. `python scripts/sync_current_files.py --check` を実行する。
7. 実装・運用・文書変更を `docs/changelog.md` へ追記する。
