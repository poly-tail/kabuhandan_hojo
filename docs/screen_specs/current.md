# Screen Spec Current

> 現在の正本: `screen_spec_v1.7.md`

## 概要

- このファイルは画面仕様書の最新 pointer です。
- 実際の画面契約は versioned file 側に保持します。

## 現在値

- 画面仕様書: v1.7
- 更新日: 2026-08-17
- 変更概要: 独立した個別銘柄AI分析画面とserver-side定型prompt適用境界の追加

## 主な変更点

- UI 4画面構成と独立URL `GET /ui/analysis`
- chart detail 強化
- live mode の no-mock 表示
- market proxy ベースの地合い表示
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- 銘柄検索、loading、safe error、plain-text answer、request診断表示
- 新画面ではmock / Web検索 / Structured Outputs / raw response fallbackを使わない
- prompt asset / version / APIキーをbrowserへ出さない
- dashboard legacy Portfolio AI画面との責務分離
- 保有銘柄全体のワンクリックAI分析
- 狙い中銘柄、ユーザー仮説、建玉意図、Web検索、mock_response、prompt_only操作
- warnings、sources、具体的な執行案、反証条件、辛口チェック表示

## 更新ルール

1. 過去版を保持し、新しい版付きspecを追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
