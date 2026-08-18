# Screen Spec Current

> 現在の正本: `screen_spec_v2.1.md`

## 概要

- このファイルは画面仕様書の最新 pointer です。
- 実際の画面契約は versioned file 側に保持します。

## 現在値

- 画面仕様書: v2.1
- 更新日: 2026-08-18
- 変更概要: 銘柄検索結果の`保有入力へ`/`詳細を見る`、公開code表示・prefill、数量focusと非自動保存を追加

## 主な変更点

- UI 5画面構成と独立URL `GET /ui/analysis`
- dashboardで銘柄名・数字/英字codeを検索し、結果からPortfolio入力またはdetailへ進む導線
- 英字5文字末尾`0`は表示・保有入力だけ公開4文字とし、detail actionはraw identifierを維持
- dashboard legacy AI usage panelと利用者向けholdings-source label
- chart detail 強化
- live mode の no-mock 表示
- market proxy ベースの地合い表示
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- 銘柄検索、loading、送信中の入力ロック、safe error、plain-text answer、request診断表示
- `persistence_status=saved`時だけ表示する保存済み状態と `別ウィンドウで大きく表示` link
- 保存失敗時は回答本文とwarningだけを表示し、reader linkと`saved_at`を表示しない
- `/ui/analysis/results/{request_id}` の最大幅1380px・plain-text readerとloading / error
- `target="_blank"` / `rel="noopener noreferrer"`、URLはUUIDだけ、responseは`no-store`
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
