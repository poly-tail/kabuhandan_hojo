# Screen Map

## 画面一覧

| 画面 | path | 主な役割 |
|---|---|---|
| analysis | `/ui/analysis` | 登録済み個別銘柄1件への自由質問とプレーンテキストAI回答 |
| top | `/ui/dashboard` | 地合い、priority、watchlist、候補一覧 |
| detail | `/ui/security/{ticker_code}` | 個別銘柄の仮説、材料、需給、テクニカル |
| chart | `/ui/security/{ticker_code}/chart` | チャート分析詳細 |

## 主な導線

1. analysis は独立URLで開き、銘柄検索から登録済み銘柄を1件選ぶ
2. top で watchlist / search / 候補から銘柄を開く
3. detail で `チャート分析詳細` を開く
4. chart で `個別銘柄ページに戻る` を開く

## 補足

- top から detail への遷移は新しいタブ
- top、detail、chart は同じ view model を共有
- analysis は `/ui/dashboard/data` を共有せず、`/securities/search` と `POST /api/ai/analyses` を使用する
- dashboard から analysis への専用導線は現時点の必須契約ではない
