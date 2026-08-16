# kabuhandan_hojo API Spec v1.1

## scope

v1.0 に加えて UI view model と検索 API を整理した版です。

## 追加・整理した契約

- `GET /ui/dashboard/data`
- `GET /securities/search`
- `GET /ui/dashboard`
- `GET /ui/security/{ticker_code}`
- `GET /ui/security/{ticker_code}/chart`

## notes

- UI 3 画面が同じ view model を使う前提を明文化
- watchlist 追加フローで検索 API を正式化
- detail payload に仮説、factor split、reference link を含める方向を定義
