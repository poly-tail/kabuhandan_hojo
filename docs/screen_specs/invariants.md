# Screen Invariants

現在の UI で崩してはいけない前提をまとめます。

## 遷移

- dashboard から個別銘柄ページは新しいタブで開く
- 元の dashboard タブは遷移しない
- chart detail から detail へ戻るリンクも新しいタブで開く

## データ表示

- live mode で mock 補完をしない
- 取得できない項目は `未取得` または空表示にする
- 地合い表示は market proxy がなければ `未取得` にする

## 個別銘柄AI分析

- 対象はactiveな登録済み銘柄1件、回答設定は `STANDARD` 固定とする
- OpenAI失敗、非completed応答、空回答を成功表示へ変換しない
- mock、cache、raw response fallback、Web検索、Structured Outputsを使用しない
- `answer_text` は `textContent` と `white-space: pre-wrap` でプレーンテキスト表示する
- APIキー、prompt全文、質問全文、stack traceを画面や診断情報へ表示しない
- 未提供の市場・価格・決算・需給情報を取得済みのように見せない
- OpenAI回答生成とローカルDB保存を別の状態として扱い、保存失敗でも生成済み本文と安全なwarningを表示する
- AI送信中は銘柄検索・選択と質問編集をロックし、応答待ちの銘柄と表示対象を入れ替えない
- `persistence_status=saved`のときだけ保存済み表示と `target="_blank"` / `rel="noopener noreferrer"` の大画面リンクを有効にする
- 大画面readerも質問・回答を `textContent` / `white-space: pre-wrap` で描画し、取得失敗時に本文を表示しない
- 保存済み回答URLにはUUID `request_id`だけを含め、回答本文や秘密情報を含めない

## dashboard legacy AI利用量

- 日次quotaの1回は銘柄数ではなく、正常完了したlive一括review 1件とする
- `review_runs`とprovider `api_calls`を別表示し、JSON repair等の追加callをreview回数へ見せない
- mock、cache hit、prompt-only、limit拒否を成功review回数へ加えない
- 本日/今月はAsia/Tokyo基準とし、概算額を正式請求額として表示しない
- 算定不能なprovider callを0円扱いせず、未算定件数を表示する
- `database`等の内部値をそのまま見せず、「対象: 実DB保有銘柄」等へ変換する
- usage表示の取得失敗をAI分析自体の失敗と混同しない
- legacy usage panelをcanonical `/ui/analysis`へ混在させない

## source policy

- 正式 source と手動参照スタックを混同しない
- Yahoo! Finance や broker site は reference link としてのみ扱う

## detail / chart

- detail と chart は同じ `GET /ui/dashboard/data` を利用する
- chart detail の描画元は `detail.price_chart` と client-side 補助計算
