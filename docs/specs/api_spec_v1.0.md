# kabuhandan_hojo API Spec v1.0

## scope

初期の monitoring API と watchlist API を対象とする版です。

## endpoints

- `GET /health`
- `GET /watchlist`
- `POST /watchlist`
- `POST /sources/bootstrap`
- `POST /securities`
- `POST /securities/{ticker_code}/prices`
- `POST /securities/{ticker_code}/financials`
- `POST /securities/{ticker_code}/flow`
- `POST /documents/import`
- `POST /documents/sync/edinet`
- `GET /securities/{ticker_code}`
- `GET /dashboard`
- `GET /screening`

## notes

- mock mode と live mode の切替を持つ
- watchlist を起点に監視データを扱う
- detail は JSON API 中心
