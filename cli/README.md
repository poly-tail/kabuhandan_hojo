# cli

`cli/` は PowerShell 互換 wrapper の置き場です。  
正本の実装は `scripts/` に置き、Windows 向けの呼び出し互換が必要なときだけここに薄い wrapper を残します。

## Current Wrappers
- `render_docs_graphs.ps1`: `python scripts/render_docs_graphs.py` を呼ぶ互換 wrapper

## Best Practices
- cross-platform 化できる処理は `scripts/` を正本にする
- `cli/` 側では引数橋渡しと exit code 制御だけを持つ
- wrapper を追加・削除したら `README.md` `scripts/README.md` `docs/changelog.md` を更新する
