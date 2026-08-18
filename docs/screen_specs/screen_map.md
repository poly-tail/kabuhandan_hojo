# Screen Map

## 画面一覧

| 画面 | path | 主な役割 |
|---|---|---|
| analysis | `/ui/analysis` | 登録済み個別銘柄1件への自由質問とプレーンテキストAI回答 |
| saved analysis reader | `/ui/analysis/results/{request_id}` | 保存済み質問・回答の幅広いプレーンテキスト再表示 |
| top | `/ui/dashboard` | 地合い、priority、watchlist、候補一覧、銘柄検索からPortfolio入力 |
| detail | `/ui/security/{ticker_code}` | 個別銘柄の仮説、材料、需給、テクニカル |
| chart | `/ui/security/{ticker_code}/chart` | チャート分析詳細 |

## 主な導線

1. analysis は独立URLで開き、銘柄検索から登録済み銘柄を1件選ぶ
2. analysis成功後の `別ウィンドウで大きく表示` から saved analysis reader を新しいタブで開く
3. top の検索結果で `保有入力へ` を押し、公開コードをPortfolioフォームへ反映して数量を入力する。明示的に`保有を保存`するまではrecordを作らない
4. top で watchlist / search / 候補から銘柄detailを開く
5. detail で `チャート分析詳細` を開く
6. chart で `個別銘柄ページに戻る` を開く

## 補足

- top から detail への遷移は新しいタブ
- 英字5文字末尾`0`のmaster identifierは、検索結果表示とPortfolio入力だけ公開4文字へ変換し、detail actionはraw identifierを維持
- top、detail、chart は同じ view model を共有
- analysis は `/ui/dashboard/data` を共有せず、`/securities/search` と `POST /api/ai/analyses` を使用する
- saved analysis readerは `GET /api/ai/analyses/{request_id}` だけを読み、URLへ質問・回答・prompt・APIキーを入れない
- dashboard から analysis への専用導線は現時点の必須契約ではない
