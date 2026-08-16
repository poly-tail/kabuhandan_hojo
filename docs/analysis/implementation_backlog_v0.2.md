# implementation backlog v0.2

2026-04-21 時点の backlog です。no-mock live UI、chart detail 強化、市場地合い proxy 化まで反映した後の残課題を整理しています。

## 優先度高

1. review 画面の正本仕様化
- review 専用 screen spec と API 契約を起こす
- watchlist / detail / chart と重複する責務を切り分ける

2. portfolio 更新フローの設計
- 現状は watchlist を中心に運用
- CSV import を正式に入れるか、入れないままにするか判断が必要

3. TDnet の正式導入判断
- 現状は参照リンクと source label のみ
- connector を持つなら EDINET との canonical ルールを明文化する必要がある

## 優先度中

4. server-side と client-side の役割整理
- chart detail の描画は client-side 中心
- screening や review に同じ補助指標を持ち込むなら、server 側でどこまで返すか決める

5. reference link の表示改善
- detail / chart で source stack をどう短く見せるか
- 速報、一次ソース、手動参照を UI 上でより区別する

## 優先度低

6. sector まわりの精度向上
- 現在の sector pulse は watchlist 内の同業比較がベース
- 業種 breadth を強化するなら別 source の追加検討が必要

7. YouTube / IR の補助観測強化
- source policy を壊さない範囲で、既存 allowlist と公式 API のみを使って拡張する
