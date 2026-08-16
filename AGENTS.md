# Agent Guide

## Product Guardrails
- このリポジトリは日本株の「判断補助」アプリであり、自動売買や投資助言の断定を目的にしない。
- 基幹ソースは J-Quants、EDINET API、YouTube Data API、明示 allowlist 化した IR サイトに限定する。
- 規約違反や robots 無視のスクレイピングを前提にした提案や実装を入れない。

## Repo Workflow
- 構成やコードを変えたら `docs/source_overview.md` `docs/folder_structure.md` `docs/src_call_graph.md` `docs/changelog.md` を確認する。
- 版付き文書を追加・昇格したら `python scripts/sync_current_files.py --write` を実行し、その後 `--check` で検証する。
- Mermaid 正本を変えたら `python scripts/render_docs_graphs.py` を実行する。
- 反復的な one-shot 操作は `scripts/` に置き、`cli/` は必要な互換ラッパだけ残す。

## Skills
- リポジトリローカル skill は `.agents/skills/` に置く。
- docs 更新作業では `update-docs` skill、`current.md` の同期では `sync-current-files` skill を使う。

