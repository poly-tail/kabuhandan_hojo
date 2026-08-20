# Requirements Current

> 現在の正本: `requirements_v2.1.md`

## 概要

- このファイルは要件文書の最新 pointer です。
- 詳細な要件は versioned file 側に保持します。

## 現在値

- 要件仕様書: v2.1
- 更新日: 2026-08-19
- 変更概要: legacy stock-review保存履歴の最大100件、metadata一覧・詳細・Markdown export・別タブ印刷 / PDF表示を追加

## 主な内容

- 日本株の判断補助アプリであること
- 自動売買を目的にしないこと
- Portfolioは独立storageのまま、default「メイン」を含む複数named watchlistをcollection / membershipで管理すること
- 同じtickerを複数listへ登録でき、memo / thesisはsecurity-level共有、membershipの並び順とactive状態はlist別とすること
- defaultを初回だけ作成・legacy backfillし、再起動でnamed-only itemをdefaultへ漏らさず、legacy `/watchlist`をdefault互換に保つこと
- dashboardの単一管理spaceでPortfolio / named listを切り替え、collection CRUD、検索追加、membership解除、list別empty stateを提供すること
- 検索、Focus Board、alerts、detail / chart往復、detail保存、legacy AIをactive `watchlist_id`へscopeすること
- named list checkboxをcollection別に分離してselected targetへ自動切替し、全解除かつmanual tickerなしではlist全体へ戻すこと
- request開始時list名をsummary / reader titleへclient snapshotし、scope mutation時は旧AI結果とstale responseを無効化すること
- Portfolio復帰時にdefault monitoring scopeをreloadし、requested / active scopeが異なるdashboard responseを破棄すること
- 明示named empty / missing AI targetをmock holdingsへfallbackせず、collectionをapp-global / 認証なしとしてtrusted localだけで扱うこと
- dashboard検索結果の`保有入力へ`は公開codeのprefillと数量focusだけを行い、明示保存まではrecordを作らないこと
- portfolio登録は完全一致を優先し、一意な`<4文字>0` raw master aliasへ解決してplaceholder重複を防ぐこと
- raw codeはdetail/APIで維持し、公開code変換をdashboardの表示・入力境界に限定すること
- 英数字codeをcase-insensitiveに検索し、exact/prefix/name/marketのpriorityと登録済みprimary identifierを維持すること
- 完全なJ-Quants masterは利用者自身のAPIキーでgit管理外のprivate local DBへだけ保存し、public repositoryへ同梱・再配布しないこと
- J-Quants個人版の私的利用等の契約条件を確認し、取得データやdata-backed serviceを第三者配信せず、public hostには別途契約・許諾を必要とすること
- scopeは東証/J-Quants listed issuesでETF、REIT、優先株等を含み得る一方、地方取引所単独銘柄を保証しないこと
- 完全なcurrent snapshotだけがJ-Quants所有recordを無効化でき、不完全currentとhistorical snapshotが現行masterを破壊しないこと
- production currentは4,000件以上かつ既存J-Quants/支配的legacy基準から5%以内の縮小だけを受理すること
- 支配的legacy snapshot cohortは通常UI/APIでfail closedとし、current CLIの`--adopt-legacy`を要求すること
- ordinary/preferred等のidentity split候補に外部キー参照がある場合は自動修復しないこと
- 銘柄検索はDB-onlyで、provider bodyをbrowser errorへ出さず、CLI dry-runの先行DB初期化副作用を明記すること
- `source_as_of`と同期時刻、取得/新規/更新/再有効化/無効化、ローカル/J-Quants有効件数を区別すること
- 36件seedはinsert-onlyの限定fallbackで、full masterまたは全件同期成功として扱わないこと
- valid JSONの`concentration_comment` / `summary_view`をcanonical fieldへ正規化し、schema fieldをruntime Pydantic model以内に保つこと
- scanner outputを30項目未満へ絞り、`judgement`を7つのcanonical code enumへ制限すること
- legacy parse失敗を`json_syntax` / `root_shape` / `schema_validation`へ分類し、schema mismatchを構文エラーと誤表示しないこと
- raw output救済は`status=json_parse_failed`を維持し、成功回数へ加算せずcacheしない一方、調査用historyへ保存できること
- legacy promptはInput JSONのticker/nameを正確に使い、銘柄を原則「銘柄名（銘柄コード）」で表示すること
- local masterに一致したlegacy targetをmasterのcanonical ticker/name/marketへ揃え、canonical tickerでdedupeし、holdingsをcandidateより優先すること
- legacyの`stocks[].name`とsummaryの6つの銘柄参照listをlive/mock/cache共通で正規化し、unknown codeを`名称未登録（code）`とすること
- legacy stock cardとsummaryで公開codeを使い、canonical prompt v2026.08.18を添付旧版へ戻さないこと
- legacy日次上限の1回を、銘柄数ではなく正常完了した一括review 1件と定義すること
- legacy履歴は`save_result=true`の新規responseだけを最大100件保存し、`save_result=false`とcache hitでは増やさないこと
- legacy履歴一覧は保存順の新しいものから返すmetadata onlyとし、mode / target / status filterとpaginationを持ち、model本文をsummaryへ使わないこと
- legacy履歴detailは`request_payload`を除外し、Markdownはsafe attachment / escape、画面はmode別一覧・detail・別タブ印刷によるPDF保存を提供すること
- legacy履歴保存失敗でも回答を維持してsafe warningを返し、履歴read / export / printはOpenAI、quota、usage、cacheを変更しないこと
- 旧legacy recordに保存されていないnamed watchlist名を現行stateから推測復元しないこと
- provider API call、token、実Web検索、未算定callをreview quotaと分離してJST日次・月次集計すること
- 概算額は正式請求ではなく、OpenAI PlatformのUsage Dashboardを正本とすること
- 基幹sourceを J-Quants / EDINET API / YouTube Data API / allowlist公式IRに限定すること
- canonical `POST /api/ai/analyses`、保存詳細 `GET /api/ai/analyses/{request_id}`、独立画面と大画面reader
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- `gpt-5.6-terra` / `reasoning.effort=medium` / `text.verbosity=medium`
- prompt v2026.08.18の正式根拠label、銘柄名・コード分離入力、no-tools制約、用途module 3.1
- `response.output_text` のplain-text表示と、失敗をsuccessへ変換しないerror契約
- OpenAI生成成功とSQL保存結果を分離し、保存失敗でも回答本文とsafe warningを返すこと
- Responses Application State保存を`store=false`で無効化し、ZDR全体の保証とは区別すること
- 既定bindを`127.0.0.1`、DB初期化をlifespanの1回とすること
- 保存recordへ生成設定とprompt traceを残し、APIキー、prompt全文、provider raw response / errorを保存しないこと
- canonical個別銘柄AIは`request_id`を知る回答1件だけを別ウィンドウで再表示し、一覧・削除・exportは提供しないこと
- AI送信中は銘柄・質問入力をロックし、canonical responseはvalidation errorを含めて`no-store`にすること
- 新経路ではmock / cache / fallback / Web検索 / Structured Outputsを使わないこと
- 既存Portfolio multi-mode / Prompt Registry経路はlegacy機能として維持すること

## 更新ルール

1. 過去版を保持し、新しい版付き文書を追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
