# kabuhandan_hojo Screen Spec v1.5

## 1. scope

この版は、現在の UI 3 画面構成と J-Quants market proxy ベースの地合い表示を含む画面仕様を対象にします。

## 2. top screen

### market overview

- `GET /ui/dashboard/data` の `market_overview` を表示する
- live mode では `TOPIX(1306)` と `Nikkei225(1321)` の market proxy を使う
- proxy が取れない場合は `未取得` を表示し、疑似的な市場推定へ戻さない

### main sections

- priority items
- important alerts
- event feed
- watchlist overview
- 銘柄検索
- watchlist 未登録の高スコア候補

### interaction

- search 結果、watchlist、候補カードから detail を新しいタブで開く
- 元の top タブは残す

## 3. detail screen

### main sections

- header / status
- hypothesis card
- factor split
- reference links
- technical
- flow
- materials
- warnings / history

### chart preview

- `チャート分析詳細` ボタンの近くに直近チャートプレビューを置く
- `price_chart` がある場合のみローソク足と出来高を表示する

### market headwind

- `market_headwind` は market proxy ベースで表示する
- 銘柄の 5 日相対強弱と組み合わせてコメントを作る

## 4. chart detail screen

### main sections

- 20日 / 40日 / 全期間切替
- MA 5 / 25 / 75 overlay
- RSI / MACD 補助表示
- 個別銘柄ページへ戻るリンク
- JSON ボタン

### empty state

- `price_chart` が無ければ `チャートデータはまだありません。` を表示する
- 補助表示に十分な本数が無ければ、その旨を明示する

## 5. live mode の表示ルール

- mock 補完はしない
- `price_chart` が空なら J-Quants 日足同期を 1 回試す
- それでも不足している項目は `未取得` または空表示

## 6. source 表示ルール

- reference link は正式 source と手動参照を区別して見せる
- TDnet、株探、みんかぶ、日経、Reuters、Bloomberg、SBI証券、楽天証券、X、StockTwits は手動参照スタック
