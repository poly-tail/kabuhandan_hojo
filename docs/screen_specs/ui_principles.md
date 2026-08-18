# UI Principles

## 目的

監視銘柄の優先度、仮説、地合い、材料を短時間で読み取れることを優先する。

## 原則

- 情報の優先順位を明確にする
- live mode では不明なものを不明なまま見せる
- source policy を UI 上でも崩さない
- top から detail、detail から chart の流れを短く保つ

## 現在の表示方針

- 地合いは market proxy ベース
- detail は仮説と factor split を先に見せる
- chart は client-side 補助表示で読みやすさを優先する
- watchlist 未登録の候補も top で見えるようにする
- AI失敗や空回答を回答として表示しない
- AI回答本文とrequest ID等の診断情報を分離する
- APIキー、prompt全文、質問全文などserver-sideの内部情報を通常画面へ露出しない
- 通常の分析画面は入力と直近回答に集中し、保存済み回答の精読は別ウィンドウの幅広いreaderへ分離する
- 別ウィンドウはユーザーが押す通常リンクで開き、`noopener noreferrer`を付ける。回答本文をURLへ渡さない
- 保存済み回答もMarkdownやHTMLとして解釈せず、プレーンテキストで表示する
- 保存失敗は生成失敗と混同せず、回答本文を維持したままwarningを表示し、保存済み導線だけを出さない
- legacy AIの利用量は「成功review」「OpenAI呼出」「未算定」を分け、銘柄数や正式請求額と誤認しない文言で表示する
- 送信前heuristicは「今回の事前概算」、provider token由来の日/月集計は「概算」として分離し、OpenAI Platformを請求の正本と案内する
