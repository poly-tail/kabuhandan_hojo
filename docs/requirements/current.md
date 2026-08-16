# Requirements Current

> 現在の正本: `requirements_v1.2.md`

## 概要

- このファイルは要件文書の最新 pointer です。
- 詳細な要件は versioned file 側に保持します。

## 現在値

- 要件仕様書: v1.2
- 更新日: 2026-08-17
- 変更概要: 個別銘柄AI最小縦スライスとversioned PromptCompilerを追加し、legacy multi-mode経路との境界を明確化

## 主な内容

- 日本株の判断補助アプリであること
- 自動売買を目的にしないこと
- 基幹sourceを J-Quants / EDINET API / YouTube Data API / allowlist公式IRに限定すること
- canonical `POST /api/ai/analyses` と独立画面 `GET /ui/analysis`
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- `gpt-5.6-terra` / `reasoning.effort=medium` / `text.verbosity=medium`
- 共通OS、共通入力必要部分、no-tools制約、用途module 3.1のversioned PromptCompiler
- `response.output_text` のplain-text表示と、失敗をsuccessへ変換しないerror契約
- 新経路ではmock / cache / fallback / Web検索 / Structured Outputsを使わないこと
- 既存Portfolio multi-mode / Prompt Registry経路はlegacy機能として維持すること

## 更新ルール

1. 過去版を保持し、新しい版付き文書を追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
