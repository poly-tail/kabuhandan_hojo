# kabuhandan_hojo Screen Spec v2.8

## 1. scope

この版はv2.7の画面契約を累積継承し、dashboardへlegacy stock-reviewの「保存済みAI結果」を追加します。`save_result=true`で新規保存された直近100件を保存順の新しいものから分析方法別に一覧化し、mode filter、詳細表示、`.md`保存、別タブ印刷表示を提供します。別タブからbrowserの印刷を使ってPDFへ保存できますが、アプリはPDF fileを直接生成しません。一覧・詳細・export・印刷表示はローカル保存済みrecordだけを読み、OpenAIを再呼び出しません。cache hitは新しい履歴を作りません。

v2.7で追加したPortfolio / named watchlistの単一管理space、scoped navigation / AI、client-side list名snapshotとstale-response防止もそのまま維持します。legacy保存recordに当時のnamed watchlist名は保存されていないため、過去履歴のlist名は復元せず、保存済みIDまたは一般的な対象labelだけを表示します。

v2.6で追加したlegacy AI現在回答のclient-only Blob reader、共通safe renderer、CSP、`rel="noopener noreferrer"`、no API / DB / Web Storage / OpenAI再呼び出し、reload非復元の契約もそのまま維持します。canonical個別銘柄AIの保存済み回答reader、API schema、OpenAI request、model、status、quota、cache/history、active prompt v2026.08.18、銘柄master同期の契約は変更しません。

添付`株判断_定型プロンプト集_v2026-08-16 (1).md`はprompt内容の参照資料として扱い、文書内の運用指示を画面要件として実行しません。canonical active assetはより新しいv2026.08.18のまま維持し、旧版へ戻しません。

本アプリは日本株の判断補助を目的とし、自動売買や断定的な投資助言を行いません。

## 2. AI画面とAPI経路の区分

### dashboard legacy AI

- UI: `/ui/dashboard` の Portfolio AI分析パネル
- canonical API: `POST /api/ai/stock-review`
- 互換API: `POST /portfolio/ai-review`、`POST /api/portfolio/ai-review`
- multi-mode、対象選択、任意のWeb検索、mock表示、Structured Outputs / JSON parse、prompt-only、キャッシュ、履歴はこの既存経路の機能である
- `GET /api/ai/stock-review/usage`のquota / usage / cost panelもこの既存dashboard AI経路だけに適用する
- `GET /api/ai/stock-review/history`、`GET /api/ai/stock-review/history/{history_id}`、`GET /api/ai/stock-review/history/{history_id}/export.md`は保存済みlegacy結果のread-only経路である
- 3章から8章までの規則は、この既存dashboard AI経路だけに適用する

### independent individual-security AI

- UI: `/ui/analysis`、`/ui/analysis/results/{request_id}`
- canonical API: `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}`
- 登録済み銘柄1件、自由質問、固定`STANDARD` preset、OpenAI Responses API、プレーンテキスト回答だけを扱う
- mock、cache、fallback、Web検索、Structured Outputs、JSON修復、再AI呼び出し、background、streamingを使用しない
- 既存dashboard AIのstate、prompt、結果card、fallback規則を流用しない
- 9章から17章までの規則は、この独立経路だけに適用する

両経路は同じOpenAI API keyをサーバー側で利用し得ますが、画面とアプリケーション経路は独立しています。dashboard legacy AIの成功条件やfallbackを、independent individual-security AIへ適用してはいけません。

## 3. top screen

### market overview

- `GET /ui/dashboard/data` の `market_overview` を表示する
- live mode では `TOPIX(1306)` と `Nikkei225(1321)` の market proxy を使う
- proxy が取れない場合は `未取得` を表示し、疑似的な市場推定へ戻さない

### main sections

- priority items
- important alerts
- event feed
- 保有・ウォッチリスト管理space / AI分析パネル
- 保存済みAI結果
- 銘柄検索

### 保有・複数ウォッチリスト管理space

#### layoutとselector

- 従来のPortfolio panelとWatchlist panelを別columnへ常時並べず、`Management Space` / `保有・ウォッチリスト管理`の全幅sectionへ統合する。
- `表示するスペース`のnative `select`を置き、valueは`portfolio`または`watchlist:<collection_id>`とする。query parameterがないdashboard初期表示は`portfolio`である。
- Portfolio optionは`保有銘柄 (件数)`、watchlist optionは`list名 (item_count)`とし、defaultには`[既定]`を付ける。collection名はescapeして表示する。
- Portfolio選択時は保有header、評価価格更新、保有入力form、保有cardを表示する。watchlist選択時はこれらを隠し、選択list名、再評価、AI選択control、watchlist cardを表示する。
- AI分析controls、usage panel、prompt output、現在回答readerは管理space内の共通領域として維持し、Portfolio / named listのどちらからも利用できる。
- selector変更時はAI targetをPortfolioなら`holdings`、named listなら`watchlist`へ揃え、対象件数と事前概算を更新する。

#### collection操作

- `新しいリスト`はPortfolio / watchlistのどちらを表示中でも利用できる。inline formへ最大80文字のlist名を入力し、作成成功後は新しいlistへ切り替える。
- watchlist表示時だけ`名前変更`と`リスト削除`を表示する。名前変更は同じinline formへ現在名を入れ、成功後も同じcollectionを表示する。
- default collectionは名前変更できるが削除できない。default表示時の削除buttonはdisabledとし、tooltipで`既定のウォッチリストは削除できません。`と説明する。
- non-default削除前はnative confirmで、保有銘柄と他listへ影響しないことを明示する。成功後はdefault listへ切り替え、defaultが解決できない例外時だけPortfolioへ戻る。
- blank、重複、通信失敗、not found等は`management-space-feedback`へsafeなerrorとして表示する。API detailやcollection名を未escape HTMLとして挿入しない。
- named listはundo / trashを持たない。削除してもPortfolioと他listのmembershipは維持する。

#### item、検索、選択state

- selected named listのitemが0件なら`このウォッチリストは空です。銘柄検索から追加できます。`と表示し、mock itemを補完しない。
- 銘柄検索結果では既存`保有入力へ`と`詳細を見る`を維持する。named list表示中だけ、`「list名」へ追加`buttonまたは同listの`登録済み`disabled stateを追加する。
- 追加時はraw master ticker、名称、市場を`POST /watchlists/{collection_id}/items`へ送り、成功後に同じlistのdashboard dataを再取得する。
- watchlist cardの`リストから外す`は`DELETE /watchlists/{collection_id}/items/{ticker_code}`を呼び、そのmembershipだけを解除する。Portfolioと他listを削除しない。
- cardのmemo / thesisはsecurity-level共有値で、list固有値のように表示・説明しない。あるlistまたはdetailで保存した変更は、同tickerを含む他listにも反映される。
- AI分析checkbox、全選択、選択解除はcollection IDごとのbrowser-memory `Set`で分離する。dashboard data再取得後は現在listに存在しないtickerを除き、別listの選択を混ぜない。Web Storageへ永続化しない。
- active named listで1件以上checkすると共通AI targetを`選択銘柄`へ自動変更する。全解除時はmanual ticker入力がなければ`監視銘柄`へ戻す。manual tickerがある場合は利用者のselected targetを保持する。

#### dashboard、detail、chart、AIのscope

- named list選択時は`GET /ui/dashboard/data?watchlist_id={id}`を呼び、選択listのitem、Focus Board、alerts等を表示する。Portfolio選択へ戻る場合はPortfolio UIを即時再表示した上で、`watchlist_id`なしのdashboard dataを再取得してdefault monitoring scopeへ戻し、named list由来のFocus Board / alertsを残さない。
- 検索はnamed list選択中だけ`GET /securities/search?...&watchlist_id={id}`を使い、`in_watchlist`をそのlistへscopeする。
- 同時に複数dashboard requestが進行した場合はrequest IDとrequest開始時のrequested `watchlist_id`を保持する。response時点のactive management scopeと両方が一致しないresponseを破棄し、後から返った旧listのdataで現在表示を上書きしない。
- `/ui/dashboard?watchlist_id={id}`から開いた場合はそのnamed listを初期表示し、共通AI targetも`監視銘柄`へ初期化する。queryなしはPortfolio / `保有銘柄`を既定とする。
- named listから銘柄detailを新しいtabで開くURL、detailからchartへ進むURL、chartからdetailへ戻るURLは`?watchlist_id={id}`を維持する。detailの`一覧へ戻る`も同じquery付きdashboardへ戻す。
- named list contextのdetail画面で`watchlistに追加`または仮説cardを保存する場合は`POST /watchlists/{id}/items`を使う。Portfolio contextではqueryを付けず、従来の`POST /watchlist` default互換を使う。
- named listへ切り替えた共通AI controlsは`target=watchlist`と`watchlist_id={id}`を送る。明示named listが空または削除済みなら`no_holdings`を表示し、テスト用仮保有銘柄へfallbackしない。
- AI実行開始時にactive collection名をclient-side context snapshotとして保持する。loading text、結果summaryのtarget chip、別タブ / 別ウィンドウreader titleはこのsnapshotを使い、実行中または実行後のrename / selector切替で別list名へ差し替えない。snapshotはAPI、DB、history、cache、Web Storageへ保存しない。
- selector切替、collection作成、active collection削除、active membershipの追加・解除、checkbox / 全選択 / 全解除では、現在のAI result、prompt output、reader actionをidleへ戻す。進行中AI requestはclient request IDを進めて後続responseを破棄し、同じ操作を理由にcancel APIや追加OpenAI callを行わない。
- AI現在回答の構造化表示とBlob readerはv2.6の条件・安全規則を維持する。list切替自体でOpenAIを呼び直さず、quota / usageを増やさない。

#### privacy boundary

- collection、membership、memo / thesisに利用者identityを表示・保存しない。現行は認証・利用者分離のないapp-global dataである。
- 既定bindはloopbackで、trusted local環境だけを前提とする。LANで明示公開した場合、同じnetworkから全named listへ到達できるためInternetへ直接公開しない。

### 銘柄検索から保有入力

- 検索labelは`銘柄名か銘柄コード（数字・英字）で検索`とする。
- placeholderは`7203 / 285A / トヨタ / キオクシア`とし、数字4桁だけを検索可能範囲として案内しない。
- 検索結果1件ごとに、`保有入力へ`と`詳細を見る`を別buttonで表示する。
- `詳細を見る`は従来どおり該当tickerのdetail画面を開く。
- 検索responseの`ticker_code`が英字を含む5文字末尾`0`形式の場合、結果のcode表示は末尾`0`を除いた公開4文字とする。例:`285A0`は`285A`と表示する。
- `保有入力へ`は同じ公開4文字codeをPortfolio panelの銘柄コード欄へ反映し、フォームを表示領域へscrollして数量欄へfocusする。
- buttonのdata属性と`詳細を見る`のURLは検索responseのraw `ticker_code`を維持する。detail対象を存在しない公開4文字keyへ置換しない。
- `保有入力へ`を押しただけではAPIへ保存せず、`数量を入力して「保有を保存」を押してください。`とfeedbackを表示する。
- 数量は必須、平均取得単価とメモは任意とし、利用者が`保有を保存`を押した場合だけ`POST /portfolio`を呼ぶ。
- 銘柄名、銘柄コード、marketはHTML文字列として挿入せず、既存のescape処理を維持する。
- 検索結果は同期済みローカルDBだけから描画し、query入力や候補描画のたびにJ-Quantsへprofileを外部照会しない。DBにない銘柄を外部callで一時補完しない。
- watchlist 未登録の高スコア候補

### 東証/J-Quants銘柄マスター同期

- 銘柄検索領域の更新buttonは`東証全銘柄を同期`と表示し、`POST /securities/master/sync?require_jquants=true`を呼ぶ。
- 「東証全銘柄」はJ-Quants上場銘柄マスターが返す東証上場issueを意味し、普通株に加えてETF、REIT、優先株等をprovider responseに含まれる限り対象とする。名古屋・福岡・札幌等の地方取引所単独銘柄の網羅を示す文言は使わない。
- dashboard初期化時に`GET /securities/master/status`を読み、取得中は`東証銘柄マスターの同期状態を確認しています...`を表示する。
- status取得失敗は検索・他panelの状態と分離し、`同期状態を取得できませんでした: ...`をerror toneで表示する。credentialやserver stackを表示しない。
- `complete=false`では、`東証全件同期は未確認です`、ローカル有効銘柄件数、同期buttonの実行とJ-Quants APIキー確認を案内する。36件seedまたは任意のlocal recordを全件同期済みとは表示しない。
- `complete=true`では、J-Quants由来有効件数、ローカル有効件数、`source_as_of`、`synced_at`を同じstatus領域へ表示する。
- `source_as_of`は`情報基準日`、`synced_at`は`同期`として別labelにする。利用者のJ-Quants planにより情報基準日が遅延し得るため、同期時刻を最新市場情報の時点として表示しない。
- 同期中はbuttonをdisableし、`J-Quantsから東証全銘柄を同期しています...`を表示する。
- 成功時は取得、新規、更新、再有効化、無効化の件数を個別に表示し、status APIを再取得する。検索queryが入力済みなら同期後に検索結果も再取得する。
- 成功表示は本番4,000件以上、単一情報基準日、既存J-Quants/支配的legacy基準から5%以内の縮小を通過したcomplete current responseだけにする。形式上4,000件以上でも縮小guardに失敗したresponseを件数付き成功として表示しない。
- 旧importer由来の4,000件以上の支配的snapshot-date legacy cohortが検出された場合、通常の同期buttonはfail closedのままとし、safe errorに示される`python scripts/sync_security_master.py --adopt-legacy`の明示操作が必要であることを案内する。画面からlegacy採用を暗黙実行するbuttonは設けない。
- ordinary/preferred等のidentity split候補にwatchlist、保有、価格等の外部キー参照がある場合も失敗表示とし、自動rename/mergeや片方を捨てる修復UIを出さない。
- 失敗時はmanual update共通feedbackの`取得できませんでした`に対象labelとsafeなAPI errorを表示し、status APIを再取得する。timeout/network/invalid JSONは安全な分類だけ、HTTP errorはstatusだけを使用し、provider response body、transport例外detail、APIキーを表示しない。36件seed、古いローカルrecord、別sourceへ暗黙fallbackして成功表示しない。
- 画面へAPIキー、full provider payload、全銘柄一覧、local DB pathを表示しない。完全なdatasetは利用者のgit管理外ローカルDBだけに保存する。

## 4. dashboard legacy Portfolio AI分析パネル

### controls

AI分析パネルは次の入力を持つ。

- AI分析モード
  - 軽量スキャン
  - 個別詳細分析
  - 全体売買判断
  - 重要局面分析
- AI分析対象
  - 保有銘柄
  - 狙い中銘柄
  - 監視銘柄
  - 選択銘柄
  - テスト用仮保有銘柄
- 選択銘柄コード入力
- Web検索最大回数
- 建玉意図
- ユーザー仮説
- Web検索ON/OFF
- APIなしのサンプル表示
- 結果保存
- 前回結果の再表示

対象が `テスト用仮保有銘柄` の場合、OpenAI APIは呼ばない。推定コストは0として表示し、Web検索チェックもOFFにする。

管理spaceがPortfolioの場合、AI targetの初期値は`保有銘柄`である。URL queryまたはselectorでnamed watchlistを表示した場合は`監視銘柄`へ変更し、requestへactive collectionの`watchlist_id`を付ける。利用者がその後targetを別値へ変更した場合は既存target controlを尊重する。ただし、active listのcheckboxを1件以上選択した時は`選択銘柄`へ自動変更し、全解除時にmanual tickerがなければ`監視銘柄`へ戻す。`target=watchlist`を送るときは画面が保持するactive collection IDを使う。明示named listが空なら対象件数を0として事前概算し、実行結果は`no_holdings`で、mock cardへ置き換えない。

### usage panel

Portfolio AI分析のcontrolsより上に、`id=stock-ai-usage`の「アプリ内利用量（legacy stock-review）」panelを表示する。

- `stock-ai-usage-today`: `本日 成功レビュー x / 300回・残り y・OpenAI呼出 z回・概算 $...`
- `stock-ai-usage-month`: `今月 成功レビュー x回・OpenAI呼出 z回・概算 $...`
- `stock-ai-usage-unpriced`: 未算定callがあるときだけ`金額未算定のAPI呼び出し: 本日 x回・今月 y回`
- `stock-ai-usage-history-note`: `incomplete_pre_v2_history=true`のときだけ「旧形式のカウンターは新集計へ移行していません。更新前の回数・金額は含まれません。」
- 常設注記: 「1回＝正常完了した一括レビュー1件（銘柄数に関係なし）です。この集計は旧stock-review経路だけが対象です。金額はtoken使用量に基づく概算で、正式な請求額ではありません。OpenAI PlatformのUsage Dashboardを正本として確認してください。」

dashboard初期化ではdashboard dataとusageを並列取得する。Portfolio reviewとWatchlist reviewの完了時は、成功・error・日次上限のいずれでもusageを再取得する。usage API取得失敗は「本日/今月の利用量を取得できませんでした」とpanel内へ表示し、AI分析結果自体を失敗へ変更しない。

日次quotaは構造化まで成功したlegacy live reviewの`review_runs`を使う。5銘柄一括reviewも1回であり、mock、cache hit、prompt-only、limit拒否、`status=json_parse_failed`のraw output救済は回数を増やさない。provider `api_calls`は別集計で、JSON repair等によりreview回数より多くなり得る。したがって失敗cardを表示した実行でもOpenAI呼出数と概算額は増え得る。

### action buttons

- `軽量スキャン`
- `個別詳細分析`
- `全体売買判断`
- `重要局面分析`
- `ChatGPT投入用プロンプトを生成`
- `プロンプトをコピー`

`ChatGPT投入用プロンプトを生成` は OpenAI API を呼ばず、手動コピペ用の全文プロンプトを生成する。通常のAI分析ボタンでは、プロンプト欄にユーザーが入力しなくても Prompt Builder が毎回テンプレートを自動適用する。

## 5. dashboard legacy AIのワンクリック実行

保有銘柄全体の判断は、次の条件で実行できる。

1. 対象が `保有銘柄`
2. `全体売買判断` ボタンを押す
3. request は `mode=judge` / `target=holdings` として送信される
4. `user_hypothesis` が空の場合は `未入力` として扱う
5. Prompt Builder が Base Policy と judge mode の章を自動適用する

高コスト条件に該当する場合は実行前に確認ダイアログを表示する。送信前のheuristic estimateは`今回の事前概算 $... / n銘柄`と明記し、usage panelのprovider token由来の事後概算と混同しない。Web検索の事前概算単価は1 callあたりUSD 0.01とする。

## 6. dashboard legacy AIのWeb検索表示

- `analyst` / `judge` / `critical` ではWeb検索ONを標準とする
- `scanner` はWeb検索OFFでも実行できる
- Web検索OFFの場合は warnings に「最新Web確認なし」を表示する
- API側の `web_search_policy` をchipとして表示する
- `actual_usage.web_search_calls` があればprovider responseで確認した実Web検索回数を`Web検索 n回`のchipとして表示する

## 7. dashboard legacy AIの結果・エラー表示

### summary card

- mode label
- generated_at
- portfolio summary
- model
- reasoning effort
- web_search_policy
- 今回の事前概算
- cache hit
- holdings sourceの利用者向けlabel
- top risks
- action plan
- critical warnings
- warnings
- sources

### stock card

- ticker / name
- judgement / judgement_label
- confidence
- needs_detail_analysis
- needs_analyst_mode
- needs_judge_mode
- verification_labels
- time_horizon_views
- short_reason
- key_risks
- key_points / watch_points
- technical_view
- news_view
- market_context_view
- supply_demand_view
- holder_action
- buy_more_condition
- take_profit_condition
- stop_or_reduce_condition
- invalidation
- next_price_levels
- bullish_case / base_case / bearish_case
- expected_value_view
- position_size_risk
- event_risk
- gap_risk
- decision_deadline
- what_would_change_my_mind
- final_recommendation_for_holder
- uncertainty_notes
- execution_plan
- critical_check
- risks
- sources

`scanner`のOpenAI生成契約は軽量schemaを使う。runtime modelが詳細mode用fieldへ空値または既定値を補っても、確認済みの分析材料として強調しない。`judgement`はcanonical codeを利用者向け`judgement_label`へ変換して表示する。

### Structured JSONの可読表示

legacy stock-reviewの成功responseは、OpenAIが返したMarkdown文書ではなく、mode別schemaで検証済みのStructured Outputs JSONである。画面はJSONを1本の文章へ連結せず、既知fieldを次の意味単位へ明示的に対応付ける。

- summary header: mode、生成時刻、model、reasoning、Web検索、事前概算、対象、cache、risk、market temperature
- 全体所見: `portfolio_summary.overall_view`をsummary冒頭の主要callout
- リスク: `top_risks`を見出し付き箇条書き
- 行動: `action_plan_today`とtop-level `action_plan`を、それぞれ内容を表す見出し付き箇条書き
- 銘柄候補: 縮小、core、入れ替え等の各fieldを独立した見出しと箇条書き
- 注意: `critical_warnings`を重要警告callout、通常`warnings`を警告callout
- portfolio補足: 資金配分、集中risk、全体の反証条件を独立した見出しと本文
- stock card: 銘柄identityと判断をheaderに置き、短評、時間軸、注目点、risk、technical、材料、地合い、需給、執行条件、scenario、反証条件、不確実性を意味別section
- sources: 回答本文とは分けた参照情報section

各sectionは利用者向けの日本語見出しを持ち、配列はsemanticな`ul` / `li`として表示する。未入力、空文字、空配列、空objectだけのsectionはDOMへ出さない。文字列化した`undefined`、`null`または見出しのない連続listを表示しない。同じ表示list内でtrim後に完全一致する項目は初出だけを残すが、表現が異なる主張を類似判定で削除しない。

Portfolio保有分析とWatchlist分析は、同じsummary、stock、list、callout、sourceの表示helperを利用する。両経路で利用可能field数が異なる場合も、存在するfieldだけを同じ見出し、順序、安全規則で表示し、一方だけが旧式の平坦な表示へ戻らない。

### 根拠labelと安全な文字列表示

- model、cache、history由来の文字列はすべてescapeしたtextとして挿入し、`innerHTML`へ未加工で渡さない。
- `#`、`##`、`**`、backtick、Markdown link、HTML tag等を含む文字列も汎用MarkdownまたはHTMLとして解釈・実行しない。
- 正式な根拠label`【V】`、`【E】`、`【U】`を認識した場合は、確認済み、推定、未確認の文字labelを伴うbadgeとして視認できる。色だけで意味を伝えず、screen readerでもlabelを判別できるようにする。
- 根拠markerを本文から分離する場合も、同じ意味をbadgeのtextまたはaccessible nameに残す。未知の括弧labelをCSS classやHTML属性へ転用せず、通常textとして扱う。
- source URLをclickable linkにするのは、URLとして解析でき、許可した`http:`または`https:` schemeの場合だけとする。`javascript:`、`data:`、`file:`、`app:`、不正URLはlinkにせず、escapeしたsource名またはURL textとして表示する。
- 新しいtabでsourceを開く場合は`rel="noopener noreferrer"`を付ける。

### raw fallback、responsive、accessibility

- `status=json_parse_failed`と`raw_model_output`は成功用の構造化cardへ変換しない。従来どおり赤いerror cardで失敗分類を示し、必要に応じてnativeな`details` / `summary`内のescape済みplain `pre`として確認できるようにする。
- raw fallbackの画面表示は先頭20,000文字までに制限できる。省略した場合は「画面は先頭20,000文字」と「全文は『Markdown保存』で確認できます。」を明示し、全文を短縮した事実を隠さない。
- raw fallbackをMarkdown、HTML、成功JSONとして再解釈せず、表示のためにOpenAIを追加callしない。
- heading level、list、`details` / `summary`、callout labelをsemanticに構成し、keyboardだけでも順番に閲覧できるようにする。重要警告、推定、未確認を色だけで区別しない。
- 狭い画面ではsummary groupとstock cardを1columnへ落とし、chipを折り返し、長い日本語本文、code、URLがviewportを押し広げないようにする。
- loading、error、成功status、quota、usage、cache/history、保存、OpenAI request回数を表示整形のために変更しない。

受け入れ時は、summaryの全体所見、主要risk、行動、候補、重要警告、通常警告が見出し付きで区別できること、空sectionと同一list内の重複が表示されないこと、Portfolio / Watchlistが共通表示規則を使うことを確認する。併せて、HTML/Markdown風test文字列が実行されないこと、根拠badgeがtextでも判別できること、unsafe source URLがanchorにならないこと、raw fallbackがplain textのままであること、mobile幅で横overflowしないことを確認する。

### 現在回答の別タブ・大画面表示

- Portfolio保有分析とWatchlist分析の結果領域へ、表示可能な現在回答がある場合だけ`回答を別タブ／ウィンドウで大きく表示`action linkを表示する。
- action linkを表示する条件は、`status=success`かつ`mode!=prompt_only`であること、または`status=json_parse_failed`かつtrim後の`raw_model_output`が非空であることとする。
- idle、loading、通信失敗、回答data欠落、`prompt_only`、生応答を持たないparse失敗ではaction linkを表示しない。手動投入用`manual_prompt`は既存textareaだけで扱い、readerへ含めない。
- successのreaderは、現在の結果cardと同じsummary / stock / list / callout / source renderer、section順序、空項目省略、重複除去、根拠badge、銘柄名・公開code表示を使う。raw JSONや汎用Markdownへ切り替えず、model由来HTMLを実行しない。
- `json_parse_failed`のreaderは失敗status、原因label、safeな説明、生応答を含む赤いerror表示とし、`raw_model_output`をescape済みplain textで表示する。構造化成功へ読み替えず、追加のJSON parseやOpenAI callを行わない。
- 印刷用Blobへ結果DOMをcloneするときは`details.ai-raw-output`をopenにし、画面に表示しているraw fallbackが印刷・PDFから欠落しないようにする。画面で20,000文字へ省略した場合はreaderも同じ省略表示と全文Markdown導線の説明を保つ。
- readerは現在描画した`state.portfolioAiReview.data`または`state.watchlistAiReview.data`の結果DOMから、browser memory上のHTML `Blob` snapshotを準備して開く。親画面で後から別の分析を実行しても、既に開いたsnapshotを書き換えない。
- Blob documentは表示に必要な静的HTMLとinline CSSだけを持ち、script、外部resource、formを含めない。restrictiveなContent Security Policyを付け、`default-src 'none'`を基本に必要なinline styleだけを許可する。
- action linkは`target="_blank"`と`rel="noopener noreferrer"`で新しい閲覧contextを開き、親画面への`window.opener`参照を渡さない。reader内の許可済み`http:` / `https:` source linkにも同じ属性を付ける。
- 回答、銘柄名、model、source等の動的値は既存のescape / URL allowlistを通す。API key、Authorization header、prompt全文、`manual_prompt`、成功responseにないraw provider dataをreaderへ含めない。
- readerは固定の日本語`title`と画面見出しを持つ。successでは複製元summaryのmode、生成時刻、対象labelを維持し、`json_parse_failed`では複製元error cardの失敗labelと対象labelを維持する。semantic heading / list / detailsを保ち、main幅はdashboardより広くする。狭いviewportでは1column、chip折返し、長文・code・URLの`overflow-wrap`を使う。
- action linkの準備・openでは`POST /api/ai/stock-review`、互換API、usage API、history/cache APIを呼ばず、OpenAI call、成功review回数、provider call数、token、概算額を増やさない。`save_result=false`、mock response、cache hitでも、上記表示条件を満たす現在回答なら利用できる。
- snapshot全体をURL query / fragment、`localStorage`、`sessionStorage`、IndexedDB、cookie、server DB、legacy JSON historyへ新たに保存しない。共有可能な恒久URL、reader一覧、再取得APIは提供しない。
- browserが新規閲覧contextをtabとwindowのどちらにするかは利用者設定へ従う。browser policyにより新規contextを開けない場合も、元のPortfolioまたはWatchlist結果は現在画面で読み続けられ、action linkの通常操作やbrowserのcontext menuから再試行できる。
- Blob snapshotは現在のbrowser session内での一時表示である。閉じた後の再表示、readerのreload、bookmark、別端末共有、親dashboard reload後の復元を保証しない。必要な場合は元画面に残る現在結果からaction linkを再実行する。

受け入れ時は、Portfolio / Watchlistのsuccessと非空raw parse failureでaction linkが現れ、`prompt_only`、loading、生応答なしerrorでは現れないことを確認する。併せて、同じ安全な表示componentがreaderでも使われること、linkの準備・openでnetwork / DB / Web Storage / OpenAI利用量が変わらないこと、`rel="noopener noreferrer"`とCSPで閲覧contextが分離されること、新規contextを開けない場合も元画面の回答が維持されること、reader reloadによる復元を契約にしないことを確認する。

### 保存済みAI結果一覧・詳細・Markdown / PDF

- dashboardへ独立した全幅section `Saved AI Results` / `保存済みAI結果`を置く。「結果保存」が有効だったlegacy stock-reviewの直近100件をAPIの保存順どおり新しいものから扱い、browser印刷によるPDF保存であることを補足する。`generated_at`でclient再sortしない。
- toolbarは分析方法selectと`履歴を更新`buttonを持つ。selectは`すべて`、`scanner`、`analyst`、`judge`、`critical`、`prompt_only`を利用者向けlabelで表示する。APIはtarget / statusもfilterできるが、この版の画面filterはmodeだけとする。
- 一覧は分析方法ごとにgroup化し、各groupに件数を表示する。各itemは分析方法、対象、生成日時、status、保存元、銘柄数と最大3銘柄preview、analysis mode、model、Web検索状態、mock / cache、概算額、決定的metadata summaryを表示する。model回答本文を一覧summaryとして再表示しない。
- `stored_count`と最大件数をfeedbackへ示す。不正entryがある場合は件数を示して一覧から除外する。loading、API失敗、空履歴、選択modeだけ0件のstateを区別し、履歴API失敗が新しいAI分析の実行には影響しないと表示する。
- validなitemは`結果を見る`と`Markdown保存`を持つ。`prompt_only`以外は`別タブ表示・PDF保存`も持つ。不正なhistory IDではactionを作らずsafeなerrorを表示する。
- detailは同じpage内の`保存済み結果`sectionへloadする。成功結果は現在回答と同じsafe structured renderer、失敗結果は同じ赤いerror / raw fallback、`prompt_only`は手動投入用promptでありOpenAI回答ではない旨、`OpenAI API非呼び出し`chip、escape済みplain `pre`を表示する。現在結果・保存履歴とも`prompt_only`を通常の`OpenAI API`実行済みchipで誤表示しない。
- detail headerの`Markdown保存`はserverの`.md` attachmentへ直接linkする。`別タブ表示・PDF保存（印刷）`はdetail DOMのclient-side Blob snapshotを既存safe readerで開き、「ブラウザの印刷（Ctrl+P）で『PDFに保存』を選ぶ」と説明する。
- raw fallbackが20,000文字を超える場合、detail / readerは先頭だけを表示して省略を明示し、Markdown保存を全文確認手段とする。印刷用cloneでは`details.ai-raw-output`をopenにして可視範囲をPDFへ含める。
- source URL allowlist、escaped text、semantic heading / list / details、CSP、`rel="noopener noreferrer"`、no external resource / script / formを現在回答readerと共用する。履歴の表示整形のためにOpenAI、history POST、usage、cache、DB write、Web Storageを呼ばない。
- 履歴saveが失敗した生成回答は現在回答として維持し、固定の安全なwarningを表示する。その回答は履歴一覧へ現れないため、保存済みと誤表示しない。
- 保存済み`watchlist_id`は表示補助に使えるが、旧recordに実行時list名がない場合は現行名を推測で付与しない。rename / delete前の名称復元を保証しない。
- SC-2026-08-19-04の「履歴一覧・download・exportは非対象」というclient-only current-result範囲は、SC-2026-08-19-06によりlegacy保存履歴についてだけ置き換える。現在回答Blob readerの`save_result=false` / mock / cache対応とreload非復元は引き続き有効で、canonical保存readerは変更しない。

受け入れ時は、履歴がAPIの保存順どおり新しいものからmode別に並び、`generated_at`でclient再sortせず、mode filter、loading / empty / error / invalid state、詳細、prompt-only、`.md`、別タブ印刷が成立することを確認する。併せて、一覧がmetadata onlyであること、raw省略・全文Markdown案内・印刷時details open、unsafe text / URLの非実行、OpenAI / usage / cache / Web Storage非変更、保存失敗回答の非履歴表示、旧named list名の非推測を確認する。

### legacy銘柄identity表示

- Portfolio / Watchlistのlegacy AI stock cardは銘柄名とcodeを併記する。codeは`publicSecurityCode(stock.ticker)`で表示し、英字を含む5文字末尾`0`だけを公開4文字へ変換する。例:cache等に`285A0`が残る場合もcard上では`285A`と表示する。
- local masterへ一致したtargetはservice側で`SecurityMaster.ticker_code`へcanonical化され得る。たとえば`local_code=285A0` / `ticker_code=285A`ならprompt・snapshotは`285A`、`local_code=72030` / `ticker_code=7203`なら`7203`となる。画面は存在する`stock.ticker`へ公開表示関数を適用し、DB primary keyやlocal codeを変更しない。
- portfolio summaryの`buy_candidates`、`sell_or_reduce_candidates`、`hold_priority`、`non_monitoring_reduce_candidates`、`core_position_candidates`、`exit_or_rotate_candidates`は、serverが返す「銘柄名（公開コード）」をそのままescapeして表示する。コードだけを通常表示にしない。
- `285A0`またはcanonical `285A`は`キオクシアホールディングス（285A）`、名称を解決できないcodeは`名称未登録（code）`と表示する。numeric 5文字codeを表示関数だけで一律短縮しない。
- live、mock、前回cache hitで同じ表示を使う。過去cacheのコードだけlistも読出し時のserver正規化後に表示するため、再分析や追加OpenAI callを要求しない。
- promptはInput JSONのticker/nameを正本として名称併記を要求するが、画面表示はprompt順守だけに依存せずserver正規化済みresponseを使う。
- scannerはquick scan短縮版とsection 8のportfolio影響を組み合わせる。全14用途moduleを画面から一括投入するcontrolは追加しない。

### holdings source label

内部値をそのまま`database`等と表示せず、次へ変換する。

| internal value | display |
|---|---|
| `request` | 対象: リクエスト指定銘柄 |
| `database` | 対象: 実DB保有銘柄 |
| `watchlist` | 対象: 監視銘柄 |
| `candidates` | 対象: 狙い中銘柄 |
| `mock` | 対象: テスト用仮保有銘柄 |
| `none` | 対象: 未指定 |
| unknown | 対象: 未確認 |

error cardとsuccess summary chipの両方で同じmappingを使う。「database」はquotaの保存先やOpenAI側制限を表すlabelとして表示しない。

### legacy error handling

- `missing_api_key` は `.env` または起動環境に `OPENAI_API_KEY` が必要であることを表示する
- `json_parse_failed` はsuccess summaryとして扱わず、赤い`ai-review-card error`で表示する
- `parse_failure_kind=schema_validation`は「JSON項目形式エラー」、`root_shape`は「JSONルート形式エラー」、`json_syntax`は「JSON構文エラー」と表示する
- `parse_failure_kind`が欠落した過去recordは「JSON構文エラー」として安全に表示する
- `raw_model_output` がある場合は、失敗card内に「OpenAI生応答」としてUIに収まる範囲で表示する
- JSON parse救済に成功した場合は、warnings に「JSON整形リトライ」を表示し、結果card表示を継続する
- JSON parse救済に失敗してOpenAI生応答を表示する場合も`status=json_parse_failed`を維持し、成功色、成功review回数、cache hitとして表示しない
- `save_result=true`なら失敗responseを調査用履歴へ残せるため、前回結果や履歴から同じ赤いerror表示を再現できる
- API key、内部stack trace、秘密情報は表示しない

このlegacy error handlingはindependent individual-security AIには適用しない。

## 8. dashboard legacy AIのprompt output

- `prompt_only` 成功時は textarea に `manual_prompt` を表示する
- `manual_prompt` がある場合だけ `プロンプトをコピー` ボタンを有効化する
- 自動投稿、ChatGPT Web画面操作、回答スクレイピングは行わない

## 9. independent individual-security AI screen

### path and entry

- pathは `GET /ui/analysis`
- 画面titleは `AI個別銘柄分析`
- 成功回答の大型表示pathは `GET /ui/analysis/results/{request_id}`
- 大型表示の画面titleは `保存済みAI個別銘柄分析`
- 現時点では独立URLとして提供し、dashboardからの導線が実装済みであるとは扱わない
- dashboardのview model `GET /ui/dashboard/data` は使用しない

### page sections

1. 銘柄選択
2. 質問
3. 回答

### security selection controls

- `銘柄コードまたは銘柄名` の検索input
  - input type: `search`
  - 最大100文字
  - autocompleteはOFF
  - placeholderは `例: 7203 または トヨタ`
- `検索` button
- 検索inputでEnterを押した場合も検索を実行する
- 検索APIは `GET /securities/search?q={query}&limit=10`
- 検索結果はbuttonの一覧で表示し、1件を選択できる
- 結果表示は `銘柄コード 銘柄名 / 市場`
- 市場が未登録の場合は `市場未登録`
- 選択後は選択銘柄を専用領域に表示し、検索結果一覧を閉じる
- 同時に選択できる銘柄は1件だけ

### question and preset controls

- `自由質問` textarea
  - 最大4000文字
  - 縦方向のresizeを許可する
  - placeholderは `この銘柄について確認したいことを入力してください。`
- 回答設定はread-only chipの `STANDARD`
- action buttonは `STANDARDで送信`
- model、reasoning effort、text verbosityを利用者が変更するcontrolは置かない
- Web検索、mock、prompt-only、prompt編集、保存の手動toggle、履歴一覧、複数銘柄選択のcontrolは置かない

## 10. independent individual-security AI state contract

### initial state

- 選択銘柄は未設定
- 回答、status、error、diagnostics、保存warning、保存済み表示、reader linkは空または非表示
- 送信buttonはdisabled
- 送信buttonは、銘柄を1件選択し、かつtrim後の質問が非空の場合だけenabledになる

### search loading

- 空の検索queryはAPIへ送らず、`銘柄コードまたは銘柄名を入力してください。` をerror領域へ表示する
- 検索開始時は検索buttonをdisabledにする
- statusに `銘柄を検索中…` を表示する
- 検索完了後は検索buttonを再びenabledにし、statusを空にする
- 検索中であってもAI分析のloading stateとしては扱わない

### search result and search error

- 0件の場合は `該当する登録銘柄がありません。` を検索結果領域へ表示する
- HTTP失敗、非JSON、network失敗は `銘柄検索に失敗しました。` をerror領域へ表示する
- 検索結果のlabelはDOMの`textContent`で生成し、検索値や銘柄名をHTMLとして挿入しない
- 銘柄選択時は既存errorをclearし、送信buttonの有効条件を再評価する

### analysis loading

- 未選択状態では送信処理を開始しない
- trim後の質問が空の場合は `質問を入力してください。` をerror領域へ表示する
- 送信開始時に多重送信を禁止し、送信buttonをdisabledにする
- 送信中は銘柄検索input・検索button・検索結果button・質問textareaをdisabledにし、送信対象銘柄と質問を固定する
- 直前の回答、error、diagnosticsをclearする
- 直前の保存warning、保存済み表示、別ウィンドウlinkを非表示にする
- statusに `OpenAIへ送信中…` を表示する
- request完了後は、選択銘柄と質問の状態に応じて送信buttonを再評価する
- request完了後は銘柄検索・選択・質問編集を再び有効化する
- streaming表示、進捗率、cancel操作は提供しない

### success

- HTTP successだけでは成功扱いにしない
- response bodyがJSONで、`status=success`、かつtrim後の`answer_text`が非空の場合だけ生成成功とする。`persistence_status`が`saved`で非空`request_id`を持つ場合だけ保存成功UIへ進み、それ以外はfail closedでreader linkを出さず保存warningを表示する
- 保存結果にかかわらず`answer_text`を回答領域へ表示する
- diagnosticsを表示可能にし、statusは保存成功時に`回答を表示しました`、保存失敗時に`回答を表示しました（保存できませんでした）`とする
- `persistence_status=saved`の場合:
  - 非空`request_id`を確認する
  - `この回答はローカルに保存済みです`を表示する
  - `/ui/analysis/results/{request_id}`への`別ウィンドウで大きく表示`linkを表示する
  - warningは表示しない
- `persistence_status=failed`の場合:
  - 回答本文の近くに`persistence_warning`をwarningとして表示する
  - 保存済み表示、`saved_at`、reader linkは表示しない
  - warningが欠落した場合は`回答は生成されましたが、ローカルDBへ保存できませんでした。大画面での再表示は利用できません。`を表示する
- 直前のerrorは非表示のままにする

### failure

- HTTP error、response JSON parse失敗、`status!=success`、OpenAI空回答、network failureは回答として表示しない
- API error responseがある場合は`{error.code}: {error.message}`を表示する
- response envelopeを取得できない場合は`REQUEST_FAILED: AI分析に失敗しました。`を表示する
- 非空の成功responseに見えても`answer_text`が空なら`EMPTY_RESPONSE: 回答本文が空でした。`を表示する
- fetch自体が失敗した場合は`NETWORK_ERROR: APIとの通信に失敗しました。`を表示する
- failure時のstatusは`失敗しました`
- OpenAI raw response、部分回答、parseできない本文をsuccessへfallbackしない
- ローカル保存失敗はこのfailure stateへ遷移させず、生成成功stateのwarningとして扱う

## 11. independent individual-security AI API and answer contract

### request

`POST /api/ai/analyses`へ次だけを送る。

```json
{
  "security_code": "7203",
  "question": "自由質問",
  "preset": "STANDARD"
}
```

### response fields used by the screen

- `request_id`
- `status`
- `answer_text`
- `error.code`
- `error.message`
- `openai_response_id`
- `persistence_status`
- `saved_at`
- `persistence_warning`

### plain-text answer

- 回答は `response.output_text` 由来の `answer_text`
- 回答領域は `<pre>` とする
- DOMへの反映は `textContent`
- CSSは `white-space: pre-wrap` と `overflow-wrap: anywhere`
- Markdown renderer、HTML sanitizer前提のHTML描画、JSON parser、構造化cardを導入しない
- 回答にMarkdown記号が含まれていても、文字列としてそのまま表示する

### saved response action

- 保存はserver側のbest-effort処理であり、手動保存buttonや保存ON/OFF controlは置かない
- `persistence_status=saved`の場合だけ`この回答はローカルに保存済みです`と`別ウィンドウで大きく表示`を表示する
- link先はresponseの`request_id`をURL encodeした`/ui/analysis/results/{request_id}`
- linkは`target="_blank"`、`rel="noopener noreferrer"`とする
- `persistence_status=failed`では回答本文とwarningだけを表示し、保存済み表示、`saved_at`、reader linkは表示しない
- loading、OpenAI error、空回答、request ID欠落時もlinkを非表示にする

### large-window saved answer screen

- pathは`GET /ui/analysis/results/{request_id}`
- 初期statusは`保存済み回答を読み込み中…`
- 同じoriginの`GET /api/ai/analyses/{request_id}`を`cache: "no-store"`で呼ぶ
- 成功時は`銘柄名（銘柄コード）`、市場、preset、model、保存日時、質問、回答を表示する
- 質問と回答は`<pre>`の`textContent`で設定し、回答は`white-space: pre-wrap`と`overflow-wrap: anywhere`を使う
- 回答本文を読みやすくするため、main領域と回答領域は元画面より広く、縦方向の最小表示領域を持つ
- 不正・欠落responseは`INVALID_SAVED_RESPONSE`、API errorはsafeなcode/message、network failureは`NETWORK_ERROR`として表示し、本文領域を表示しない
- `分析画面へ戻る`linkを持つ
- Markdown renderer、構造化card、編集、削除、export、一覧表示は行わない

## 12. independent individual-security AI diagnostics

- diagnosticsは初期状態では非表示
- success時は次だけを表示する
  - `request_id`
  - `openai_response_id`。欠ける場合は `未取得`
- error responseに`request_id`がある場合は、そのIDだけをdiagnosticsに表示できる
- error responseにIDがない場合はdiagnosticsを表示しない
- prompt全文、自由質問全文、security context全文、prompt asset本文、prompt version、asset ID、compiled hash、model raw response、内部stack traceをdiagnosticsへ表示しない
- diagnosticsは開閉可能な`details`要素とする

## 13. independent individual-security AI error codes

画面はAPIから返る次の分類をsafeなerror codeとして表示できる。

- `AUTHENTICATION_ERROR`
- `MODEL_UNAVAILABLE`
- `INVALID_API_PARAMETERS`
- `RATE_LIMITED`
- `TIMEOUT`
- `NETWORK_ERROR`
- `EMPTY_RESPONSE`
- `UNKNOWN_OPENAI_ERROR`
- `SECURITY_NOT_FOUND`
- `DATABASE_UNAVAILABLE`
- `PERSISTENCE_ERROR`（schema互換。通常の保存失敗はHTTP 200の`persistence_status=failed`であり、このerror表示にはしない）
- `ANALYSIS_NOT_FOUND`（大型表示画面の保存record未検出）

FastAPI request validationなど上記response envelopeを返さない失敗は、画面側で`REQUEST_FAILED`として扱う。

## 14. independent individual-security AI prompt application

- prompt合成はserver側の`IndividualSecurityPromptCompiler`が担当し、UI内で長いpromptを生成しない
- OpenAI `instructions`は次の順序とする
  1. 株判断共通OS
  2. 共通入力ルール
  3. Web検索・外部市場データなしの実行制約
  4. `3.1 総合的な個別銘柄分析`
- OpenAI `input`は次の順序とする
  1. 選択した`security_master`由来の銘柄context
  2. ユーザーの自由質問
- `3.2`から`3.14`までの用途moduleを送信しない
- 利用できない現在価格、決算、テクニカル、需給、信用、市場、マクロ、イベント情報を推測で補完させず、`【U】`、`insufficient_data`、`no_trade`を利用できるようにする
- prompt version、使用asset、module、source hash、compiled hashはOpenAI response metadataへ記録する
- prompt metadataとprompt本文はpublic FastAPI responseやbrowserへ返さない
- active prompt versionは`2026.08.18`、compilerは`individual-security-v2`とし、銘柄の表示・言及は原則`銘柄名（銘柄コード）`とする
- 根拠ラベルは`【V】確認済み`、`【E】推定`、`【U】未確認`に統一し、active compiled promptへ旧括弧ラベルを残さない
- v18 source provenanceは非送信`SOURCE.md`で管理し、v2026.08.17原資料のprovenanceは`revision.base_source`として、v2026.08.17 asset自体はimmutableな履歴として維持する

## 15. independent individual-security AI security and privacy

- `OPENAI_API_KEY`はサーバー側だけで読み込み、HTML、JavaScript、request body、API response、diagnosticsへ含めない
- API key、Authorization header、secret、prompt全文を通常logへ出力しない
- 自由質問はOpenAI requestのinputとして送られるが、API responseやdiagnosticsへechoしない
- 成功した質問と回答は大型表示のためローカルSQLへ保存を試みる。保存成功した1件取得responseでは質問を返す。保存失敗時は回答本文を現在画面だけに表示し、reader導線を出さない。APIキー、prompt全文、provider raw responseは保存・表示しない
- 銘柄検索結果、error message、回答本文は`innerHTML`を使わず、`textContent`で反映する
- OpenAI API失敗をmock回答やcache回答へ置き換えない
- modelを暗黙fallbackしない
- 回答画面には「回答は判断補助であり、投資助言ではありません。」と明記する

## 16. independent individual-security AI non-goals

この版では次を実装済みとして扱わない。

- dashboardから`/ui/analysis`への導線
- `LIGHT` / `HIGH` / `PRO` / `MAX` preset
- model選択UI
- `reasoning.mode`選択UI
- 複数銘柄、市場全体、総合分析
- Web検索またはJ-Quants等の追加市場context取得
- Structured Outputs、JSON Schema、JSON修復、parse失敗時の再AI呼び出し
- Markdown rendering、複雑な結果card
- streaming、background response、polling、cancel
- prompt編集、prompt全文表示、prompt asset選択
- prompt cache、回答cache、mock fallback
- 保存回答の一覧・検索・削除・export・共有、回答copy、回答download
- 保存recordの保持期限設定、自動purge、認証・認可
- 旧dashboard AI経路の統合、削除、廃止
- 完全な銘柄masterの一覧表示、download、CSV export、public共有
- 地方取引所単独銘柄まで含む国内全取引所の網羅保証
- 銘柄masterの定期background同期、browserへのJ-Quants APIキー保存

## 17. known limitations

- `/ui/analysis`は独立URLであり、現時点でdashboard内の正式導線を持たない
- 登録済み`security_master`の銘柄だけを選択できる
- 一度に分析できる銘柄は1件だけ
- presetは`STANDARD`固定で、modelは`gpt-5.6-terra`固定
- `reasoning.effort=medium`、`text.verbosity=medium`を固定し、画面から変更できない
- AI分析request内でWeb検索やJ-Quants同期を行わない
- serverが渡す銘柄contextはコード、名称、市場、業種、上場日を中心とし、現在価格、取得時刻、最新決算、テクニカル、需給、信用、市場・マクロ情報は通常未提供である
- 未提供情報が結論に必要な場合、回答は情報不足、`insufficient_data`、`no_trade`へ着地し得る
- プレーンテキスト表示のため、Markdown記号は装飾されない
- 回答のstreaming、cancel、履歴一覧はない。保存済み回答はrequest IDを知っている場合だけ1件再表示できる
- 保存recordの削除、export、保持期限、自動purge、access controlはない
- browserではprompt versionやasset IDを確認できない。追跡情報はserverからOpenAI response metadataへ記録する
- error時にOpenAIのraw error本文やraw model outputは表示しない
- dashboard検索responseの`ticker_code`は登録済みmaster identifierである。英字を含む5文字末尾`0`形式は表示と保有入力だけ公開4文字へ変換し、detail actionではraw identifierを維持する。
- この版では`security_master` primary keyの4文字化、既存参照recordのmigration、J-Quants connector全体のcode正規化を行わない。
- `東証全銘柄`はJ-Quantsが返す東証listed issuesの範囲で、地方取引所単独銘柄を保証しない。完全なdatasetはpublic repositoryに同梱されず、利用者自身のAPIキーで同期したlocal DBにだけ存在する。
- `source_as_of`はJ-Quants planに応じて遅延し得る。画面の`同期`時刻はローカル取り込み時刻で、最新市場情報の保証ではない。
- J-Quantsの429、network、plan権限、endpoint変更で同期が失敗し得る。失敗時は既存masterを維持し、36件seedを全件同期済みとして表示しない。
- 本番4,000件/5%縮小guardは安全側に停止するため、正当な大幅減少でもdashboard同期が失敗し得る。画面から閾値を緩和できない。
- 支配的legacy cohortは画面から採用できずCLIの明示`--adopt-legacy`が必要である。参照付きidentity splitは専用migration未実装のため、参照を保全した個別reconciliationが必要である。
- legacy JSON整形retryは残るため、軽量スキャン1回でprimaryとrepairの最大2 provider callが発生し得る。最終結果が`json_parse_failed`なら成功回数へは加算されないが、OpenAI呼出数と概算費用は発生し得る。
- legacy大画面表示は現在回答のclient-only Blob snapshotであり、恒久URL、bookmark、reload、履歴からの復元、別端末共有を保証しない。親画面に現在結果が残っている間はaction linkを再実行できる。
- 新規閲覧contextが別タブと別ウィンドウのどちらになるかはbrowser設定に依存する。browser policyで開けない場合も元画面の結果は維持されるが、block検出や専用feedbackは保証しない。
- named watchlistは認証・利用者分離のないapp-global dataであり、同じappへ接続できる利用者間で分離されない。Internetへ直接公開しない。
- memo / thesisはcollection固有ではなくsecurity-level共有値である。同じtickerを複数listへ登録しても、listごとに別の仮説を保持できない。
- queryの`watchlist_id`が存在しない、無効化済み、または不正な場合、dashboard dataはdefault collectionへfallbackする。一方、collection / item / 検索APIは404またはvalidation errorを返し得る。
- non-default collection削除にundo / trash / exportはなく、そのcollectionのmembershipは復元されない。Portfolio、他collection、security-level memo / thesisは削除対象外である。
- checkbox選択はbrowser memoryだけに保持し、reload、別tab、別端末へ復元・共有しない。
- AI結果のlist名contextもbrowser memory上のrequest snapshotだけで、history / cacheからの再表示時にcollectionの現行名へ追従する契約はない。scope mutationで無効化した現在結果は画面から復元しない。
- legacy保存履歴は最大100件固定で、削除、全文検索、pin、保持期限、自動purge、共有URL、cloud同期、利用者別access controlを持たない。
- 保存済みnamed watchlist履歴は`watchlist_id`を持ち得るが、実行時のlist名は保存していない。rename / delete前の名称を履歴画面から復元できない。
- PDFはbrowser印刷に依存し、page size、改ページ、header/footer、保存先、tab / windowの選択をアプリから保証しない。server-side PDF生成は行わない。

## 18. detail screen

- named listから開く場合はURL query `watchlist_id`を保持し、dashboard data取得、一覧への戻りlink、chart linkへ同じIDを渡す。
- named list contextの`watchlistに追加`と仮説保存はそのcollection item APIを使う。queryなしのPortfolio contextではlegacy default `/watchlist`を使う。
- memo / thesisはsecurity-level共有値であり、同tickerを含む他collectionでも更新後の値が見える。画面上でlist固有memoと誤認させない。

### main sections

- header / status
- hypothesis card
- factor split
- reference links
- technical
- flow
- materials
- warnings / history

### chart preview

- `チャート分析詳細` ボタンの近くに直近chart previewを置く
- `price_chart` がある場合のみローソク足と出来高を表示する

## 19. chart detail screen

- named list contextでは`watchlist_id`をqueryに維持し、個別銘柄ページへ戻るlinkも同じcollection contextを保持する。

### main sections

- 20日 / 40日 / 全期間切替
- MA 5 / 25 / 75 overlay
- RSI / MACD 補助表示
- 個別銘柄ページへ戻るlink
- JSON button

### empty state

- `price_chart` が無ければ `チャートデータはまだありません。` を表示する
- 補助表示に十分な本数が無ければ、その旨を明示する

## 20. live mode の表示ルール

- dashboard / detail / chartではmock補完をしない
- 銘柄masterはdashboardの明示buttonで同期し、画面読込や検索だけでJ-Quants full masterを自動取得しない
- `price_chart` が空ならJ-Quants日足同期を1回試す
- それでも不足している項目は`未取得`または空表示
- independent individual-security AIでは、live / mock起動モードにかかわらずAI回答のmock fallbackを行わない

## 21. source 表示ルール

- reference linkは正式sourceと手動参照を区別して見せる
- TDnet、株探、みんかぶ、日経、Reuters、Bloomberg、SBI証券、楽天証券、X、StockTwitsは手動参照stack
- independent individual-security AIはsource一覧を表示せず、外部sourceを自動取得したと表現しない

## 22. document change history

| version | date | changes |
|---|---|---|
| v2.8 | 2026-08-19 | v2.7を累積継承し、legacy保存済みAI結果の最大100件・保存順の新しいものから返すmode別一覧、mode filter、metadata item、detail、prompt-only、Markdown保存、別タブ印刷によるPDF保存を追加。raw表示の20,000文字上限・全文Markdown案内・印刷clone時details open、OpenAI非再呼出、cache hit非保存、保存失敗warning、旧named watchlist名非復元を定義。SC-2026-08-19-04の履歴非対象をlegacy保存履歴についてSC-2026-08-19-06で置換。 |
| v2.7 | 2026-08-19 | v2.6を累積継承し、Portfolioとdefault「メイン」を含む複数named watchlistをselectorで切り替える単一の全幅管理spaceへ統合。collection操作、list別membership、検索 / monitoring / detail / chart / legacy AIのscope、checkboxによるselected target自動切替、request開始時list名snapshot、scope mutation時の結果無効化、async stale-response破棄、Portfolio復帰時default reload、security-level共有memo / thesis、明示named empty時のmock非fallback、app-global / 認証なしの境界を追加。 |
| v2.6 | 2026-08-19 | v2.5を累積継承し、legacy Portfolio / Watchlistの現在回答をclient-only Blob snapshotとして別タブ・別ウィンドウへ大きく表示するaction linkを追加。success（prompt-only除外）と非空raw parse failureだけを対象とし、共通safe renderer、CSP、`rel="noopener noreferrer"`、no API / DB / Web Storage / OpenAI再呼び出し、reload非復元を明記。canonical保存readerは変更しない。 |
| v2.5 | 2026-08-19 | v2.4を累積継承し、legacy Structured Outputs JSONをsemanticな見出し、箇条書き、callout、根拠badgeへ安全に対応付ける表示契約を追加。空項目省略、同一list内重複除去、Portfolio / Watchlist共通helper、escaped text、unsafe source非link、raw fallback plain表示、mobile / accessibilityを明記。API/OpenAI call/statusは変更しない。 |
| v2.4 | 2026-08-19 | v2.3を累積継承し、legacy AI stock cardの正式名称・公開code併記、portfolio summaryの「銘柄名（公開コード）」、local master canonical identity、未知名称label、live/mock/cache共通表示を追加。canonical個別銘柄AI v2026.08.18は変更しない。 |
| v2.3 | 2026-08-19 | v2.2を累積継承し、legacy軽量スキャンの`json_parse_failed`を赤いerror cardへ変更。`schema_validation` / `root_shape` / `json_syntax`の利用者向けlabel、生応答表示、成功回数非加算、cache不可、履歴保存可、scanner軽量生成契約を追加。canonical個別銘柄AI画面は変更しない。 |
| v2.2 | 2026-08-18 | v2.1を累積継承し、`東証全銘柄を同期`、完全/未確認status、J-Quants/ローカル件数、情報基準日と同期時刻、取得/新規/更新/再有効化/無効化のfeedback、BYOK/private local/非再配布/地方単独非保証の表示境界を追加。本番4,000件/5%縮小guard、支配的legacy/参照identity splitのfail-closed表示、DB-only検索、provider body非露出も同版契約として明記。 |
| v2.1 | 2026-08-18 | v2.0を累積継承し、銘柄名・数字/英字コード検索、検索結果の`保有入力へ`/`詳細を見る`分離、portfolioフォームへの非保存prefill、数量focusと明示保存を追加。 |
| v2.0 | 2026-08-17 | v1.9を累積継承し、legacy stock-reviewの日次quota 300、1 batch=1回の説明、JST日次/月次usage・概算panel、未算定/旧履歴注記、実Web検索回数、friendly holdings-source labelを追加。canonical個別銘柄AI画面は変更しない。 |
| v1.9 | 2026-08-17 | v1.8を累積継承し、保存失敗時も回答を表示するwarning state、保存成功時だけの保存済み表示/reader link、active prompt 2026.08.18の正式根拠ラベルを追加。 |
| v1.8 | 2026-08-17 | v1.7を累積継承し、canonical成功回答のローカル保存表示、別ウィンドウ大型表示link、保存回答reader、loading/error/plain-text描画、v2026.08.17の銘柄名・コード併記規則を追加。履歴一覧・削除・exportは非対象。 |
| v1.7 | 2026-08-17 | v1.6を累積継承し、dashboard legacy AIと独立`/ui/analysis`を分離。個別銘柄AIのcontrols、state、loading、error、plain-text answer、diagnostics、security、PromptCompiler境界、non-goals、known limitationsを追加。 |
| v1.6 | 2026-06-15 | dashboard Portfolio AI分析パネル、multi-mode stock AI review、Prompt Registry / Builder、prompt-only、warnings / sources表示を追加。 |
