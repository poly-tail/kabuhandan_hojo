# kabuhandan_hojo Screen Spec v1.8

## 1. scope

この版は、v1.7 の画面契約を累積継承し、canonical個別銘柄AIの成功回答をローカルへ自動保存する表示、別ウィンドウ導線、大型の保存回答画面 `/ui/analysis/results/{request_id}` を追加した現行画面仕様を対象にします。

本アプリは日本株の判断補助を目的とし、自動売買や断定的な投資助言を行いません。

## 2. AI画面とAPI経路の区分

### dashboard legacy AI

- UI: `/ui/dashboard` の Portfolio AI分析パネル
- canonical API: `POST /api/ai/stock-review`
- 互換API: `POST /portfolio/ai-review`、`POST /api/portfolio/ai-review`
- multi-mode、対象選択、任意のWeb検索、mock表示、Structured Outputs / JSON parse、prompt-only、キャッシュ、履歴はこの既存経路の機能である
- 3章から8章までの規則は、この既存dashboard AI経路だけに適用する

### independent individual-security AI

- UI: `/ui/analysis`、`/ui/analysis/results/{request_id}`
- canonical API: `POST /api/ai/analyses`、`GET /api/ai/analyses/{request_id}`
- 登録済み銘柄1件、自由質問、固定`STANDARD` preset、OpenAI Responses API、プレーンテキスト回答だけを扱う
- mock、cache、fallback、Web検索、Structured Outputs、JSON修復、再AI呼び出し、background、streamingを使用しない
- 既存dashboard AIのstate、prompt、結果card、fallback規則を流用しない
- 9章から17章までの規則は、この独立経路だけに適用する

両経路は同じOpenAI API keyをサーバー側で利用し得ますが、画面とアプリケーション経路は独立しています。dashboard legacy AIの成功条件やfallbackを、independent individual-security AIへ適用してはいけません。

## 3. top screen

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

## 4. dashboard legacy Portfolio AI分析パネル

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

## 5. dashboard legacy AIのワンクリック実行

保有銘柄全体の判断は、次の条件で実行できる。

1. 対象が `保有銘柄`
2. `全体売買判断` ボタンを押す
3. request は `mode=judge` / `target=holdings` として送信される
4. `user_hypothesis` が空の場合は `未入力` として扱う
5. Prompt Builder が Base Policy と judge mode の章を自動適用する

高コスト条件に該当する場合は実行前に確認ダイアログを表示する。

## 6. dashboard legacy AIのWeb検索表示

- `analyst` / `judge` / `critical` ではWeb検索ONを標準とする
- `scanner` はWeb検索OFFでも実行できる
- Web検索OFFの場合は warnings に「最新Web確認なし」を表示する
- API側の `web_search_policy` をchipとして表示する
- `actual_usage.web_search_calls` があればWeb検索回数上限をchipとして表示する

## 7. dashboard legacy AIの結果・エラー表示

### summary card

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

### stock card

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

### legacy error handling

- `missing_api_key` は `.env` または起動環境に `OPENAI_API_KEY` が必要であることを表示する
- `json_parse_failed` は OpenAI応答を指定JSONとして解析できなかったことを表示する
- `raw_model_output` がある場合は、UIに収まる範囲で表示する
- JSON parse救済に成功した場合は、warnings に「JSON整形リトライ」を表示し、結果card表示を継続する
- JSON parse救済に失敗してもOpenAI生応答がある場合は、summary card 内に「OpenAI生応答」として表示する
- API key、内部stack trace、秘密情報は表示しない

このlegacy error handlingはindependent individual-security AIには適用しない。

## 8. dashboard legacy AIのprompt output

- `prompt_only` 成功時は textarea に `manual_prompt` を表示する
- `manual_prompt` がある場合だけ `プロンプトをコピー` ボタンを有効化する
- 自動投稿、ChatGPT Web画面操作、回答スクレイピングは行わない

## 9. independent individual-security AI screen

### path and entry

- pathは `GET /ui/analysis`
- 画面titleは `AI個別銘柄分析`
- 成功回答の大型表示pathは `GET /ui/analysis/results/{request_id}`
- 大型表示の画面titleは `保存済みAI個別銘柄分析`
- 現時点では独立URLとして提供し、dashboardからの導線が実装済みであるとは扱わない
- dashboardのview model `GET /ui/dashboard/data` は使用しない

### page sections

1. 銘柄選択
2. 質問
3. 回答

### security selection controls

- `銘柄コードまたは銘柄名` の検索input
  - input type: `search`
  - 最大100文字
  - autocompleteはOFF
  - placeholderは `例: 7203 または トヨタ`
- `検索` button
- 検索inputでEnterを押した場合も検索を実行する
- 検索APIは `GET /securities/search?q={query}&limit=10`
- 検索結果はbuttonの一覧で表示し、1件を選択できる
- 結果表示は `銘柄コード 銘柄名 / 市場`
- 市場が未登録の場合は `市場未登録`
- 選択後は選択銘柄を専用領域に表示し、検索結果一覧を閉じる
- 同時に選択できる銘柄は1件だけ

### question and preset controls

- `自由質問` textarea
  - 最大4000文字
  - 縦方向のresizeを許可する
  - placeholderは `この銘柄について確認したいことを入力してください。`
- 回答設定はread-only chipの `STANDARD`
- action buttonは `STANDARDで送信`
- model、reasoning effort、text verbosityを利用者が変更するcontrolは置かない
- Web検索、mock、prompt-only、prompt編集、保存の手動toggle、履歴一覧、複数銘柄選択のcontrolは置かない

## 10. independent individual-security AI state contract

### initial state

- 選択銘柄は未設定
- 回答、status、error、diagnosticsは空または非表示
- 送信buttonはdisabled
- 送信buttonは、銘柄を1件選択し、かつtrim後の質問が非空の場合だけenabledになる

### search loading

- 空の検索queryはAPIへ送らず、`銘柄コードまたは銘柄名を入力してください。` をerror領域へ表示する
- 検索開始時は検索buttonをdisabledにする
- statusに `銘柄を検索中…` を表示する
- 検索完了後は検索buttonを再びenabledにし、statusを空にする
- 検索中であってもAI分析のloading stateとしては扱わない

### search result and search error

- 0件の場合は `該当する登録銘柄がありません。` を検索結果領域へ表示する
- HTTP失敗、非JSON、network失敗は `銘柄検索に失敗しました。` をerror領域へ表示する
- 検索結果のlabelはDOMの`textContent`で生成し、検索値や銘柄名をHTMLとして挿入しない
- 銘柄選択時は既存errorをclearし、送信buttonの有効条件を再評価する

### analysis loading

- 未選択状態では送信処理を開始しない
- trim後の質問が空の場合は `質問を入力してください。` をerror領域へ表示する
- 送信開始時に多重送信を禁止し、送信buttonをdisabledにする
- 送信中は銘柄検索input・検索button・検索結果button・質問textareaをdisabledにし、送信対象銘柄と質問を固定する
- 直前の回答、error、diagnosticsをclearする
- 直前の保存済み表示と別ウィンドウlinkを非表示にする
- statusに `OpenAIへ送信中…` を表示する
- request完了後は、選択銘柄と質問の状態に応じて送信buttonを再評価する
- request完了後は銘柄検索・選択・質問編集を再び有効化する
- streaming表示、進捗率、cancel操作は提供しない

### success

- HTTP successだけでは成功扱いにしない
- response bodyがJSONで、`status=success`、かつtrim後の`answer_text`が非空の場合だけ成功とする
- `answer_text`を回答領域へ表示する
- 非空`request_id`を確認し、`この回答はローカルに保存済みです`を表示する
- `/ui/analysis/results/{request_id}`への`別ウィンドウで大きく表示` linkを表示する
- diagnosticsを表示可能にする
- statusに `回答を表示しました` を表示する
- 直前のerrorは非表示のままにする

### failure

- HTTP error、response JSON parse失敗、`status!=success`、空回答、network failureは回答として表示しない
- API error responseがある場合は `{error.code}: {error.message}` を表示する
- response envelopeを取得できない場合は `REQUEST_FAILED: AI分析に失敗しました。` を表示する
- 非空の成功responseに見えても`answer_text`が空なら `EMPTY_RESPONSE: 回答本文が空でした。` を表示する
- fetch自体が失敗した場合は `NETWORK_ERROR: APIとの通信に失敗しました。` を表示する
- failure時のstatusは `失敗しました`
- `PERSISTENCE_ERROR`ではOpenAI回答本文を表示せず、保存済み表示と大型表示linkも表示しない
- OpenAI raw response、部分回答、parseできない本文をsuccessへfallbackしない

## 11. independent individual-security AI API and answer contract

### request

`POST /api/ai/analyses`へ次だけを送る。

```json
{
  "security_code": "7203",
  "question": "自由質問",
  "preset": "STANDARD"
}
```

### response fields used by the screen

- `request_id`
- `status`
- `answer_text`
- `error.code`
- `error.message`
- `openai_response_id`
- `saved_at`

### plain-text answer

- 回答は `response.output_text` 由来の `answer_text`
- 回答領域は `<pre>` とする
- DOMへの反映は `textContent`
- CSSは `white-space: pre-wrap` と `overflow-wrap: anywhere`
- Markdown renderer、HTML sanitizer前提のHTML描画、JSON parser、構造化cardを導入しない
- 回答にMarkdown記号が含まれていても、文字列としてそのまま表示する

### saved response action

- 成功回答はserver側で自動保存され、手動保存buttonや保存ON/OFF controlは置かない
- `別ウィンドウで大きく表示`は成功時だけ表示する
- link先はresponseの`request_id`をURL encodeした`/ui/analysis/results/{request_id}`
- linkは`target="_blank"`、`rel="noopener noreferrer"`とする
- loading、error、空回答、request ID欠落時はlinkを非表示にする

### large-window saved answer screen

- pathは`GET /ui/analysis/results/{request_id}`
- 初期statusは`保存済み回答を読み込み中…`
- 同じoriginの`GET /api/ai/analyses/{request_id}`を`cache: "no-store"`で呼ぶ
- 成功時は`銘柄名（銘柄コード）`、市場、preset、model、保存日時、質問、回答を表示する
- 質問と回答は`<pre>`の`textContent`で設定し、回答は`white-space: pre-wrap`と`overflow-wrap: anywhere`を使う
- 回答本文を読みやすくするため、main領域と回答領域は元画面より広く、縦方向の最小表示領域を持つ
- 不正・欠落responseは`INVALID_SAVED_RESPONSE`、API errorはsafeなcode/message、network failureは`NETWORK_ERROR`として表示し、本文領域を表示しない
- `分析画面へ戻る`linkを持つ
- Markdown renderer、構造化card、編集、削除、export、一覧表示は行わない

## 12. independent individual-security AI diagnostics

- diagnosticsは初期状態では非表示
- success時は次だけを表示する
  - `request_id`
  - `openai_response_id`。欠ける場合は `未取得`
- error responseに`request_id`がある場合は、そのIDだけをdiagnosticsに表示できる
- error responseにIDがない場合はdiagnosticsを表示しない
- prompt全文、自由質問全文、security context全文、prompt asset本文、prompt version、asset ID、compiled hash、model raw response、内部stack traceをdiagnosticsへ表示しない
- diagnosticsは開閉可能な`details`要素とする

## 13. independent individual-security AI error codes

画面はAPIから返る次の分類をsafeなerror codeとして表示できる。

- `AUTHENTICATION_ERROR`
- `MODEL_UNAVAILABLE`
- `INVALID_API_PARAMETERS`
- `RATE_LIMITED`
- `TIMEOUT`
- `NETWORK_ERROR`
- `EMPTY_RESPONSE`
- `UNKNOWN_OPENAI_ERROR`
- `SECURITY_NOT_FOUND`
- `DATABASE_UNAVAILABLE`
- `PERSISTENCE_ERROR`
- `ANALYSIS_NOT_FOUND`（大型表示画面の保存record未検出）

FastAPI request validationなど上記response envelopeを返さない失敗は、画面側で`REQUEST_FAILED`として扱う。

## 14. independent individual-security AI prompt application

- prompt合成はserver側の`IndividualSecurityPromptCompiler`が担当し、UI内で長いpromptを生成しない
- OpenAI `instructions`は次の順序とする
  1. 株判断共通OS
  2. 共通入力ルール
  3. Web検索・外部市場データなしの実行制約
  4. `3.1 総合的な個別銘柄分析`
- OpenAI `input`は次の順序とする
  1. 選択した`security_master`由来の銘柄context
  2. ユーザーの自由質問
- `3.2`から`3.14`までの用途moduleを送信しない
- 利用できない現在価格、決算、テクニカル、需給、信用、市場、マクロ、イベント情報を推測で補完させず、`【U】`、`insufficient_data`、`no_trade`を利用できるようにする
- prompt version、使用asset、module、source hash、compiled hashはOpenAI response metadataへ記録する
- prompt metadataとprompt本文はpublic FastAPI responseやbrowserへ返さない
- prompt sourceはv2026.08.17とし、銘柄の表示・言及は原則`銘柄名（銘柄コード）`とする

## 15. independent individual-security AI security and privacy

- `OPENAI_API_KEY`はサーバー側だけで読み込み、HTML、JavaScript、request body、API response、diagnosticsへ含めない
- API key、Authorization header、secret、prompt全文を通常logへ出力しない
- 自由質問はOpenAI requestのinputとして送られるが、API responseやdiagnosticsへechoしない
- 成功した質問と回答は大型表示のためローカルSQLへ保存され、保存済み1件取得responseでは質問を返す。APIキー、prompt全文、provider raw responseは保存・表示しない
- 銘柄検索結果、error message、回答本文は`innerHTML`を使わず、`textContent`で反映する
- OpenAI API失敗をmock回答やcache回答へ置き換えない
- modelを暗黙fallbackしない
- 回答画面には「回答は判断補助であり、投資助言ではありません。」と明記する

## 16. independent individual-security AI non-goals

この版では次を実装済みとして扱わない。

- dashboardから`/ui/analysis`への導線
- `LIGHT` / `HIGH` / `PRO` / `MAX` preset
- model選択UI
- `reasoning.mode`選択UI
- 複数銘柄、市場全体、総合分析
- Web検索またはJ-Quants等の追加市場context取得
- Structured Outputs、JSON Schema、JSON修復、parse失敗時の再AI呼び出し
- Markdown rendering、複雑な結果card
- streaming、background response、polling、cancel
- prompt編集、prompt全文表示、prompt asset選択
- prompt cache、回答cache、mock fallback
- 保存回答の一覧・検索・削除・export・共有、回答copy、回答download
- 保存recordの保持期限設定、自動purge、認証・認可
- 旧dashboard AI経路の統合、削除、廃止

## 17. known limitations

- `/ui/analysis`は独立URLであり、現時点でdashboard内の正式導線を持たない
- 登録済み`security_master`の銘柄だけを選択できる
- 一度に分析できる銘柄は1件だけ
- presetは`STANDARD`固定で、modelは`gpt-5.6-terra`固定
- `reasoning.effort=medium`、`text.verbosity=medium`を固定し、画面から変更できない
- AI分析request内でWeb検索やJ-Quants同期を行わない
- serverが渡す銘柄contextはコード、名称、市場、業種、上場日を中心とし、現在価格、取得時刻、最新決算、テクニカル、需給、信用、市場・マクロ情報は通常未提供である
- 未提供情報が結論に必要な場合、回答は情報不足、`insufficient_data`、`no_trade`へ着地し得る
- プレーンテキスト表示のため、Markdown記号は装飾されない
- 回答のstreaming、cancel、履歴一覧はない。保存済み回答はrequest IDを知っている場合だけ1件再表示できる
- 保存recordの削除、export、保持期限、自動purge、access controlはない
- browserではprompt versionやasset IDを確認できない。追跡情報はserverからOpenAI response metadataへ記録する
- error時にOpenAIのraw error本文やraw model outputは表示しない

## 18. detail screen

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

- `チャート分析詳細` ボタンの近くに直近chart previewを置く
- `price_chart` がある場合のみローソク足と出来高を表示する

## 19. chart detail screen

### main sections

- 20日 / 40日 / 全期間切替
- MA 5 / 25 / 75 overlay
- RSI / MACD 補助表示
- 個別銘柄ページへ戻るlink
- JSON button

### empty state

- `price_chart` が無ければ `チャートデータはまだありません。` を表示する
- 補助表示に十分な本数が無ければ、その旨を明示する

## 20. live mode の表示ルール

- dashboard / detail / chartではmock補完をしない
- `price_chart` が空ならJ-Quants日足同期を1回試す
- それでも不足している項目は`未取得`または空表示
- independent individual-security AIでは、live / mock起動モードにかかわらずAI回答のmock fallbackを行わない

## 21. source 表示ルール

- reference linkは正式sourceと手動参照を区別して見せる
- TDnet、株探、みんかぶ、日経、Reuters、Bloomberg、SBI証券、楽天証券、X、StockTwitsは手動参照stack
- independent individual-security AIはsource一覧を表示せず、外部sourceを自動取得したと表現しない

## 22. document change history

| version | date | changes |
|---|---|---|
| v1.8 | 2026-08-17 | v1.7を累積継承し、canonical成功回答のローカル保存表示、別ウィンドウ大型表示link、保存回答reader、loading/error/plain-text描画、v2026.08.17の銘柄名・コード併記規則を追加。履歴一覧・削除・exportは非対象。 |
| v1.7 | 2026-08-17 | v1.6を累積継承し、dashboard legacy AIと独立`/ui/analysis`を分離。個別銘柄AIのcontrols、state、loading、error、plain-text answer、diagnostics、security、PromptCompiler境界、non-goals、known limitationsを追加。 |
| v1.6 | 2026-06-15 | dashboard Portfolio AI分析パネル、multi-mode stock AI review、Prompt Registry / Builder、prompt-only、warnings / sources表示を追加。 |
