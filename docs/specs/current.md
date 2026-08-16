# API Spec Current

> 現在の正本: `api_spec_v1.5.md`

## 概要

- このファイルは API 仕様書の最新 pointer です。
- 実際の契約は versioned file 側に保持します。

## 現在値

- API仕様書: v1.5
- 更新日: 2026-08-17
- 変更概要: 個別銘柄AI最小縦スライス、plain Responses出力、versioned prompt trace契約の追加

## 主な変更点

- `/ui/dashboard/data` を中心にした UI view model 契約
- live mode の no-mock 方針
- J-Quants market proxy を使う市場地合い表示
- `POST /api/ai/analyses` と `GET /ui/analysis`
- `gpt-5.6-terra` / `STANDARD` / medium reasoning / medium verbosityの固定契約
- `response.status`、response ID、非空 `response.output_text` のfail-closed検証
- prompt v2026.08.16、用途module 3.1、asset/hash trace metadata
- typed OpenAI errorと、prompt全文・質問・APIキーの非露出
- 新経路ではmock / cache / fallback / Web検索 / Structured Outputsを使用しない
- `POST /api/ai/stock-review` の `scanner` / `analyst` / `judge` / `critical` / `prompt_only`
- `target=candidates`、`user_hypothesis`、`position_intent`、`web_search_policy`、`action_plan`、`critical_warnings`
- legacy経路に限定したWeb検索、JSON Schema、JSON parse救済

## 更新ルール

1. 過去版を保持し、新しい版付きspecを追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
