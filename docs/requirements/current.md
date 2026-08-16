# Requirements Current

> 現在の正本: `requirements_v1.3.md`

## 概要

- このファイルは要件文書の最新 pointer です。
- 詳細な要件は versioned file 側に保持します。

## 現在値

- 要件仕様書: v1.3
- 更新日: 2026-08-17
- 変更概要: canonical個別銘柄AI回答のローカル保存、UUID再取得、大画面reader、prompt v2026.08.17を追加

## 主な内容

- 日本株の判断補助アプリであること
- 自動売買を目的にしないこと
- 基幹sourceを J-Quants / EDINET API / YouTube Data API / allowlist公式IRに限定すること
- canonical `POST /api/ai/analyses`、保存詳細 `GET /api/ai/analyses/{request_id}`、独立画面と大画面reader
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- `gpt-5.6-terra` / `reasoning.effort=medium` / `text.verbosity=medium`
- prompt v2026.08.17の共通OS、銘柄名・コード分離入力、no-tools制約、用途module 3.1
- `response.output_text` のplain-text表示と、失敗をsuccessへ変換しないerror契約
- 成功回答だけをSQLへ自動保存し、保存失敗はrollbackして`PERSISTENCE_ERROR`にすること
- 保存recordへ生成設定とprompt traceを残し、APIキー、prompt全文、provider raw response / errorを保存しないこと
- `request_id`を知る回答1件だけを別ウィンドウで再表示し、一覧・削除・exportは提供しないこと
- AI送信中は銘柄・質問入力をロックし、canonical responseはvalidation errorを含めて`no-store`にすること
- 新経路ではmock / cache / fallback / Web検索 / Structured Outputsを使わないこと
- 既存Portfolio multi-mode / Prompt Registry経路はlegacy機能として維持すること

## 更新ルール

1. 過去版を保持し、新しい版付き文書を追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
