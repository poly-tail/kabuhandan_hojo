# 情報源

## このリポジトリの前提

`kabuhandan_hojo` では、情報源を次の 2 層に分けて扱います。

- 自動取得する基幹ソース
- UI 上で案内する手動参照スタック

この区別を崩さないことが重要です。手動参照先は有用でも、ただちに connector や ingest source へ格上げするわけではありません。

## 自動取得する基幹ソース

| source | 種別 | 用途 | repo 内での扱い |
|---|---|---|---|
| J-Quants | 公式 API | 日足、銘柄マスタ、市場 proxy | 価格同期と地合い推定の基幹ソース |
| EDINET API | 公式 API | 開示書類、提出情報 | 一次情報の canonical source |
| YouTube Data API | 公式 API | 動画メタデータ | 補助的な観測ソース |
| allowlist IR サイト | 公式 IR | IR ページ参照 | 許可済みドメインのみ手動・補助参照 |
| 手入力 API | アプリ内部 API | prototype データ投入 | 検証・補完用の正式経路 |

## 市場地合いの扱い

2026-04-21 時点の live mode では、`market_overview`、`market_headwind`、`factor_split.market` を J-Quants で取得する次の proxy で組み立てます。

- `TOPIX(1306)`
- `Nikkei225(1321)`

現行 connector は stock OHLC endpoint を利用しているため、指数 endpoint 直結ではなく proxy 銘柄ベースで扱います。proxy が取得できない場合は `未取得` とし、watchlist の雰囲気推定には戻しません。

## live mode のデータ補完方針

- live mode では mock 補完を行いません。
- `detail.price_chart` が空で `JQUANTS_API_KEY` がある場合のみ、J-Quants から日足同期を 1 回試します。
- それでも足りない項目は `未取得` または空表示にします。
- Yahoo! Finance や証券会社サイトを基幹取得ソースとして追加しません。

## 手動参照スタック

次の情報源は、実務上の確認先として有用ですが、この repo では connector を持たない前提です。

| 層 | 内容 | 主なサービス | 扱い |
|---|---|---|---|
| 一次情報 | 決算・適時開示 | TDnet | 手動参照 |
| 二次加工 | 指標・ランキング | 株探 / みんかぶ | 手動参照 |
| ニュース | マクロ・材料 | 日経 / Reuters / Bloomberg | 手動参照 |
| 証券会社系 | 口座情報・板感覚 | SBI証券 / 楽天証券 | 手動参照 |
| センチメント | 投資家の温度感 | X / StockTwits | 手動参照 |

結論として、実務上の参照セットは次の組み合わせが最も使いやすいです。

**株探 + TDnet + ニュース（Reuters / Bloomberg） + 証券口座**

## TDnet と EDINET の役割分担

- EDINET:
  - アプリが canonical に扱う開示の正式ソース
  - connector と sync route の対象
- TDnet:
  - 速報確認や適時開示の導線として有用
  - 現時点では手動参照先であり、自動 connector は未実装

設計メモは [docs/analysis/tdnet_edinet_roles_v0.1.md](analysis/tdnet_edinet_roles_v0.1.md) を参照してください。

## UI での見せ方

- `/ui/security/{ticker_code}` の reference link では、Yahoo! Finance Japan、公式 IR、最新の source URL を優先表示します。
- source label の解決では、TDnet、株探、みんかぶ、日経、Reuters、Bloomberg、SBI証券、楽天証券、X、StockTwits を表示名として扱います。
- ただし、これらは自動 ingest source ではありません。

## 禁止事項

- 証券会社サイトの自動ログイン連携
- 規約違反または robots 無視のスクレイピング
- 一次ソース不明のデータを canonical fact として保存すること
