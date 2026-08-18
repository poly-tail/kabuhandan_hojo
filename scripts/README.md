# scripts

`scripts/` は cross-platform の実行入口です。  
PowerShell 固有の互換ラッパは `cli/` に残してもよいですが、正本の自動化ロジックはここへ寄せます。

## Current Scripts
- `run_api.py`: FastAPI runner。既定はloopbackの`127.0.0.1`へbindする。信頼できる閉じたLANでだけ`--host 0.0.0.0`を明示でき、`--mock`でDBなしのin-memory sample responseを返す
- `smoke_openai_response.py`: 固定の短い入力を実OpenAI Responses APIへ送り、status、response ID、非空output_textを確認する。APIキー、prompt本文、回答本文は出力しない
- `sync_security_master.py`: 利用者自身のJ-Quants APIキーで東証listed-issue masterをgit管理外のprivate local DBへ同期する。current/historical `--as-of`、`--dry-run`、currentだけの明示`--adopt-legacy`を提供し、credentialや銘柄全件ではなくprovenance/countだけを出力する。`--dry-run`がrollbackするのはmaster同期transactionであり、先行する`init_db()`のschema初期化・migrationと不足36件seed bootstrapは永続化され得る。完全datasetをrepositoryへ同梱・再配布しない
- `render_docs_graphs.py`: Mermaid 正本から SVG を生成する。`--check` で差分確認もできる
- `sync_current_files.py`: `docs/*/current.md` を最新版の versioned file に同期する
