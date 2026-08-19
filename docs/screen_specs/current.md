# Screen Spec Current

> 現在の正本: `screen_spec_v2.6.md`

## 概要

- このファイルは画面仕様書の最新 pointer です。
- 実際の画面契約は versioned file 側に保持します。

## 現在値

- 画面仕様書: v2.6
- 更新日: 2026-08-19
- 変更概要: legacy Portfolio / Watchlistの現在回答を、安全なclient-only Blob snapshotとして別タブ・別ウィンドウへ大きく表示

## 主な変更点

- UI 5画面構成と独立URL `GET /ui/analysis`
- dashboardで銘柄名・数字/英字codeを検索し、結果からPortfolio入力またはdetailへ進む導線
- 英字5文字末尾`0`は表示・保有入力だけ公開4文字とし、detail actionはraw identifierを維持
- `東証全銘柄を同期`のrequired J-Quants実行と、同期中のbutton lock・safe error・再検索
- complete/未確認status、J-Quants/ローカル有効件数、遅延し得る情報基準日と同期時刻の分離表示
- complete成功表示は本番4,000件/最大5%縮小guard通過時だけとし、支配的legacy cohortと参照identity splitはfail closed表示
- 検索はDB-only、同期errorはprovider body非露出とし、legacy採用を画面から暗黙実行しないこと
- 取得、新規、更新、再有効化、無効化countのsuccess feedbackと、seed fallbackを全件成功表示しない境界
- BYOK/private local/full dataset非同梱・非再配布、地方取引所単独銘柄を保証しない表示範囲
- dashboard legacy AI usage panelと利用者向けholdings-source label
- legacy成功responseはMarkdown本文として解釈せず、既知JSON fieldを全体所見、risk、行動、候補、warning、stock detail、sourceへ意味別表示すること
- 空section省略、同じlist内の重複除去、Portfolio / Watchlist共通helper、escaped textと文字label付き`【V】` / `【E】` / `【U】` badge
- legacy Portfolio / Watchlistの`status=success`（`prompt_only`除外）または非空生応答を持つ`json_parse_failed`に、`回答を別タブ／ウィンドウで大きく表示`action linkを出すこと
- 大画面表示は現在dataのclient-only Blob snapshotとし、共通safe renderer、restrictive CSP、`target="_blank"` / `rel="noopener noreferrer"`、source URL allowlistを維持すること
- action linkの準備・openでAPI、DB、Web Storage、history/cache、OpenAI再呼び出し、quota / usageを増やさず、Blob readerのreload・bookmark・恒久URL復元を保証しないこと
- unsafe source URLをlinkにせず、raw fallbackを赤いerror card内のplain escaped表示に保ち、mobile / keyboard / screen readerで読めること
- `json_parse_failed`を成功表示しない赤いerror cardと、`json_syntax` / `root_shape` / `schema_validation`の利用者向けlabel
- raw output救済を成功回数とcacheへ含めず、調査用historyと生応答表示を維持する境界
- scannerは軽量生成schemaを使い、runtimeの空値・既定値を確認済みの詳細分析として強調しないこと
- legacy Portfolio / Watchlist stock cardは銘柄名と公開codeを併記し、`285A0`を`285A`として表示できること
- legacy summaryの6つの銘柄参照listを「銘柄名（公開コード）」で表示し、unknown codeを`名称未登録（code）`とすること
- local masterへ一致したtargetはcanonical tickerへ揃い、live/mock/cache hitで同じ表示を使うこと
- 添付v2026.08.16は参照資料として扱い、canonical個別銘柄AI v2026.08.18を変更しないこと
- chart detail 強化
- live mode の no-mock 表示
- market proxy ベースの地合い表示
- 登録済み個別銘柄1件、自由質問、固定 `STANDARD`
- 銘柄検索、loading、送信中の入力ロック、safe error、plain-text answer、request診断表示
- `persistence_status=saved`時だけ表示する保存済み状態と `別ウィンドウで大きく表示` link
- 保存失敗時は回答本文とwarningだけを表示し、reader linkと`saved_at`を表示しない
- `/ui/analysis/results/{request_id}` の最大幅1380px・plain-text readerとloading / error
- `target="_blank"` / `rel="noopener noreferrer"`、URLはUUIDだけ、responseは`no-store`
- 新画面ではmock / Web検索 / Structured Outputs / raw response fallbackを使わない
- prompt asset / version / APIキーをbrowserへ出さない
- dashboard legacy Portfolio AI画面との責務分離
- 保有銘柄全体のワンクリックAI分析
- 狙い中銘柄、ユーザー仮説、建玉意図、Web検索、mock_response、prompt_only操作
- warnings、sources、具体的な執行案、反証条件、辛口チェック表示

## 更新ルール

1. 過去版を保持し、新しい版付きspecを追加する
2. `current.md` を追従させる
3. `docs/spec_change_history.md` と `docs/changelog.md` を更新する
