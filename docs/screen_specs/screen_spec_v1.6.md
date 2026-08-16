# kabuhandan_hojo Screen Spec v1.6

## 1. scope

この版は、dashboard の Portfolio AI分析パネル、multi-mode stock AI review、Prompt Registry / Prompt Builder、自動テンプレ適用、ChatGPT投入用プロンプト生成、warnings/sources表示を含む画面仕様を対象にします。

## 2. top screen

### market overview

- `GET /ui/dashboard/data` の `market_overview` を表示する
- live mode では `TOPIX(1306)` と `Nikkei225(1321)` の market proxy を使う
- proxy が取れない場合は `未取得` を表示し、疑似的な市場推定へ戻さない

### main sections

- priority items
- important alerts
- event feed
- portfolio / AI分析パネル
- watchlist overview
- 銘柄検索
- watchlist 未登録の高スコア候補

## 3. Portfolio AI分析パネル

### controls

AI分析パネルは次の入力を持つ。

- AI分析モード
  - 軽量スキャン
  - 個別詳細分析
  - 全体売買判断
  - 重要局面分析
- AI分析対象
  - 保有銘柄
  - 狙い中銘柄
  - 監視銘柄
  - 選択銘柄
  - テスト用仮保有銘柄
- 選択銘柄コード入力
- Web検索最大回数
- 建玉意図
- ユーザー仮説
- Web検索ON/OFF
- APIなしのサンプル表示
- 結果保存
- 前回結果の再表示

対象が `テスト用仮保有銘柄` の場合、OpenAI APIは呼ばない。推定コストは0として表示し、Web検索チェックもOFFにする。

### action buttons

- `軽量スキャン`
- `個別詳細分析`
- `全体売買判断`
- `重要局面分析`
- `ChatGPT投入用プロンプトを生成`
- `プロンプトをコピー`

`ChatGPT投入用プロンプトを生成` は OpenAI API を呼ばず、手動コピペ用の全文プロンプトを生成する。通常のAI分析ボタンでは、プロンプト欄にユーザーが入力しなくても Prompt Builder が毎回テンプレートを自動適用する。

## 4. ワンクリック実行

保有銘柄全体の判断は、次の条件で実行できる。

1. 対象が `保有銘柄`
2. `全体売買判断` ボタンを押す
3. request は `mode=judge` / `target=holdings` として送信される
4. `user_hypothesis` が空の場合は `未入力` として扱う
5. Prompt Builder が Base Policy と judge mode の章を自動適用する

高コスト条件に該当する場合は実行前に確認ダイアログを表示する。

## 5. Web検索表示

- `analyst` / `judge` / `critical` ではWeb検索ONを標準とする
- `scanner` はWeb検索OFFでも実行できる
- Web検索OFFの場合は warnings に「最新Web確認なし」を表示する
- API側の `web_search_policy` をchipとして表示する
- `actual_usage.web_search_calls` があればWeb検索回数上限をchipとして表示する

## 6. 結果表示

summary card には次を表示する。

- mode label
- generated_at
- portfolio summary
- model
- reasoning effort
- web_search_policy
- estimated cost
- cache hit
- holdings source
- top risks
- action plan
- critical warnings
- warnings
- sources

stock card には次を表示する。

- ticker / name
- judgement / judgement_label
- confidence
- needs_detail_analysis
- needs_analyst_mode
- needs_judge_mode
- verification_labels
- time_horizon_views
- short_reason
- key_risks
- key_points / watch_points
- technical_view
- news_view
- market_context_view
- supply_demand_view
- holder_action
- buy_more_condition
- take_profit_condition
- stop_or_reduce_condition
- invalidation
- next_price_levels
- bullish_case / base_case / bearish_case
- expected_value_view
- position_size_risk
- event_risk
- gap_risk
- decision_deadline
- what_would_change_my_mind
- final_recommendation_for_holder
- uncertainty_notes
- execution_plan
- critical_check
- risks
- sources

## 7. エラー表示

- `missing_api_key` は `.env` または起動環境に `OPENAI_API_KEY` が必要であることを表示する
- `json_parse_failed` は OpenAI応答を指定JSONとして解析できなかったことを表示する
- `raw_model_output` がある場合は、UIに収まる範囲で表示する
- JSON parse救済に成功した場合は、warnings に「JSON整形リトライ」を表示し、結果カード表示を継続する
- JSON parse救済に失敗してもOpenAI生応答がある場合は、summary card 内に「OpenAI生応答」として表示する
- APIキー、内部スタックトレース、秘密情報は表示しない

## 8. prompt output

- `prompt_only` 成功時は textarea に `manual_prompt` を表示する
- `manual_prompt` がある場合だけ `プロンプトをコピー` ボタンを有効化する
- 自動投稿、ChatGPT Web画面操作、回答スクレイピングは行わない

## 9. detail screen

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

## 10. chart detail screen

### main sections

- 20日 / 40日 / 全期間切替
- MA 5 / 25 / 75 overlay
- RSI / MACD 補助表示
- 個別銘柄ページへ戻るリンク
- JSON ボタン

### empty state

- `price_chart` が無ければ `チャートデータはまだありません。` を表示する
- 補助表示に十分な本数が無ければ、その旨を明示する

## 11. live mode の表示ルール

- mock 補完はしない
- `price_chart` が空なら J-Quants 日足同期を 1 回試す
- それでも不足している項目は `未取得` または空表示

## 12. source 表示ルール

- reference link は正式 source と手動参照を区別して見せる
- TDnet、株探、みんかぶ、日経、Reuters、Bloomberg、SBI証券、楽天証券、X、StockTwits は手動参照スタック
