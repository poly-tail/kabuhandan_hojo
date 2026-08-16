# Context

## 2026-08-17 個別銘柄AI分析 addendum

- 独立画面 `/ui/analysis` と canonical API `POST /api/ai/analyses` は、登録済み個別銘柄1件、自由質問、固定 `STANDARD`、OpenAI Responses API、プレーンテキスト回答だけを扱います。
- この経路は dashboard の旧Portfolio AI分析とは独立しています。mock、cache、fallback、Web検索、Structured Outputs、JSON修復、streaming は使用せず、OpenAI失敗や空回答を成功へ変換しません。
- 個別銘柄用promptは `app/prompts/individual_security/` のversioned assetsとmanifestを正本とし、共通OS、共通入力ルール、Web・外部市場データなし制約、用途module 3.1、銘柄context、自由質問をserver側で合成します。
- source v2026.08.17の「銘柄名（銘柄コード）」併記規則を使い、銘柄名とコードを分離してcontextへ入れます。3.2〜3.14やJSON Schemaは組み込みません。
- completedかつ非空の成功回答は `ai_analysis_record` へ自動保存し、同じ `request_id` で再取得できます。保存失敗はrollbackして成功扱いにしません。
- `/ui/analysis/results/{request_id}` は保存済み回答を幅広い別ウィンドウで再表示します。質問と回答はローカルDBへ保存しますが、APIキー、prompt全文、provider raw response / errorは保存しません。
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
- portfolio 更新フローは watchlist 中心で、CSV import は未実装
- TDnet は参照導線までで、自動 connector は未実装
- 一部 analysis メモは設計意図の保持が主目的で、実装と 1 対 1 ではない
