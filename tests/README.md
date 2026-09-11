# Tests

- `unit/`: API/service/UI shellの単体・回帰テスト。外部providerはstub、DB・履歴・cache・usageは一時保存先を使う。
- `js/`: Dashboard実関数をNode VMとstub DOMで実行するイベント系列・snapshot表示テスト。追加npm依存は不要。
- `integration/`: 結合テスト。
- `fixtures/`: 機密・実保有・実AI回答を含まない固定入力。

## 信頼性修正の検証

repositoryの開発依存を隔離Python環境へ導入して実行する。実API keyは不要。

```bash
python -m pip install -e .[dev]
python -m pytest -q tests/unit/test_review_target_provenance.py tests/unit/test_review_search_evidence.py tests/unit/test_review_cache_identity.py tests/unit/test_stock_ai_workbench.py
python -m pytest -q tests/unit/test_mock_ui.py tests/unit/test_analysis_ui.py tests/unit/test_watchlist_collections.py tests/unit/test_ai_review_history.py tests/unit/test_portfolio_ai_review.py tests/unit/test_stock_analysis_prompt_builder.py tests/unit/test_ai_usage.py
node tests/js/stock_ai_state.test.cjs
node tests/js/stock_ai_snapshot.test.cjs
python -m pytest -q
python scripts/sync_current_files.py --check
python -m compileall -q app src scripts
git diff --check
```

Nodeは22をCIで使う。状態テストは送信→条件変更→旧成功／旧失敗、mutation成功／失敗・再取得失敗、重複実行抑止と復帰を検査する。snapshotテストは送信時条件と系列別基準日時の表示を検査する。`test_stock_ai_workbench.py`はpane class・主要ID・main内配置とcanonical HTMLを検査する。これらは実ブラウザの画面検証とは別である。

cache回帰は時刻注入によるTTL境界・JST日付跨ぎ・未来／不正時刻、意味入力・元データ・prompt変更、一時DB固定入力でreview経路2回目provider 0回・usage増分0、metadata不足、保存失敗・raw fallbackを分けて検査する。

## 実ブラウザQA（合成API）

画面の完了確認には次を実行する。Playwrightは検証専用の任意依存でproduction依存には追加しない。

```bash
python -m pip install -e ".[dev,browser]"
python -m playwright install chromium
python scripts/check_stock_ai_browser.py
```

`browser` extraは`playwright>=1.58,<2.0`を追加する検証専用の任意依存である。CIも両extraを導入し、Linuxでは`python -m playwright install --with-deps chromium`を使って同じ画面QAを実行する。

全HTTPを合成responseへ差し替え、アプリserver・実DB・OpenAI providerを起動・呼出ししない。1440・960・390pxのempty/loading/success/failure/長文/prompt、Portfolio/named Watchlist、reader・履歴・keyboardを検査する。390pxのdocument幅も測る。検証結果と画像は既定でGit管理外の`test-results/stock-ai`へ出力する。オプションは`python scripts/check_stock_ai_browser.py --help`を参照する。

copy handlerはstub clipboardで検査し、利用者のOS clipboardを書き換えない。Markdownはdownload属性・hrefとrouteで差し替えたexport取得・内容を検査する。serverなしのChromiumではnative downloadがrouteを迂回するため、実OS clipboard転送とnativeファイルdownload完了はこのQAの確認範囲に含めない。readerのpopup・CSP・スクリーンショット・PDF描画は実Chromiumで検査する。

Windowsでは一時directoryの書込権限がpytest fixtureに必要である。隔離した`--basetemp`を指定できる。canonical immutable promptのhash検査はGitの改行変換でも失敗し得るため、assetのGit上のbytesと照合し、期待hashや旧asset内容を変更して通さない。
