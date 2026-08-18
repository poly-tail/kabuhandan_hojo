# Context

## 2026-08-18 銘柄検索・保有入力 addendum

- dashboardの`GET /securities/search`利用箇所は、銘柄名、数字コード、英字を含むコードを案内し、検索結果ごとに`保有入力へ`と`詳細を見る`を分けます。
- `保有入力へ`はPortfolio panelへcodeをprefillし、数量欄へfocusするだけです。数量入力と`保有を保存`の明示操作まではrecordを作りません。平均取得単価とメモは任意です。
- J-Quants masterの英字5文字末尾`0`形式は、検索結果の表示と保有入力だけ公開4文字へ変換します。detail actionと検索API responseはraw master identifierを維持します。
- `POST /portfolio`は完全一致を優先し、公開4文字codeに完全一致がない場合だけ、一意な`<code>0`の`ticker_code`/`local_code`を既存masterとして解決します。`285A`は既存`285A0`へ紐付き、公開codeのplaceholder重複を防ぎます。
- master primary keyと既存参照recordのmigration、J-Quants connector全体のcode canonical化は行っていません。

## 2026-08-17 legacy stock-review usage addendum

- dashboardのlegacy stock-reviewだけに、既定300回/日のアプリ内quotaと、`GET /api/ai/stock-review/usage`によるJST本日・今月の利用量表示を追加しました。canonical `/api/ai/analyses`には適用しません。
- quotaの`review_runs`は銘柄数ではなく、正常完了したtop-level一括review数です。5銘柄を一度にscanしても1回です。mock、cache hit、prompt-only、limit拒否は増えません。
- providerの`api_calls`はreview数と別に記録します。primary response、JSON整形repair、後段parseに失敗したresponseを含み得るため、`api_calls`が`review_runs`より多い場合があります。
- usage v2 ledgerは`data/ai_review_usage_v2.json`へJST日別bucketを保存します。旧`ai_review_usage.json`はtest汚染の可能性があるため移行せず、更新前の月間回数・概算額は含みません。
- 概算額はprovider usageのinput / cached input / output tokenと実Web検索callを、2026-08-17時点のversioned standard pricingへ適用したUSD参考値です。算定不能callは`unpriced_api_calls`として残し、OpenAI PlatformのUsage Dashboardと請求情報を正本とします。
- ledgerとusage APIはAPIキー、prompt、質問、回答、銘柄contextを持ちません。unit testはusage/history/cache pathを一時directoryへ隔離します。

## 2026-08-17 個別銘柄AI分析 addendum

- 独立画面 `/ui/analysis` と canonical API `POST /api/ai/analyses` は、登録済み個別銘柄1件、自由質問、固定 `STANDARD`、OpenAI Responses API、プレーンテキスト回答だけを扱います。
- この経路は dashboard の旧Portfolio AI分析とは独立しています。mock、cache、fallback、Web検索、Structured Outputs、JSON修復、streaming は使用せず、OpenAI失敗や空回答を成功へ変換しません。
- 個別銘柄用promptは `app/prompts/individual_security/` のversioned assetsとmanifestを正本とし、共通OS、共通入力ルール、Web・外部市場データなし制約、用途module 3.1、銘柄context、自由質問をserver側で合成します。
- active prompt v2026.08.18では「銘柄名（銘柄コード）」規則を維持し、根拠labelを`【V】`、`【E】`、`【U】`へ統一します。v2026.08.17は履歴として不変で、3.2〜3.14やJSON Schemaは組み込みません。
- completedかつ非空の成功回答は `ai_analysis_record` への保存を試みます。同じ `request_id` で再取得できるのは保存成功時だけです。保存失敗でも生成済み本文を返し、保存結果は`persistence_status`で分離します。
- `/ui/analysis/results/{request_id}` は保存済み回答を幅広い別ウィンドウで再表示します。質問と回答は保存成功時だけローカルDBへ保存し、APIキー、prompt全文、provider raw response / errorは保存しません。
- canonical Responses requestは`store=false`を明示します。これはOpenAIのResponses Application State保存を無効化する設定で、Zero Data Retention全体の保証ではありません。
- API runnerは既定で`127.0.0.1`へbindします。認証、利用者分離、canonical rate limit、HTTPSがないため、`0.0.0.0`は信頼できる閉じたLANでだけ明示し、Internetへ直接公開しません。
- AI送信中は銘柄検索・選択と質問編集をロックし、応答待ちの間に表示対象が変わらないようにします。canonical APIはvalidation errorを含む全responseを`no-store`にします。
- 現在渡せる銘柄情報は主に `security_master` のcode、name、market、industry、listed dateです。価格、決算、テクニカル、需給、市場、マクロ、イベントは未提供として区別します。
- 現行endpointにはアプリ独自の認証とrate limitがないため、trusted local環境向けです。Internetへ直接公開する前にhardeningが必要です。

## 2026-04-23 manual refresh addendum

- 取得状況を画面上で切り分けるため、dashboard / detail / chart の各セクション内に手動更新ボタンを配置しました。global なまとめ更新パネルは使いません。
- 主要な自動取得系は UI から個別に叩けます。API key が無い場合、失敗理由は押したボタンと同じセクションの feedback 領域に表示します。開示・動画の対象なしは失敗ではなく 0 件の正常終了として扱います。

## 2026-04-23 local master addendum

- 銘柄検索は `data/security_master_jp.csv` をローカル正本として `security_master` に同期します。J-Quants V2 `/equities/master` は全上場銘柄検索用の正本で、UI の `銘柄DB更新` は API key が無い場合に失敗として表示します。
- API key が無い環境でも最低限の日本語検索は動きますが、全上場銘柄を検索対象にするには `JQUANTS_API_KEY` が必要です。
- Market Overview は `price_daily` にある `1306` / `1321` の価格系列から作ります。dashboard 読み込み時の自動同期は行わず、未取得時は `市場価格更新` ボタンでだけ J-Quants daily bars を試します。

## 2026-04-23 YouTube / IR addendum

- YouTube / official IR は backlog のままではなく、`POST /documents/sync/youtube` + `YOUTUBE_MONITORED_CHANNELS` で recent observation を同期でき、`POST /documents/import/ir` で allowlist domain の公式 IR URL を event 化できるようにしました。

## 2026-04-23 addendum

- portfolio は watchlist 代替ではなくなり、`portfolio_holding` と `/portfolio` API、`/portfolio/import/csv` で保持します。dashboard から手入力で更新できます。
- 銘柄検索は seed catalog 依存をやめ、`security_master` に同期済みの listed master を前提にした DB-only 検索です。
- TDnet は JPX official API connector を追加し、sync job と detail 時の当日 auto sync を持ちます。
- sector 比較は watchlist 内の雰囲気比較ではなく、`security_master` と `price_daily` から同業全体の breadth を集計して使います。
- review 画面は `/ui/review` として追加済みです。残る主な強化余地は YouTube / official IR の構造化シグナル強化です。

## 目的

`kabuhandan_hojo` は、日本株の監視と仮説整理を補助するローカルアプリです。売買を自動化するのではなく、地合い、個別材料、テクニカル、需給を同時に見て「今どこに注意を向けるべきか」を整理します。

## 現在の画面構成

- `/ui/analysis`
  - 登録済み個別銘柄1件の検索・選択
  - 自由質問と固定 `STANDARD`
  - loading / error / プレーンテキスト回答
  - 成功時の保存済み表示と別ウィンドウreaderへのリンク
- `/ui/analysis/results/{request_id}`
  - 保存済みの銘柄、質問、回答、生成日時を大画面で再表示
  - `textContent` / `white-space: pre-wrap` のプレーンテキスト描画
- `/ui/dashboard`
  - 地合い overview
  - 優先度の高い監視銘柄
  - alerts / event feed
  - watchlist 一覧
  - watchlist 未登録の高スコア候補
  - legacy Portfolio AIの本日/今月の成功review、OpenAI呼出数、残数、概算額
  - 銘柄名・数字/英字コード検索からPortfolio入力またはdetailへ進む導線
- `/ui/security/{ticker_code}`
  - 個別銘柄 detail
  - 仮説メモ
  - 地合い分離
  - テクニカル / 需給 / 材料 / 参考リンク
  - 直近チャートプレビュー
- `/ui/security/{ticker_code}/chart`
  - チャート分析詳細
  - 20日 / 40日 / 全期間切替
  - MA 5 / 25 / 75 overlay
  - RSI / MACD 補助表示

## live mode の原則

- UI は live mode で mock 補完を行いません。
- 価格系列が足りない場合のみ、J-Quants からの同期を 1 回試します。
- それでも不足している項目は `未取得` または空のまま返します。
- 地合い分離は watchlist の雰囲気推定ではなく、J-Quants の `TOPIX(1306)` と `Nikkei225(1321)` proxy を使います。

## データソースの方針

- 自動取得の基幹ソース:
  - J-Quants
  - EDINET API
  - YouTube Data API
  - allowlist 化した公式 IR
- 手動参照スタック:
  - TDnet
  - 株探 / みんかぶ
  - 日経 / Reuters / Bloomberg
  - SBI証券 / 楽天証券
  - X / StockTwits

## いまの積み残し

- `/api/ai/analyses` の認証、アプリ側rate limit、公開host/TLS方針
- prompt構成異常のtyped API error
- 保存済みAI回答の認証・利用者分離・暗号化・保持期限・削除・一覧導線
- review 画面の正本仕様はまだ別文書に切り出していない
- portfolioはdashboardの銘柄検索結果から入力フォームへ進める。CSV importの画面導線は未実装
- TDnet connectorと手動・detail時の同期経路は実装済みだが、有料の`TDNET_API_KEY`がない環境では参照リンクだけを利用する
- 一部 analysis メモは設計意図の保持が主目的で、実装と 1 対 1 ではない
