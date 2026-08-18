# 株判断プロジェクト｜定型プロンプト集 v2026.08.18（根拠ラベル表記正規化版）

## 派生元

- source title: 株判断プロジェクト｜定型プロンプト集 v2026.08.17
- source SHA-256: `09C7412D2C8FF81BB5F3BDF2EC07C1DC7E251EBA370A0CA994C0D7E2642FFFC1`

## この版の変更

- 根拠ラベルの括弧を、U+3016 / U+3017から正式表記のU+3010 / U+3011へ統一する。
- 正式ラベルは`【V】確認済み`、`【E】推定`、`【U】未確認`とする。
- 共通OS、個別銘柄MVP用の共通入力rule、no-tools実行制約、用途module 3.1の意味内容は変更しない。
- runtimeの銘柄contextと自由質問に旧括弧が含まれる場合も、OpenAI requestへ渡す前に正式括弧へ正規化する。

## 送信境界

このrelease descriptor自体はOpenAI requestへ送信しない。manifestのsource provenanceと整合性検証にだけ使用する。
