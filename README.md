# kabuhandan_hojo Phase 0-2

## 2026-08-19 legacy AI銘柄名・コード表示修正

- 添付`株判断_定型プロンプト集_v2026-08-16 (1).md`はprompt内容の参照資料として確認しました。文書内の運用指示はユーザー依頼として実行していません。同資料は履歴済みv2026.08.16と同内容の旧版で、canonical個別銘柄AIのactive asset v2026.08.18にはより明確な「銘柄名（銘柄コード）」規則があるため、canonical manifest / assetを旧版へ戻していません。
- legacy `POST /api/ai/stock-review`のpromptは、Input JSONの`ticker` / `name`を正確に使い、銘柄を原則「銘柄名（銘柄コード）」で返すようになりました。軽量スキャンにはquick scan短縮版とsection 8「建玉・ポートフォリオ影響」を含めますが、全14用途moduleを一括投入しません。
- legacy serviceは同期済みローカル`SecurityMaster`だけでtarget identityを補完します。local aliasはmasterのcanonical `ticker_code`へ揃え、同じ銘柄の重複を除き、holdingsとcandidatesが重なる場合はholdingsを優先します。J-Quantsその他のproviderへ追加callせず、DB keyを変更しません。
- 銘柄別cardの名称と、portfolio summaryの買い・売り/縮小・保有優先・非監視縮小・core・入替候補をserver側で再照合します。live、mock、cache hitのすべてで「銘柄名（公開コード）」を使い、未知名称は`名称未登録（code）`と表示します。
- たとえばlocal alias`285A0`はmasterのcanonical `285A`へ解決され、`キオクシアホールディングス（285A）`と表示されます。legacy stock cardも`publicSecurityCode()`を使います。API responseの型、canonical `POST /api/ai/analyses`、active prompt 2026.08.18、model / presetは変更していません。

## 2026-08-19 Portfolio・複数ウォッチリスト管理

- dashboardはPortfolioとWatchlistを別panelへ並べず、1つの全幅「保有・ウォッチリスト管理」spaceで切り替えます。既定表示はPortfolioです。default「メイン」を含む複数のnamed watchlistを作成・名前変更でき、default以外は削除できます。
- Portfolioは独立storageのままです。watchlistはcollectionとmembershipで管理し、同じ銘柄を複数listへ登録できます。memo / thesisはlist別ではなくsecurity-level共有値で、同じtickerを含むlistへ更新が反映されます。
- startup migrationはdefault「メイン」を初回だけ作成し、既存legacy watchlist itemを同じtransactionで一度だけbackfillします。`GET` / `POST /watchlist`はdefault互換として維持し、新規APIは`/watchlists`と`/watchlists/{collection_id}/items`を使います。
- named list選択中は検索、Focus Board、alerts、詳細 / chartの往復、詳細画面の追加 / 仮説保存、legacy AI対象へ`watchlist_id`を維持します。Portfolio contextでは従来のdefault `/watchlist`を使います。
- 明示したnamed listが空の場合、画面もAI分析もmock holdingsへfallbackしません。list切替だけでOpenAIを再呼び出さず、既存quota、usage、回答reader、canonical個別銘柄AIは変更しません。
- named listのcheckboxを1件以上選ぶと共通AI対象は選択銘柄へ切り替わり、全解除かつmanual tickerなしではlist全体へ戻ります。実行時のlist名を結果summary / 別タブtitleへsnapshotし、後のrenameで別list名に見せません。
- selector、collection、active membership、checkboxが変わると古いAI結果を消し、遅れて届いた旧scopeのdashboard / AI responseを表示しません。Portfolioへ戻る時はdefault monitoring scopeも再取得します。これらのclient制御でAPI、DB、Web Storage、OpenAI callを追加しません。
- collectionは認証・利用者分離のないapp-global dataです。既定loopbackのtrusted local利用を前提とし、Internetへ直接公開しないでください。LAN / Android等へ広げる前に認証、HTTPS、利用者分離、rate limitが必要です。
- 現在baselineは要件v2.0、API v2.3、画面v2.7、変更単位`SC-2026-08-19-05`です。

## 2026-08-19 軽量スキャンJSON契約修正

- legacy `POST /api/ai/stock-review`の軽量スキャンで、valid JSONの`portfolio_summary.concentration_comment`と`summary_view`を、それぞれcanonicalな`concentration_risk`と`overall_view`へ追加OpenAI callなしで正規化します。
- mode別JSON Schemaをruntime Pydantic modelのfieldへ揃え、top-level、portfolio summary、stock itemを`additionalProperties=false`にしました。scannerのstock schemaは30項目未満へ縮小し、`judgement`を7つのcanonical codeへ限定します。
- provider JSON rootはrequest modeのoutput schemaが許可するkeyだけを受理します。`status`、`error`、`cache_hit`、`parse_failure_kind`等のservice-owned fieldをmodelが返しても`schema_validation`です。有効なJSON配列は内部objectを抜き出さず`root_shape`とします。
- `stocks`の各要素はobject、存在する`judgement`と互換summary aliasはstringでなければなりません。異なる型を黙って破棄・文字列化せず`schema_validation`にします。
- parse失敗は`json_syntax`（JSON構文）、`root_shape`（root形式）、`schema_validation`（項目・型・Pydantic不一致）へ分けます。有効なJSONの項目不一致を「JSON構文エラー」とは表示しません。
- JSON整形retry後も構造化できない場合、生応答は調査用に表示・履歴保存できますが、`status=json_parse_failed`の失敗のままです。raw fallback判定はservice自身のparse経路だけが設定し、providerが返したstatusには依存しません。成功review回数へ加算せず、cacheへ保存・読出ししません。
- dashboardは上記3分類を赤いerror cardで表示します。失敗attemptでもprimary/repairのprovider call、token、概算額は発生し得て、`api_calls`へ記録されます。
- canonical `POST /api/ai/analyses`の`gpt-5.6-terra`、`STANDARD`、plain `response.output_text`、`store=false`、ローカルSQL保存契約は変更していません。

## 2026-08-18 東証/J-Quants銘柄マスター同期

- dashboardの`東証全銘柄を同期`は、利用者自身の`JQUANTS_API_KEY`でJ-Quants上場銘柄マスターを取得し、git管理外のローカルDBへ保存します。取得した完全な一覧をこのpublic repositoryへ同梱・再配布しません。
- J-Quants個人版は個人の私的利用等の契約条件があります。利用者は自身のplanと[J-Quants利用規約](https://jpx-jquants.com/termsofservice)を確認し、取得データそのものの第三者配信や、そのデータを使ったserviceの第三者提供を行わないでください。本repositoryはデータとAPIキーを含まないlocal-use codeだけを公開しており、public hostや第三者向け運用には別途適切な契約・許諾が必要です。
- 対象はJ-Quantsが返す東証上場issueです。普通株に加えてETF、REIT、優先株等もprovider responseに含まれる限り同期しますが、名古屋・福岡・札幌等の地方取引所単独銘柄を含む「国内全取引所の全銘柄」は保証しません。
- bundled `data/security_master_jp.csv`は36件の初期検索seedだけです。seedは不足recordのinsertに限定され、既存J-Quants recordを上書きせず、全件同期済みとは扱いません。
- dashboardは完全/未確認status、J-Quants由来/ローカル有効件数、情報基準日`source_as_of`、同期時刻を表示します。`source_as_of`は利用者のJ-Quants planに応じて遅延し得るため、同期時刻やリアルタイム時点とは区別してください。
- 完全な現行snapshotは、本番では4,000件以上かつ全recordの`source_as_of`が1日へ一致する必要があります。さらに、既存のJ-Quants有効件数と旧importer由来の支配的legacy cohortを足した基準件数から5%を超えて縮小する取得は、DB変更前に拒否します。検証を通った現行snapshotだけが今回集合にないJ-Quants所有recordをinactiveへ変更し、historical同期は現行status/active状態を上書きしません。
- 旧importerがproviderの`Date`を`listed_date`へ誤格納した4,000件以上の支配的legacy cohortを検出した場合、通常のdashboard/API同期はDB変更前に停止します。内容を確認した上でcurrent snapshotに`python scripts/sync_security_master.py --adopt-legacy`を明示指定してください。
- 5桁numeric普通株の末尾`0`は既存4桁identifierへ正規化しますが、非zero suffixの優先株等と英数字raw identifierは別issueとして保持します。ordinary/preferred等のidentity split候補にwatchlist、保有、価格等の外部キー参照があれば自動修復せず同期全体を拒否します。pagination循環・code衝突はfail closed、429は有限回だけ再試行します。
- 銘柄検索は同期済みローカルDBだけを読み、検索候補ごとのJ-Quants外部照会を行いません。J-Quantsのtimeout、network、invalid JSON、HTTP errorは安全な分類またはstatusだけを表示し、provider response bodyやAPIキーをbrowserへ返しません。
- `python scripts/sync_security_master.py --dry-run`はJ-Quants同期transactionをrollbackしますが、実行前の`init_db()`によるschema初期化・migrationと、不足している36件seedのbootstrapは先に永続化され得ます。完全に無変更のpreviewではありません。

## 2026-08-18 銘柄検索から保有入力

- dashboardの銘柄検索は、銘柄名、数字コード、英字を含むコードに対応します。たとえば`キオクシア`または公開コード`285A`で、同期済みmasterのキオクシアホールディングスを検索できます。
- 各検索結果に`保有入力へ`と`詳細を見る`を表示します。`保有入力へ`はPortfolio panelへ銘柄コードを入れて数量欄へ移動するだけで、自動保存しません。数量を入力し、必要なら平均取得単価・メモを追加してから`保有を保存`を押してください。
- J-Quants masterが英字を含むコードを末尾`0`付きraw identifier（例:`285A0`）で保持している場合、検索結果の表示と保有入力は公開コード`285A`にします。詳細画面は登録済みmasterを開くためraw identifierを維持します。
- `POST /portfolio`は公開4文字コード`285A`を、一意な既存raw master`285A0`へ解決します。これにより`285A`という別placeholder masterの重複作成を防ぎます。既存の5文字identifier入力も引き続き利用できます。
- キオクシアが検索結果へ出ない環境では、dashboardの`東証全銘柄を同期`でJ-Quants上場masterを同期してください。同期には利用者自身の`JQUANTS_API_KEY`が必要です。

## 2026-08-17 legacy AI利用量・概算額

- dashboardのlegacy stock-review日次上限を50回から300回へ変更しました。1回は銘柄数に関係なく、正常完了した一括レビュー1件です。5銘柄をまとめて軽量スキャンしても1回です。
- OpenAI Responses APIのprovider callは`api_calls`として別に集計します。JSON整形repair等により、1レビューでprovider callが複数になる場合があります。
- 300回は成功した一括reviewの運用上限で、provider call数や費用のhard capではありません。OpenAI/最終parse失敗は成功review回数を消費せず、provider attemptの原子的予約やhard cost ceilingは今後の課題です。
- `GET /api/ai/stock-review/usage`は、JSTの本日・今月について、成功レビュー回数、OpenAI呼出回数、残数、token使用量、実Web検索回数、USD概算額、金額未算定callを返します。
- dashboardは起動時と各AIレビュー終了時に利用量を更新し、「本日 成功レビュー x / 300回」「今月 成功レビュー x回」、OpenAI呼出回数、概算額を表示します。`database`等の内部値は「対象: 実DB保有銘柄」等の利用者向けlabelへ変換します。
- 概算はOpenAIが返したinput / cached input / output tokenと実Web検索callを、versionedな2026-08-17時点のstandard pricingへ適用した参考値です。正式な請求額ではなく、OpenAI PlatformのUsage Dashboardと請求情報が正本です。算定できないcallは0円とせず件数を表示します。
- usage正本はgit管理外の`data/ai_review_usage_v2.json`です。旧`data/ai_review_usage.json`はtest汚染の可能性があるため移行せず、更新前の回数・金額は新集計に含めません。ledgerへAPIキー、prompt、質問、回答は保存しません。
- このquotaと集計はlegacy `/api/ai/stock-review`系だけが対象です。canonical `/api/ai/analyses`のmodel、`STANDARD`、保存、error契約は変更しません。

## 2026-08-17 canonical AI安全性・保存失敗処理・prompt表記修正

- canonical `POST /api/ai/analyses` のOpenAI Responses requestは常に`store=false`を送ります。これはResponses APIのApplication State保存を無効化する設定であり、組織全体のZero Data Retentionやabuse monitoring logの非保持まで保証するものではありません。保持方針は[OpenAI公式のデータ管理資料](https://developers.openai.com/api/docs/guides/your-data)を確認してください。
- OpenAI回答生成とローカルSQL保存を別の結果として返します。生成成功後に保存できなかった場合もHTTP 200、`status=success`、非空`answer_text`を返し、`persistence_status=failed`と安全なwarningを付けます。OpenAIを再呼び出ししません。
- 保存成功時だけ「保存済み」と「別ウィンドウで大きく表示」を出します。保存失敗時は回答本文とwarningだけを表示し、そのrequest IDは保存詳細APIではnot foundになります。
- API runnerの既定bindは`127.0.0.1`です。LAN確認は信頼できる閉じたネットワークでのみ、明示的に`python scripts/run_api.py --host 0.0.0.0`を使います。現在は認証、利用者分離、canonical endpointのrate limitがないため、Internetへ直接公開しないでください。Android対応や外部公開の前に認証、HTTPS、rate limitが必要です。
- Docker Composeの公開portも既定でhostの`127.0.0.1`だけにbindします。container内部のUvicorn bindはport forwardingのため`0.0.0.0`のままです。
- DB schema初期化はFastAPI lifespanだけで1回実行し、`create_app()`からDB副作用を除きました。
- active promptは`2026.08.18`です。immutableなv2026.08.17 assetを残し、runtime入力も含めて根拠labelを`【V】確認済み`、`【E】推定`、`【U】未確認`へ統一します。

## AI回答保存・大画面表示

- canonical `POST /api/ai/analyses` の成功回答をSQLite / PostgreSQLの `ai_analysis_record` に自動保存します。保存の成否は`persistence_status`で回答生成の成否と分離します。
- 保存済み回答は `GET /api/ai/analyses/{request_id}` で再取得できます。保存成功後にだけ「別ウィンドウで大きく表示」が現れ、`GET /ui/analysis/results/{request_id}` の幅広いプレーンテキストreaderを開きます。
- AI送信中は銘柄検索・銘柄選択・質問編集をロックし、送信対象と表示先が途中で入れ替わる競合を防ぎます。canonical APIはFastAPIの入力検証エラーを含む全responseへ`Cache-Control: no-store`を付与します。
- 保存するのは質問、回答、銘柄snapshot、生成設定、OpenAI response ID、prompt provenanceです。APIキー、prompt全文、providerのraw response / errorは保存しません。
- prompt sourceの選択範囲はv2026.08.17由来の共通OS、必要な共通入力、no-tools制約、module 3.1だけを維持します。active bundleは表記正規化版v2026.08.18で、3.2〜3.14やJSON Schemaは送りません。
- 保存済み回答APIには認証・利用者分離・削除・保持期限がまだありません。ローカルDBはGit管理外ですが、現状はtrusted local環境だけで利用してください。

## 2026-08-19 仕様baseline更新

- 当該変更時baselineを要件 v1.9、API v2.2、画面 v2.4へ更新し、legacy軽量スキャンのlocal master identity補完、canonical ticker重複解消、名称・code併記、live/mock/cache共通のsummary表示を反映しました。現在の正本は冒頭の最新baselineと各`current.md`を参照してください。
- 仕様版の対応、変更理由、互換性、非対象、既知制約は `docs/spec_change_history.md` で追跡します。
- 旧versioned文書とlegacy AI endpointは履歴・互換機能として保持しています。

## 2026-08-17 定型prompt最小統合

- `POST /api/ai/analyses` の既存縦スライスへ、添付 `株判断プロジェクト｜定型プロンプト集 v2026.08.17` の「1. 株判断共通OS」と「3.1 総合的な個別銘柄分析」だけを統合しました。3.2〜3.14は送信しません。
- `app/prompts/individual_security/` がversioned Markdown asset、manifest、`IndividualSecurityPromptCompiler`を管理します。合成順は共通OS、共通入力ルール、Web・外部市場データなしの実行制約、3.1用途module、銘柄context、自由質問です。
- OpenAI requestの`instructions`へ共通規則と3.1、`input`へ銘柄contextと質問を渡します。prompt version、使用asset、module ID、compiled SHA-256はOpenAI response metadataへ記録し、prompt全文・質問はmetadata、公開API response、browserへ出しません。
- 固定model `gpt-5.6-terra`、`STANDARD`、`reasoning.effort=medium`、`text.verbosity=medium`、`response.output_text`方式を維持します。Web検索、Structured Outputs、JSON修復、fallbackは追加していません。
- 現行promptの比較用代表質問10件は `tests/fixtures/ai_analysis/individual_security_questions_v2026_08_18.json` にあり、v2026.08.17 fixtureも再現比較用に保持します。

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
- 1回あたりの対象銘柄数、日次実行回数、推定コスト、ローカルキャッシュ、ローカルJSON履歴保存を持ちます。現在の日次既定値は300で、成功した一括reviewを銘柄数に関係なく1回と数えます。
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

- `data/security_master_jp.csv`は36件のローカル日本語検索seedとして追加されました。現行実装では起動時に不足recordだけをinsertし、検索操作で暗黙同期せず、J-Quants metadataを上書きしません。
- dashboardの現行buttonは`東証全銘柄を同期`です。`POST /securities/master/sync?require_jquants=true`を呼び、J-Quants V2 `/equities/master`から完全な現行snapshotを取得できない場合は失敗として表示します。
- `JQUANTS_API_KEY`が無い環境でも36件seedの最低限検索は動きますが、東証/J-Quants listed issuesを検索対象にするには`.env`または起動環境へ利用者自身のkeyを設定してください。
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
- `API_HOST=127.0.0.1`
- `API_PORT=8000`
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
- `OPENAI_DAILY_REQUEST_LIMIT=300`
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

既定のlisten先はこのPCだけから到達できる`127.0.0.1:8000`です。LANまたはAndroid端末から一時的に確認する場合は、信頼できる閉じたLANでだけ次を明示してください。

```bash
python scripts/run_api.py --host 0.0.0.0
```

`0.0.0.0`はLAN内の他端末から到達可能になります。現在は認証、利用者分離、canonical endpointのrate limit、HTTPS終端がないため、Internetへ直接公開しないでください。Android対応や外部公開の前に認証、HTTPS、rate limitを実装してください。

## 起動モード

### live mode

```bash
python scripts/run_api.py --reload
```

- `--mock` を付けない通常起動です。
- 価格データが不足していて `JQUANTS_API_KEY` がある場合、UI 用の `price_chart` 取得時に J-Quants の日足同期を 1 回試します。
- それでも取得できない項目は、mock 補完せず `未取得` または空表示にします。

### 東証銘柄マスターを同期する

通常はdashboardの`東証全銘柄を同期`を使います。APIを直接確認する場合は次を実行します。

```bash
curl http://127.0.0.1:8000/securities/master/status
curl -X POST "http://127.0.0.1:8000/securities/master/sync?require_jquants=true"
```

browserを介さず運用確認する場合は次を使えます。出力はcredentialや銘柄全件ではなく、非secret provenanceと集計件数だけです。

```bash
python scripts/sync_security_master.py --dry-run
python scripts/sync_security_master.py
```

旧importでsource未記録のrecordをJ-Quants所有として明示採用する必要がある場合だけ、current snapshotへ`--adopt-legacy`を指定します。historical `--as-of YYYY-MM-DD`との同時指定はできません。

```bash
python scripts/sync_security_master.py --adopt-legacy --dry-run
python scripts/sync_security_master.py --as-of 2026-05-26 --dry-run
```

完全なprovider datasetは`data/`配下のローカルDBにだけ保持され、`.gitignore`で追跡対象外です。CSVへ書き出してpublic repositoryへ追加しないでください。

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
  - 個別銘柄1件の最小AI分析入口です。現在は `preset=STANDARD` のみ受け付けます。回答生成成功とローカル保存結果は別fieldで返し、保存失敗でも生成済み本文を返します。
- `GET /api/ai/analyses/{request_id}`
  - canonical経路で保存した回答1件をUUIDで再取得します。回答一覧は提供しません。
- `GET /watchlist`
- `POST /watchlist`
- `GET /portfolio`
- `POST /portfolio`
- `POST /portfolio/import/csv`
- `POST /api/ai/stock-review`
  - 5モードのAI分析入口です。`prompt_only` ではOpenAI APIを呼ばず、手動投入用プロンプトを返します。
- `GET /api/ai/stock-review/usage`
  - legacy stock-reviewだけのJST本日・今月の成功review数、provider call数、残数、token由来USD概算、未算定call、pricing provenanceを返します。正式請求額はOpenAI Platformを確認してください。
- `POST /portfolio/ai-review`
  - 互換入口です。内部的には multi-mode AI review service を使います。
- `DELETE /portfolio/{ticker_code}`
- `GET /securities/search`
- `POST /sources/bootstrap`
- `GET /securities/master/status`
  - 最新の完全な現行J-Quants同期について、scope、情報基準日、同期時刻、完全性、ローカル/J-Quants有効件数を返します。APIキーや銘柄全件は返しません。
- `POST /securities/master/sync`
  - UIの`東証全銘柄を同期`は`require_jquants=true`を付け、J-Quants V2 `/equities/master`の完全な現行snapshotを必須にします。取得・新規・更新・再有効化・無効化を別countで返します。
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

- 銘柄検索はDB-onlyです。36件seedは不足recordの初期insertだけに使い、全体検索には`POST /securities/master/sync`でJ-Quants listed masterをprivate local DBへ同期します。
- portfolio panel は watchlist 代替ではなく、`/portfolio` API と dashboard 内の手入力フォーム、`/portfolio/import/csv` で保持します。
- detail の信用需給は `flow` が空のとき J-Quants margin data を試行し、取得できれば `FlowSnapshot` を補完します。
- TDnet は JPX の official paid API connector を追加し、`POST /documents/sync/tdnet` で event 化できます。detail では `TDNET_API_KEY` があると当日分の自動同期も試行します。
- sector pulse / factor split の sector 比較は watchlist 内比較ではなく、`security_master` と `price_daily` から同業全体の 5 日 breadth を集計して使います。

- YouTube 補助観測は `POST /documents/sync/youtube` と `YOUTUBE_MONITORED_CHANNELS` で正式 route 化し、detail では recent 動画が無いときだけ auto sync を試します。
- 公式 IR は `POST /documents/import/ir` で allowlist domain の URL だけ event 化できるようにし、YouTube / IR も raw document と event の構造化シグナルに載せます。

### UI

- `GET /ui/analysis`
- `GET /ui/analysis/results/{request_id}`
  - 保存済み回答を別ウィンドウで読む大画面プレーンテキストreaderです。
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
