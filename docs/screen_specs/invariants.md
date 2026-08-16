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

## source policy

- 正式 source と手動参照スタックを混同しない
- Yahoo! Finance や broker site は reference link としてのみ扱う

## detail / chart

- detail と chart は同じ `GET /ui/dashboard/data` を利用する
- chart detail の描画元は `detail.price_chart` と client-side 補助計算
