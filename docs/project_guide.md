# Project Guide

## 基本姿勢

- 日本株の判断補助アプリとして、説明可能な情報整理を優先します。
- 自動売買や断定的な投資助言へ寄せません。
- 正式ソースと手動参照先を混同しません。

## 実装の置き場

- FastAPI route / UI shell は `app/`
- connector / feature / scoring / ingestion は `src/kabuhandan_hojo/`
- リポジトリ運用の one-shot 操作は `scripts/`
- 仕様書や設計メモは `docs/`

## docs 更新ルール

- 構成やコードを変えたら次を確認します。
  - `docs/source_overview.md`
  - `docs/folder_structure.md`
  - `docs/src_call_graph.md`
  - `docs/changelog.md`
- 版付き文書を追加・昇格したら次を実行します。

```bash
python scripts/sync_current_files.py --write
python scripts/sync_current_files.py --check
```

- 要件・API・画面の契約を変更したら `docs/spec_change_history.md` に、変更理由、互換性、非対象、既知制約を追記します。
- 過去の版付き文書は変更せず、新しい版を追加して `current.md` を昇格します。

- Mermaid 正本を変えたら次を実行します。

```bash
python scripts/render_docs_graphs.py
```

## UI / データ方針

- live mode で mock 補完はしません。
- 価格系列が不足している場合だけ J-Quants 同期を 1 回試します。
- 市場地合いは J-Quants の `TOPIX(1306)` / `Nikkei225(1321)` proxy を使います。
- proxy や価格が取得できない場合は `未取得` を返します。

## 変更時の確認

- Python の構文確認: `py -3 -m py_compile ...`
- unit test: `py -3 -m pytest tests\\unit\\...`
- docs 同期: `py -3 scripts\\sync_current_files.py --check`

## いまの推奨参照順

1. `README.md`
2. `docs/context.md`
3. `docs/requirements/current.md`
4. `docs/specs/current.md`
5. `docs/screen_specs/current.md`
6. `docs/spec_change_history.md`
7. `docs/information_sources.md`
8. `docs/analysis/README.md`
