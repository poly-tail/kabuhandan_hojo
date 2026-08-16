# kabuhandan_hojo API Spec v1.2

## scope

live mode の no-mock 方針と `price_chart` の扱いを反映した版です。

## 主な追加

- `detail.price_chart` を UI payload の正式項目として整理
- live mode では mock 補完を行わない
- `price_chart` が空なら J-Quants 日足同期を 1 回試す
- 取得できない項目は `未取得` または空表示とする

## notes

- Yahoo! Finance や broker site は基幹 source に含めない
- chart detail の client-side 描画前提を API 側からも説明
