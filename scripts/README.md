# scripts

`scripts/` は cross-platform の実行入口です。  
PowerShell 固有の互換ラッパは `cli/` に残してもよいですが、正本の自動化ロジックはここへ寄せます。

## Current Scripts
- `run_api.py`: FastAPI runner。既定はloopbackの`127.0.0.1`へbindする。信頼できる閉じたLANでだけ`--host 0.0.0.0`を明示でき、`--mock`でDBなしのin-memory sample responseを返す
- `smoke_openai_response.py`: 固定の短い入力を実OpenAI Responses APIへ送り、status、response ID、非空output_textを確認する。APIキー、prompt本文、回答本文は出力しない
- `sync_security_master.py`: 利用者自身のJ-Quants APIキーで東証listed-issue masterをgit管理外のprivate local DBへ同期する。current/historical `--as-of`、`--dry-run`、currentだけの明示`--adopt-legacy`を提供し、credentialや銘柄全件ではなくprovenance/countだけを出力する。`--dry-run`がrollbackするのはmaster同期transactionであり、先行する`init_db()`のschema初期化・migrationと不足36件seed bootstrapは永続化され得る。完全datasetをrepositoryへ同梱・再配布しない
- `render_docs_graphs.py`: Mermaid 正本から SVG を生成する。`--check` で差分確認もできる
- `sync_current_files.py`: `docs/*/current.md` を最新版の versioned file に同期する

## Dashboard AIの画面QA

`check_stock_ai_browser.py`は任意のPlaywright / Chromiumを使い、アプリHTMLの全HTTPを合成APIへ差し替えて画面を検証する。server、実DB、外部providerを呼ばない。production依存へPlaywrightを混ぜない。

```bash
python -m pip install -e ".[dev,browser]"
python -m playwright install chromium
python scripts/check_stock_ai_browser.py
```

viewportは1440・960・390pxで、状態、長文、prompt、Portfolio/named Watchlist、reader、履歴、keyboard、document幅を検査する。既定の画像・report出力先はGit管理外の`test-results/stock-ai`で、出力先等は`--help`を参照する。CIは`.[dev,browser]`と`python -m playwright install --with-deps chromium`を導入し、同じコマンドを実行する。Nodeの軽量動的検証は`node tests/js/stock_ai_state.test.cjs`と`node tests/js/stock_ai_snapshot.test.cjs`で、CIでも実行する。画面描画の確認とは区別する。

全検証手順は[../tests/README.md](../tests/README.md)、契約の現行版は[../docs/spec_change_history.md](../docs/spec_change_history.md)を参照する。

OS clipboardはstubを使い、Markdownはdownload導線・routeで差し替えたexport取得を検査する。実OS clipboard転送とnativeファイルdownload完了は確認範囲外である。readerのpopup・CSP・スクリーンショット・PDF描画は実Chromiumで検査する。
