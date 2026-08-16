# API Spec Current

> 現在の正本: `api_spec_v1.6.md`

## 概要

- このファイルは API 仕様書の最新 pointer です。
- 実際の契約は versioned file 側に保持します。

## 現在値

- API仕様書: v1.6
- 更新日: 2026-08-17
- 変更概要: canonical成功回答の原子的なSQL保存、UUID詳細GET、大画面reader、prompt v2026.08.17を追加

## 主な変更点

- `/ui/dashboard/data` を中心にした UI view model 契約
- live mode の no-mock 方針
- J-Quants market proxy を使う市場地合い表示
- `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}`、`GET /ui/analysis/results/{request_id}`
- `gpt-5.6-terra` / `STANDARD` / medium reasoning / medium verbosityの固定契約
- `response.status`、response ID、非空 `response.output_text` のfail-closed検証
- prompt v2026.08.17、銘柄名（銘柄コード）規則、用途module 3.1、asset/hash trace
- 成功responseのSQL保存、保存失敗時のrollback / `PERSISTENCE_ERROR`、未知UUIDの`ANALYSIS_NOT_FOUND`
- validation errorを含む保存API / HTMLの`Cache-Control: no-store`と、prompt全文・APIキー・provider raw payloadの非保存
- typed OpenAI errorと、prompt全文・質問・APIキーの非露出
- 新経路ではmock / cache / fallback / Web検索 / Structured Outputsを使用しない
- `POST /api/ai/stock-review` の `scanner` / `analyst` / `judge` / `critical` / `prompt_only`
- `target=candidates`、`user_hypothesis`、`position_intent`、`web_search_policy`、`action_plan`、`critical_warnings`
- legacy経路に限定したWeb検索、JSON Schema、JSON parse救済

## 更新ルール

1. 過去版を保持し、新しい版付きspecを追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
