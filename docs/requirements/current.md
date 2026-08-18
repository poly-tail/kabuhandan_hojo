# Requirements Current

> 現在の正本: `requirements_v1.6.md`

## 概要

- このファイルは要件文書の最新 pointer です。
- 詳細な要件は versioned file 側に保持します。

## 現在値

- 要件仕様書: v1.6
- 更新日: 2026-08-18
- 変更概要: 銘柄名・数字/英字コード検索、検索結果から保有入力への非保存導線、4文字公開codeのJ-Quants raw alias解決を追加

## 主な内容

- 日本株の判断補助アプリであること
- 自動売買を目的にしないこと
- dashboard検索結果の`保有入力へ`は公開codeのprefillと数量focusだけを行い、明示保存まではrecordを作らないこと
- portfolio登録は完全一致を優先し、一意な`<4文字>0` raw master aliasへ解決してplaceholder重複を防ぐこと
- raw codeはdetail/APIで維持し、公開code変換をdashboardの表示・入力境界に限定すること
- legacy日次上限の1回を、銘柄数ではなく正常完了した一括review 1件と定義すること
- provider API call、token、実Web検索、未算定callをreview quotaと分離してJST日次・月次集計すること
- 概算額は正式請求ではなく、OpenAI PlatformのUsage Dashboardを正本とすること
- 基幹sourceを J-Quants / EDINET API / YouTube Data API / allowlist公式IRに限定すること
- canonical `POST /api/ai/analyses`、保存詳細 `GET /api/ai/analyses/{request_id}`、独立画面と大画面reader
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- `gpt-5.6-terra` / `reasoning.effort=medium` / `text.verbosity=medium`
- prompt v2026.08.18の正式根拠label、銘柄名・コード分離入力、no-tools制約、用途module 3.1
- `response.output_text` のplain-text表示と、失敗をsuccessへ変換しないerror契約
- OpenAI生成成功とSQL保存結果を分離し、保存失敗でも回答本文とsafe warningを返すこと
- Responses Application State保存を`store=false`で無効化し、ZDR全体の保証とは区別すること
- 既定bindを`127.0.0.1`、DB初期化をlifespanの1回とすること
- 保存recordへ生成設定とprompt traceを残し、APIキー、prompt全文、provider raw response / errorを保存しないこと
- `request_id`を知る回答1件だけを別ウィンドウで再表示し、一覧・削除・exportは提供しないこと
- AI送信中は銘柄・質問入力をロックし、canonical responseはvalidation errorを含めて`no-store`にすること
- 新経路ではmock / cache / fallback / Web検索 / Structured Outputsを使わないこと
- 既存Portfolio multi-mode / Prompt Registry経路はlegacy機能として維持すること

## 更新ルール

1. 過去版を保持し、新しい版付き文書を追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
