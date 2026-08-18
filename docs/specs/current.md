# API Spec Current

> 現在の正本: `api_spec_v1.9.md`

## 概要

- このファイルは API 仕様書の最新 pointer です。
- 実際の契約は versioned file 側に保持します。

## 現在値

- API仕様書: v1.9
- 更新日: 2026-08-18
- 変更概要: `GET /securities/search`の数字/英字code対応と、`POST /portfolio`の一意なJ-Quants raw code aliasを追加

## 主な変更点

- `/ui/dashboard/data` を中心にした UI view model 契約
- 銘柄名、数字code、英字を含むcodeを検索し、raw master identifierを返す`GET /securities/search`
- `POST /portfolio`の完全一致優先と、一意な`<4文字>0` aliasによる既存master解決
- legacy stock-reviewの`review_runs`とprovider `api_calls`を分離したusage API契約
- `openai-standard-2026-08-17`によるtoken/Web検索概算と`unpriced_api_calls`
- live mode の no-mock 方針
- J-Quants market proxy を使う市場地合い表示
- `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}`、`GET /ui/analysis/results/{request_id}`
- `gpt-5.6-terra` / `STANDARD` / medium reasoning / medium verbosityの固定契約
- `response.status`、response ID、非空 `response.output_text` のfail-closed検証
- prompt v2026.08.18、正式根拠label、用途module 3.1、asset/source/hash trace
- `store=false`、保存結果field、保存失敗時もHTTP 200 + 生成済み本文、未知UUIDの`ANALYSIS_NOT_FOUND`
- `127.0.0.1`既定と明示LAN bind、lifespan-only `init_db()`
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
